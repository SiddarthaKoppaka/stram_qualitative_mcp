"""HTTP-level audit and telemetry around the MCP endpoint, outside the protocol framework."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import uuid4

from opentelemetry import propagate
from opentelemetry.trace import SpanKind
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from stram_qualitative_mcp.audit import AuditEvent, AuditWriteError
from stram_qualitative_mcp.runtime import Runtime
from stram_qualitative_mcp.telemetry import correlation_ids
from stram_qualitative_mcp.tool_registry import TOOLS_BY_NAME

MAX_TOOL_NAME_LENGTH = 100
HTTP_UNAUTHORIZED = 401
HTTP_ERROR_FLOOR = 400
DENIAL_STATUSES = frozenset({HTTP_UNAUTHORIZED, 403, 421})
# Unauthenticated callers can cause these denials at will, and each audit record is a synchronous,
# hash-chained write. Past this many in a window, denials are counted instead of written one by one.
DENIALS_AUDITED_PER_WINDOW = 20
DENIAL_WINDOW_SECONDS = 60.0
SAMPLED_OUTCOME = "transport_denials_sampled"


class DenialSampler:
    """Admit the first ``per_window`` denials of each window for individual audit; count the rest.

    The count is handed back once, when the first denial of a later window arrives, so it can be
    written as one summary record. Memory and audit writes per window are constant.
    """

    def __init__(
        self,
        per_window: int = DENIALS_AUDITED_PER_WINDOW,
        window_seconds: float = DENIAL_WINDOW_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a sampler; ``clock`` is replaceable in tests."""
        self._per_window = per_window
        self._window = window_seconds
        self._clock = clock
        self._window_start = float("-inf")
        self._seen = 0
        self._suppressed = 0

    @property
    def window_seconds(self) -> float:
        """Length of one sampling window."""
        return self._window

    def admit(self) -> tuple[bool, int]:
        """Return (audit this denial individually, suppressed count to summarize first)."""
        now = self._clock()
        carried = 0
        if now - self._window_start >= self._window:
            carried, self._suppressed = self._suppressed, 0
            self._window_start, self._seen = now, 0
        self._seen += 1
        if self._seen <= self._per_window:
            return True, carried
        self._suppressed += 1
        return False, carried


class TransportDenialAuditMiddleware:
    """Audit HTTP auth/Host/Origin denials that occur before MCP dispatch."""

    def __init__(
        self, app: ASGIApp, runtime: Runtime, sampler: DenialSampler | None = None
    ) -> None:
        """Wrap ``app``, recording to ``runtime``."""
        self._app = app
        self._runtime = runtime
        self._sampler = sampler or DenialSampler()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI event."""
        if scope["type"] != "http" or scope.get("path") != "/mcp":
            await self._app(scope, receive, send)
            return
        started = time.monotonic()
        suppressed = False

        async def audited_send(message: Message) -> None:
            nonlocal suppressed
            if suppressed:
                return
            if message["type"] == "http.response.start" and message["status"] in DENIAL_STATUSES:
                status = int(message["status"])
                try:
                    self._audit_denial(scope, status, started)
                except (AuditWriteError, ValueError):
                    suppressed = True
                    response = JSONResponse({"error": "service_unavailable"}, status_code=503)
                    await response(scope, receive, send)
                    return
            await send(message)

        await self._app(scope, receive, audited_send)

    def _audit_denial(self, scope: Scope, status: int, started: float) -> None:
        audit_this, suppressed = self._sampler.admit()
        if suppressed:
            self._runtime.audit.append(
                AuditEvent(
                    request_id=str(uuid4()),
                    tool="mcp_request",
                    authorization_outcome="denied",
                    policy_version=self._runtime.worker.policy_version,
                    row_count=suppressed,
                    data_scope={"window_seconds": self._sampler.window_seconds},
                    duration_ms=0.0,
                    outcome=SAMPLED_OUTCOME,
                    image_digest=self._runtime.settings.image_digest,
                )
            )
        if audit_this:
            self._append_denial(scope, status, started)

    def _append_denial(self, scope: Scope, status: int, started: float) -> None:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        candidate = headers.get("mcp-name", "mcp_request")
        tool = (
            candidate
            if 0 < len(candidate) <= MAX_TOOL_NAME_LENGTH and candidate.isascii()
            else "mcp_request"
        )
        spec = TOOLS_BY_NAME.get(tool)
        outcome = "authentication_denied" if status == HTTP_UNAUTHORIZED else "transport_denied"
        self._runtime.audit.append(
            AuditEvent(
                request_id=str(uuid4()),
                tool=tool,
                schema_hash=spec.schema_hash() if spec else None,
                authorization_outcome="denied",
                required_scope=spec.scope if spec else None,
                policy_version=self._runtime.worker.policy_version,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome=outcome,
                error_class=f"HTTP{status}",
                image_digest=self._runtime.settings.image_digest,
            )
        )


class HttpTelemetryMiddleware:
    """Create one HTTP server span from W3C headers without trusting baggage as policy."""

    def __init__(self, app: ASGIApp, runtime: Runtime) -> None:
        """Wrap ``app``, recording to ``runtime``."""
        self._app = app
        self._runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI event."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started = time.monotonic()
        status_code = 500
        method = str(scope.get("method", "OTHER"))
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        parent = propagate.extract(headers)

        async def observed_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        with self._runtime.telemetry.start_span(
            "http.server.request",
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": method,
                "url.path": _route_path(scope),
            },
            context=parent,
        ):
            await self._app(scope, receive, observed_send)
            duration = time.monotonic() - started
            trace_id, span_id = correlation_ids()
            self._runtime.telemetry.http_result(method, status_code, duration)
            self._runtime.telemetry.events.emit(
                "http.completed",
                trace_id=trace_id,
                span_id=span_id,
                outcome="success" if status_code < HTTP_ERROR_FLOOR else "error",
                duration_ms=duration * 1000,
                status_code=status_code,
            )


def _route_path(scope: Scope) -> str:
    path = scope.get("path")
    return path if path in {"/mcp", "/health/live", "/health/ready"} else "unknown"
