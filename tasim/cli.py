"""tasim — signals, simulate, paper."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from tasim.config import ALL_ANALYSTS, PROFILES, QUICK_ANALYSTS

RUNS = Path("runs")


def _tickers(value: str) -> list[str]:
    return [t.strip().upper() for t in value.split(",") if t.strip()]


def cmd_signals(args) -> None:
    from tradingagents.backtest import iter_grid

    from tasim.signals import generate_signals

    dates = iter_grid(args.start, args.end, every_n_days=args.every)
    analysts = ALL_ANALYSTS if args.full else QUICK_ANALYSTS
    cells = len(args.tickers) * len(dates)
    print(f"{cells} cells ({len(args.tickers)} tickers x {len(dates)} dates), "
          f"analysts: {', '.join(analysts)}")
    if not args.yes and input("Each cell is a full multi-agent LLM run. Continue? [y/N] ") != "y":
        return
    store = generate_signals(args.tickers, dates, RUNS / args.run, analysts, args.profile)
    print(f"Signals written to {store}")


def cmd_simulate(args) -> None:
    from tasim.data import load_prices
    from tasim.portfolio import buy_and_hold, metrics, simulate
    from tasim.signals import load_signals

    run_dir = RUNS / args.run
    signals = load_signals(Path(args.signals) if args.signals else run_dir / "signals.csv")
    if signals.empty:
        raise SystemExit(f"no signals in {run_dir}; run `tasim signals` first")
    tickers = sorted(signals["ticker"].unique())
    start = signals["date"].min()
    end = args.end or pd.Timestamp.today().strftime("%Y-%m-%d")
    prices = load_prices(tickers + [args.benchmark], start, end)

    sim = simulate(signals, prices.open[tickers], prices.close[tickers],
                   capital=args.capital, fee_bps=args.fee_bps, tickers=tickers)
    first_trade = sim.trades[0].date if sim.trades else sim.equity.index[0]
    curves = pd.DataFrame({
        "strategy": sim.equity.loc[first_trade:],
        "buy_and_hold": buy_and_hold(prices.close, prices.open, tickers, first_trade,
                                     args.capital, args.fee_bps),
        args.benchmark: buy_and_hold(prices.close, prices.open, [args.benchmark], first_trade,
                                     args.capital, args.fee_bps),
    }).dropna()

    run_dir.mkdir(parents=True, exist_ok=True)
    curves.to_csv(run_dir / "equity.csv")
    pd.DataFrame([t.__dict__ for t in sim.trades]).to_csv(run_dir / "trades.csv", index=False)

    table = pd.DataFrame({name: metrics(curve) for name, curve in curves.items()}).T
    final = curves.iloc[-1].rename("final_value")
    report = pd.concat([final, table], axis=1)
    print(f"\nCapital {args.capital:,.0f} $ · {first_trade.date()} -> {curves.index[-1].date()} "
          f"· {len(sim.trades)} trades · fees {sim.fees:,.2f} $\n")
    print(report.to_string(float_format=lambda x: f"{x:,.4f}"))
    for ticker, date, reason in sim.skipped_signals:
        print(f"skipped {ticker} {date}: {reason}")
    print(f"\nCurves: {run_dir / 'equity.csv'} · trades: {run_dir / 'trades.csv'}")


def cmd_paper(args) -> None:
    from tasim.paper import run_daily

    analysts = ALL_ANALYSTS if args.full else QUICK_ANALYSTS
    orders = run_daily(args.tickers, RUNS / args.run, execute=args.execute,
                       selected_analysts=analysts, profile=args.profile)
    if not orders:
        print("No orders (all Hold/REVIEW or already on target).")
    for o in orders:
        print(f"{'SENT' if args.execute else 'DRY-RUN'}: {o.side} {o.ticker} ${o.notional:,.2f} ({o.rating})")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="tasim")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("signals", help="run TradingAgents over a ticker x date grid")
    p.add_argument("tickers", type=_tickers)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--every", type=int, default=7, help="days between analyses")
    p.add_argument("--run", default="default")
    p.add_argument("--full", action="store_true", help="all four analysts (more LLM cost)")
    p.add_argument("--profile", choices=sorted(PROFILES), help="LLM profile (default: balanced)")
    p.add_argument("-y", "--yes", action="store_true", help="skip the cost confirmation")
    p.set_defaults(func=cmd_signals)

    p = sub.add_parser("simulate", help="replay stored signals as a cash portfolio")
    p.add_argument("--run", default="default")
    p.add_argument("--signals", help="CSV of ticker,date,rating (defaults to the run's)")
    p.add_argument("--capital", type=float, default=10_000)
    p.add_argument("--fee-bps", type=float, default=5.0)
    p.add_argument("--benchmark", default="SPY")
    p.add_argument("--end")
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("paper", help="today's ratings -> Alpaca paper orders")
    p.add_argument("tickers", type=_tickers)
    p.add_argument("--run", default="paper")
    p.add_argument("--full", action="store_true")
    p.add_argument("--profile", choices=sorted(PROFILES), help="LLM profile (default: balanced)")
    p.add_argument("--execute", action="store_true", help="actually send orders (paper account)")
    p.set_defaults(func=cmd_paper)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
