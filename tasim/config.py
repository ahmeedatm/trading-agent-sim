"""Build a TradingAgents config with cost-conscious defaults."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Analysts run per cell. "social" and "fundamentals" add LLM calls and text feeds
# that are not archived point-in-time, so the quick preset leaves them out.
ALL_ANALYSTS = ("market", "social", "news", "fundamentals")
QUICK_ANALYSTS = ("market", "news")


def build_config(results_dir: str | None = None, memory_log_path: str | None = None) -> dict:
    # Imported lazily: it reads TRADINGAGENTS_* env vars at import time, after load_dotenv.
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    if not os.getenv("TRADINGAGENTS_LLM_PROVIDER"):
        config["llm_provider"] = "anthropic"
        config["deep_think_llm"] = "claude-sonnet-5"
        config["quick_think_llm"] = "claude-haiku-4-5"
    if results_dir:
        config["results_dir"] = results_dir
    if memory_log_path:
        # Keep simulation decisions out of the user's live decision log.
        config["memory_log_path"] = memory_log_path
    return config
