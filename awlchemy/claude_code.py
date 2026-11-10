"""Bridge to Claude Code on this computer, through the Claude Agent SDK.

Every AI feature runs as a headless Claude Code session that uses the Claude
account you're signed in with in Claude Code (`claude` → /login), so no
Anthropic API key is needed. Usage counts against that account's plan.

Sessions are locked down: only the tools a feature asks for (Read, WebSearch,
WebFetch), no Bash or file edits, none of your own Claude Code settings,
plugins, hooks or MCP servers, and the working directory is data/.
"""

from __future__ import annotations

import asyncio
import queue
import shutil
import threading
from pathlib import Path
from typing import Any, Iterator

import claude_agent_sdk as sdk

from . import config

# Re-exported so callers don't import the SDK themselves.
AssistantMessage = sdk.AssistantMessage
UserMessage = sdk.UserMessage
ResultMessage = sdk.ResultMessage
StreamEvent = sdk.StreamEvent
TextBlock = sdk.TextBlock
ToolUseBlock = sdk.ToolUseBlock
ToolResultBlock = sdk.ToolResultBlock

NOT_SIGNED_IN = ("Claude Code isn't signed in. Open a terminal, run `claude`, type /login and sign in "
                 "with your Claude account, then try again.")


class ClaudeCodeError(RuntimeError):
    pass


def cli_path() -> str | None:
    """Your own Claude Code install if it's on PATH, else None (the SDK then uses its bundled copy)."""
    return shutil.which("claude")


def info() -> dict:
    path = cli_path()
    bundled = Path(sdk.__file__).parent / "_bundled"
    return {"cli": path or ("bundled with the app" if bundled.exists() else None),
            "found": bool(path) or bundled.exists()}


def options(settings: dict, *, system: str, tools: list[str], schema: dict | None = None,
            resume: str | None = None, stream: bool = False, max_turns: int = 30) -> sdk.ClaudeAgentOptions:
    return sdk.ClaudeAgentOptions(
        cli_path=cli_path(),
        model=settings.get("model") or None,
        system_prompt=system,
        tools=tools,                 # the only built-in tools the session has
        allowed_tools=tools,         # ...and they run without asking
        permission_mode="dontAsk",   # anything else is refused, never prompted
        setting_sources=[],          # ignore the user's CLAUDE.md, hooks, plugins
        strict_mcp_config=True,      # ...and their MCP servers
        cwd=str(config.DATA_DIR),
        add_dirs=[str(config.LIBRARY_DIR)],
        env={"ANTHROPIC_API_KEY": ""},  # always use the Claude Code sign-in, never an API key
        output_format={"type": "json_schema", "schema": schema} if schema else None,
        resume=resume,
        include_partial_messages=stream,
        max_turns=max_turns,
    )


def run(prompt: str, opts: sdk.ClaudeAgentOptions) -> Iterator[Any]:
    """Run one Claude Code query and yield its messages, from synchronous code.

    The SDK is async and spawns a subprocess; it runs on its own event loop in a
    worker thread so it works from the job threads and from Starlette's
    threadpool alike (asyncio.run gives the Proactor loop Windows needs)."""
    q: queue.Queue = queue.Queue()
    done = object()

    async def main() -> None:
        async for msg in sdk.query(prompt=prompt, options=opts):
            q.put(msg)

    def worker() -> None:
        try:
            asyncio.run(main())
        except BaseException as ex:  # noqa: BLE001 - handed to the consumer
            q.put(ex)
        finally:
            q.put(done)

    threading.Thread(target=worker, daemon=True, name="claude-code").start()
    while (item := q.get()) is not done:
        if isinstance(item, BaseException):
            raise _translate(item) from item
        if isinstance(item, AssistantMessage) and item.error == "authentication_failed":
            raise ClaudeCodeError(NOT_SIGNED_IN)
        yield item


def result_error(res: ResultMessage | None) -> str | None:
    """A readable error for a failed run, or None if it succeeded."""
    if res is None:
        return "Claude Code stopped without an answer."
    if not res.is_error:
        return None
    text = " ".join([res.result or "", *(res.errors or [])]).strip()
    if "login" in text.lower() or "auth" in text.lower() or res.api_error_status == 401:
        return NOT_SIGNED_IN
    if res.subtype == "error_max_turns":
        return "Claude Code took too many steps and stopped. Try again."
    return f"Claude Code error: {text or res.subtype}"


def _translate(ex: BaseException) -> Exception:
    if isinstance(ex, sdk.CLINotFoundError):
        return ClaudeCodeError("Claude Code wasn't found. Install it from https://claude.com/claude-code "
                               "and sign in once by running `claude` in a terminal.")
    if isinstance(ex, sdk.ProcessError):
        err = (ex.stderr or str(ex)).strip()
        if "login" in err.lower() or "auth" in err.lower():
            return ClaudeCodeError(NOT_SIGNED_IN)
        return ClaudeCodeError(f"Claude Code failed: {err[-400:]}")
    if isinstance(ex, ClaudeCodeError):
        return ex
    return ClaudeCodeError(f"Claude Code failed: {ex}")


def check(settings: dict) -> dict:
    """Tiny round trip to confirm Claude Code runs and is signed in."""
    opts = options(settings, system="Reply with exactly: ok", tools=[], max_turns=1)
    res = None
    for msg in run("ping", opts):
        if isinstance(msg, ResultMessage):
            res = msg
    if err := result_error(res):
        raise ClaudeCodeError(err)
    return {"ok": True, "model": settings.get("model")}
