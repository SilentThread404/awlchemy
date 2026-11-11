# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Awlchemy is an open-source (AGPL-3.0-or-later), local, single-user leathercraft app. It mirrors the user's own pattern sources (shared Google Drive folders and local folders) into `library/`, indexes them into SQLite, and serves a FastAPI + vanilla-JS web UI on `127.0.0.1:8765`. A Claude-powered "tutor" writes structured build guides per pattern and runs a streaming chat with web search. All AI runs through **Claude Code on the user's PC** (Claude Agent SDK, the user's own Claude sign-in), never an Anthropic API key.

## Commands

Uses `uv` (Python ≥ 3.13). Entry point is `awlchemy.cli:main`. `main.py` and `python -m awlchemy` exist only for backwards compatibility.

```
uv run awlchemy                       # = serve: start the app and open the browser
uv run awlchemy serve --no-browser --port 8765
uv run awlchemy source add|list|remove ...                   # manage pattern sources
uv run awlchemy sync [--dry-run] [--source NAME]            # mirror sources, then index
uv run awlchemy index                 # re-scan library/ into the DB
uv run awlchemy import <link|file> --collection NAME
```

Tests are pytest and fully offline. Run `uv run pytest` for all of them, or `uv run pytest tests/test_sources.py::test_folder_mirror_is_incremental` for a single test.
- `tests/conftest.py` points `AWLCHEMY_HOME` at a temp dir **before** `awlchemy` is imported (`config` reads it at import time), then builds a sample library with `make_fixtures.py`.
- `test_demo.py` builds the demo site and, when Node is installed, runs `tests/demo_smoke.mjs` against `demo/demo.js`.
- `test_app.py` drives the FastAPI app with `claude_code.run` replaced by `tests/fake_claude.py`. The fake asserts the session lockdown options (`dontAsk`, no setting sources, empty `ANTHROPIC_API_KEY`, no Bash/Write/Edit) and returns canned guide, video and chat messages. One of the video URLs is invented and must be filtered out.
- Manual UI demo with fake data: `make_fixtures.py <dir>`, then `tests/serve_fake.py` with `AWLCHEMY_HOME=<dir>`.
- CI (`.github/workflows/ci.yml`) runs pytest on Windows, macOS and Linux. It also fails if a PDF or a real-looking Drive folder ID (25 or more characters) is committed.

## Architecture

**Paths and state** (`config.py`): every path derives from `ROOT`, which is `AWLCHEMY_HOME` or the repo root. `library/<source name>/` holds one mirror per source and `library/Imported/` holds importer additions. `data/` holds `awlchemy.db`, `settings.json` (including the sources) and the generated files. Both directories are git-ignored and hold purchased content and personal data.

**Open-source hygiene:** the code must never contain a real pattern-folder link, seller name or pattern text. Sources exist only in `data/settings.json`. Fixtures and `awlchemy/knowledge/*.md` are original text, and users can add their own notes in `data/knowledge/`, which `tutor._knowledge()` also loads.

**Pipeline:** `sources` → `indexer` → `tutor`, with the disk as the source of truth.

- `sources.py` stores sources as `{name, kind: gdrive|folder, location, enabled}`, validated in `add_source` and managed through `/api/sources` and the `source` CLI command (`PUT /api/settings` ignores `sources`).
  - `sync_all()` mirrors each enabled source into `library/<name>/`. A `gdrive` source goes through `drive_sync.sync_folder`. A `folder` source goes through `mirror_folder`, which copies PDFs/ZIPs with `copy2` and skips files whose size and mtime are unchanged.
  - One failing source is recorded in `errors` and doesn't stop the others.
  - `remove_source(name, delete_files=True)` (the UI's "Delete them too", `source remove --delete-files`) also deletes `library/<name>/`; the caller then runs `indexer.purge_source`, which drops that source's rows and generated files but keeps (as `missing=1`) any pattern the user wrote notes, a guide, a status, a favourite or a chat for.
  - `config._migrate()` turns the legacy single `drive_folder` setting into a source, and drops sources of a kind that no longer exists (the removed `web` catalogue kind).

- `drive_sync.py` (also used by `importer.py`) scrapes `drive.google.com/embeddedfolderview?id=…`, which needs no Google auth or API key. It downloads through `drive.usercontent.google.com/download?...&confirm=t` and exports Google Docs as PDF. Incrementality comes from `<out>/.sync-manifest.json`, keyed by Drive **file ID**: a file is skipped if its ID is in the manifest and the local file exists. Files changed on Drive are not detected. An HTML response to a file download means Drive refused it (quota exceeded); that file is logged as failed and retried on the next run.
- `indexer.scan()` walks `library/**/*.pdf`. It re-processes a file only when its mtime or size changed, and marks rows `missing=1` instead of deleting them, which preserves the user's notes, guides and progress. Metadata comes from folder names: difficulty from `1. EASY`-style folders, `kind=guide` from names like readme/handbook/toolkit, and the collection from the parent folder. Text is converted with **pymupdf4llm**; PDFs under `MIN_TEXT_CHARS` count as image-only. `_dedupe_titles` numbers same-named variants but never overrides a title the user renamed. `_group_print_sizes` folds paper-size copies (`Sling Bag A4.pdf`, `… Letter`, `… A1`) into the folder's one other PDF by setting `print_of`, so the library shows one card and the pattern page offers the sizes (`print_versions`). Anything listing patterns must filter `print_of IS NULL`.
- `claude_code.py` is the only module that touches the Claude Agent SDK (`claude-agent-sdk`).
  - `options()` builds a locked-down session: only the requested tools (Read, WebSearch, WebFetch), `permission_mode="dontAsk"`, `setting_sources=[]` and `strict_mcp_config` (so none of the user's own CLAUDE.md, plugins, hooks or MCP servers load), `cwd=data/` plus `add_dirs=[library/]`, and `ANTHROPIC_API_KEY` blanked so the subscription sign-in is used.
  - A `PreToolUse` hook (`guard_tools`) is the prompt-injection fence. Read is only allowed under `library/`, `data/markdown`, `data/pages` and `data/chat_photos`, so `settings.json` and the DB are off-limits. WebFetch is only allowed to public http(s) hosts, never localhost or the LAN. The hook fails closed. If a feature needs Claude to read a new folder, add it to `_read_roots()`.
  - `run()` bridges the async SDK into sync generators by running `asyncio.run` in a worker thread with a queue. Job threads and Starlette's threadpool both call it, and the worker thread gives Windows the Proactor loop it needs for subprocesses.
  - It prefers the `claude` on PATH, otherwise the SDK's bundled CLI.
- `tutor.py` passes **file paths, not file contents**: Claude opens them itself with Read.
  - `pattern_context()` lists the Markdown conversion plus one JPEG per page, up to 40, rendered with PyMuPDF through `indexer.page_image`. Claude Code's own PDF reader can't see drawings on this machine because it needs poppler, so don't point Read at the raw PDF.
  - Guides and video searches use `output_format` JSON-schema structured output (`GUIDE_SCHEMA`, `VIDEO_SCHEMA`) and read `ResultMessage.structured_output`. Guides are stored as JSON in `patterns.guide` and rendered by `static/app.js`, so a schema change must be made in both places.
  - Video URLs are only kept if their YouTube ID appeared in a WebSearch tool result (`_collect` gathers these IDs).
  - Each chat is one Claude Code session (`chats.session_id`), resumed every turn. If resuming fails, a fresh session gets the context plus `_transcript()` of the stored messages.
  - Chat text streams from `StreamEvent` text deltas. Sources are the Markdown links found in the reply, which is why the system prompt asks for `[title](url)` links.

**Background work** (`jobs.py`): an in-process, in-memory thread runner that the UI polls through `/api/jobs/{id}`. Long steps call `jobs.report(log, phase=…, done=…, total=…)` for structured progress (a no-op outside a job); the library page's setup panel and the top-bar progress bar are drawn from it, so keep the field names in step with `renderSyncPanel` in `static/app.js`. Sync, import and index all share `exclusive_key="library"` in `app.py` so they never run concurrently. On startup, `app.lifespan` auto-syncs if sources exist and the last sync was more than 20 hours ago; otherwise it only re-indexes.

**Frontend:** `awlchemy/static/` (`index.html`, `app.js`, `style.css`) has no build step and is served directly by FastAPI. Every request and every picture or file URL in `app.js` goes through `request()` / `asset()`, never a bare `fetch` or a literal `/api/...` in an `src`/`href`, because the demo site swaps those two out.

**Demo site** (`demo/`): the same `app.js` running as a static page for GitHub Pages. `demo/demo.js` sets `window.AWLCHEMY_DEMO` (`fetch`, `asset`) and answers every `/api/*` call in memory with made-up patterns, SVG drawings, two pre-written guides and canned chat answers. `demo/build.py` (standard library only) assembles `index.html` + `style.css` + `app.js` + `demo.js` into `demo/_site/`, and `.github/workflows/demo.yml` deploys it. When an endpoint or its JSON shape changes, change `demo.js` too: `tests/test_demo.py` runs `tests/demo_smoke.mjs` under Node and fails if `app.js` calls a path the demo doesn't answer. The demo must stay invented: no real patterns, shops or video links.

## Conventions

- Default models are in `config.DEFAULT_SETTINGS["model"]` and `tutor.MODELS`. They are passed straight to Claude Code as `--model`.
- `config.load_settings()` drops keys that aren't in `DEFAULT_SETTINGS`, which is how the old `anthropic_api_key` disappears. The `session_id` column is added to old databases in `db.init()`, the place for small schema migrations.
- Settings are only persisted for keys present in `DEFAULT_SETTINGS`. Add new settings there first, with neutral defaults (no personal country, links or paths).
- `indexer.classify` sets `source` to the top folder under `library/`, which is the source name. The UI's Source filter relies on this.
- The printable pattern must always come from the untouched original PDF (`/files/{pid}/…`), never from a conversion.
- List queries must not `SELECT *` from `patterns`: `text` and `guide` hold whole documents. `app.LIST_COLUMNS` is the list shape.
- The tutor is called "the Awlchemist" in the UI copy (`static/app.js`) and in its persona in `tutor.system_prompt`. Keep the two consistent. Personal brand assets live in the git-ignored `branding/`; the README cover image is `docs/cover.jpeg`.
