"""Check the staging service through its private URL with Keycloak client tokens.

    uv run python tools/m6_check.py --endpoint URL --issuer URL --smoke-secret-file PATH \
        [--text-secret-file PATH] [--discovery-secret-file PATH]

Client secrets are read from files and never printed, nor are tokens or article text. Each check
prints PASS or FAIL with a UTC time and the request ID where there is one. Any FAIL exits non-zero.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from stram_qualitative_mcp.errors import ToolForbiddenError

DATES = {"start_date": "2026-10-01", "end_date": "2026-10-31"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "m6-check", "version": "1"},
    },
}
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
UNKNOWN_ARTICLE = "00000000-0000-4000-8000-000000000000"
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_MISDIRECTED = 421
ERROR_META_KEY = "io.stram/error"
SMOKE = "stram-qual-smoke"
TEXT = "stram-qual-text"
DISCOVERY = "stram-qual-discovery-only"
CLIENTS = {
    SMOKE: {"qual:discover", "qual:read", "qual:analytics"},
    TEXT: {"qual:discover", "qual:text"},
    DISCOVERY: {"qual:discover"},
}
# A caller is shown only the tools its scopes allow.
VISIBLE_TOOLS = {
    SMOKE: {
        "qual_describe_coverage",
        "qual_search_news",
        "qual_get_filings",
        "qual_get_news_timeline",
    },
    TEXT: {"qual_describe_coverage", "qual_get_article"},
    DISCOVERY: {"qual_describe_coverage"},
}


class Report:
    """Prints one line per check and counts failures."""

    def __init__(self) -> None:
        """Start with no failures."""
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        """Print PASS or FAIL for one check, with the UTC time and an optional detail."""
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"{'PASS' if ok else 'FAIL'} {now} {name}" + (f" ({detail})" if detail else ""))
        self.failed += not ok


@dataclass(frozen=True)
class Caller:
    """An open MCP session for one Keycloak client."""

    label: str
    session: ClientSession


async def fetch_token(http: httpx2.AsyncClient, issuer: str, client_id: str, secret: str) -> str:
    """Return an access token for ``client_id`` holding exactly its expected scopes.

    Raises:
        SystemExit: If the realm refuses the request.
    """
    response = await http.post(
        f"{issuer}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": " ".join(sorted(CLIENTS[client_id])),
        },
    )
    if response.status_code != HTTP_OK:
        raise SystemExit(f"{client_id}: token request returned HTTP {response.status_code}")
    return str(response.json()["access_token"])


def claims(token: str) -> dict[str, Any]:
    """Decode a token's claims without verifying it; the service does the verifying."""
    payload = token.split(".")[1]
    decoded: dict[str, Any] = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    return decoded


def check_claims(report: Report, client_id: str, token: str, endpoint: str) -> None:
    """Check that the token is for this service and holds exactly the client's scopes."""
    values = claims(token)
    audience = values.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    granted = {scope for scope in str(values.get("scope", "")).split() if scope.startswith("qual:")}
    report.check(f"{client_id} token is for this service", endpoint in audiences)
    report.check(
        f"{client_id} token holds exactly its scopes",
        granted == CLIENTS[client_id],
        " ".join(sorted(granted)) or "no qual scopes",
    )


async def check_login_details(
    report: Report, http: httpx2.AsyncClient, endpoint: str, issuer: str
) -> None:
    """Check that a call without a token is refused and points to this service's login details."""
    response = await http.post(endpoint, json=INITIALIZE, headers=HEADERS)
    status = response.status_code
    report.check("call without a token is refused", status == HTTP_UNAUTHORIZED, f"HTTP {status}")
    found = re.search(r'resource_metadata="([^"]+)"', response.headers.get("www-authenticate", ""))
    if found is None:
        report.check("refusal points to login details", False, "no resource_metadata")
        return
    metadata = await http.get(found.group(1))
    body = metadata.json() if metadata.status_code == HTTP_OK else {}
    servers = [str(server).rstrip("/") for server in body.get("authorization_servers", [])]
    report.check(
        "login details name this service and the issuer",
        str(body.get("resource", "")).rstrip("/") == endpoint.rstrip("/")
        and issuer.rstrip("/") in servers,
        f"HTTP {metadata.status_code}",
    )


async def check_refusals(
    report: Report, http: httpx2.AsyncClient, endpoint: str, token: str
) -> None:
    """Check that bad tokens, a wrong Host and a foreign Origin are refused."""
    authorized = {**HEADERS, "Authorization": f"Bearer {token}"}
    cases = (
        ("malformed token is refused", {**HEADERS, "Authorization": "Bearer not-a-token"}),
        (
            "token with a broken signature is refused",
            {**HEADERS, "Authorization": f"Bearer {token[: token.rindex('.') + 1]}AAAA"},
        ),
        ("wrong Host is refused", {**authorized, "Host": "wrong.invalid"}),
        ("foreign Origin is refused", {**authorized, "Origin": "https://wrong.invalid"}),
    )
    expected = (HTTP_UNAUTHORIZED, HTTP_UNAUTHORIZED, HTTP_MISDIRECTED, HTTP_FORBIDDEN)
    for (name, headers), status in zip(cases, expected, strict=True):
        response = await http.post(endpoint, json=INITIALIZE, headers=headers)
        report.check(name, response.status_code == status, f"HTTP {response.status_code}")


@asynccontextmanager
async def session(endpoint: str, token: str) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP session that sends ``token``."""
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30) as http,
        streamable_http_client(endpoint, http_client=http, terminate_on_close=False) as streams,
        ClientSession(streams[0], streams[1]) as mcp_session,
    ):
        await mcp_session.initialize()
        yield mcp_session


async def check_listing(report: Report, caller: Caller, client_id: str) -> None:
    """Check that the caller is shown exactly the tools its scopes allow."""
    listed = {tool.name for tool in (await caller.session.list_tools()).tools}
    wanted = VISIBLE_TOOLS[client_id]
    report.check(f"{caller.label}: lists only its tools", listed == wanted, f"{len(listed)} listed")


async def expect_result(
    report: Report, caller: Caller, tool: str, arguments: dict[str, object]
) -> dict[str, Any]:
    """Check that a call succeeds, and return its data."""
    result = await caller.session.call_tool(tool, arguments)
    content = result.structured_content or {}
    detail = f"request {content['request_id']}" if "request_id" in content else "error"
    report.check(f"{caller.label}: {tool} succeeds", not result.is_error, detail)
    data: dict[str, Any] = content.get("data", {})
    return data


async def expect_denied(
    report: Report, caller: Caller, tool: str, arguments: dict[str, object]
) -> None:
    """Check that a call is refused with the fixed denial, marked as not worth retrying."""
    result = await caller.session.call_tool(tool, arguments)
    text = " ".join(getattr(item, "text", "") for item in result.content)
    error = (getattr(result, "meta", None) or {}).get(ERROR_META_KEY) or {}
    denied = (
        result.is_error
        and text == ToolForbiddenError().caller_text
        and error.get("code") == ToolForbiddenError.code
        and error.get("category") == ToolForbiddenError.category
        and error.get("retryable") is False
    )
    report.check(f"{caller.label}: {tool} is refused", denied, text or "no error")


async def check_smoke(report: Report, endpoint: str, token: str, search: dict[str, object]) -> str:
    """Run the read-scope client through its tools; return an article ID for the text client."""
    async with session(endpoint, token) as mcp_session:
        caller = Caller("smoke", mcp_session)
        await check_listing(report, caller, SMOKE)
        await expect_result(report, caller, "qual_describe_coverage", {})
        found = await expect_result(report, caller, "qual_search_news", search)
        await expect_result(report, caller, "qual_get_filings", search)
        await expect_result(report, caller, "qual_get_news_timeline", search)
        rows = found.get("rows", [])
        held = next((row for row in rows if row["text_available"]), rows[0] if rows else None)
        article_id = str(held["article_id"]) if held else UNKNOWN_ARTICLE
        await expect_denied(report, caller, "qual_get_article", {"article_id": article_id})
    return article_id


async def check_text(
    report: Report, endpoint: str, token: str, search: dict[str, object], article_id: str
) -> None:
    """Check that the text client reads articles and nothing else."""
    async with session(endpoint, token) as mcp_session:
        caller = Caller("text", mcp_session)
        await check_listing(report, caller, TEXT)
        article = await expect_result(
            report, caller, "qual_get_article", {"article_id": article_id}
        )
        if article:
            held_text = article["text_available"]
            print(f"     text available: {held_text}, {article['total_chars']} chars")
        await expect_denied(report, caller, "qual_search_news", search)


async def check_discovery(
    report: Report, endpoint: str, token: str, search: dict[str, object]
) -> None:
    """Check that the discovery-only client can call coverage and nothing else."""
    async with session(endpoint, token) as mcp_session:
        caller = Caller("discovery-only", mcp_session)
        await check_listing(report, caller, DISCOVERY)
        await expect_result(report, caller, "qual_describe_coverage", {})
        await expect_denied(report, caller, "qual_search_news", search)
        await expect_denied(report, caller, "qual_get_news_timeline", search)


async def run(args: argparse.Namespace, secrets: dict[str, str]) -> int:
    """Run every check and return the process exit code."""
    report = Report()
    endpoint, issuer = args.endpoint.rstrip("/"), args.issuer.rstrip("/")
    search: dict[str, object] = {**DATES, "tickers": [args.ticker]}
    async with httpx2.AsyncClient(timeout=30) as http:
        tokens = {
            client_id: await fetch_token(http, issuer, client_id, secret)
            for client_id, secret in secrets.items()
        }
        for client_id, token in tokens.items():
            check_claims(report, client_id, token, endpoint)
        await check_login_details(report, http, endpoint, issuer)
        await check_refusals(report, http, endpoint, tokens[SMOKE])
    article_id = await check_smoke(report, endpoint, tokens[SMOKE], search)
    if TEXT in tokens:
        await check_text(report, endpoint, tokens[TEXT], search, article_id)
    if DISCOVERY in tokens:
        await check_discovery(report, endpoint, tokens[DISCOVERY], search)
    print(f"{report.failed} failed" if report.failed else "all checks passed")
    return 1 if report.failed else 0


def main() -> None:
    """Parse arguments, read the secret files, and run the checks."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--endpoint", required=True, help="the service URL, ending in /mcp")
    parser.add_argument("--issuer", required=True, help="the Keycloak realm URL")
    parser.add_argument("--smoke-secret-file", type=Path, required=True)
    parser.add_argument("--text-secret-file", type=Path)
    parser.add_argument("--discovery-secret-file", type=Path)
    parser.add_argument("--ticker", default="AAPL")
    args = parser.parse_args()
    files = {
        SMOKE: args.smoke_secret_file,
        TEXT: args.text_secret_file,
        DISCOVERY: args.discovery_secret_file,
    }
    secrets = {client: path.read_text().strip() for client, path in files.items() if path}
    raise SystemExit(asyncio.run(run(args, secrets)))


if __name__ == "__main__":
    main()
