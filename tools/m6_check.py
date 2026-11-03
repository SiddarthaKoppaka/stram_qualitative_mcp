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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from stram_qualitative_mcp.errors import ToolForbiddenError

DATES = {"start_date": "2026-10-01", "end_date": "2026-10-31"}
TOOLS = {
    "qual_describe_coverage",
    "qual_search_news",
    "qual_get_filings",
    "qual_get_article",
    "qual_get_news_timeline",
}
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
CLIENTS = {
    "stram-qual-smoke": {"qual:discover", "qual:read", "qual:analytics"},
    "stram-qual-text": {"qual:discover", "qual:text"},
    "stram-qual-discovery-only": {"qual:discover"},
}


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"{'PASS' if ok else 'FAIL'} {now} {name}" + (f" ({detail})" if detail else ""))
        self.failed += not ok


async def fetch_token(
    http: httpx2.AsyncClient, issuer: str, client_id: str, secret: str, scope: str
) -> str:
    response = await http.post(
        f"{issuer}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": scope,
        },
    )
    if response.status_code != 200:
        raise SystemExit(f"{client_id}: token request returned HTTP {response.status_code}")
    return str(response.json()["access_token"])


def claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    decoded: dict[str, Any] = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    return decoded


def check_claims(
    report: Report, client_id: str, token: str, endpoint: str, scopes: set[str]
) -> None:
    values = claims(token)
    audience = values.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    granted = {scope for scope in str(values.get("scope", "")).split() if scope.startswith("qual:")}
    report.check(f"{client_id} token is for this service", endpoint in audiences)
    report.check(
        f"{client_id} token holds exactly its scopes",
        granted == scopes,
        " ".join(sorted(granted)) or "no qual scopes",
    )


async def check_http(
    report: Report, http: httpx2.AsyncClient, endpoint: str, issuer: str, token: str
) -> None:
    response = await http.post(endpoint, json=INITIALIZE, headers=HEADERS)
    report.check(
        "call without a token is refused",
        response.status_code == 401,
        f"HTTP {response.status_code}",
    )
    found = re.search(r'resource_metadata="([^"]+)"', response.headers.get("www-authenticate", ""))
    if found is None:
        report.check("refusal points to login details", False, "no resource_metadata")
    else:
        metadata = await http.get(found.group(1))
        body = metadata.json() if metadata.status_code == 200 else {}
        servers = [str(server).rstrip("/") for server in body.get("authorization_servers", [])]
        report.check(
            "login details name this service and the issuer",
            str(body.get("resource", "")).rstrip("/") == endpoint.rstrip("/")
            and issuer.rstrip("/") in servers,
            f"HTTP {metadata.status_code}",
        )
    bad_tokens = {
        "malformed token is refused": "not-a-token",
        "token with a broken signature is refused": token[: token.rindex(".") + 1] + "AAAA",
    }
    for name, value in bad_tokens.items():
        response = await http.post(
            endpoint, json=INITIALIZE, headers={**HEADERS, "Authorization": f"Bearer {value}"}
        )
        report.check(name, response.status_code == 401, f"HTTP {response.status_code}")
    authorized = {**HEADERS, "Authorization": f"Bearer {token}"}
    response = await http.post(
        endpoint, json=INITIALIZE, headers={**authorized, "Host": "wrong.invalid"}
    )
    report.check(
        "wrong Host is refused", response.status_code == 421, f"HTTP {response.status_code}"
    )
    response = await http.post(
        endpoint, json=INITIALIZE, headers={**authorized, "Origin": "https://wrong.invalid"}
    )
    report.check(
        "foreign Origin is refused", response.status_code == 403, f"HTTP {response.status_code}"
    )


@asynccontextmanager
async def session(endpoint: str, token: str) -> AsyncIterator[ClientSession]:
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30) as http,
        streamable_http_client(endpoint, http_client=http, terminate_on_close=False) as streams,
        ClientSession(streams[0], streams[1]) as mcp_session,
    ):
        await mcp_session.initialize()
        yield mcp_session


async def call(
    mcp_session: ClientSession, tool: str, arguments: dict[str, object]
) -> tuple[str, dict[str, Any]]:
    result = await mcp_session.call_tool(tool, arguments)
    if result.is_error:
        text = " ".join(getattr(item, "text", "") for item in result.content)
        return ("forbidden" if text == ToolForbiddenError.public_message else "error"), {}
    return "ok", result.structured_content or {}


async def expect(
    report: Report,
    mcp_session: ClientSession,
    label: str,
    tool: str,
    arguments: dict[str, object],
    wanted: str,
) -> dict[str, Any]:
    outcome, content = await call(mcp_session, tool, arguments)
    detail = f"request {content['request_id']}" if "request_id" in content else outcome
    verb = "succeeds" if wanted == "ok" else "is refused"
    report.check(f"{label}: {tool} {verb}", outcome == wanted, detail)
    data: dict[str, Any] = content.get("data", {})
    return data


async def run(args: argparse.Namespace, secrets: dict[str, str]) -> int:
    report = Report()
    endpoint, issuer = args.endpoint.rstrip("/"), args.issuer.rstrip("/")
    search: dict[str, object] = {**DATES, "tickers": [args.ticker]}
    tokens: dict[str, str] = {}
    async with httpx2.AsyncClient(timeout=30) as http:
        for client_id, secret in secrets.items():
            scopes = CLIENTS[client_id]
            tokens[client_id] = await fetch_token(
                http, issuer, client_id, secret, " ".join(sorted(scopes))
            )
            check_claims(report, client_id, tokens[client_id], endpoint, scopes)
        smoke = tokens["stram-qual-smoke"]
        await check_http(report, http, endpoint, issuer, smoke)
    text = tokens.get("stram-qual-text")
    discovery = tokens.get("stram-qual-discovery-only")

    async with session(endpoint, smoke) as mcp_session:
        listed = {tool.name for tool in (await mcp_session.list_tools()).tools}
        report.check("smoke: all five tools are listed", listed == TOOLS, f"{len(listed)} listed")
        await expect(report, mcp_session, "smoke", "qual_describe_coverage", {}, "ok")
        found = await expect(report, mcp_session, "smoke", "qual_search_news", search, "ok")
        await expect(report, mcp_session, "smoke", "qual_get_filings", search, "ok")
        await expect(report, mcp_session, "smoke", "qual_get_news_timeline", search, "ok")
        rows = found.get("rows", [])
        held = next((row for row in rows if row["text_available"]), rows[0] if rows else None)
        article_id = held["article_id"] if held else UNKNOWN_ARTICLE
        await expect(
            report,
            mcp_session,
            "smoke",
            "qual_get_article",
            {"article_id": article_id},
            "forbidden",
        )

    if text:
        async with session(endpoint, text) as mcp_session:
            article = await expect(
                report, mcp_session, "text", "qual_get_article", {"article_id": article_id}, "ok"
            )
            if article:
                held_text = article["text_available"]
                print(f"     text available: {held_text}, {article['total_chars']} chars")
            await expect(report, mcp_session, "text", "qual_search_news", search, "forbidden")
    if discovery:
        async with session(endpoint, discovery) as mcp_session:
            await expect(report, mcp_session, "discovery-only", "qual_describe_coverage", {}, "ok")
            await expect(
                report, mcp_session, "discovery-only", "qual_search_news", search, "forbidden"
            )
            await expect(
                report, mcp_session, "discovery-only", "qual_get_news_timeline", search, "forbidden"
            )

    print(f"{report.failed} failed" if report.failed else "all checks passed")
    return 1 if report.failed else 0


def main() -> None:
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
        "stram-qual-smoke": args.smoke_secret_file,
        "stram-qual-text": args.text_secret_file,
        "stram-qual-discovery-only": args.discovery_secret_file,
    }
    secrets = {client: path.read_text().strip() for client, path in files.items() if path}
    raise SystemExit(asyncio.run(run(args, secrets)))


if __name__ == "__main__":
    main()
