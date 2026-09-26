"""Build a TradingAgents config with cost-conscious defaults."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Analysts run per cell. "social" and "fundamentals" add LLM calls and text feeds
# that are not archived point-in-time, so the quick preset leaves them out.
ALL_ANALYSTS = ("market", "social", "news", "fundamentals")
QUICK_ANALYSTS = ("market", "news")

# Model profiles (TradingAgents takes one provider for both tiers). The quick model
# runs ~8 of the ~10 agent roles per cell, so its price dominates the bill; the
# deep model only runs the Research Manager and Portfolio Manager.
PROFILES = {
    "eco": ("deepseek", "deepseek-v4-pro", "deepseek-flash"),
    "balanced": ("openai", "gpt-6-sol", "gpt-6-luna"),
    "premium": ("anthropic", "claude-sonnet-5", "claude-haiku-4-5"),
    # One key, providers mixed per tier: cheapest strong deep model + cheapest quick model.
    "openrouter": ("openrouter", "deepseek/deepseek-v4-pro", "openai/gpt-6-luna"),
}
DEFAULT_PROFILE = "balanced"


def build_config(results_dir: str | None = None, memory_log_path: str | None = None,
                 profile: str | None = None) -> dict:
    # Imported lazily: it reads TRADINGAGENTS_* env vars at import time, after load_dotenv.
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    # An explicit profile wins; otherwise TRADINGAGENTS_* env vars, then the default profile.
    profile = profile or os.getenv("TASIM_PROFILE")
    if profile or not os.getenv("TRADINGAGENTS_LLM_PROVIDER"):
        profile = profile or DEFAULT_PROFILE
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; expected one of {sorted(PROFILES)}")
        provider, deep, quick = PROFILES[profile]
        config.update(llm_provider=provider, deep_think_llm=deep, quick_think_llm=quick)
    if results_dir:
        config["results_dir"] = results_dir
    if memory_log_path:
        # Keep simulation decisions out of the user's live decision log.
        config["memory_log_path"] = memory_log_path
    return config
