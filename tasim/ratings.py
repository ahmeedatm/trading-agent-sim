"""Map TradingAgents' 5-tier ratings to a target exposure for one ticker slot.

Each ticker owns an equal slot of the portfolio (1/N of equity). The exposure
is the fraction of that slot held long. ``None`` means "keep what you hold":
Hold claims no direction, and REVIEW is an unreadable decision, so neither
should move money. An optional ``hold_entry`` makes a Hold on a ticker you do
not own open a position at that exposure instead (a Hold on an existing position
still leaves it alone).
"""

from __future__ import annotations

DEFAULT_EXPOSURE: dict[str, float | None] = {
    "Buy": 1.0,
    "Overweight": 0.75,
    "Hold": None,
    "Underweight": 0.25,
    "Sell": 0.0,
    "REVIEW": None,
}


def target_exposure(rating: str, mapping: dict[str, float | None] | None = None, *,
                    held: bool = True, hold_entry: float | None = None) -> float | None:
    mapping = mapping or DEFAULT_EXPOSURE
    if rating not in mapping:
        raise ValueError(f"unknown rating {rating!r}; expected one of {sorted(mapping)}")
    if rating == "Hold" and not held and hold_entry is not None:
        return hold_entry
    return mapping[rating]
