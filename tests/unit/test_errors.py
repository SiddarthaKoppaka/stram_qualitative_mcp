from __future__ import annotations

import pytest

from stram_qualitative_mcp.errors import (
    MAX_RETRY_AFTER_SECONDS,
    ErrorCategory,
    QualToolError,
    ToolForbiddenError,
    ToolInputError,
    ToolNotFoundError,
    ToolOverloadedError,
    ToolResourceLimitError,
    ToolTimeoutError,
    ToolUnavailableError,
)

ALL_ERRORS = (
    QualToolError,
    ToolInputError,
    ToolNotFoundError,
    ToolForbiddenError,
    ToolUnavailableError,
    ToolTimeoutError,
    ToolOverloadedError,
    ToolResourceLimitError,
)
# The client policy in the Quant integration handoff branches on these categories.
QUANT_CATEGORIES = {
    "caller_error",
    "access_denied",
    "service_credentials",
    "data_plane_unavailable",
    "data_plane_error",
    "deadline",
    "capacity",
    "resource_limit",
    "internal",
}
EXPECTED = {
    ToolInputError: ("invalid_request", "caller_error", False),
    ToolNotFoundError: ("not_found", "caller_error", False),
    ToolForbiddenError: ("access_denied", "access_denied", False),
    ToolUnavailableError: ("unavailable", "data_plane_unavailable", True),
    ToolTimeoutError: ("deadline_exceeded", "deadline", True),
    ToolOverloadedError: ("overloaded", "capacity", True),
    ToolResourceLimitError: ("resource_limit", "resource_limit", False),
    QualToolError: ("internal_error", "internal", False),
}


def test_every_category_is_one_the_quant_client_policy_knows() -> None:
    assert {category.value for category in ErrorCategory} <= QUANT_CATEGORIES


@pytest.mark.parametrize("error_type", ALL_ERRORS)
def test_each_error_has_its_code_category_and_retry_marking(
    error_type: type[QualToolError],
) -> None:
    error = error_type()

    assert (error.code, error.category.value, error.retryable) == EXPECTED[error_type]


@pytest.mark.parametrize("error_type", ALL_ERRORS)
def test_public_details_carry_the_shared_fields(error_type: type[QualToolError]) -> None:
    details = error_type().public_details()

    assert {"code", "category", "retryable", "reason", "next_action"} <= set(details)
    assert all(isinstance(details[key], str) for key in ("reason", "next_action"))


@pytest.mark.parametrize("error_type", ALL_ERRORS)
def test_caller_text_states_what_why_and_next(error_type: type[QualToolError]) -> None:
    error = error_type()

    assert error.caller_text.startswith(error.public_message)
    assert f"Why: {error.reason}" in error.caller_text
    assert f"Next: {error.next_action}" in error.caller_text


def test_capacity_errors_suggest_a_wait() -> None:
    details = ToolOverloadedError().public_details()

    assert details["retry_after_seconds"] == ToolOverloadedError.retry_after_seconds
    assert "Wait at least" in ToolOverloadedError().caller_text


def test_a_caller_error_has_no_wait_hint() -> None:
    assert "retry_after_seconds" not in ToolInputError().public_details()


@pytest.mark.parametrize(
    ("requested", "expected"), [(0, 1), (-9, 1), (42, 42), (10_000, MAX_RETRY_AFTER_SECONDS)]
)
def test_retry_after_is_clamped(requested: int, expected: int) -> None:
    assert ToolUnavailableError(retry_after_seconds=requested).retry_after_seconds == expected


def test_reviewed_reason_and_next_action_replace_the_defaults() -> None:
    error = ToolInputError("end_date is before start_date.", next_action="Swap the dates.")

    assert error.public_details()["reason"] == "end_date is before start_date."
    assert error.public_details()["next_action"] == "Swap the dates."
