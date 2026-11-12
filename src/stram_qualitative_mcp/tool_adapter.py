"""Thin delegation from validated tool contracts to the public Data Interface."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import UTC, datetime, timedelta

import stram_data
from pydantic import BaseModel, ValidationError
from stram_data.data_interface import (
    INTERFACE_VERSION,
    DataInterface,
    DataUnavailableError,
    InvalidQueryError,
    NewsFeedQuery,
    NewsQuery,
    NewsTimelineQuery,
    NotFoundError,
)

from stram_qualitative_mcp.clean_views import clean_article, clean_filings, clean_news_search
from stram_qualitative_mcp.errors import ToolInputError, ToolNotFoundError, ToolUnavailableError
from stram_qualitative_mcp.tool_models import (
    COVERAGE_LIMITATIONS,
    HISTORY_INGESTED_FROM,
    MAX_SPAN_DAYS,
    TONE_NOTE,
    ArticleData,
    ArticleInput,
    CoverageData,
    FeedCard,
    FilingCard,
    FilingsData,
    FilingsInput,
    NewsCard,
    NewsFeedData,
    NewsFeedInput,
    NewsSearchData,
    NewsSearchInput,
    TimelineData,
    TimelineInput,
    TimelineRow,
    text_available,
)
from stram_qualitative_mcp.tool_registry import TOOLS_BY_NAME
from stram_qualitative_mcp.version import __version__


class QualToolAdapter:
    """Execute reviewed tool calls without adding news logic."""

    def __init__(self, data: DataInterface) -> None:
        self._data = data
        descriptions = [
            item.model_dump(mode="json") for item in data.describe_availability_policies()
        ]
        encoded = json.dumps(descriptions, sort_keys=True, separators=(",", ":")).encode()
        self._policy_version = hashlib.sha256(encoded).hexdigest()[:16]

    @property
    def policy_version(self) -> str:
        return self._policy_version

    def execute(self, tool_name: str, arguments: object, request_id: str) -> BaseModel:
        spec = TOOLS_BY_NAME.get(tool_name)
        if spec is None:
            raise ToolInputError from None
        try:
            request = spec.input_model.model_validate(arguments)
            # The view selects the response shape only; the Data Interface never sees it.
            data = self._dispatch(tool_name, request)
            # Warnings come from the raw result, so both views carry the same ones.
            warnings = _warnings(data)
            if getattr(request, "view", "raw") == "clean":
                data = _clean(data, request)
            envelope = spec.output_model.model_validate(
                {
                    "tool_version": __version__,
                    "stram_data_version": stram_data.__version__,
                    "interface_version": INTERFACE_VERSION,
                    "policy_version": self._policy_version,
                    "request_id": request_id,
                    "data": data,
                    "warnings": warnings,
                }
            )
        except (ValidationError, InvalidQueryError) as error:
            raise ToolInputError from error
        except NotFoundError as error:
            raise ToolNotFoundError from error
        except DataUnavailableError as error:
            raise ToolUnavailableError from error
        return envelope

    def _dispatch(self, tool_name: str, request: BaseModel) -> BaseModel:
        if tool_name == "qual_describe_coverage":
            return self._coverage()
        if isinstance(request, NewsSearchInput):
            return self._search_news(request)
        if isinstance(request, FilingsInput):
            return self._filings(request)
        if isinstance(request, ArticleInput):
            return self._article(request)
        if isinstance(request, TimelineInput):
            return self._timeline(request)
        if isinstance(request, NewsFeedInput):
            return self._feed(request)
        raise ToolInputError

    def _feed(self, request: NewsFeedInput) -> NewsFeedData:
        result = self._data.get_news_feed(NewsFeedQuery.model_validate(request.model_dump()))
        return NewsFeedData(
            rows=tuple(FeedCard.from_row(row) for row in result.rows),
            count=result.count,
            limit=result.limit,
            truncated=result.truncated,
            next_cursor=result.next_cursor,
            settled_until=result.settled_until,
            availability_note=result.availability_note,
        )

    def _coverage(self) -> CoverageData:
        coverage = self._data.get_news_coverage()
        return CoverageData(
            providers=coverage.providers,
            tracked_tickers=coverage.tracked_tickers,
            missing_gdelt_slots=coverage.missing_gdelt_slots,
            missing_gdelt_slot_count=coverage.missing_gdelt_slot_count,
            gdelt_window_days=coverage.gdelt_window_days,
            limitations=COVERAGE_LIMITATIONS,
        )

    def _timeline(self, request: TimelineInput) -> TimelineData:
        rows = self._data.get_news_timeline(
            NewsTimelineQuery.model_validate(request.model_dump())
        ).rows
        return TimelineData(
            rows=tuple(
                TimelineRow(
                    ticker=row.ticker,
                    day=row.day,
                    articles=row.articles,
                    stories=row.stories,
                    gdelt_article_tone=row.mean_tone,
                    tone_articles=row.tone_articles,
                )
                for row in rows
            ),
            count=len(rows),
            tone_note=TONE_NOTE,
        )

    def _search_news(self, request: NewsSearchInput) -> NewsSearchData:
        result = self._data.get_news(NewsQuery.model_validate(request.model_dump(exclude={"view"})))
        return NewsSearchData(
            rows=tuple(NewsCard.from_row(row) for row in result.rows),
            count=result.count,
            limit=result.limit,
            truncated=result.truncated,
            as_of=result.as_of,
            availability_note=result.availability_note,
        )

    def _filings(self, request: FilingsInput) -> FilingsData:
        result = self._data.get_news(
            NewsQuery(
                start_date=request.start_date,
                end_date=request.end_date,
                tickers=request.tickers,
                providers=("sec",),
                forms=request.forms,
                limit=request.limit,
            )
        )
        return FilingsData(
            rows=tuple(FilingCard.from_row(row) for row in result.rows),
            count=result.count,
            limit=result.limit,
            truncated=result.truncated,
        )

    def _article(self, request: ArticleInput) -> ArticleData:
        stored = self._data.get_news_text(request.article_id)  # raises for an unknown article
        end = datetime.now(UTC).date() + timedelta(days=1)
        rows = self._data.get_news(
            NewsQuery(
                start_date=end - timedelta(days=MAX_SPAN_DAYS),
                end_date=end,
                article_ids=(request.article_id,),
                include_flagged=True,
                limit=1,
            )
        ).rows
        if not rows:
            raise ToolNotFoundError
        available = text_available(rows[0]) and stored.text is not None
        text = _strip_invisible(stored.text or "") if available else ""
        window = text[request.offset : request.offset + request.max_chars]
        return ArticleData(
            article=NewsCard.from_row(rows[0]),
            text_available=available,
            untrusted_text=window if available else None,
            offset=request.offset,
            total_chars=len(text),
            has_more=request.offset + request.max_chars < len(text),
        )


def _clean(data: BaseModel, request: BaseModel) -> BaseModel:
    """Reshape a raw result into its clean view; values are copied, never rewritten."""
    if isinstance(data, NewsSearchData) and isinstance(request, NewsSearchInput):
        return clean_news_search(data, request.min_confidence)
    if isinstance(data, FilingsData):
        return clean_filings(data)
    if isinstance(data, ArticleData):
        return clean_article(data)
    raise ToolInputError


def _strip_invisible(text: str) -> str:
    """Drop control and format characters. This reduces hidden text; it does not make text safe."""

    return "".join(
        character
        for character in text
        if character in "\n\t" or unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
    )


def _warnings(data: BaseModel) -> tuple[str, ...]:
    warnings: list[str] = []
    truncated = getattr(data, "truncated", False)
    if truncated and isinstance(data, NewsFeedData):
        warnings.append("More news is waiting; call again at once with next_cursor.")
    elif truncated:
        warnings.append("Result is truncated; narrow the date range or filters.")
    as_of = getattr(data, "as_of", None)
    if as_of is not None and as_of < HISTORY_INGESTED_FROM:
        warnings.append("as_of precedes the ingestion of history, so few items are visible.")
    availability = getattr(data, "availability", None)
    if availability is not None:
        if availability.hindsight_only:
            warnings.append("Result uses ex_post availability and is hindsight-only.")
        warnings.extend(availability.warnings)
        if availability.uncovered:
            warnings.append("Some rows are outside covered availability policies.")
    return tuple(dict.fromkeys(warnings))
