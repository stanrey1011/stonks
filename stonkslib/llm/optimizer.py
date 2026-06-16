import json
import logging
import copy
import yaml
from pathlib import Path

from stonkslib.backtest.strategy import run_strategy_backtest, load_strategy
from stonkslib.backtest.leaps import run_leaps_backtest
from stonkslib.strategies.engine import is_v2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPTIMIZED_DIR = PROJECT_ROOT / "stonkslib" / "strategies" / "optimized"
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = """You are a quantitative trading strategy optimizer.
Your job is to suggest improved indicator parameters based on backtest results.
Always return valid JSON only — no explanation outside the JSON object."""


def _enabled_indicators(strategy):
    """Indicators eligible for tuning. Legacy: `enabled: true`. v2: present (and not
    explicitly disabled), since in v2 presence is what enables an indicator."""
    v2 = is_v2(strategy)
    out = {}
    for k, cfg in (strategy.get("indicators") or {}).items():
        cfg = cfg or {}
        if cfg.get("enabled") is False:
            continue
        if cfg.get("enabled") or v2:
            out[k] = cfg
    return out


_CONFLUENCE_INSTRUCTIONS = (
    "You may also tune the confluence gate: confluence.weights maps each indicator to a "
    "vote weight (0.0-3.0), and confluence.min_score is the weighted agreement required "
    "before a trade is taken. Raise weights on indicators that align with profitable trades "
    "and raise min_score to demand stronger multi-indicator agreement (fewer, higher-quality "
    "entries). Leave min_score at 0 to disable the gate."
)


def _confluence_json_field():
    return ('  "confluence": {"min_score": <float>, '
            '"weights": {"<indicator>": <weight 0.0-3.0>}}')


def _build_prompt(strategy, metrics_list):
    enabled = _enabled_indicators(strategy)
    tickers_summary = "\n".join(
        f"  {m['ticker']}: P&L=${m['net_pnl']:.2f}, Trades={m['trades']}, Win rate={m['win_rate']:.1%}"
        for m in metrics_list
    )
    avg_pnl = sum(m["net_pnl"] for m in metrics_list) / len(metrics_list)
    avg_win = sum(m["win_rate"] for m in metrics_list) / len(metrics_list)
    return f"""Current strategy: {strategy.get("name")}
Description: {strategy.get("description", "")}

Enabled indicators and current params:
{json.dumps(enabled, indent=2)}

Risk settings:
{json.dumps(strategy.get("risk", {}), indent=2)}

Current confluence gate (weights + min_score):
{json.dumps(strategy.get("confluence", {}), indent=2)}

Backtest results across {len(metrics_list)} ticker(s) ({metrics_list[0]["interval"]}):
{tickers_summary}
Average P&L: ${avg_pnl:.2f} | Average win rate: {avg_win:.1%}

Suggest new parameter values to improve average P&L and win rate across all tickers.
{_CONFLUENCE_INSTRUCTIONS}
Prioritize signal quality over quantity — fewer high-conviction entries beat many weak ones.
Raise thresholds (RSI levels, MACD sensitivity, BB periods) to reduce false signals and whipsaws.
A strategy that fires 3-5 times per month with 65%+ win rate is better than one firing daily at 45%.
IMPORTANT — Markov chain constraints: bull_threshold and bear_threshold are probabilities drawn from a
transition matrix. With typical lookback (60-120 bars) and 3 states, the maximum observable probability
is ~0.55-0.65. Never set these thresholds above 0.62. To reduce signals, prefer increasing lookback
(60→90→120) or states (3→4→5) rather than raising thresholds above 0.55.
Return ONLY this JSON structure (keep the same indicator names, only change numeric param values):
{{
  "reasoning": "one sentence explaining the changes",
  "indicators": {{
    "<indicator_name>": {{"params": {{"<param>": <value>}}}}
  }},
  "risk": {{"risk_per_trade": <float>, "stop_loss_pct": <float>}},
{_confluence_json_field()}
}}"""


def _build_leaps_prompt(strategy, metrics_list, option_type):
    enabled = _enabled_indicators(strategy)
    tickers_summary = "\n".join(
        f"  {m['ticker']}: P&L=${m['net_pnl']:.2f}, Avg%={m.get('avg_pnl_pct', 0):.1f}%, "
        f"Trades={m['trades']}, Win rate={m['win_rate']:.1%}"
        for m in metrics_list
    )
    avg_pnl = sum(m["net_pnl"] for m in metrics_list) / len(metrics_list)
    avg_win = sum(m["win_rate"] for m in metrics_list) / len(metrics_list)
    avg_pct = sum(m.get("avg_pnl_pct", 0) for m in metrics_list) / len(metrics_list)
    direction = (
        "bullish call options" if option_type == "call"
        else "bearish put options" if option_type == "put"
        else "call or put options depending on signal direction"
    )
    return f"""Current strategy: {strategy.get("name")}
You are optimizing entry/exit signals for LEAP options trading ({direction}).

Context:
- Signals trigger buying a 365-day LEAP call or put, not the underlying stock
- Options lose value from theta decay — signals must identify high-conviction moves
- Average trade return % is more important than total P&L — 3 trades at +150% beats 30 at +10%
- Fewer, stronger signals are better than many weak ones
- A 50% stop loss on option premium is in effect

Enabled indicators and current params:
{json.dumps(enabled, indent=2)}

LEAP backtest results across {len(metrics_list)} ticker(s):
{tickers_summary}
Average net P&L: ${avg_pnl:.2f} | Win rate: {avg_win:.1%} | Avg trade return: {avg_pct:.1f}%

Suggest parameter changes to improve average trade return % and win rate.
Prefer changes that raise signal thresholds (stronger confirmation before entry),
reduce whipsaw entries, and suit {direction} momentum moves.
{_CONFLUENCE_INSTRUCTIONS}

Return ONLY this JSON structure (keep the same indicator names, only change numeric param values):
{{
  "reasoning": "one sentence explaining the changes",
  "indicators": {{
    "<indicator_name>": {{"params": {{"<param>": <value>}}}}
  }},
  "risk": {{"risk_per_trade": <float>, "stop_loss_pct": <float>}},
{_confluence_json_field()}
}}"""


def _apply_suggestions(strategy, suggestions):
    updated = copy.deepcopy(strategy)
    v2 = is_v2(updated)
    for ind_name, ind_data in suggestions.get("indicators", {}).items():
        cfg = updated.get("indicators", {}).get(ind_name)
        if cfg is None or cfg.get("enabled") is False:
            continue
        if cfg.get("enabled") or v2:  # legacy enabled, or v2 (presence enables)
            cfg.setdefault("params", {}).update(ind_data.get("params", {}))
    risk_updates = suggestions.get("risk", {})
    if risk_updates:
        updated.setdefault("risk", {}).update(risk_updates)
    conf_updates = suggestions.get("confluence", {}) or {}
    if conf_updates:
        conf = updated.setdefault("confluence", {})
        if "min_score" in conf_updates:
            conf["min_score"] = conf_updates["min_score"]
        if conf_updates.get("weights"):
            conf.setdefault("weights", {}).update(conf_updates["weights"])
    return updated


def _avg_pnl(metrics_list):
    return sum(m["net_pnl"] for m in metrics_list) / len(metrics_list)


def _avg_leaps_score(metrics_list):
    """Score LEAP results by avg trade return % — better than net P&L for options."""
    return sum(m.get("avg_pnl_pct", 0) for m in metrics_list) / len(metrics_list)


def optimize(strategy_path, tickers, interval="1d", iterations=5, model=DEFAULT_MODEL,
             output_ticker=None, use_leaps=False, option_type="auto", warm_start=False):
    """
    LLM-driven strategy parameter optimization.

    warm_start: if True and an optimized YAML already exists for this strategy/ticker,
                start from those params instead of the base strategy. Use this for a
                second-pass refinement (e.g. 7b exploration → 32b refinement).
    use_leaps:  score against the LEAP backtest; output files get a _leaps_{option_type} suffix.
    """
    try:
        import ollama
    except ImportError:
        logger.error("[!] ollama package not installed")
        return None

    strategy_path = Path(strategy_path)

    # Resolve warm-start: load from existing optimized YAML if available
    parts = [strategy_path.stem]
    if output_ticker:
        parts.append(output_ticker)
    if use_leaps:
        parts.append(f"leaps_{option_type}")
    existing_opt = OPTIMIZED_DIR / f"{'_'.join(parts)}_optimized.yaml"

    if warm_start and existing_opt.exists():
        strategy = load_strategy(existing_opt)
        logger.info(f"[*] Warm start: loading from {existing_opt.name}")
    else:
        strategy = load_strategy(strategy_path)
        if warm_start:
            logger.info(f"[*] Warm start: no existing optimized YAML found, using base strategy")

    if isinstance(tickers, str):
        tickers = [tickers]

    best_strategy = copy.deepcopy(strategy)
    next_strategy = copy.deepcopy(strategy)
    best_metrics_list = None
    history = []
    mode = f"LEAP {option_type}" if use_leaps else "equity"

    logger.info(f"[*] Optimizing '{strategy.get('name')}' [{mode}] on {tickers} ({interval}) — {iterations} iterations")

    for i in range(iterations):
        logger.info(f"\n--- Iteration {i + 1}/{iterations} ---")
        current = next_strategy if i > 0 else strategy

        metrics_list = []
        for ticker in tickers:
            if use_leaps:
                m = run_leaps_backtest(ticker, interval, current, option_type=option_type)
            else:
                m = run_strategy_backtest(ticker, interval, current)
            if m:
                metrics_list.append(m)

        if not metrics_list:
            logger.error("[!] All backtests failed, stopping")
            break

        if use_leaps:
            score = _avg_leaps_score(metrics_list)
            best_score = _avg_leaps_score(best_metrics_list) if best_metrics_list else None
            logger.info(f"    Avg trade return: {score:.1f}%")
            is_better = best_metrics_list is None or score > best_score
        else:
            score = _avg_pnl(metrics_list)
            best_score = _avg_pnl(best_metrics_list) if best_metrics_list else None
            logger.info(f"    Avg P&L: ${score:.2f}")
            is_better = best_metrics_list is None or score > best_score

        if is_better:
            best_metrics_list = metrics_list
            best_strategy = copy.deepcopy(current)
            logger.info(f"    [✓] New best")

        history.append({"iteration": i + 1, "score": round(score, 2), "per_ticker": metrics_list})

        if i == iterations - 1:
            break

        prompt = (_build_leaps_prompt(best_strategy, metrics_list, option_type)
                  if use_leaps else _build_prompt(best_strategy, metrics_list))
        try:
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                format="json"
            )
            suggestions = json.loads(response.message.content)
            logger.info(f"    LLM: {suggestions.get('reasoning', '')}")
            # Apply suggestions to a fresh copy of best — never mutate best_strategy itself
            next_strategy = _apply_suggestions(copy.deepcopy(best_strategy), suggestions)
        except ConnectionError:
            logger.error("[!] Ollama not running — start with: ollama serve")
            break
        except Exception as e:
            logger.error(f"[!] LLM error: {e}")
            break

    OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)
    parts = [strategy_path.stem]
    if output_ticker:
        parts.append(output_ticker)
    if use_leaps:
        parts.append(f"leaps_{option_type}")
    out_path = OPTIMIZED_DIR / f"{'_'.join(parts)}_optimized.yaml"

    with open(out_path, "w") as f:
        yaml.dump(best_strategy, f, default_flow_style=False)

    logger.info(f"\n[✓] Optimized strategy saved → {out_path}")
    return {"best_metrics": best_metrics_list, "best_strategy": best_strategy,
            "history": history, "out_path": str(out_path)}
