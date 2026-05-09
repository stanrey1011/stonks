import json
import logging
import copy
import yaml
from pathlib import Path

from stonkslib.backtest.strategy import run_strategy_backtest, load_strategy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPTIMIZED_DIR = PROJECT_ROOT / "stonkslib" / "strategies" / "optimized"
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = """You are a quantitative trading strategy optimizer.
Your job is to suggest improved indicator parameters based on backtest results.
Always return valid JSON only — no explanation outside the JSON object."""


def _build_prompt(strategy, metrics_list):
    enabled = {k: v for k, v in strategy.get("indicators", {}).items() if v.get("enabled")}
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

Backtest results across {len(metrics_list)} ticker(s) ({metrics_list[0]["interval"]}):
{tickers_summary}
Average P&L: ${avg_pnl:.2f} | Average win rate: {avg_win:.1%}

Suggest new parameter values to improve average P&L and win rate across all tickers.
Return ONLY this JSON structure (keep the same indicator names, only change numeric param values):
{{
  "reasoning": "one sentence explaining the changes",
  "indicators": {{
    "<indicator_name>": {{"params": {{"<param>": <value>}}}}
  }},
  "risk": {{"risk_per_trade": <float>, "stop_loss_pct": <float>}}
}}"""


def _apply_suggestions(strategy, suggestions):
    updated = copy.deepcopy(strategy)
    for ind_name, ind_data in suggestions.get("indicators", {}).items():
        if ind_name in updated.get("indicators", {}) and updated["indicators"][ind_name].get("enabled"):
            new_params = ind_data.get("params", {})
            updated["indicators"][ind_name]["params"].update(new_params)
    risk_updates = suggestions.get("risk", {})
    if risk_updates:
        updated.setdefault("risk", {}).update(risk_updates)
    return updated


def _avg_pnl(metrics_list):
    return sum(m["net_pnl"] for m in metrics_list) / len(metrics_list)


def optimize(strategy_path, tickers, interval="1d", iterations=5, model=DEFAULT_MODEL):
    try:
        import ollama
    except ImportError:
        logger.error("[!] ollama package not installed")
        return None

    strategy_path = Path(strategy_path)
    strategy = load_strategy(strategy_path)

    if isinstance(tickers, str):
        tickers = [tickers]

    best_strategy = copy.deepcopy(strategy)
    best_metrics_list = None
    history = []

    logger.info(f"[*] Optimizing '{strategy.get('name')}' on {tickers} ({interval}) — {iterations} iterations")

    for i in range(iterations):
        logger.info(f"\n--- Iteration {i + 1}/{iterations} ---")
        current = best_strategy if i > 0 else strategy

        metrics_list = []
        for ticker in tickers:
            m = run_strategy_backtest(ticker, interval, current)
            if m:
                metrics_list.append(m)

        if not metrics_list:
            logger.error("[!] All backtests failed, stopping")
            break

        avg = _avg_pnl(metrics_list)
        logger.info(f"    Avg P&L: ${avg:.2f}")

        if best_metrics_list is None or avg > _avg_pnl(best_metrics_list):
            best_metrics_list = metrics_list
            best_strategy = copy.deepcopy(current)
            logger.info(f"    [✓] New best avg: ${avg:.2f}")

        history.append({"iteration": i + 1, "avg_pnl": round(avg, 2), "per_ticker": metrics_list})

        if i == iterations - 1:
            break

        prompt = _build_prompt(best_strategy, metrics_list)
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
            best_strategy = _apply_suggestions(best_strategy, suggestions)
        except ConnectionError:
            logger.error("[!] Ollama not running — start with: ollama serve")
            break
        except Exception as e:
            logger.error(f"[!] LLM error: {e}")
            break

    OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OPTIMIZED_DIR / f"{strategy_path.stem}_optimized.yaml"
    with open(out_path, "w") as f:
        yaml.dump(best_strategy, f, default_flow_style=False)

    logger.info(f"\n[✓] Optimized strategy saved → {out_path}")
    return {"best_metrics": best_metrics_list, "best_strategy": best_strategy, "history": history}
