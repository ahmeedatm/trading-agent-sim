"""Turn dated ratings into a simulated cash portfolio.

Rules (long-only, no leverage):
- Each ticker owns an equal slot: 1/N of equity.
- A rating dated D is executed at the OPEN of the first trading day strictly
  after D. TradingAgents may read D's close, so trading on D would be look-ahead.
- On execution the ticker is traded to ``equity_at_open * exposure / N``; Hold
  and REVIEW leave the position alone. Buys are capped by available cash.
- Fees are charged in basis points of traded notional. Equity is marked at close.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from tasim.ratings import target_exposure


@dataclass
class Trade:
    date: pd.Timestamp
    ticker: str
    rating: str
    shares: float
    price: float
    fee: float


@dataclass
class SimulationResult:
    equity: pd.Series
    trades: list[Trade] = field(default_factory=list)
    skipped_signals: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def fees(self) -> float:
        return sum(t.fee for t in self.trades)


def simulate(signals: pd.DataFrame, open_px: pd.DataFrame, close_px: pd.DataFrame,
             capital: float = 10_000.0, fee_bps: float = 5.0,
             tickers: list[str] | None = None,
             exposure_map: dict[str, float | None] | None = None) -> SimulationResult:
    tickers = tickers or sorted(signals["ticker"].unique())
    n = len(tickers)
    days = close_px.index
    fee_rate = fee_bps / 10_000

    # Schedule each signal on the first trading day after its date.
    schedule: dict[pd.Timestamp, list[tuple[str, str]]] = {}
    result = SimulationResult(equity=pd.Series(dtype=float))
    for row in signals.itertuples(index=False):
        if row.ticker not in tickers:
            continue
        pos = days.searchsorted(pd.Timestamp(row.date), side="right")
        if pos >= len(days):
            result.skipped_signals.append((row.ticker, row.date, "no trading day after signal"))
            continue
        schedule.setdefault(days[pos], []).append((row.ticker, row.rating))

    cash = capital
    shares = dict.fromkeys(tickers, 0.0)
    equity_curve = {}
    for day in days:
        orders = schedule.get(day, [])
        if orders:
            opens = open_px.loc[day]
            equity_open = cash + sum(shares[t] * _px(opens, t) for t in tickers if shares[t])
            # Sells first so their cash funds the buys on the same open.
            planned = []
            for ticker, rating in orders:
                exposure = target_exposure(rating, exposure_map)
                price = _px(opens, ticker)
                if exposure is None or np.isnan(price):
                    continue
                delta = equity_open * exposure / n / price - shares[ticker]
                planned.append((delta, ticker, rating, price))
            for delta, ticker, rating, price in sorted(planned):
                if delta > 0:
                    delta = min(delta, cash / (price * (1 + fee_rate)))
                if abs(delta * price) < 0.01:
                    continue
                fee = abs(delta * price) * fee_rate
                cash -= delta * price + fee
                shares[ticker] += delta
                result.trades.append(Trade(day, ticker, rating, delta, price, fee))
        closes = close_px.loc[day]
        equity_curve[day] = cash + sum(shares[t] * _px(closes, t) for t in tickers if shares[t])

    result.equity = pd.Series(equity_curve, name="strategy")
    return result


def _px(row: pd.Series, ticker: str) -> float:
    return float(row.get(ticker, np.nan))


def buy_and_hold(close_px: pd.DataFrame, open_px: pd.DataFrame, tickers: list[str],
                 start: pd.Timestamp, capital: float, fee_bps: float = 5.0) -> pd.Series:
    """Equal-weight buy at the open of ``start``, held to the end."""
    fee_rate = fee_bps / 10_000
    per = capital / len(tickers) / (1 + fee_rate)
    shares = {t: per / float(open_px.loc[start, t]) for t in tickers}
    window = close_px.loc[start:, tickers]
    return (window * pd.Series(shares)).sum(axis=1)


def metrics(equity: pd.Series) -> dict[str, float]:
    equity = equity.dropna()
    rets = equity.pct_change().dropna()
    years = max(len(equity) / 252, 1 / 252)
    total = equity.iloc[-1] / equity.iloc[0] - 1
    vol = rets.std() * np.sqrt(252) if len(rets) > 1 else 0.0
    return {
        "total_return": total,
        "cagr": (1 + total) ** (1 / years) - 1,
        "volatility": vol,
        "sharpe": (rets.mean() * 252 / vol) if vol else 0.0,
        "max_drawdown": (equity / equity.cummax() - 1).min(),
    }
