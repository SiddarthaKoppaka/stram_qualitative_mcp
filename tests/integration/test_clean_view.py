"""The clean view is lossless: every raw card can be rebuilt from it, and raw is untouched."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from pydantic import JsonValue

from stram_qualitative_mcp.errors import ToolInputError
from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_models import (
    CleanArticleData,
    CleanFilingsData,
    CleanNewsSearchData,
)
from tests.support.build_news_fixture import FURNITURE_TEXT, LONG_TEXT

SEARCH = {"start_date": "2026-10-01", "end_date": "2026-10-31", "tickers": ["AAPL", "IBM"]}
FILINGS = {"start_date": "2026-10-01", "end_date": "2026-10-31", "tickers": ["AAPL", "MSFT"]}
CASES = [
    ("qual_search_news", SEARCH),
    ("qual_get_filings", FILINGS),
    ("qual_get_article", {"article_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "furniture"))}),
]
# Parsed JSON payloads are indexed freely in assertions; the clean models validate their shape.
Payload = dict[str, Any]
Arguments = dict[str, JsonValue]


def _id(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _run(adapter: QualToolAdapter, tool: str, arguments: Arguments) -> Payload:
    result: Payload = adapter.execute(tool, arguments, "request").model_dump(mode="json")
    return result


def _clean(adapter: QualToolAdapter, tool: str, arguments: Arguments) -> Payload:
    data: Payload = _run(adapter, tool, {**arguments, "view": "clean"})["data"]
    return data


def _rebuild(clean: CleanNewsSearchData | CleanFilingsData) -> list[Payload]:
    cards = [dict(zip(clean.columns, row, strict=True)) for row in clean.rows]
    return [
        {
            **card,
            "tickers": [
                dict(zip(clean.ticker_columns, link, strict=True)) for link in card["tickers"]
            ],
        }
        for card in cards
    ]


def _furniture(adapter: QualToolAdapter, **arguments: JsonValue) -> CleanArticleData:
    return CleanArticleData.model_validate(
        _clean(adapter, "qual_get_article", {"article_id": _id("furniture"), **arguments})
    )


@pytest.mark.parametrize(("tool", "arguments"), CASES)
def test_raw_view_is_unchanged_when_requested_explicitly(
    tool_adapter: QualToolAdapter, tool: str, arguments: Arguments
) -> None:
    default = _run(tool_adapter, tool, arguments)
    explicit = _run(tool_adapter, tool, {**arguments, "view": "raw"})

    assert json.dumps(default, sort_keys=True) == json.dumps(explicit, sort_keys=True)
    assert "view" not in default["data"]


@pytest.mark.parametrize(("tool", "arguments"), CASES)
def test_clean_view_keeps_envelope_trust_and_warnings(
    tool_adapter: QualToolAdapter, tool: str, arguments: Arguments
) -> None:
    raw = _run(tool_adapter, tool, arguments)
    clean = _run(tool_adapter, tool, {**arguments, "view": "clean"})

    assert clean["data"]["view"] == "clean"
    assert clean["content_trust"] == "untrusted_external"
    assert {key: value for key, value in clean.items() if key not in {"data", "request_id"}} == {
        key: value for key, value in raw.items() if key not in {"data", "request_id"}
    }


def test_clean_search_rebuilds_every_raw_card(tool_adapter: QualToolAdapter) -> None:
    raw = _run(tool_adapter, "qual_search_news", SEARCH)["data"]
    clean = CleanNewsSearchData.model_validate(_clean(tool_adapter, "qual_search_news", SEARCH))

    assert _rebuild(clean) == raw["rows"]
    assert (clean.count, clean.limit, clean.truncated) == (
        raw["count"],
        raw["limit"],
        raw["truncated"],
    )
    assert clean.availability_note == raw["availability_note"]


def test_clean_search_counts_kept_links_under_the_confidence_filter(
    tool_adapter: QualToolAdapter,
) -> None:
    clean = CleanNewsSearchData.model_validate(_clean(tool_adapter, "qual_search_news", SEARCH))

    links = [link for card in _rebuild(clean) for link in card["tickers"]]

    assert (clean.min_confidence, clean.links_below_min_confidence) == (0.6, 1)
    assert {"ticker": "ORCL", "match_method": "name", "confidence": 0.3} in links


def test_an_empty_search_explains_itself(tool_adapter: QualToolAdapter) -> None:
    empty = {**SEARCH, "start_date": "2001-01-01", "end_date": "2001-01-31"}

    clean = CleanNewsSearchData.model_validate(_clean(tool_adapter, "qual_search_news", empty))

    assert clean.rows == ()
    assert clean.explanation is not None
    assert "No items matched" in clean.explanation
    assert "2026-10-30" in clean.explanation


def test_clean_filings_rebuild_every_raw_card(tool_adapter: QualToolAdapter) -> None:
    raw = _run(tool_adapter, "qual_get_filings", FILINGS)["data"]
    clean = CleanFilingsData.model_validate(_clean(tool_adapter, "qual_get_filings", FILINGS))

    assert _rebuild(clean) == raw["rows"]
    assert (clean.count, clean.truncated, clean.explanation) == (raw["count"], False, None)


def test_an_empty_filing_search_explains_itself(tool_adapter: QualToolAdapter) -> None:
    clean = CleanFilingsData.model_validate(
        _clean(tool_adapter, "qual_get_filings", {**FILINGS, "tickers": ["IBM"]})
    )

    assert clean.rows == ()
    assert clean.explanation is not None
    assert "No SEC filings" in clean.explanation


def test_clean_article_keeps_the_raw_text_and_card(tool_adapter: QualToolAdapter) -> None:
    arguments: Arguments = {"article_id": _id("furniture")}
    raw = _run(tool_adapter, "qual_get_article", arguments)["data"]
    clean = _clean(tool_adapter, "qual_get_article", arguments)

    assert {key: clean[key] for key in raw} == raw
    assert clean["untrusted_text"] == FURNITURE_TEXT


def test_clean_article_flags_furniture_lines_by_position(tool_adapter: QualToolAdapter) -> None:
    clean = _furniture(tool_adapter)

    flagged = {
        FURNITURE_TEXT[offset : offset + length]: category
        for offset, length, category in clean.flagged_lines
    }

    assert flagged == {
        "IBM": "ticker_symbol",
        "NYSE - As of 3:00 PM EST": "quote_stamp",
        "Read Next": "read_next",
        "Photo by Example Staff Photographer": "photo_credit",
        "This article was written by Example Writer.": "byline_footer",
        "Contact [email protected] with corrections.": "contact_footer",
    }


def test_flagged_offsets_count_from_the_start_of_the_text(tool_adapter: QualToolAdapter) -> None:
    start = FURNITURE_TEXT.index("Read Next")

    # Starting on the newline before the line shows it begins a line of the whole text.
    clean = _furniture(tool_adapter, offset=start - 1)

    assert clean.flagged_lines[0] == (start, len("Read Next"), "read_next")


def test_a_line_cut_by_the_slice_edge_is_not_flagged(tool_adapter: QualToolAdapter) -> None:
    clean = _furniture(tool_adapter, offset=FURNITURE_TEXT.index("Read Next") + 1, max_chars=8)

    assert clean.flagged_lines == ()


def test_ordinary_text_has_no_flagged_lines(tool_adapter: QualToolAdapter) -> None:
    clean = CleanArticleData.model_validate(
        _clean(tool_adapter, "qual_get_article", {"article_id": _id("held-text")})
    )

    assert clean.untrusted_text == LONG_TEXT[:4000]
    assert (clean.flagged_lines, clean.explanation) == ((), None)


def test_an_article_without_text_explains_itself(tool_adapter: QualToolAdapter) -> None:
    clean = CleanArticleData.model_validate(
        _clean(tool_adapter, "qual_get_article", {"article_id": _id("paywalled")})
    )

    assert (clean.text_available, clean.untrusted_text, clean.flagged_lines) == (False, None, ())
    assert clean.explanation is not None
    assert "No fetched full text" in clean.explanation


def test_an_offset_past_the_end_explains_itself(tool_adapter: QualToolAdapter) -> None:
    clean = _furniture(tool_adapter, offset=len(FURNITURE_TEXT))

    assert clean.untrusted_text == ""
    assert clean.explanation is not None
    assert "past the end" in clean.explanation


def test_an_unknown_view_is_rejected(tool_adapter: QualToolAdapter) -> None:
    with pytest.raises(ToolInputError):
        tool_adapter.execute("qual_search_news", {**SEARCH, "view": "pretty"}, "request")


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("qual_describe_coverage", {}),
        (
            "qual_get_news_timeline",
            {"start_date": "2026-10-01", "end_date": "2026-10-31", "tickers": ["AAPL"]},
        ),
    ],
)
def test_tools_without_a_clean_view_reject_the_option(
    tool_adapter: QualToolAdapter, tool: str, arguments: Arguments
) -> None:
    with pytest.raises(ToolInputError):
        tool_adapter.execute(tool, {**arguments, "view": "clean"}, "request")
