"""Behavior added by the FastMCP migration: hidden tools, Access denied and retry marking.

Unauthorized tools are hidden, an unauthorized call is refused as ``Access denied`` and marked not
retryable, and whether a client may retry is part of every error reply.
"""

from __future__ import annotations

from stram_qualitative_mcp.tool_registry import TOOL_SPECS
from tests.parity.harness import ALL_SCOPES, ParityClient

ERROR_META_KEY = "io.stram/error"
ACCESS_DENIED_TEXT = "Access denied."


def test_a_denied_call_says_access_denied_and_is_not_retryable(
    parity: ParityClient,
) -> None:
    token = parity.minter.mint("qual:discover")

    result = parity.call_tool("qual_search_news", {}, token).result

    assert result["isError"] is True
    assert result["content"][0]["text"] == ACCESS_DENIED_TEXT
    assert result["_meta"][ERROR_META_KEY] == {"code": "access_denied", "retryable": False}


def test_a_tool_the_caller_cannot_use_is_hidden_from_the_list(
    parity: ParityClient,
) -> None:
    token = parity.minter.mint("qual:discover")

    listed = parity.rpc("tools/list", token=token).result["tools"]

    expected = {spec.name for spec in TOOL_SPECS if spec.scope == "qual:discover"}
    assert {tool["name"] for tool in listed} == expected


def test_hiding_a_tool_does_not_change_the_error_for_calling_it(
    parity: ParityClient,
) -> None:
    narrow = parity.minter.mint("qual:discover")
    full = parity.minter.mint(" ".join(ALL_SCOPES))

    hidden = parity.call_tool("qual_search_news", {}, narrow).result
    unknown = parity.call_tool("qual_no_such_tool", {}, full).result

    assert hidden["content"][0]["text"] == ACCESS_DENIED_TEXT
    assert unknown["content"][0]["text"] != hidden["content"][0]["text"]


def test_an_invalid_request_is_marked_not_retryable(parity: ParityClient) -> None:
    token = parity.minter.mint("qual:discover")

    result = parity.call_tool("qual_describe_coverage", {"limit": "bad"}, token).result

    assert result["_meta"][ERROR_META_KEY]["retryable"] is False
