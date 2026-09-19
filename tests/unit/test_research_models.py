"""R0 — modele de graniță + registry de surse. Fără rețea, fără fallback silențios."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.research.models import RawDocument, ResearchDocument, SourceConfig
from src.research.registry import active_sources, load_source_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_REGISTRY = REPO_ROOT / "config" / "research_sources.yaml"


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _valid_source_payload() -> dict:
    return {
        "source_id": "fred",
        "name": "FRED",
        "kind": "api",
        "base_url": "https://api.stlouisfed.org/fred",
        "credibility_score": 0.95,
        "robots_txt_status": "not_applicable_api",
        "tos_reviewed_at": "2026-09-18T00:00:00+00:00",
        "rate_limit_per_min": 120,
    }


def _valid_raw_document_payload() -> dict:
    return {
        "url": "https://example.com/article",
        "source_id": "fred",
        "fetched_at": "2026-09-18T00:00:00+00:00",
        "raw_payload_ref": "raw/abc123.html",
    }


def _valid_research_document_payload() -> dict:
    return {
        "doc_id": "sha256:abc123",
        "url": "https://example.com/article",
        "title": "Fed holds rates steady",
        "source_id": "fred",
        "author": None,
        "published_at": "2026-09-18T00:00:00+00:00",
        "fetched_at": "2026-09-18T01:00:00+00:00",
        "event_date": None,
        "assets_mentioned": ["AAPL"],
        "category": "macro_indicator",
        "extracted_text": "The Federal Reserve held interest rates steady.",
        "summary": None,
        "sentiment_score": 0.1,
        "impact_magnitude": "medium",
        "impact_direction": "neutral",
        "confidence_score": 0.8,
        "last_verified_at": "2026-09-18T01:00:00+00:00",
        "content_hash": "abc123",
    }


# --- SourceConfig ---------------------------------------------------------


def test_source_config_accepts_valid_payload() -> None:
    source = SourceConfig.model_validate(_valid_source_payload())
    assert source.source_id == "fred"
    assert source.tos_reviewed_at == datetime(2026, 9, 18, tzinfo=timezone.utc)


def test_source_config_allows_missing_tos_reviewed_at() -> None:
    payload = _valid_source_payload()
    del payload["tos_reviewed_at"]
    source = SourceConfig.model_validate(payload)
    assert source.tos_reviewed_at is None
    assert source.review_status == "pending"
    assert source.is_fetchable() is False


def test_source_config_date_only_tos_reviewed_at_is_utc_midnight() -> None:
    payload = _valid_source_payload()
    payload["tos_reviewed_at"] = "2026-09-19"
    source = SourceConfig.model_validate(payload)
    assert source.tos_reviewed_at == datetime(2026, 9, 19, tzinfo=timezone.utc)


def test_source_config_rejects_extra_fields() -> None:
    payload = _valid_source_payload()
    payload["auto_activate"] = True
    with pytest.raises(ValidationError):
        SourceConfig.model_validate(payload)


def test_source_config_rejects_unknown_kind() -> None:
    payload = _valid_source_payload()
    payload["kind"] = "web_scraper_v2"
    with pytest.raises(ValidationError):
        SourceConfig.model_validate(payload)


def test_source_config_rejects_credibility_out_of_range() -> None:
    payload = _valid_source_payload()
    payload["credibility_score"] = 1.5
    with pytest.raises(ValidationError):
        SourceConfig.model_validate(payload)


# --- RawDocument / ResearchDocument ---------------------------------------


def test_raw_document_accepts_valid_payload() -> None:
    doc = RawDocument.model_validate(_valid_raw_document_payload())
    assert doc.source_id == "fred"


def test_raw_document_rejects_extra_fields() -> None:
    payload = _valid_raw_document_payload()
    payload["inline_payload"] = "<html>injected</html>"
    with pytest.raises(ValidationError):
        RawDocument.model_validate(payload)


def test_research_document_accepts_valid_payload() -> None:
    doc = ResearchDocument.model_validate(_valid_research_document_payload())
    assert doc.category == "macro_indicator"
    assert doc.assets_mentioned == ["AAPL"]


def test_research_document_rejects_extra_fields() -> None:
    payload = _valid_research_document_payload()
    payload["risk_override"] = True
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(payload)


def test_research_document_accepts_crypto_categories() -> None:
    for category in (
        "protocol_upgrade",
        "token_unlock",
        "governance",
        "listing",
        "onchain_alert",
        "funding_regime",
        "regulatory",
    ):
        payload = _valid_research_document_payload()
        payload["category"] = category
        payload["assets_mentioned"] = ["ETHUSD"]
        doc = ResearchDocument.model_validate(payload)
        assert doc.category == category


def test_research_document_rejects_unknown_category() -> None:
    payload = _valid_research_document_payload()
    payload["category"] = "earnings_call"
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(payload)


def test_research_document_rejects_sentiment_out_of_range() -> None:
    payload = _valid_research_document_payload()
    payload["sentiment_score"] = 2.0
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(payload)


# --- load_source_registry --------------------------------------------------


def test_real_registry_file_loads() -> None:
    sources = load_source_registry(REAL_REGISTRY)
    ids = [source.source_id for source in sources]
    assert ids == [
        "fred",
        "alfred",
        "sec_edgar",
        "bls",
        "bea",
        "ecb_data",
        "eurostat",
        "sec_press_rss",
        "federal_reserve_press_rss",
        "ecb_press_rss",
    ]
    assert [source.source_id for source in active_sources(sources)] == [
        "fred",
        "alfred",
        "sec_edgar",
        "bls",
        "bea",
    ]
    pending_ids = {source.source_id for source in sources if not source.is_fetchable()}
    assert pending_ids == {
        "ecb_data",
        "eurostat",
        "sec_press_rss",
        "federal_reserve_press_rss",
        "ecb_press_rss",
    }
    by_id = {source.source_id: source for source in sources}
    assert by_id["sec_edgar"].base_url == "https://data.sec.gov"
    assert by_id["sec_edgar"].min_request_interval_s == 0.1
    assert by_id["sec_edgar"].rate_limit_per_min is None
    assert by_id["bls"].min_request_interval_s == 0.2
    assert by_id["bea"].rate_limit_per_min == 100
    assert by_id["fred"].rate_limit_per_min == 120


def test_missing_registry_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        load_source_registry(tmp_path / "does-not-exist.yaml")


def test_registry_without_sources_key_raises(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path / "sources.yaml", {"not_sources": []})
    with pytest.raises(ValueError, match="sources list"):
        load_source_registry(path)


def test_registry_valid_source_loads(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path / "sources.yaml", {"sources": [_valid_source_payload()]})
    sources = load_source_registry(path)
    assert len(sources) == 1
    assert sources[0].source_id == "fred"


def test_registry_source_without_tos_reviewed_at_loads_but_is_not_active(
    tmp_path: Path,
) -> None:
    payload = _valid_source_payload()
    del payload["tos_reviewed_at"]
    payload["review_status"] = "pending"
    path = _write_yaml(tmp_path / "sources.yaml", {"sources": [payload]})
    sources = load_source_registry(path)
    assert len(sources) == 1
    assert sources[0].tos_reviewed_at is None
    assert active_sources(sources) == []


def test_registry_rejects_duplicate_source_id(tmp_path: Path) -> None:
    payload = _valid_source_payload()
    path = _write_yaml(tmp_path / "sources.yaml", {"sources": [payload, payload]})
    with pytest.raises(ValueError, match="duplicate"):
        load_source_registry(path)


def test_registry_rejects_extra_field_on_a_source(tmp_path: Path) -> None:
    payload = _valid_source_payload()
    payload["auto_activate"] = True
    path = _write_yaml(tmp_path / "sources.yaml", {"sources": [payload]})
    with pytest.raises(ValueError, match="invalid"):
        load_source_registry(path)


def test_registry_empty_sources_list_is_valid(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path / "sources.yaml", {"sources": []})
    assert load_source_registry(path) == []
