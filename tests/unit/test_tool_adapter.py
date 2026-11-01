from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from stram_data.data_interface import DataInterface, DataUnavailableError, NotFoundError

from stram_qualitative_mcp.errors import ToolInputError, ToolNotFoundError, ToolUnavailableError
from stram_qualitative_mcp.tool_adapter import QualToolAdapter, _warnings


def test_unknown_tool_and_undeclared_arguments_are_rejected(
    tool_adapter: QualToolAdapter,
) -> None:
    with pytest.raises(ToolInputError):
        tool_adapter.execute("qual_missing", {}, "unknown")
    with pytest.raises(ToolInputError):
        tool_adapter.execute("qual_describe_coverage", {"limit": 1}, "extra")


@pytest.mark.parametrize(
    ("raised", "expected"),
    [(NotFoundError, ToolNotFoundError), (DataUnavailableError, ToolUnavailableError)],
)
def test_data_interface_errors_map_to_safe_tool_errors(
    monkeypatch: pytest.MonkeyPatch,
    data_interface: DataInterface,
    raised: type[Exception],
    expected: type[Exception],
) -> None:
    adapter = QualToolAdapter(data_interface)

    def fail(_self: QualToolAdapter, _tool: str, _request: BaseModel) -> BaseModel:
        raise raised("private detail")

    monkeypatch.setattr(QualToolAdapter, "_dispatch", fail)
    with pytest.raises(expected) as caught:
        adapter.execute("qual_describe_coverage", {}, "mapped")
    assert "private detail" not in str(caught.value)


def test_warnings_report_truncation_and_availability_once() -> None:
    availability = SimpleNamespace(hindsight_only=True, warnings=("late", "late"), uncovered=True)
    data = SimpleNamespace(truncated=True, availability=availability)
    assert _warnings(data) == (  # type: ignore[arg-type]
        "Result is truncated; narrow the date range or filters.",
        "Result uses ex_post availability and is hindsight-only.",
        "late",
        "Some rows are outside covered availability policies.",
    )
