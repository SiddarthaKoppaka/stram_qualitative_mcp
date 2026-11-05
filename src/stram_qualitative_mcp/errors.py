"""Stable failures safe to cross the MCP transport boundary.

Every failure carries the same caller-safe facts as the Quant MCP's errors, so one client policy
serves both services:

* ``code``: the stable machine name.
* ``category``: who or what failed (the caller, authorization, the news lake, a deadline, our
  capacity, a resource budget, or this service).
* ``reason``: one specific sentence on why it failed.
* ``next_action``: what the caller or operator should do, and whether retrying can ever help.

Reasons and next actions are fixed, reviewed text. They never contain exception text, paths,
SQL, stack traces, tokens or the submitted values.
"""

from __future__ import annotations

from enum import StrEnum

MAX_RETRY_AFTER_SECONDS = 300


class ErrorCategory(StrEnum):
    """Why a call failed, grouped by who can fix it.

    The values match the Quant MCP's categories. The news lake plays the Data Plane's role.
    """

    CALLER_ERROR = "caller_error"
    ACCESS_DENIED = "access_denied"
    DATA_PLANE_UNAVAILABLE = "data_plane_unavailable"
    DEADLINE = "deadline"
    CAPACITY = "capacity"
    RESOURCE_LIMIT = "resource_limit"
    INTERNAL = "internal"


class QualToolError(Exception):
    """Base error carrying only a stable public classification."""

    code = "internal_error"
    category = ErrorCategory.INTERNAL
    retryable = False
    public_message = "The tool call could not be completed."
    default_reason = "An unexpected internal failure occurred."
    default_next_action = "Do not retry. Report the request_id to the service operator."
    retry_after_seconds: int | None = None

    def __init__(
        self,
        reason: str | None = None,
        *,
        next_action: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        """Create the error.

        Args:
            reason: A reviewed sentence replacing the class default; never exception text.
            next_action: A reviewed sentence replacing the class default.
            retry_after_seconds: A wait hint, clamped to one second to five minutes.
        """
        super().__init__(self.code)
        self.reason = reason or self.default_reason
        self.next_action = next_action or self.default_next_action
        if retry_after_seconds is not None:
            self.retry_after_seconds = max(
                1, min(int(retry_after_seconds), MAX_RETRY_AFTER_SECONDS)
            )

    @property
    def caller_text(self) -> str:
        """The complete, safe, human-readable failure text shown to the caller."""
        retry = "Retryable." if self.retryable else "Not retryable."
        wait = (
            f" Wait at least {self.retry_after_seconds}s first."
            if self.retry_after_seconds is not None
            else ""
        )
        return f"{self.public_message} Why: {self.reason} {retry}{wait} Next: {self.next_action}"

    def public_details(self) -> dict[str, object]:
        """Structured twin of ``caller_text`` for clients that branch on fields."""
        details: dict[str, object] = {
            "code": self.code,
            "category": self.category.value,
            "retryable": self.retryable,
            "reason": self.reason,
            "next_action": self.next_action,
        }
        if self.retry_after_seconds is not None:
            details["retry_after_seconds"] = self.retry_after_seconds
        return details


class ToolInputError(QualToolError):
    """The caller supplied an invalid or out-of-policy request."""

    code = "invalid_request"
    category = ErrorCategory.CALLER_ERROR
    public_message = "The tool arguments are invalid or outside the allowed bounds."
    default_reason = "One or more arguments violate the tool's input schema."
    default_next_action = "Correct the arguments to match the tool schema and call again."


class ToolNotFoundError(QualToolError):
    """The requested public Data Interface entity was not found."""

    code = "not_found"
    category = ErrorCategory.CALLER_ERROR
    public_message = "The requested qualitative data entity was not found."
    default_reason = "No item with the given identifier exists in the news lake."
    default_next_action = "Check the identifier with qual_search_news; retrying cannot help."


class ToolForbiddenError(QualToolError):
    """The caller has no grant for this tool; never retryable."""

    code = "access_denied"
    category = ErrorCategory.ACCESS_DENIED
    public_message = "Access denied."
    default_reason = "The caller's token does not grant this tool."
    default_next_action = "Request the required scope from the identity administrator."


class ToolUnavailableError(QualToolError):
    """The news lake or the isolated query worker is temporarily unavailable."""

    code = "unavailable"
    category = ErrorCategory.DATA_PLANE_UNAVAILABLE
    retryable = True
    public_message = "Qualitative data is temporarily unavailable."
    default_reason = "The news lake or its query worker is not ready."
    default_next_action = "Retry with exponential backoff; if it persists, contact the operator."
    retry_after_seconds = 5


class ToolTimeoutError(QualToolError):
    """The isolated query exceeded its server-side deadline."""

    code = "deadline_exceeded"
    category = ErrorCategory.DEADLINE
    retryable = True
    public_message = "The qualitative query exceeded its deadline."
    default_reason = "The query did not finish within this tool's time limit."
    default_next_action = (
        "Retry once with a narrower date range, fewer tickers or a smaller limit; "
        "do not retry the identical request in a loop."
    )


class ToolOverloadedError(QualToolError):
    """The bounded query worker cannot accept more work, or the caller hit its rate limit."""

    code = "overloaded"
    category = ErrorCategory.CAPACITY
    retryable = True
    public_message = "The qualitative service is at capacity."
    default_reason = "A query is already running or the caller exceeded its rate limit."
    default_next_action = "Wait for the indicated delay, then retry with backoff."
    retry_after_seconds = 5


class ToolResourceLimitError(QualToolError):
    """A response or operation exceeded a deterministic resource budget."""

    code = "resource_limit"
    category = ErrorCategory.RESOURCE_LIMIT
    public_message = "The qualitative result exceeds the allowed resource budget."
    default_reason = "The result is larger than this service allows."
    default_next_action = "Do not retry unchanged. Reduce the limit, date range or text window."
