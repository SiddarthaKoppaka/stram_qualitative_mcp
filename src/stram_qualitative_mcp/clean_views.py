"""Reshape raw tool results into the lossless clean view.

Cards become one table: every card field is kept, serialized exactly as the raw view serializes it,
and only the repeated field names go. Article text is never rewritten; lines of the returned slice
that look like page furniture are flagged by position, so a reader can skip them and the raw text
stays the record. Nothing else is computed except counts of what is being returned.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence

from pydantic import BaseModel

from stram_qualitative_mcp.tool_models import (
    ArticleData,
    CleanArticleData,
    CleanFilingsData,
    CleanNewsSearchData,
    FilingCard,
    FilingsData,
    NewsCard,
    NewsSearchData,
    Row,
)

NEWS_COLUMNS = tuple(NewsCard.model_fields)
FILING_COLUMNS = tuple(FilingCard.model_fields)
TICKER_COLUMNS = ("ticker", "match_method", "confidence")
LINE_COLUMNS = ("offset", "length", "category")

# Whole-line shapes seen in fetched Finnhub article text (2026-11-04 sample of 30 articles, where
# they were 1.2% of characters). A line is flagged only if it matches completely.
# Patterns are strings so `re` caches them; `(?i)` marks the case-insensitive ones.
FLAGGED_LINE_PATTERNS = {
    "ticker_symbol": r"[A-Z]{1,5}(?:\.[A-Z])?",
    "quote_stamp": r"(?i)(?:NASDAQ|NYSE|AMEX)\W{0,3}.{0,20}\bAs of\b.{0,40}",
    "read_next": r"(?i)(?:Read Next|Read More|Related(?: Articles| Stories)?)\s*:?",
    "methodology": r"(?i)Our Methodology\b.*",
    "byline_footer": r"(?i)This article was (?:written|originally published|produced) by\b.*",
    "contact_footer": r"(?i)(?:.*\b)?Contact\b.{0,60}\[email protected\].*",
    "companies_discussed": r"(?i)Companies discussed\b.*",
    "photo_credit": r"(?i)(?:Photo|Image|Photograph)(?: credit| source)?\s*(?::|by)\s.{0,80}",
}

NO_NEWS = (
    "No items matched. Without as_of, this covers what is stored now; history was ingested from "
    "about 2026-10-30, so earlier periods hold less."
)
NO_FILINGS = "No SEC filings or announcements matched these tickers, forms and dates."
NO_TEXT = "No fetched full text is held for this article; the card's title and summary remain."
PAST_THE_END = "offset is at or past the end of the text."


def _table(cards: Iterable[BaseModel], columns: Sequence[str]) -> tuple[Row, ...]:
    """Pick ``columns`` from each card's raw JSON form, with ticker links as rows of their own."""
    rows = []
    for card in cards:
        item = card.model_dump(mode="json")
        item["tickers"] = [[link[name] for name in TICKER_COLUMNS] for link in item["tickers"]]
        rows.append(tuple(item[name] for name in columns))
    return tuple(rows)


def clean_news_search(data: NewsSearchData, min_confidence: float) -> CleanNewsSearchData:
    """Turn search cards into one table and count ticker links under the confidence filter.

    Args:
        data: The raw search result.
        min_confidence: The request's filter, which a card meets through any one of its links.
    """
    return CleanNewsSearchData(
        view="clean",
        columns=NEWS_COLUMNS,
        ticker_columns=TICKER_COLUMNS,
        rows=_table(data.rows, NEWS_COLUMNS),
        count=data.count,
        limit=data.limit,
        truncated=data.truncated,
        as_of=data.as_of,
        availability_note=data.availability_note,
        min_confidence=min_confidence,
        links_below_min_confidence=sum(
            link.confidence < min_confidence for card in data.rows for link in card.tickers
        ),
        explanation=None if data.rows else NO_NEWS,
    )


def clean_filings(data: FilingsData) -> CleanFilingsData:
    """Turn filing cards into one table."""
    return CleanFilingsData(
        view="clean",
        columns=FILING_COLUMNS,
        ticker_columns=TICKER_COLUMNS,
        rows=_table(data.rows, FILING_COLUMNS),
        count=data.count,
        limit=data.limit,
        truncated=data.truncated,
        explanation=None if data.rows else NO_FILINGS,
    )


def clean_article(data: ArticleData) -> CleanArticleData:
    """Keep the raw article and flag the furniture lines of its text slice."""
    return CleanArticleData(
        view="clean",
        article=data.article,
        text_available=data.text_available,
        untrusted_text=data.untrusted_text,
        offset=data.offset,
        total_chars=data.total_chars,
        has_more=data.has_more,
        line_columns=LINE_COLUMNS,
        flagged_lines=tuple(flagged_lines(data)),
        explanation=_article_explanation(data),
    )


def _article_explanation(data: ArticleData) -> str | None:
    if not data.text_available:
        return NO_TEXT
    return PAST_THE_END if data.offset >= data.total_chars else None


def flagged_lines(data: ArticleData) -> Iterator[Row]:
    """Yield ``(offset, length, category)`` for each complete flagged line in the slice.

    A line cut by either edge of the slice is not judged, because its missing part could change
    what it is. Offsets count from the start of the whole text, like the request's ``offset``.
    """
    text = data.untrusted_text or ""
    position = 0
    for line in text.split("\n"):
        start, position = position, position + len(line) + 1
        cut_at_start = start == 0 and data.offset > 0
        cut_at_end = position > len(text) and data.has_more
        category = None if cut_at_start or cut_at_end else line_category(line)
        if category is not None:
            yield (data.offset + start, len(line), category)


def line_category(line: str) -> str | None:
    """Return the furniture category a whole line matches, or None for ordinary text."""
    stripped = line.strip()
    if not stripped:
        return None
    for category, pattern in FLAGGED_LINE_PATTERNS.items():
        if re.fullmatch(pattern, stripped):
            return category
    return None
