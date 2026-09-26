import numpy as np
import pandas as pd
import pytest

from tasim.paper import plan_orders
from tasim.portfolio import metrics, simulate

DAYS = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])


def frame(values):
    return pd.DataFrame(values, index=DAYS)


def signals(rows):
    return pd.DataFrame(rows, columns=["ticker", "date", "rating"])


def test_signal_executes_at_next_open_not_same_day():
    open_px = frame({"A": [10.0, 20.0, 20.0, 20.0]})
    close_px = frame({"A": [10.0, 20.0, 20.0, 40.0]})
    sim = simulate(signals([("A", "2026-01-05", "Buy")]), open_px, close_px,
                   capital=1000, fee_bps=0)
    assert sim.trades[0].date == DAYS[1]
    assert sim.trades[0].price == 20.0          # not the 10.0 open of the signal day
    assert sim.equity.iloc[0] == 1000
    assert sim.equity.iloc[-1] == pytest.approx(2000)


def test_fees_reduce_cash_and_buy_is_capped_by_cash():
    px = frame({"A": [10.0] * 4})
    sim = simulate(signals([("A", "2026-01-05", "Buy")]), px, px, capital=1000, fee_bps=100)
    assert sim.equity.iloc[-1] == pytest.approx(1000 - sim.fees)
    assert sim.equity.iloc[-1] > 0


def test_hold_keeps_position_and_sell_liquidates():
    px = frame({"A": [10.0, 10.0, 12.0, 12.0]})
    sim = simulate(signals([("A", "2026-01-05", "Buy"), ("A", "2026-01-06", "Hold"),
                            ("A", "2026-01-07", "Sell")]), px, px, capital=1000, fee_bps=0)
    assert [t.rating for t in sim.trades] == ["Buy", "Sell"]
    assert sim.trades[1].shares == pytest.approx(-100)
    assert sim.equity.iloc[-1] == pytest.approx(1200)


def test_equal_slots_across_tickers():
    px = frame({"A": [10.0] * 4, "B": [50.0] * 4})
    sim = simulate(signals([("A", "2026-01-05", "Buy"), ("B", "2026-01-05", "Underweight")]),
                   px, px, capital=1000, fee_bps=0)
    notional = {t.ticker: t.shares * t.price for t in sim.trades}
    assert notional == {"A": pytest.approx(500), "B": pytest.approx(125)}


def test_signal_after_last_day_is_reported_not_traded():
    px = frame({"A": [10.0] * 4})
    sim = simulate(signals([("A", "2026-01-08", "Buy")]), px, px, capital=1000)
    assert not sim.trades and sim.skipped_signals


def test_metrics_drawdown():
    m = metrics(pd.Series([100.0, 120.0, 90.0, 110.0]))
    assert m["max_drawdown"] == pytest.approx(-0.25)
    assert m["total_return"] == pytest.approx(0.10)


def test_metrics_measured_from_starting_capital():
    # The first close already lost 2 % versus the 100 of starting cash.
    m = metrics(pd.Series([98.0, 99.0, 101.0]), capital=100)
    assert m["total_return"] == pytest.approx(0.01)
    assert m["max_drawdown"] == pytest.approx(-0.02)
    assert np.isnan(m["cagr"])                    # too short to annualise


def test_plan_orders():
    orders = plan_orders({"A": "Buy", "B": "Sell", "C": "Hold", "D": "Overweight"},
                         equity=4000, holdings={"B": 300, "C": 900, "D": 750})
    by = {o.ticker: (o.side, o.notional) for o in orders}
    assert by == {"A": ("buy", 1000), "B": ("close", 300)}   # D is already on target


def test_profiles_set_provider_and_models(monkeypatch):
    from tasim.config import build_config

    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TASIM_PROFILE", raising=False)
    assert build_config()["quick_think_llm"] == "gpt-6-luna"
    eco = build_config(profile="eco")
    assert (eco["llm_provider"], eco["deep_think_llm"]) == ("deepseek", "deepseek-v4-pro")
    mixed = build_config(profile="openrouter")
    assert (mixed["llm_provider"], mixed["quick_think_llm"]) == ("openrouter", "openai/gpt-6-luna")
    with pytest.raises(ValueError):
        build_config(profile="nope")


def test_openrouter_deepseek_uses_json_schema_native_deepseek_untouched():
    from tradingagents.llm_clients import openai_client

    from tasim.config import build_config

    build_config(profile="openrouter")
    caps = openai_client.get_capabilities
    assert caps("deepseek/deepseek-v4-pro").preferred_structured_method == "json_schema"
    assert caps("deepseek-v4-pro").preferred_structured_method == "function_calling"
    assert caps("openai/gpt-6-luna").preferred_structured_method == "function_calling"


def test_hold_entry_opens_unowned_ticker_but_keeps_existing_position():
    px = frame({"A": [10.0] * 4, "B": [10.0] * 4})
    sigs = signals([("A", "2026-01-05", "Underweight"), ("A", "2026-01-06", "Hold"),
                    ("B", "2026-01-06", "Hold")])
    default = simulate(sigs, px, px, capital=1000, fee_bps=0)
    assert [t.ticker for t in default.trades] == ["A"]          # Hold never trades
    sim = simulate(sigs, px, px, capital=1000, fee_bps=0, hold_entry=0.5)
    notional = {(t.ticker, t.rating): t.shares * t.price for t in sim.trades}
    assert notional == {("A", "Underweight"): pytest.approx(125),   # A's Hold keeps 125
                        ("B", "Hold"): pytest.approx(250)}


def test_plan_orders_hold_entry():
    orders = plan_orders({"A": "Hold", "B": "Hold"}, equity=4000, holdings={"B": 300},
                         hold_entry=0.5)
    assert {o.ticker: (o.side, o.notional) for o in orders} == {"A": ("buy", 1000)}
