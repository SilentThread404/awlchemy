"""FastAPI server for the Awlchemy web app (runs locally on 127.0.0.1)."""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import claude_code, config, db, importer, indexer, jobs, sources, tutor

STATIC = Path(__file__).resolve().parent / "static"
SYNC_KEY = "library"  # sync, import and index all touch the library — never run two at once


# --------------------------------------------------------------------------- background work

def run_sync(log) -> dict:
    result = sources.sync_all(log=log)
    log("Updating the library index…")
    counts = indexer.scan(log=log)
    config.save_settings({"last_sync": db.now()})
    return {"downloaded": len(result.downloaded), "failed": result.failed, "errors": result.errors, **counts}


def start_sync() -> dict:
    return jobs.start("sync", run_sync, exclusive_key=SYNC_KEY)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    settings = config.load_settings()
    last = settings.get("last_sync")
    stale = not last or datetime.now(timezone.utc) - datetime.fromisoformat(last) > timedelta(hours=20)
    if settings.get("auto_sync_on_start") and settings.get("sources") and stale:
        start_sync()
    else:
        jobs.start("index", lambda log: indexer.scan(log=log), exclusive_key=SYNC_KEY)
    yield


app = FastAPI(title="Awlchemy", lifespan=lifespan)


# --------------------------------------------------------------------------- helpers

def get_pattern(pid: int) -> dict:
    with db.session() as conn:
        row = conn.execute("SELECT * FROM patterns WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "Pattern not found")
    return dict(row)


# --------------------------------------------------------------------------- library

@app.get("/api/patterns")
def list_patterns(q: str = "", difficulty: str = "", kind: str = "pattern", status: str = "",
                  source: str = "", favorite: bool = False):
    sql = "SELECT * FROM patterns WHERE missing=0"
    args: list = []
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if difficulty:
        if difficulty == "unrated":
            sql += " AND difficulty IS NULL"
        else:
            sql += " AND difficulty=?"
            args.append(difficulty)
    if status:
        sql += " AND status=?"
        args.append(status)
    if source:
        sql += " AND source=?"
        args.append(source)
    if favorite:
        sql += " AND favorite=1"
    for word in q.split():
        like = f"%{word}%"
        sql += " AND (title LIKE ? OR collection LIKE ? OR text LIKE ? OR notes LIKE ?)"
        args += [like, like, like, like]
    order = {"Easy": 1, "Medium": 2, "Hard": 3, "Very Hard": 4}
    with db.session() as conn:
        rows = [db.row_to_pattern(r) for r in conn.execute(sql, args)]
    rows.sort(key=lambda r: (order.get(r["difficulty"] or "", 5), (r["collection"] or "").lower(), r["title"].lower()))
    return rows


@app.get("/api/stats")
def stats():
    with db.session() as conn:
        counts = dict(conn.execute(
            "SELECT COUNT(*) total, SUM(kind='pattern') patterns, SUM(kind='guide') guides, "
            "SUM(guide IS NOT NULL) with_guide, SUM(status='in_progress') in_progress, SUM(status='done') done "
            "FROM patterns WHERE missing=0").fetchone())
        sources = [r[0] for r in conn.execute("SELECT DISTINCT source FROM patterns WHERE missing=0 ORDER BY source")]
    s = config.load_settings()
    return {**{k: v or 0 for k, v in counts.items()}, "sources": sources, "last_sync": s.get("last_sync"),
            "library_job": jobs.running(SYNC_KEY), "claude": claude_code.info(),
            "library_path": str(config.LIBRARY_DIR), "source_count": len(s.get("sources") or [])}


@app.get("/api/patterns/{pid}")
def pattern_detail(pid: int):
    p = get_pattern(pid)
    out = db.row_to_pattern(_row(pid), full=True)
    out["has_text"] = bool((p.get("text") or "").strip())
    with db.session() as conn:
        out["siblings"] = [dict(r) for r in conn.execute(
            "SELECT id, title FROM patterns WHERE missing=0 AND id<>? AND rel_path LIKE ? ORDER BY title",
            (pid, Path(p["rel_path"]).parent.as_posix() + "/%"))][:20]
    out["videos"] = tutor.videos_for(tutor.guide_techniques(out["guide"])) if out["guide"] else {}
    return out


def _row(pid: int):
    with db.session() as conn:
        return conn.execute("SELECT * FROM patterns WHERE id=?", (pid,)).fetchone()


@app.get("/api/patterns/{pid}/markdown")
def pattern_markdown(pid: int):
    get_pattern(pid)
    path = indexer.markdown_path(pid)
    return {"markdown": path.read_text(encoding="utf-8") if path.exists() else ""}


class PatternUpdate(BaseModel):
    favorite: bool | None = None
    status: str | None = None
    notes: str | None = None
    progress: list[int] | None = None
    title: str | None = None


@app.patch("/api/patterns/{pid}")
def update_pattern(pid: int, body: PatternUpdate):
    get_pattern(pid)
    fields = body.model_dump(exclude_none=True)
    if "status" in fields and fields["status"] not in ("", "wishlist", "in_progress", "done"):
        raise HTTPException(400, "bad status")
    if "progress" in fields:
        fields["progress"] = json.dumps(sorted(set(fields["progress"])))
    if "favorite" in fields:
        fields["favorite"] = int(fields["favorite"])
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        with db.session() as conn:
            conn.execute(f"UPDATE patterns SET {sets} WHERE id=?", [*fields.values(), pid])
    return db.row_to_pattern(_row(pid), full=True)


@app.get("/api/patterns/{pid}/cover")
def cover(pid: int):
    path = indexer.cover_path(pid)
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@app.post("/api/patterns/{pid}/cover")
def set_cover(pid: int, page: int = Form(...)):
    p = get_pattern(pid)
    if not 0 <= page < (p["pages"] or 0):
        raise HTTPException(400, "No such page")
    indexer.set_cover_from_page(pid, p["rel_path"], page)
    return {"ok": True}


@app.get("/api/patterns/{pid}/page/{page}")
def page_preview(pid: int, page: int, w: int = 900):
    p = get_pattern(pid)
    if not 0 <= page < (p["pages"] or 0):
        raise HTTPException(404)
    w = max(200, min(w, 1600))
    return FileResponse(indexer.page_image(pid, p["rel_path"], page, w), media_type="image/jpeg")


@app.get("/files/{pid}/{name}")
def pdf_file(pid: int, name: str):
    """The original PDF, untouched — this is what you print (at 100% / Actual size)."""
    p = get_pattern(pid)
    path = config.LIBRARY_DIR / p["rel_path"]
    if not path.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline", filename=path.name)


# --------------------------------------------------------------------------- guides

@app.post("/api/patterns/{pid}/guide")
def make_guide(pid: int):
    get_pattern(pid)
    return jobs.start("guide", lambda log: tutor.generate_guide(pid, log), exclusive_key=f"guide-{pid}")


@app.get("/api/patterns/{pid}/guide-job")
def guide_job(pid: int):
    return jobs.running(f"guide-{pid}") or {}


@app.post("/api/patterns/{pid}/videos")
def find_pattern_videos(pid: int, refresh: bool = False):
    """Search YouTube for the techniques in this pattern's guide (only ones not searched yet, unless refresh)."""
    p = get_pattern(pid)
    if not p.get("guide"):
        raise HTTPException(400, "Write the build guide first; the videos follow its techniques.")
    techniques = tutor.guide_techniques(json.loads(p["guide"]))
    return jobs.start("videos", lambda log: tutor.find_videos(techniques, log, refresh=refresh),
                      exclusive_key=f"guide-{pid}")


@app.get("/api/videos")
def technique_videos():
    return tutor.all_videos()


# --------------------------------------------------------------------------- sync & import

@app.post("/api/sync")
def sync_now():
    return start_sync()


@app.post("/api/reindex")
def reindex():
    return jobs.start("index", lambda log: indexer.scan(log=log), exclusive_key=SYNC_KEY)


class ImportLink(BaseModel):
    url: str
    collection: str | None = None


@app.post("/api/import/url")
def import_link(body: ImportLink):
    if jobs.running(SYNC_KEY):
        raise HTTPException(409, "The library is busy syncing — try again in a moment.")

    def work(log):
        files = importer.import_url(body.url, body.collection or None, log)
        if not files:
            raise RuntimeError("Nothing was downloaded from that link.")
        counts = indexer.scan(log=log)
        return {**counts, "files": [str(f.relative_to(config.LIBRARY_DIR)) for f in files]}

    return jobs.start("import", work, exclusive_key=SYNC_KEY)


@app.post("/api/import/upload")
async def import_files(files: list[UploadFile] = File(...), collection: str = Form("")):
    if jobs.running(SYNC_KEY):
        raise HTTPException(409, "The library is busy syncing — try again in a moment.")
    saved = []
    try:
        for f in files:
            saved.append(importer.import_upload(f.filename or "pattern.pdf", f.file, collection or None))
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return jobs.start("import", lambda log: {**indexer.scan(log=log), "files": [s.name for s in saved]},
                      exclusive_key=SYNC_KEY)


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404)
    return job


# --------------------------------------------------------------------------- tutor chats

@app.get("/api/chats")
def list_chats(pattern_id: int | None = None):
    with db.session() as conn:
        if pattern_id:
            rows = conn.execute("SELECT * FROM chats WHERE pattern_id=? ORDER BY updated_at DESC", (pattern_id,))
        else:
            rows = conn.execute("SELECT * FROM chats WHERE pattern_id IS NULL ORDER BY updated_at DESC")
        return [dict(r) for r in rows]


class NewChat(BaseModel):
    pattern_id: int | None = None
    title: str = "New question"


@app.post("/api/chats")
def new_chat(body: NewChat):
    if body.pattern_id:
        get_pattern(body.pattern_id)
    return {"id": tutor.create_chat(body.pattern_id, body.title)}


@app.get("/api/chats/{cid}")
def chat_detail(cid: int):
    with db.session() as conn:
        chat = conn.execute("SELECT * FROM chats WHERE id=?", (cid,)).fetchone()
        if not chat:
            raise HTTPException(404)
        msgs = []
        for m in conn.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY id", (cid,)):
            blocks = json.loads(m["content"])
            msgs.append({"role": m["role"], "text": m["display"] or "",
                         "sources": json.loads(m["sources"] or "[]"),
                         "photos": [b["file"] for b in blocks if b.get("type") == "image_ref"]})
    return {**dict(chat), "messages": msgs}


@app.delete("/api/chats/{cid}")
def delete_chat(cid: int):
    with db.session() as conn:
        conn.execute("DELETE FROM chats WHERE id=?", (cid,))
    return {"ok": True}


@app.post("/api/chats/{cid}/message")
async def send_message(cid: int, text: str = Form(...), photos: list[UploadFile] | None = File(None)):
    names = []
    for ph in photos or []:
        try:
            names.append(tutor.save_photo(ph.filename or "photo.jpg", await ph.read()))
        except tutor.TutorError as ex:
            raise HTTPException(400, str(ex))

    def events():
        for ev in tutor.chat_stream(cid, text, names):
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/photos/{name}")
def photo(name: str):
    if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp|gif)", name):
        raise HTTPException(404)
    path = config.UPLOAD_DIR / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


# --------------------------------------------------------------------------- settings

def _public_settings() -> dict:
    s = config.load_settings()
    s["models"] = tutor.MODELS
    return s


@app.get("/api/settings")
def get_settings():
    return _public_settings()


@app.put("/api/settings")
def put_settings(body: dict):
    if "toolkit" in body:
        body["toolkit"] = sorted({t.strip() for t in body["toolkit"] if t and t.strip()}, key=str.lower)
    body.pop("last_sync", None)
    body.pop("sources", None)  # managed through /api/sources so they're validated
    config.save_settings(body)
    return _public_settings()


class NewSource(BaseModel):
    name: str
    location: str


@app.get("/api/sources")
def list_sources():
    return sources.list_sources()


@app.post("/api/sources")
def add_source(body: NewSource):
    try:
        src = sources.add_source(body.name, body.location)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return {"source": src, "job": start_sync()}


@app.delete("/api/sources/{name}")
def remove_source(name: str):
    try:
        sources.remove_source(name)
    except ValueError as ex:
        raise HTTPException(404, str(ex))
    return sources.list_sources()


@app.post("/api/claude/check")
def claude_check():
    """Round trip through Claude Code to confirm it's installed and signed in."""
    return claude_code.check(config.load_settings())


# --------------------------------------------------------------------------- frontend

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.exception_handler(tutor.TutorError)
async def tutor_error(_req, ex: tutor.TutorError):
    return JSONResponse({"detail": str(ex)}, status_code=400)


@app.get("/favicon.ico")
def favicon():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" '
           'fill="#7a4a2a"/><path d="M9 23 L16 8 L23 23" stroke="#f4e9dc" stroke-width="3" fill="none" '
           'stroke-linecap="round"/><circle cx="16" cy="19" r="1.8" fill="#f4e9dc"/></svg>')
    return Response(svg, media_type="image/svg+xml")
