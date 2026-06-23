import json

import click


@click.command("agents")
@click.argument("target", required=False, default="all",
                metavar="[TICKER|CATEGORY|all]")
@click.option("--interval", default="1d", help="Bar interval (1d, 1wk).")
@click.option("--model", default=None, help="LLM model override (defaults to LLM_MODEL).")
@click.option("--json", "as_json", is_flag=True, help="Emit raw FundReport JSON.")
def agents(target, interval, model, as_json):
    """Run the multi-agent hedge-fund chain over a ticker or the watchlist.

    Hydrates the unified snapshot, then runs the analyst -> bull/bear -> portfolio
    manager chain (all one local model via LLM_MODEL). The portfolio manager
    returns a per-vehicle verdict: LEAP / DCA / Swing.

    Examples:\n
      stonks agents NVDA\n
      stonks agents stocks --interval 1wk\n
      stonks agents all --json
    """
    from stonkslib.agents.orchestrator import run_fund, run_fund_watchlist, render
    from stonkslib.snapshot import _watchlist

    if target and target.lower() not in ("all", "stocks", "etfs", "crypto"):
        reports = [run_fund(target.upper(), interval=interval, model=model)]
    elif target and target.lower() in ("stocks", "etfs", "crypto"):
        reports = run_fund_watchlist(interval=interval, model=model,
                                     tickers=_watchlist((target.lower(),)))
    else:
        reports = run_fund_watchlist(interval=interval, model=model)

    if as_json:
        click.echo(json.dumps(reports, indent=2, default=str))
    else:
        click.echo(render(reports))
