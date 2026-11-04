"""Stable failures safe to cross the MCP transport boundary."""

from __future__ import annotations


class QualToolError(Exception):
    """Base error carrying only a stable public classification."""

    code = "internal_error"
    retryable = False
    public_message = "The tool call could not be completed."


class ToolInputError(QualToolError):
    """The caller supplied an invalid or out-of-policy request."""

    code = "invalid_request"
    public_message = "The tool arguments are invalid or outside the allowed bounds."


class ToolNotFoundError(QualToolError):
    """The requested public Data Interface entity was not found."""

    code = "not_found"
    public_message = "The requested qualitative data entity was not found."


class ToolForbiddenError(QualToolError):
    """The caller has no grant for this tool; never retryable."""

    code = "access_denied"
    public_message = "Access denied."


class ToolUnavailableError(QualToolError):
    """The Data Plane or isolated query worker is temporarily unavailable."""

    code = "unavailable"
    retryable = True
    public_message = "Qualitative data is temporarily unavailable."


class ToolTimeoutError(QualToolError):
    """The isolated query exceeded its server-side deadline."""

    code = "deadline_exceeded"
    retryable = True
    public_message = "The qualitative query exceeded its deadline."


class ToolOverloadedError(QualToolError):
    """The bounded query worker cannot accept more work."""

    code = "overloaded"
    retryable = True
    public_message = "The qualitative service is at capacity."


class ToolResourceLimitError(QualToolError):
    """A response or operation exceeded a deterministic resource budget."""

    code = "resource_limit"
    public_message = "The qualitative result exceeds the allowed resource budget."
