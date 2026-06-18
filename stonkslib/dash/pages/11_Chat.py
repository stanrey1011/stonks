import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from stonkslib.dash.common import load_watchlist, flat_tickers, load_alert_cache
from stonkslib.llm import client

SYSTEM_PROMPT = """\
You are Stonks Assistant — a sharp, data-driven trading analyst with full access to the user's \
real watchlist and latest signal data. You help interpret technical signals, explain indicator \
readings, think through trade setups, and discuss LEAP options strategy.

Guidelines:
- Reference specific tickers, signal counts, and reasons from the snapshot when relevant
- For LEAP discussions, factor in IV environment and time decay
- Be concise and actionable — skip generic disclaimers mid-response
- End with one clear next action when the question warrants it

You are not a licensed financial advisor. Major decisions should involve a professional."""

QUICK_PROMPTS = [
    "Summarize today's signals",
    "Which tickers have the most SELL pressure?",
    "Any BUY setups worth watching?",
    "Explain RSI divergence signals",
    "Which tickers look good for LEAPs?",
]

# ── LLM helpers ──────────────────────────────────────────────────────────────

def get_available_models() -> list[str]:
    return client.list_models()


def build_context() -> str:
    lines = [
        "## Stonks Snapshot",
        f"Date: {datetime.now(timezone.utc).strftime('%A, %B %d, %Y %H:%M UTC')}",
        "",
    ]

    # Watchlist
    try:
        wl = load_watchlist()
        for cat, tickers in wl.items():
            if tickers:
                lines.append(f"**Watchlist — {cat.title()}:** {', '.join(tickers)}")
        lines.append("")
    except Exception as e:
        lines.append(f"[Watchlist unavailable: {e}]\n")

    # Latest alert scan
    cache = load_alert_cache()
    if cache:
        ts       = cache.get("ts", "unknown")
        interval = cache.get("interval", "?")
        results  = cache.get("results", {})
        lines.append(f"## Latest Alert Scan  ({interval}, as of {ts})")

        buy_tickers, sell_tickers, quiet_tickers = [], [], []
        signal_details = []

        for ticker, data in results.items():
            signals = data.get("signals", [])
            close   = data.get("close")
            if not signals:
                quiet_tickers.append(ticker)
                continue
            buys  = [s for s in signals if s.get("type") == "BUY"]
            sells = [s for s in signals if s.get("type") == "SELL"]
            price = f" @ ${close:.2f}" if close else ""
            if buys:
                buy_tickers.append(ticker)
            if sells:
                sell_tickers.append(ticker)
            detail = f"**{ticker}**{price}: {len(buys)} BUY, {len(sells)} SELL"
            reasons = list({s.get("reason", "") for s in signals if s.get("reason")})[:4]
            if reasons:
                detail += " — " + "; ".join(reasons)
            signal_details.append(detail)

        if signal_details:
            lines.append("\n### Tickers with signals")
            lines.extend(f"- {d}" for d in signal_details)
        if quiet_tickers:
            lines.append(f"\n### No signals: {', '.join(quiet_tickers)}")
    else:
        lines.append("## Latest Alert Scan\nNo scan data available — run the Alerts scan first.")

    return "\n".join(lines)


def ask_stream(messages: list[dict], model: str):
    try:
        yield from client.chat_stream(messages, model=model)
    except Exception as e:
        yield f"\n\n[Error: {e}]"


# ── Page ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Chat — Stonks", layout="wide")
st.title("Stonks Assistant")
st.caption("Ask anything about your watchlist, signals, or trade setups. Powered by your local LLM.")

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Model")
    models = get_available_models()
    if models:
        _default = client.default_model()
        selected_model = st.selectbox(
            "Model",
            models,
            index=models.index(_default) if _default in models else 0,
            key="chat_model",
            label_visibility="collapsed",
        )
    else:
        st.warning(f"LLM server not reachable at {client.base_url()}.")
        selected_model = client.default_model()

    st.divider()

    if st.button("Clear conversation", key="chat_clear", use_container_width=True):
        st.session_state.chat_messages = []
        st.rerun()

    with st.expander("Context snapshot"):
        st.text(build_context())

# ── Session state ──────────────────────────────────────────────────────────────

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# ── Quick prompts ──────────────────────────────────────────────────────────────

if not st.session_state.chat_messages:
    st.markdown("**Quick prompts:**")
    cols = st.columns(len(QUICK_PROMPTS))
    for col, prompt in zip(cols, QUICK_PROMPTS):
        with col:
            if st.button(prompt, key=f"chat_quick_{prompt}", use_container_width=True):
                st.session_state.chat_pending = prompt
                st.rerun()

# ── Render history ─────────────────────────────────────────────────────────────

for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Input ──────────────────────────────────────────────────────────────────────

pending = st.session_state.pop("chat_pending", None)
user_input = st.chat_input("Ask about your watchlist, signals, or trade setups…") or pending

if user_input:
    if not models:
        st.error(f"LLM server not reachable at {client.base_url()}. Check it's running and refresh.")
        st.stop()

    # Show user message
    st.session_state.chat_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build LLM message list: system + full history
    context = build_context()
    llm_messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context}]
    llm_messages += [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.chat_messages
    ]

    # Stream response
    with st.chat_message("assistant"):
        response = st.write_stream(ask_stream(llm_messages, selected_model))

    st.session_state.chat_messages.append({"role": "assistant", "content": response})
