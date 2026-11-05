from __future__ import annotations

import pytest

from stram_qualitative_mcp.clean_views import line_category


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("AAPL", "ticker_symbol"),
        ("  BRK.B  ", "ticker_symbol"),
        ("NASDAQ - As of 4:00 PM EST", "quote_stamp"),
        ("Read More:", "read_next"),
        ("Related Stories", "read_next"),
        ("Our Methodology", "methodology"),
        ("This article was originally published by Example News.", "byline_footer"),
        ("Questions? Contact [email protected] today.", "contact_footer"),
        ("Companies discussed in this piece: Example Corp.", "companies_discussed"),
        ("Image source: Example Images", "photo_credit"),
    ],
)
def test_furniture_lines_get_their_category(line: str, expected: str) -> None:
    assert line_category(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "Apple",
        "AAPL shares rose after the report.",
        "Analysts said the deal would close as of next year.",
        "Read the full filing before deciding.",
        "The photographer said the image was staged.",
        "Investors can contact the company for details.",
    ],
)
def test_ordinary_lines_are_not_flagged(line: str) -> None:
    assert line_category(line) is None
