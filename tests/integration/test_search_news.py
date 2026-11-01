from __future__ import annotations

import json

import pytest

from stram_qualitative_mcp.errors import ToolInputError
from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_models import NewsSearchData

OCTOBER = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


def _search(adapter: QualToolAdapter, **arguments: object) -> NewsSearchData:
    envelope = adapter.execute("qual_search_news", {**OCTOBER, **arguments}, "search")
    data = envelope.data  # type: ignore[attr-defined]
    assert isinstance(data, NewsSearchData)
    return data


def _titles(data: NewsSearchData) -> list[str]:
    return [row.title for row in data.rows]


def test_defaults_hide_weak_links_and_flagged_items(tool_adapter: QualToolAdapter) -> None:
    assert _titles(_search(tool_adapter, tickers=["AAPL"])) == [
        "Synthetic Apple supplier update",
        "Synthetic 8-K announcement",
        "Synthetic backfilled story",
    ]


def test_filters_can_widen_the_defaults(tool_adapter: QualToolAdapter) -> None:
    titles = _titles(
        _search(tool_adapter, tickers=["AAPL"], min_confidence=0.0, include_flagged=True)
    )
    assert "Synthetic fruit market report" in titles
    assert "Synthetic spam listing" in titles


def test_text_and_provider_filters_work_without_tickers(tool_adapter: QualToolAdapter) -> None:
    assert _titles(_search(tool_adapter, text="tariffs")) == ["Synthetic Apple supplier update"]
    assert _titles(_search(tool_adapter, providers=["sec"], tickers=["AAPL"])) == [
        "Synthetic 8-K announcement"
    ]


def test_text_available_requires_a_stored_body(tool_adapter: QualToolAdapter) -> None:
    rows = {row.title: row for row in _search(tool_adapter, tickers=["AAPL"]).rows}
    assert rows["Synthetic Apple supplier update"].text_available is True
    assert rows["Synthetic 8-K announcement"].text_available is False  # fetched, but no file
    assert rows["Synthetic backfilled story"].text_available is False  # pending


def test_stored_text_from_a_paywalled_page_is_not_offered(tool_adapter: QualToolAdapter) -> None:
    row = _search(tool_adapter, tickers=["TSLA"]).rows[0]
    assert row.text_available is False


def test_cards_never_expose_storage_paths_or_body_status(tool_adapter: QualToolAdapter) -> None:
    envelope = tool_adapter.execute(
        "qual_search_news", {**OCTOBER, "tickers": ["AAPL"]}, "no-paths"
    )
    serialized = json.dumps(envelope.model_dump(mode="json"))
    assert ".jsonl" not in serialized
    assert "body_path" not in serialized
    assert "body_status" not in serialized
    assert "pending" not in serialized


def test_injected_text_stays_in_data_fields(tool_adapter: QualToolAdapter) -> None:
    envelope = tool_adapter.execute("qual_search_news", {**OCTOBER, "tickers": ["MSFT"]}, "inject")
    payload = envelope.model_dump(mode="json")
    assert payload["content_trust"] == "untrusted_external"
    assert "Ignore previous instructions" in payload["data"]["rows"][0]["title"]
    assert "Ignore previous" not in " ".join(payload["warnings"])
    assert "Ignore previous" not in payload["data"]["availability_note"]


def test_as_of_hides_later_ingestion_and_warns_before_history(
    tool_adapter: QualToolAdapter,
) -> None:
    arguments = {**OCTOBER, "tickers": ["AAPL"], "as_of": "2026-10-20"}
    envelope = tool_adapter.execute("qual_search_news", arguments, "as-of")
    assert "Synthetic backfilled story" not in [
        row.title
        for row in envelope.data.rows  # type: ignore[attr-defined]
    ]
    assert any("as_of" in warning for warning in envelope.warnings)  # type: ignore[attr-defined]


def test_truncation_is_reported_as_a_warning(tool_adapter: QualToolAdapter) -> None:
    envelope = tool_adapter.execute(
        "qual_search_news", {**OCTOBER, "tickers": ["AAPL"], "limit": 1}, "truncated"
    )
    assert envelope.data.truncated is True  # type: ignore[attr-defined]
    assert any("truncated" in warning for warning in envelope.warnings)  # type: ignore[attr-defined]


def test_links_add_up_across_versions(tool_adapter: QualToolAdapter) -> None:
    row = _search(tool_adapter, tickers=["AMD"]).rows[0]
    assert row.title == "Synthetic chip story, corrected"
    assert row.version_count == 2
    assert {ticker.ticker for ticker in row.tickers} == {"AMD", "NVDA"}


def test_wide_search_without_tickers_is_rejected_not_clamped(
    tool_adapter: QualToolAdapter,
) -> None:
    with pytest.raises(ToolInputError):
        tool_adapter.execute(
            "qual_search_news",
            {"start_date": "2026-01-01", "end_date": "2026-10-31", "text": "tariffs"},
            "wide",
        )
