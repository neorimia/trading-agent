"""Prompturile P1–P7 sunt crypto-adapted și nu cer execuție."""

from __future__ import annotations

from src.llm.analysis_prompts import ANALYSIS_SYSTEM_PROMPT, type_instruction


def test_system_prompt_is_crypto_research_only() -> None:
    text = ANALYSIS_SYSTEM_PROMPT.lower()
    assert "token unlock" in text or "unlocks" in text
    assert "funding" in text
    assert "position_size_suggestion to null" in text
    assert "research only" in text
    assert "submit orders" in text
    assert "earnings, guidance, or sec filings" in text


def test_priced_in_drops_equity_framing() -> None:
    text = type_instruction("priced_in").lower()
    assert "earnings" in text
    assert "do not use earnings" in text
    assert "catalysts" in text


def test_technical_uses_precomputed_levels() -> None:
    text = type_instruction("technical").lower()
    assert "precomputed" in text
    assert "do not invent support" in text


def test_daily_plan_forbids_invented_events() -> None:
    text = type_instruction("daily_plan").lower()
    assert "do not add events" in text
    assert "00:00 utc" in text
