"""Daily adjusted open/close prices from Yahoo Finance."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Prices:
    open: pd.DataFrame   # index: trading days, columns: tickers
    close: pd.DataFrame


def load_prices(tickers: list[str], start: str, end: str) -> Prices:
    import yfinance as yf

    # yfinance's end is exclusive; pad it so the last requested day is included.
    end_padded = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    raw = yf.download(sorted(set(tickers)), start=start, end=end_padded,
                      auto_adjust=True, progress=False, group_by="column")
    if raw.empty:
        raise RuntimeError(f"no price data for {tickers} between {start} and {end}")
    opens, closes = raw["Open"], raw["Close"]
    if isinstance(opens, pd.Series):
        opens, closes = opens.to_frame(tickers[0]), closes.to_frame(tickers[0])
    opens.index = pd.to_datetime(opens.index).tz_localize(None)
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    return Prices(open=opens.dropna(how="all"), close=closes.dropna(how="all"))
