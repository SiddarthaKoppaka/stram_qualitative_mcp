"""Thin delegation from validated tool contracts to the public Data Interface."""

from __future__ import annotations

import hashlib
import json

import stram_data
from pydantic import BaseModel, ValidationError
from stram_data.data_interface import (
    INTERFACE_VERSION,
    DataInterface,
    DataUnavailableError,
    InvalidQueryError,
    NewsQuery,
    NotFoundError,
)

from stram_qualitative_mcp.errors import ToolInputError, ToolNotFoundError, ToolUnavailableError
from stram_qualitative_mcp.tool_models import (
    HISTORY_INGESTED_FROM,
    CoverageData,
    NewsCard,
    NewsSearchData,
    NewsSearchInput,
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
            data = self._dispatch(tool_name, request)
            envelope = spec.output_model.model_validate(
                {
                    "tool_version": __version__,
                    "stram_data_version": stram_data.__version__,
                    "interface_version": INTERFACE_VERSION,
                    "policy_version": self._policy_version,
                    "request_id": request_id,
                    "data": data,
                    "warnings": _warnings(data),
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
            return CoverageData(policies=self._data.describe_availability_policies())
        if isinstance(request, NewsSearchInput):
            return self._search_news(request)
        raise ToolInputError

    def _search_news(self, request: NewsSearchInput) -> NewsSearchData:
        result = self._data.get_news(NewsQuery.model_validate(request.model_dump()))
        return NewsSearchData(
            rows=tuple(NewsCard.from_row(row) for row in result.rows),
            count=result.count,
            limit=result.limit,
            truncated=result.truncated,
            as_of=result.as_of,
            availability_note=result.availability_note,
        )


def _warnings(data: BaseModel) -> tuple[str, ...]:
    warnings: list[str] = []
    truncated = getattr(data, "truncated", False)
    if truncated:
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
