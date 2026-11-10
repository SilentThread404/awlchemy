"""The PreToolUse guard that keeps a prompt-injected session away from private files and local URLs."""
import asyncio

import pytest

from awlchemy import claude_code as cc
from awlchemy import config


def decide(tool, **tool_input):
    out = asyncio.run(cc.guard_tools({"tool_name": tool, "tool_input": tool_input}, None, {}))
    return out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")


@pytest.mark.parametrize("path", [
    config.LIBRARY_DIR / "Src" / "pattern.pdf",
    config.DATA_DIR / "markdown" / "1.md",
    config.DATA_DIR / "pages" / "1" / "0_1100.jpg",
    config.UPLOAD_DIR / "abc.jpg",
    "markdown/1.md",  # relative to the session's working folder, data/
])
def test_reads_inside_the_library_are_allowed(path):
    assert decide("Read", file_path=str(path)) == "allow"


@pytest.mark.parametrize("path", [
    config.SETTINGS_PATH,
    config.DB_PATH,
    "settings.json",
    config.LIBRARY_DIR / ".." / "data" / "settings.json",
    config.ROOT.parent / "elsewhere" / ".ssh" / "id_rsa",
    "",
])
def test_reads_of_private_files_are_denied(path):
    assert decide("Read", file_path=str(path)) == "deny"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8765/api/settings",
    "http://localhost:8765/api/sources",
    "http://[::1]/",
    "http://192.168.1.1/",
    "http://10.0.0.5/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://printer.local/",
    "file:///etc/passwd",
    "not a url",
])
def test_fetches_of_local_addresses_are_denied(url):
    assert decide("WebFetch", url=url) == "deny"


def test_public_fetches_and_other_tools_are_left_alone():
    assert decide("WebFetch", url="https://93.184.215.14/") == "allow"  # a public IP, no DNS needed
    assert decide("WebSearch", query="saddle stitch") == "allow"


def test_a_broken_check_fails_closed():
    out = asyncio.run(cc.guard_tools({"tool_name": "Read", "tool_input": {"file_path": 42}}, None, {}))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    out = asyncio.run(cc.guard_tools(None, None, {}))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
