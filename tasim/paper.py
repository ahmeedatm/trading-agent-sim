"""Daily paper-trading loop against an Alpaca PAPER account.

Run it after the US close (e.g. 22:30 Paris): ratings are dated today and the
market orders fill at tomorrow's open, the same timing the backtest simulates.
Dry-run by default; ``execute=True`` sends orders. There is no live-money path:
the client is always built with ``paper=True``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from tasim.config import build_config
from tasim.ratings import target_exposure
from tasim.signals import append_signal

logger = logging.getLogger(__name__)

MIN_ORDER_USD = 5.0  # skip dust rebalances


@dataclass
class Order:
    ticker: str
    rating: str
    side: str       # "buy" | "sell" | "close"
    notional: float


def _client():
    from alpaca.trading.client import TradingClient

    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("ALPACA_API_KEY / ALPACA_SECRET_KEY are not set (see .env.example)")
    return TradingClient(key, secret, paper=True)


def plan_orders(ratings: dict[str, str], equity: float, holdings: dict[str, float],
                exposure_map=None, hold_entry: float | None = None) -> list[Order]:
    """Orders that move each ticker's market value to its slot target."""
    n = len(ratings)
    orders = []
    for ticker, rating in ratings.items():
        held = holdings.get(ticker, 0.0)
        exposure = target_exposure(rating, exposure_map, held=held > 0, hold_entry=hold_entry)
        if exposure is None:
            continue
        if exposure == 0 and held > 0:
            orders.append(Order(ticker, rating, "close", held))
            continue
        delta = equity * exposure / n - held
        if abs(delta) >= MIN_ORDER_USD:
            orders.append(Order(ticker, rating, "buy" if delta > 0 else "sell", round(abs(delta), 2)))
    return orders


def run_daily(tickers: list[str], run_dir: Path, execute: bool = False,
              selected_analysts=("market", "news"), profile: str | None = None,
              hold_entry: float | None = None) -> list[Order]:
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.portfolio import PortfolioContext

    client = _client()
    account = client.get_account()
    positions = {p.symbol: p for p in client.get_all_positions()}
    equity = float(account.equity)
    holdings = {s: float(p.market_value) for s, p in positions.items()}
    book = PortfolioContext.model_validate({
        "cash": float(account.cash), "currency": "USD",
        "positions": [{"ticker": s, "quantity": float(p.qty), "average_price": float(p.avg_entry_price)}
                      for s, p in positions.items()],
    })

    run_dir.mkdir(parents=True, exist_ok=True)
    config = build_config(results_dir=str(run_dir / "reports"),
                          memory_log_path=str(run_dir / "trading_memory.md"), profile=profile)
    graph = TradingAgentsGraph(list(selected_analysts), config=config)
    today = date.today().isoformat()

    ratings = {}
    for ticker in tickers:
        _, rating = graph.propagate(ticker, today, portfolio=book)
        ratings[ticker] = rating
        append_signal(run_dir / "signals.csv", ticker, today, rating)
        logger.info("%s %s -> %s", ticker, today, rating)

    orders = plan_orders(ratings, equity, holdings, hold_entry=hold_entry)
    for order in orders:
        logger.info("%s %s %s $%.2f", "SEND" if execute else "DRY-RUN",
                    order.side, order.ticker, order.notional)
        if not execute:
            continue
        if order.side == "close":
            client.close_position(order.ticker)
        else:
            side = OrderSide.BUY if order.side == "buy" else OrderSide.SELL
            client.submit_order(MarketOrderRequest(symbol=order.ticker, notional=order.notional,
                                                   side=side, time_in_force=TimeInForce.DAY))
    return orders
