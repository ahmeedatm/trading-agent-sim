"""Run TradingAgents over a ticker x date grid and store one rating per cell.

The store is a CSV in the run directory, so an interrupted sweep resumes by
being run again: cells already present are skipped (LLM calls cost money).
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from tasim.config import build_config

logger = logging.getLogger(__name__)

FIELDS = ("ticker", "date", "rating", "generated_at")


def load_signals(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(columns=FIELDS)
    return pd.read_csv(path, dtype=str)


def append_signal(path: Path, ticker: str, date: str, rating: str) -> None:
    new = not path.is_file()
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({"ticker": ticker, "date": date, "rating": rating,
                         "generated_at": datetime.now().isoformat(timespec="seconds")})


def generate_signals(tickers: list[str], dates: list[str], run_dir: Path,
                     selected_analysts=("market", "news"), profile: str | None = None) -> Path:
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    run_dir.mkdir(parents=True, exist_ok=True)
    store = run_dir / "signals.csv"
    config = build_config(results_dir=str(run_dir / "reports"),
                          memory_log_path=str(run_dir / "trading_memory.md"), profile=profile)
    graph = TradingAgentsGraph(list(selected_analysts), config=config)

    existing = load_signals(store)
    done = set(zip(existing["ticker"], existing["date"], strict=True))
    todo = [(t, d) for t in tickers for d in dates if (t, d) not in done]
    logger.info("%d cells to run, %d already stored", len(todo), len(done))

    for i, (ticker, date) in enumerate(todo, 1):
        try:
            _, rating = graph.propagate(ticker, date)
        except Exception as exc:  # one failed cell must not end a paid sweep
            logger.warning("[%d/%d] %s %s failed: %s", i, len(todo), ticker, date, exc)
            continue
        append_signal(store, ticker, date, rating)
        logger.info("[%d/%d] %s %s -> %s", i, len(todo), ticker, date, rating)
    return store
