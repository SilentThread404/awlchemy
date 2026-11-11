"""The Awlchemist: the Claude-powered leathercraft teacher inside Awlchemy.

* generate_guide(): reads a pattern (the real PDF pages, so diagrams count) and
  produces a structured beginner guide: leather per part, tools, hardware,
  every step re-explained, and where the pattern is vague.
* chat_stream(): a streaming conversation, optionally about one pattern, with
  web search for buying materials or finding technique videos, and photos of
  your work for feedback.

All of it runs through Claude Code on this computer (see claude_code.py): Claude
opens the PDFs, Markdown and photos itself with the Read tool, so prompts carry
file paths rather than file contents.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from . import claude_code as cc
from . import config, db, indexer

IMAGE_PAGES_MAX = 40     # pages rendered as images for Claude to look at
PAGE_IMAGE_WIDTH = 1100

MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]


TutorError = cc.ClaudeCodeError


# --------------------------------------------------------------------------- setup

def _knowledge() -> str:
    parts = []
    files = sorted(config.KNOWLEDGE_DIR.glob("*.md")) + sorted(config.USER_KNOWLEDGE_DIR.glob("*.md"))
    for f in files:
        text = f.read_text(encoding="utf-8")
        if text.startswith("---"):
            text = text.split("---", 2)[-1]
        parts.append(text.strip())
    return "\n\n".join(parts)


def system_prompt(settings: dict) -> str:
    toolkit = ", ".join(settings.get("toolkit") or []) or "nothing recorded yet"
    country = settings.get("country") or "unknown (ask before recommending shops)"
    currency = settings.get("currency") or "local currency"
    units = settings.get("units") or "metric"
    about = settings.get("about_me") or ""
    text = f"""You are the Awlchemist, the workshop mentor inside Awlchemy, a personal leathercraft app.
Your student works from a library of printable PDF patterns and wants to learn the craft properly.
The name is a pun on awl + alchemy: you help turn a flat pattern and a piece of hide into something finished.

# Your voice
- Warm, calm and plain-spoken, like an experienced maker at the next bench. Encouraging, never gushing.
- A light touch of craft humour is fine, but instructions are always literal and exact.
- Call yourself "the Awlchemist" only if asked who you are; otherwise just teach.

# The student
- Experience: {settings.get("experience") or "complete beginner"}
- Tools they own: {toolkit}
- Lives in: {country} (prices in {currency}; prefer shops that ship there)
- Units: {units} first, imperial in brackets where useful
{f"- Also: {about}" if about else ""}

# How to teach
- Be a patient workshop mentor. Explain *why* as well as *how*, with exact measurements.
- Pattern instructions are often terse or ambiguous. When they are, say so plainly, then fill the gap
  with standard practice and mark it as your interpretation.
- Flag irreversible moments (cutting, punching, gluing, dyeing) and suggest a test on scrap first.
- Prefer what the student already owns; when something is missing, offer the cheapest sensible
  substitute before suggesting a purchase.
- Safety where it matters: blade handling, cutting away from the body, ventilation for contact cement and dyes.
- When the student asks where to buy leather/tools/hardware, what something costs, or for a video showing
  a technique, use WebSearch. Give real links only from search results, never invented URLs or prices,
  and write every source as a Markdown link [title](url).
- Pattern PDFs, their text conversions and the student's photos are files on this computer: open them
  with the Read tool when you need them. Never claim to have seen a page you haven't read.
- If the student shares a photo of their work, give specific, kind, actionable feedback.
- The printable pattern itself always comes from the original PDF; remind them to print at 100% /
  "Actual size" and check the calibration square when printing comes up.
- Format with short Markdown sections and lists. Keep answers focused on what was asked.

# Reference knowledge
{_knowledge()}
"""
    return text


# --------------------------------------------------------------------------- pattern context

def _pattern_row(pid: int) -> dict:
    with db.session() as conn:
        row = conn.execute("SELECT * FROM patterns WHERE id=?", (pid,)).fetchone()
    if not row:
        raise TutorError("Pattern not found")
    return dict(row)


def pattern_context(p: dict) -> str:
    """Tells Claude where the pattern's content lives so it can open it with Read: the Markdown
    text conversion plus one rendered JPEG per page (Claude Code's own PDF reader needs extra
    software to see drawings, so pages are rendered here with PyMuPDF and cached in data/pages)."""
    path = config.LIBRARY_DIR / p["rel_path"]
    if not path.exists():
        raise TutorError("The PDF for this pattern is missing from the library folder.")
    pages = p.get("pages") or 0
    lines = [f"Pattern: {p['title']}"
             + (f" (collection: {p['collection']})" if p.get("collection") else "")
             + (f", labelled difficulty: {p['difficulty']}" if p.get("difficulty") else "")
             + f", {pages} page(s)."]
    md = indexer.markdown_path(p["id"])
    if md.exists() and (p.get("text") or "").strip():
        lines.append(f"Text of the PDF (Markdown conversion, without the drawings): {md}")
    else:
        lines.append("The PDF has (almost) no text: everything is in the page images.")
    imgs = [indexer.page_image(p["id"], p["rel_path"], i, PAGE_IMAGE_WIDTH) for i in range(min(pages, IMAGE_PAGES_MAX))]
    if imgs:
        lines.append("Page images (the drawings, parts and measurements are here):\n"
                     + "\n".join(f"- page {i + 1}: {f}" for i, f in enumerate(imgs)))
    if pages > IMAGE_PAGES_MAX:
        lines.append(f"Only the first {IMAGE_PAGES_MAX} pages are rendered; the text conversion covers the rest.")
    with db.session() as conn:
        prints = [v for v in indexer.print_versions(conn, p["id"]) if v["id"] != p["id"]]
    if prints:
        lines.append("The pattern pieces also come as separate print files, which the user prints from the app: "
                     + ", ".join(f"{v['paper']} ({v['pages']} page(s))" for v in prints)
                     + ". Point to these for printing instead of describing how to print the pieces from this file.")
    return "\n".join(lines)


def _collect(prompt: str, opts, log=None) -> tuple[cc.ResultMessage, set[str]]:
    """Run a non-streaming query; returns the result and every YouTube id seen in tool results."""
    res, seen_ids = None, set()
    for msg in cc.run(prompt, opts):
        if isinstance(msg, cc.AssistantMessage) and log:
            for b in msg.content:
                if isinstance(b, cc.ToolUseBlock):
                    if b.name == "Read":
                        pages = b.input.get("pages")
                        log(f"Reading {Path(b.input.get('file_path', '')).name}"
                            + (f" (pages {pages})" if pages else "") + "…")
                    elif b.name == "WebSearch":
                        log(f"Searching: {b.input.get('query', '')}…")
        elif isinstance(msg, cc.UserMessage):
            blob = json.dumps(msg.tool_use_result or "", default=str)
            if isinstance(msg.content, list):
                blob += json.dumps([b.content for b in msg.content if isinstance(b, cc.ToolResultBlock)], default=str)
            seen_ids.update(YT_ID_RE.findall(blob))
        elif isinstance(msg, cc.ResultMessage):
            res = msg
    if err := cc.result_error(res):
        raise TutorError(err)
    return res, seen_ids


# --------------------------------------------------------------------------- guide

_str = {"type": "string"}
_strs = {"type": "array", "items": {"type": "string"}}

GUIDE_SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {**_str, "description": "2-3 sentences: what this makes and what makes it nice."},
            "difficulty": {"type": "string", "enum": ["beginner", "advanced beginner", "intermediate", "advanced"]},
            "difficulty_reason": _str,
            "time_estimate": {**_str, "description": "Realistic time for a beginner, e.g. '3-4 hours over 2 sessions'."},
            "finished_size": _str,
            "skills_learned": _strs,
            "before_you_start": {**_str, "description": "Printing/scale checks and preparation, in Markdown."},
            "leather": {
                "type": "array",
                "description": "One entry per part or group of parts that share a leather.",
                "items": {"type": "object", "properties": {
                    "parts": _str,
                    "leather": {**_str, "description": "e.g. 'Vegetable-tanned cowhide (full grain)'"},
                    "thickness_mm": _str,
                    "thickness_oz": _str,
                    "why": _str,
                    "alternative": {**_str, "description": "Cheaper or easier-to-find option for a beginner."},
                }, "required": ["parts", "leather", "thickness_mm", "why"]},
            },
            "leather_amount": {**_str, "description": "How much leather to buy, with a margin for mistakes."},
            "hardware": {"type": "array", "items": {"type": "object", "properties": {
                "item": _str, "quantity": _str, "size": _str, "notes": _str}, "required": ["item"]}},
            "consumables": {"type": "array", "description": "Thread, glue, edge products, dye, finish.",
                            "items": {"type": "object", "properties": {
                                "item": _str, "spec": _str, "notes": _str}, "required": ["item"]}},
            "tools": {"type": "array", "items": {"type": "object", "properties": {
                "name": _str,
                "purpose": _str,
                "essential": {"type": "boolean"},
                "substitute": {**_str, "description": "What to use if you don't have it."},
            }, "required": ["name", "purpose", "essential"]}},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "title": _str,
                "pattern_says": {**_str, "description": "Short faithful paraphrase of the original instruction."},
                "how_to": {**_str, "description": "Detailed beginner explanation in Markdown: exactly what to do and why."},
                "techniques": {**_strs, "description": (
                    "Hands-on techniques in this step that a video could demonstrate, using short standard names "
                    "so they're consistent across patterns: e.g. 'saddle stitch', 'edge beveling', 'edge burnishing', "
                    "'punching stitch holes', 'setting rivets', 'setting line 24 snaps', 'skiving', 'gluing with contact "
                    "cement', 'cutting leather with a knife', 'dyeing leather', 'wet molding'. Empty for steps like printing.")},
                "tools_used": _strs,
                "tips": _strs,
                "watch_out": {**_strs, "description": "Common mistakes and irreversible moments."},
            }, "required": ["title", "how_to"]}},
            "unclear_points": {**_strs, "description": "Where the pattern is vague, missing info or inconsistent, and how you resolved it."},
            "practice_first": {**_str, "description": "A short scrap exercise to do before starting."},
            "finishing_and_care": _str,
        },
        "required": ["summary", "difficulty", "time_estimate", "leather", "tools", "steps"],
}


def generate_guide(pid: int, log=print) -> dict:
    settings = config.load_settings()
    p = _pattern_row(pid)
    log(f"Asking Claude Code ({settings['model']}) to read '{p['title']}'…")
    prompt = pattern_context(p) + "\n\n" + (
        "Create the complete build guide for this pattern and return it as the structured output. "
        "Open the text and every page image with Read, including the diagrams and parts list. Recommend leather per part "
        "(type, tannage, thickness in mm and oz) and say why; list every tool, hardware item and consumable. "
        "Rewrite each step so a beginner can follow it without guessing, keeping the pattern's own step order "
        "and part names (e.g. G1, G2). If the pattern has few written steps (image-only), derive the "
        "construction sequence from the drawings and say so in unclear_points."
    )
    opts = cc.options(settings, system=system_prompt(settings), tools=["Read"], schema=GUIDE_SCHEMA, max_turns=40)
    res, _ = _collect(prompt, opts, log)
    guide = res.structured_output
    if not isinstance(guide, dict) or not guide.get("steps"):
        raise TutorError("Claude didn't return a guide. Try again.")
    with db.session() as conn:
        conn.execute("UPDATE patterns SET guide=?, guide_model=?, guide_at=? WHERE id=?",
                     (json.dumps(guide, ensure_ascii=False), settings["model"], db.now(), pid))
    log(f"Guide ready: {len(guide.get('steps', []))} steps. Looking for technique videos…")
    try:
        find_videos(guide_techniques(guide), log)
    except Exception as ex:  # videos are a bonus; never lose the guide over them
        log(f"Couldn't fetch videos this time ({ex}). Use 'Find videos' later.")
    return {"pattern_id": pid, "steps": len(guide.get("steps", []))}


# --------------------------------------------------------------------------- technique videos

YT_ID_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})")
VIDEOS_PER_TECHNIQUE = 2
TECHNIQUES_PER_CALL = 6
MAX_TECHNIQUES_PER_PATTERN = 10

VIDEO_SCHEMA = {
        "type": "object",
        "properties": {"techniques": {"type": "array", "items": {"type": "object", "properties": {
            "technique": {"type": "string", "description": "Exactly as given in the request."},
            "videos": {"type": "array", "items": {"type": "object", "properties": {
                "url": {"type": "string"},
                "title": {"type": "string"},
                "channel": {"type": "string"},
                "why": {"type": "string", "description": "One line: what a beginner learns from it."},
            }, "required": ["url", "title"]}},
        }, "required": ["technique", "videos"]}}},
        "required": ["techniques"],
}


def norm_technique(t: str) -> str:
    t = re.sub(r"[^a-z0-9 /&+-]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def guide_techniques(guide: dict) -> list[str]:
    """Techniques used in a guide, most frequently used first."""
    counts: dict[str, int] = {}
    for step in guide.get("steps") or []:
        for t in step.get("techniques") or []:
            n = norm_technique(t)
            if n:
                counts[n] = counts.get(n, 0) + 1
    return sorted(counts, key=lambda k: (-counts[k], k))[:MAX_TECHNIQUES_PER_PATTERN]


def videos_for(techniques: list[str]) -> dict[str, list[dict]]:
    if not techniques:
        return {}
    with db.session() as conn:
        rows = conn.execute(
            f"SELECT * FROM technique_videos WHERE technique IN ({','.join('?' * len(techniques))}) ORDER BY id",
            techniques).fetchall()
    out: dict[str, list[dict]] = {t: [] for t in techniques}
    for r in rows:
        out[r["technique"]].append({"video_id": r["video_id"], "title": r["title"], "channel": r["channel"],
                                    "why": r["why"], "url": f"https://www.youtube.com/watch?v={r['video_id']}"})
    return out


def all_videos() -> dict[str, list[dict]]:
    with db.session() as conn:
        techs = [r[0] for r in conn.execute("SELECT DISTINCT technique FROM technique_videos ORDER BY technique")]
    return videos_for(techs)


def find_videos(techniques: list[str], log=print, refresh: bool = False) -> int:
    """Search YouTube for each technique that hasn't been searched yet. Returns videos added."""
    techniques = [norm_technique(t) for t in techniques if norm_technique(t)]
    if not refresh:
        with db.session() as conn:
            done = {r[0] for r in conn.execute("SELECT technique FROM technique_searches")}
        techniques = [t for t in techniques if t not in done]
    if not techniques:
        log("Videos: all techniques already have videos.")
        return 0
    settings = config.load_settings()
    added = 0
    for i in range(0, len(techniques), TECHNIQUES_PER_CALL):
        batch = techniques[i:i + TECHNIQUES_PER_CALL]
        log(f"Searching YouTube for: {', '.join(batch)}…")
        try:
            found, seen_ids = _search_videos(settings, batch)
        except TutorError as ex:
            log(f"Video search failed: {ex}")
            continue
        with db.session() as conn:
            for entry in found:
                tech = norm_technique(entry.get("technique", ""))
                if tech not in batch:
                    continue
                for v in (entry.get("videos") or [])[:VIDEOS_PER_TECHNIQUE]:
                    m = YT_ID_RE.search(v.get("url", ""))
                    if not m or m.group(1) not in seen_ids:  # only links that really came back from search
                        continue
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO technique_videos (technique, video_id, title, channel, why, found_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (tech, m.group(1), v.get("title"), v.get("channel"), v.get("why"), db.now()))
                    added += cur.rowcount
            for t in batch:
                conn.execute("INSERT OR REPLACE INTO technique_searches (technique, searched_at) VALUES (?,?)", (t, db.now()))
    log(f"Videos: {added} added.")
    return added


def _search_videos(settings: dict, batch: list[str]) -> tuple[list[dict], set[str]]:
    prompt = (
        "Find the best YouTube tutorial videos for a beginner leatherworker for each technique below. "
        f"Pick up to {VIDEOS_PER_TECHNIQUE} per technique: clear close-up demonstrations by reputable leathercraft "
        "channels, ideally in English, preferring focused how-to videos over long vlogs. Use WebSearch with "
        'allowed_domains ["youtube.com"], then return what you found as the structured output. Use only video '
        "URLs that appear in your search results, and copy each technique name exactly as given.\n\n"
        + "\n".join(f"- {t}" for t in batch)
    )
    opts = cc.options(settings, system="You find leathercraft tutorial videos on YouTube.",
                      tools=["WebSearch"], schema=VIDEO_SCHEMA, max_turns=2 * len(batch) + 6)
    res, seen_ids = _collect(prompt, opts)
    out = res.structured_output if isinstance(res.structured_output, dict) else {}
    return out.get("techniques") or [], seen_ids


# --------------------------------------------------------------------------- chat

def _library_overview() -> str:
    with db.session() as conn:
        rows = conn.execute(
            "SELECT id, title, collection, difficulty, status FROM patterns "
            "WHERE missing=0 AND print_of IS NULL AND kind='pattern' ORDER BY difficulty, collection, title"
        ).fetchall()
    lines = [f"- #{r['id']} {r['title']}"
             + (f" [{r['collection']}]" if r["collection"] and r["collection"] != r["title"] else "")
             + f" — {r['difficulty'] or 'unrated'}"
             + (f" — student status: {r['status'].replace('_', ' ')}" if r["status"] else "")
             for r in rows]
    return ("The student's pattern library (reference patterns as 'Title (#id)' so the app can link them):\n"
            + "\n".join(lines)) if lines else "The student's library is still empty."


def _photo_lines(files: list[str]) -> str:
    if not files:
        return ""
    return ("The student attached photo(s) of their work; open them with Read:\n"
            + "\n".join(f"- {config.UPLOAD_DIR / f}" for f in files) + "\n\n")


def _transcript(history) -> str:
    """Earlier turns as text, for chats whose Claude Code session can't be resumed."""
    lines = []
    for r in history:
        blocks = json.loads(r["content"])
        photos = [str(config.UPLOAD_DIR / b["file"]) for b in blocks if b.get("type") == "image_ref"]
        text = r["display"] or " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        who = "Student" if r["role"] == "user" else "You"
        lines.append(f"{who}: {text}" + (f" [photos: {', '.join(photos)}]" if photos else ""))
    return ("Conversation so far:\n\n" + "\n\n".join(lines)) if lines else ""


def create_chat(pattern_id: int | None, title: str) -> int:
    with db.session() as conn:
        cur = conn.execute("INSERT INTO chats (pattern_id, title, created_at, updated_at) VALUES (?,?,?,?)",
                           (pattern_id, title[:120], db.now(), db.now()))
        return cur.lastrowid


MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
TOOL_STATUS = {"WebSearch": "Searching the web", "WebFetch": "Opening a web page", "Read": "Reading"}


def chat_stream(chat_id: int, user_text: str, image_files: list[str]) -> Iterator[dict]:
    """Yields events: {'type': 'text'|'status'|'done'|'error', ...}.

    Each chat is one Claude Code session (chats.session_id), resumed on every turn so Claude
    keeps what it already read. If the session can't be resumed, a fresh one gets the context
    and a transcript of the earlier turns instead."""
    settings = config.load_settings()
    with db.session() as conn:
        chat = conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        history = conn.execute("SELECT role, content, display FROM messages WHERE chat_id=? ORDER BY id",
                               (chat_id,)).fetchall()
    if not chat:
        yield {"type": "error", "text": "Chat not found"}
        return

    turn = _photo_lines(image_files) + user_text

    def fresh_prompt() -> str:
        if chat["pattern_id"]:
            p = _pattern_row(chat["pattern_id"])
            context = pattern_context(p)
            if p.get("guide"):
                context += ("\n\nThe build guide you wrote earlier for this pattern "
                            "(the student sees these step numbers in the app):\n" + p["guide"])
        else:
            context = _library_overview()
        parts = [context, _transcript(history), "The student now asks:\n" + turn]
        return "\n\n".join(x for x in parts if x)

    attempts = [(turn, chat["session_id"])] if chat["session_id"] else []
    attempts.append((None, None))  # fresh session; also the fallback when resuming fails

    texts: list[str] = []
    res = None
    for prompt, resume in attempts:
        try:
            prompt = prompt or fresh_prompt()
        except TutorError as ex:
            yield {"type": "error", "text": str(ex)}
            return
        opts = cc.options(settings, system=system_prompt(settings), tools=["Read", "WebSearch", "WebFetch"],
                          resume=resume, stream=True, max_turns=25)
        texts, res, streamed, need_gap = [], None, False, False
        try:
            for msg in cc.run(prompt, opts):
                if isinstance(msg, cc.StreamEvent):
                    if msg.parent_tool_use_id:
                        continue
                    ev = msg.event
                    if ev.get("type") == "message_start" and streamed:
                        need_gap = True
                    elif ev.get("type") == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                        text = ev["delta"]["text"]
                        if need_gap:
                            text, need_gap = "\n\n" + text, False
                        streamed = True
                        yield {"type": "text", "text": text}
                elif isinstance(msg, cc.AssistantMessage) and not msg.parent_tool_use_id:
                    for b in msg.content:
                        if isinstance(b, cc.TextBlock) and b.text.strip():
                            texts.append(b.text)
                        elif isinstance(b, cc.ToolUseBlock):
                            detail = (b.input.get("query") or b.input.get("url")
                                      or Path(b.input.get("file_path", "")).name)
                            yield {"type": "status", "text": f"{TOOL_STATUS.get(b.name, b.name)}: {detail}…"}
                elif isinstance(msg, cc.ResultMessage):
                    res = msg
        except TutorError as ex:
            if resume and not streamed:
                continue  # session gone or unreadable: start fresh with the transcript
            yield {"type": "error", "text": str(ex)}
            return
        err = cc.result_error(res)
        if err and resume and not streamed:
            continue
        if err:
            yield {"type": "error", "text": err}
            return
        break

    display = "\n\n".join(texts) or (res.result or "")
    sources, seen = [], set()
    for title, url in MD_LINK_RE.findall(display):
        if url not in seen:
            seen.add(url)
            sources.append({"title": title, "url": url})

    user_blocks: list[dict] = [{"type": "image_ref", "file": f} for f in image_files]
    user_blocks.append({"type": "text", "text": user_text})
    with db.session() as conn:
        conn.execute("INSERT INTO messages (chat_id, role, content, display, sources, created_at) VALUES (?,?,?,?,?,?)",
                     (chat_id, "user", json.dumps(user_blocks), user_text, "[]", db.now()))
        conn.execute("INSERT INTO messages (chat_id, role, content, display, sources, created_at) VALUES (?,?,?,?,?,?)",
                     (chat_id, "assistant", json.dumps([{"type": "text", "text": display}]), display,
                      json.dumps(sources), db.now()))
        conn.execute("UPDATE chats SET updated_at=?, session_id=? WHERE id=?", (db.now(), res.session_id, chat_id))
    yield {"type": "done", "sources": sources}


def save_photo(filename: str, data: bytes) -> str:
    import uuid

    ext = Path(filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise TutorError("Photos must be JPG, PNG, WEBP or GIF")
    if len(data) > 3 * 1024 * 1024:  # phone photos: shrink to what Claude uses anyway
        data, ext = _shrink(data), ".jpg"
    name = f"{uuid.uuid4().hex}{'.jpg' if ext == '.jpeg' else ext}"
    (config.UPLOAD_DIR / name).write_bytes(data)
    return name


def _shrink(data: bytes) -> bytes:
    import pymupdf

    pix = pymupdf.Pixmap(data)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    scale = 1568 / max(pix.width, pix.height)
    if scale < 1:
        pix = pymupdf.Pixmap(pix, int(pix.width * scale), int(pix.height * scale), None)
    return pix.tobytes("jpeg", jpg_quality=85)
