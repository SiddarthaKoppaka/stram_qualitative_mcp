from __future__ import annotations

import pytest
from pydantic import ValidationError

from stram_qualitative_mcp.tool_models import (
    ArticleInput,
    EmptyInput,
    FilingsInput,
    NewsSearchInput,
    TimelineInput,
)

OCTOBER = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


def test_tool_inputs_reject_undeclared_fields() -> None:
    with pytest.raises(ValidationError):
        EmptyInput.model_validate({"limit": 1})


@pytest.mark.parametrize(
    "payload",
    [
        {**OCTOBER},
        {**OCTOBER, "tickers": ["AAPL"], "limit": 101},
        {**OCTOBER, "tickers": [f"T{i}" for i in range(11)]},
        {**OCTOBER, "tickers": ["aapl; drop"]},
        {**OCTOBER, "text": "x"},
        {**OCTOBER, "text": "x" * 101},
        {**OCTOBER, "providers": ["ir"]},
        {**OCTOBER, "tickers": ["AAPL"], "min_confidence": 1.5},
        {"start_date": "2026-10-31", "end_date": "2026-10-01", "tickers": ["AAPL"]},
        {"start_date": "2020-01-01", "end_date": "2026-10-31", "tickers": ["AAPL"]},
        {"start_date": "2026-01-01", "end_date": "2026-10-31", "text": "tariffs"},
        {"start_date": "2026-01-01", "end_date": "2026-10-31", "providers": ["gdelt"]},
    ],
)
def test_search_bounds_are_rejected_not_clamped(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NewsSearchInput.model_validate(payload)


ARTICLE = "00000000-0000-0000-0000-000000000000"


@pytest.mark.parametrize(
    "payload",
    [
        {"article_id": ARTICLE, "max_chars": 8001},
        {"article_id": ARTICLE, "max_chars": 0},
        {"article_id": ARTICLE, "offset": -1},
        {"article_id": "../../etc/passwd"},
        {},
    ],
)
def test_article_bounds_are_rejected_not_clamped(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ArticleInput.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {**OCTOBER},
        {**OCTOBER, "tickers": []},
        {**OCTOBER, "tickers": ["AAPL"], "limit": 101},
        {**OCTOBER, "tickers": ["AAPL"], "forms": ["8-k; drop"]},
        {**OCTOBER, "tickers": ["AAPL"], "forms": [f"F{i}" for i in range(11)]},
        {"start_date": "2020-01-01", "end_date": "2026-10-31", "tickers": ["AAPL"]},
    ],
)
def test_filing_bounds_are_rejected_not_clamped(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FilingsInput.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {**OCTOBER},
        {**OCTOBER, "tickers": []},
        {**OCTOBER, "tickers": [f"T{i}" for i in range(6)]},
        {**OCTOBER, "tickers": ["AAPL"], "min_confidence": -0.1},
        {"start_date": "2025-01-01", "end_date": "2026-10-31", "tickers": ["AAPL"]},
    ],
)
def test_timeline_bounds_are_rejected_not_clamped(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TimelineInput.model_validate(payload)


def test_search_defaults_are_the_planned_ones() -> None:
    search = NewsSearchInput.model_validate({**OCTOBER, "tickers": ["AAPL"]})
    assert (search.limit, search.min_confidence, search.include_flagged) == (20, 0.6, False)
