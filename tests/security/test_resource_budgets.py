from __future__ import annotations

import pytest
from pydantic import ValidationError

from stram_qualitative_mcp.tool_models import EmptyInput, NewsSearchInput

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


def test_search_defaults_are_the_planned_ones() -> None:
    search = NewsSearchInput.model_validate({**OCTOBER, "tickers": ["AAPL"]})
    assert (search.limit, search.min_confidence, search.include_flagged) == (20, 0.6, False)
