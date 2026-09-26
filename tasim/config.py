"""Build a TradingAgents config with cost-conscious defaults."""

from __future__ import annotations

import os
from dataclasses import replace

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


def _use_json_schema_for_openrouter_deepseek() -> None:
    """Make DeepSeek models reached through OpenRouter use ``json_schema`` structured output.

    TradingAgents maps ``deepseek/<id>`` to the native DeepSeek capabilities: schema bound
    as a tool with no ``tool_choice``. On the long Research/Portfolio Manager prompts the
    thinking model then answers in plain text, every structured call misses and the agent
    falls back to free text. OpenRouter supports ``response_format`` json_schema for these
    models, which parsed reliably in testing. The native ``deepseek`` provider is untouched.
    """
    from tradingagents.llm_clients import openai_client
    from tradingagents.llm_clients.capabilities import ModelCapabilities, get_capabilities

    if getattr(openai_client.get_capabilities, "_tasim_patched", False):
        return

    def patched(model_name: str) -> ModelCapabilities:
        caps = get_capabilities(model_name)
        if model_name.startswith("deepseek/"):
            return replace(caps, supports_json_schema=True,
                           preferred_structured_method="json_schema")
        return caps

    patched._tasim_patched = True
    openai_client.get_capabilities = patched


def build_config(results_dir: str | None = None, memory_log_path: str | None = None,
                 profile: str | None = None) -> dict:
    # Imported lazily: it reads TRADINGAGENTS_* env vars at import time, after load_dotenv.
    from tradingagents.default_config import DEFAULT_CONFIG

    _use_json_schema_for_openrouter_deepseek()

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
