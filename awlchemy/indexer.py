"""Scans library/ for pattern PDFs and keeps the database in step with the disk.

For every PDF it records title, difficulty (from the "1. EASY" style folders),
collection (the folder it sits in), page count, a Markdown conversion of the
text (used for search, the readable Instructions tab and as cheap context for
the tutor), and a cover image of the finished design.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Callable

import pymupdf

from . import config, db, jobs

Log = Callable[[str], None]

DIFFICULTY_RE = re.compile(r"^\s*\d+\s*[.)_-]?\s*(very hard|hard|medium|easy|beginner|intermediate|advanced)\s*$", re.I)
DIFFICULTY_NAMES = {
    "easy": "Easy", "beginner": "Easy",
    "medium": "Medium", "intermediate": "Medium",
    "hard": "Hard", "advanced": "Hard",
    "very hard": "Very Hard",
}
GUIDE_NAME_RE = re.compile(r"readme|licen[cs]e|handbook|guide|roadmap|toolkit", re.I)
LEADING_NUM_RE = re.compile(r"^\s*(\d+)\s*[_.\-)\s]+\s*")
# "Sling Bag A4", "Wallet_US Letter", "Tote (A1) size": a print-ready copy of a pattern in one paper size.
PAPER_RE = re.compile(r"(?:^|[\s_\-(])(A[0-5]|US[\s_-]?Letter|Letter|Legal|Tabloid)\)?(?:[\s_\-]+(?:size|format|paper|print))?$", re.I)
PAPER_ORDER = ["A4", "Letter", "A3", "Legal", "Tabloid", "A2", "A1", "A0", "A5"]
MARKDOWN_MAX_PAGES = 150
MIN_TEXT_CHARS = 150  # below this a PDF is treated as image-only


def markdown_path(pid: int) -> Path:
    return config.DATA_DIR / "markdown" / f"{pid}.md"


def cover_path(pid: int) -> Path:
    return config.THUMB_DIR / f"{pid}.jpg"


def page_image_path(pid: int, page: int, width: int) -> Path:
    return config.DATA_DIR / "pages" / str(pid) / f"{page}_{width}.jpg"


# --------------------------------------------------------------------------- helpers

def clean_title(stem: str) -> str:
    t = LEADING_NUM_RE.sub("", stem)
    t = t.replace("_", " ").replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\bpattern\b\s*$", "", t, flags=re.I).strip() or t
    return t or stem


def paper_size(stem: str) -> str | None:
    """'Sling Bag A4' -> 'A4', 'Belt US_Letter' -> 'Letter', 'Card Holder' -> None."""
    if not (m := PAPER_RE.search(stem.strip())):
        return None
    word = m.group(1)
    return word.upper() if word[0] in "aA" and word[1:].isdigit() else ("Letter" if "letter" in word.lower() else word.title())


def paper_rank(paper: str | None) -> int:
    return PAPER_ORDER.index(paper) if paper in PAPER_ORDER else len(PAPER_ORDER)


def classify(rel: Path) -> dict:
    parts = rel.parts
    source = parts[0] if len(parts) > 1 else "Library"
    difficulty = None
    for p in parts[:-1]:
        if m := DIFFICULTY_RE.match(p):
            difficulty = DIFFICULTY_NAMES[m.group(1).lower()]
    parent = rel.parent
    collection = parent.name if len(parent.parts) > 1 else None
    is_guide = any(p.strip().upper() == "BONUS" for p in parts[:-1]) or (
        difficulty is None and bool(GUIDE_NAME_RE.search(rel.stem))
    )
    return {
        "source": source,
        "difficulty": difficulty,
        "collection": collection,
        "kind": "guide" if is_guide else "pattern",
        "title": clean_title(rel.stem),
    }


def pdf_to_markdown(doc: pymupdf.Document) -> str:
    """Markdown for text PDFs; empty string for image-only PDFs."""
    raw = "".join(doc[i].get_text() for i in range(min(len(doc), MARKDOWN_MAX_PAGES)))
    if len(raw.strip()) < MIN_TEXT_CHARS:
        return ""
    pages = list(range(min(len(doc), MARKDOWN_MAX_PAGES)))
    try:
        import contextlib
        import io

        import pymupdf4llm

        # No OCR: image-only pages go to Claude as pictures instead. Silence the parser chatter.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            md = pymupdf4llm.to_markdown(
                doc, pages=pages, show_progress=False, use_ocr=False,
                header=False, footer=False, page_separators=True,
            )
        if isinstance(md, list):
            md = "\n\n".join(chunk.get("text", "") for chunk in md)
        if len(md.strip()) >= MIN_TEXT_CHARS:
            return md
    except Exception:
        pass
    # Fallback: plain text with page headings
    return "\n\n".join(f"## Page {i + 1}\n\n{doc[i].get_text().strip()}" for i in pages)


def _scaled_jpeg(pix: pymupdf.Pixmap, max_w: int = 720) -> bytes:
    if pix.alpha or pix.n - pix.alpha != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
    if pix.width > max_w:
        h = int(pix.height * max_w / pix.width)
        pix = pymupdf.Pixmap(pix, max_w, h, None)
    return pix.tobytes("jpeg", jpg_quality=82)


def render_page(doc: pymupdf.Document, page_no: int, width: int = 720) -> bytes:
    page = doc[page_no]
    zoom = width / max(page.rect.width, 1)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("jpeg", jpg_quality=82)


def make_cover(doc: pymupdf.Document) -> bytes:
    """Prefer the largest photo embedded in the first pages (usually the finished
    product); fall back to rendering page 1."""
    best = None
    best_area = 0
    for pno in range(min(len(doc), 4)):
        for img in doc[pno].get_images(full=True):
            xref, w, h = img[0], img[2], img[3]
            if w < 300 or h < 220 or max(w, h) / max(min(w, h), 1) > 3.5:
                continue
            if w * h > best_area:
                best, best_area = xref, w * h
    if best:
        try:
            return _scaled_jpeg(pymupdf.Pixmap(doc, best))
        except Exception:
            pass
    return render_page(doc, 0)


def page_image(pattern_id: int, rel_path: str, page_no: int, width: int = 1100) -> Path:
    """Render (and cache) one page of a pattern as JPEG."""
    out = page_image_path(pattern_id, page_no, width)
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(config.LIBRARY_DIR / rel_path) as doc:
        out.write_bytes(render_page(doc, page_no, width))
    return out


def set_cover_from_page(pattern_id: int, rel_path: str, page_no: int) -> None:
    with pymupdf.open(config.LIBRARY_DIR / rel_path) as doc:
        cover_path(pattern_id).write_bytes(render_page(doc, page_no, 720))


def extract_zips(root: Path, log: Log) -> None:
    for z in root.rglob("*.zip"):
        target = z.with_suffix("")
        if target.exists():
            continue
        root = target.resolve()
        try:
            with zipfile.ZipFile(z) as zf:
                for member in zf.infolist():
                    dest = (target / member.filename).resolve()
                    if not dest.is_relative_to(root):
                        continue  # ignore path-traversal entries such as ../x or ../<name>-evil/x
                    if member.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(member))
            log(f"  unzipped {z.name}")
        except zipfile.BadZipFile:
            log(f"  ! could not unzip {z.name}")


# --------------------------------------------------------------------------- main scan

def scan(log: Log = print, only: list[Path] | None = None) -> dict:
    """Index new/changed PDFs. Returns counts."""
    db.init()
    (config.DATA_DIR / "markdown").mkdir(parents=True, exist_ok=True)
    extract_zips(config.LIBRARY_DIR, log)

    pdfs = sorted(p for p in config.LIBRARY_DIR.rglob("*") if p.suffix.lower() == ".pdf" and p.is_file())
    added = updated = 0
    seen: set[str] = set()

    with db.session() as conn:
        existing = {r["rel_path"]: r for r in conn.execute("SELECT id, rel_path, mtime, file_size, missing FROM patterns")}

        def unchanged(pdf: Path) -> bool:
            row, st = existing.get(pdf.relative_to(config.LIBRARY_DIR).as_posix()), pdf.stat()
            return bool(row) and row["mtime"] == st.st_mtime and row["file_size"] == st.st_size

        todo = sum(1 for pdf in pdfs if not unchanged(pdf))
        jobs.report(log, phase="indexing", done=0, total=todo, current="")
        done = 0

        for pdf in pdfs:
            rel = pdf.relative_to(config.LIBRARY_DIR)
            rel_s = rel.as_posix()
            seen.add(rel_s)
            stat = pdf.stat()
            row = existing.get(rel_s)
            if row and row["mtime"] == stat.st_mtime and row["file_size"] == stat.st_size:
                if row["missing"]:
                    conn.execute("UPDATE patterns SET missing=0 WHERE id=?", (row["id"],))
                continue

            meta = classify(rel)
            jobs.report(log, current=pdf.name)
            done += 1
            try:
                with pymupdf.open(pdf) as doc:
                    pages = len(doc)
                    md = pdf_to_markdown(doc)
                    cover = make_cover(doc) if pages else None
            except Exception as ex:
                log(f"  ! could not read {rel_s}: {ex}")
                jobs.report(log, done=done)
                continue

            if row:
                pid = row["id"]
                # the PDF changed, so cached page renders are stale
                shutil.rmtree(config.DATA_DIR / "pages" / str(pid), ignore_errors=True)
                conn.execute(
                    "UPDATE patterns SET pages=?, file_size=?, mtime=?, text=?, missing=0 WHERE id=?",
                    (pages, stat.st_size, stat.st_mtime, md, pid),
                )
                updated += 1
            else:
                cur = conn.execute(
                    """INSERT INTO patterns (rel_path, title, collection, difficulty, source, kind,
                       pages, file_size, mtime, text, added_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (rel_s, meta["title"], meta["collection"], meta["difficulty"], meta["source"],
                     meta["kind"], pages, stat.st_size, stat.st_mtime, md, db.now()),
                )
                pid = cur.lastrowid
                added += 1
                log(f"  indexed {rel_s}")
            markdown_path(pid).write_text(md, encoding="utf-8")
            if cover:
                cover_path(pid).write_bytes(cover)
            conn.commit()
            jobs.report(log, done=done)

        # flag rows whose file disappeared
        for rel_s, row in existing.items():
            if rel_s not in seen and not row["missing"]:
                conn.execute("UPDATE patterns SET missing=1 WHERE id=?", (row["id"],))

        _group_print_sizes(conn)
        _dedupe_titles(conn)

    log(f"Library: {added} new, {updated} updated, {len(pdfs)} PDFs in total.")
    return {"added": added, "updated": updated, "total": len(pdfs)}


def _group_print_sizes(conn) -> None:
    """Many sellers ship one pattern as an instructions PDF plus the pieces in several paper
    sizes (A4, Letter, A1). Show one card per pattern and offer the sizes when printing.

    In each folder, files named after a paper size become print copies of the folder's one
    other PDF. A folder with only paper sizes shows its A4 (or first) copy. Folders with several
    other PDFs are left alone, because then it isn't clear which pattern a size belongs to."""
    rows = conn.execute("SELECT id, rel_path, kind, notes, guide, status, favorite, print_of, paper "
                        "FROM patterns WHERE missing=0").fetchall()
    per_folder: dict[str, list] = defaultdict(list)
    for r in rows:
        per_folder[str(Path(r["rel_path"]).parent)].append(r)

    for folder in per_folder.values():
        want: dict[int, tuple] = {}  # id -> (print_of, paper)
        sizes = [r for r in folder if r["kind"] == "pattern" and paper_size(Path(r["rel_path"]).stem)]
        others = [r for r in folder if r not in sizes and r["kind"] == "pattern"]
        mains = others if len(others) <= 1 else [
            r for r in others if re.search(r"instruction|tutorial|guide|step", Path(r["rel_path"]).stem, re.I)]
        main = None
        if sizes and len(mains) == 1:
            main = mains[0]
        elif sizes and not others:
            main = min(sizes, key=lambda r: (paper_rank(paper_size(Path(r["rel_path"]).stem)), r["rel_path"]))
        for r in folder:
            paper = paper_size(Path(r["rel_path"]).stem) if r in sizes else None
            # Never hide a copy the user already wrote notes on or made a guide for.
            hide = main is not None and r in sizes and r["id"] != main["id"] and not (r["notes"] or r["guide"])
            want[r["id"]] = (main["id"] if hide else None, paper)
            if hide and r["print_of"] is None and (r["favorite"] or r["status"]):
                conn.execute("UPDATE patterns SET favorite=MAX(favorite, ?), status=CASE WHEN status='' THEN ? ELSE status END "
                             "WHERE id=?", (r["favorite"], r["status"], main["id"]))
        for r in folder:
            if (r["print_of"], r["paper"]) != want[r["id"]]:
                conn.execute("UPDATE patterns SET print_of=?, paper=? WHERE id=?", (*want[r["id"]], r["id"]))


def print_versions(conn, pid: int) -> list[dict]:
    """The paper-size PDFs to print a pattern from, home-printer sizes first."""
    rows = [dict(r) for r in conn.execute(
        "SELECT id, rel_path, paper, pages FROM patterns WHERE missing=0 AND paper IS NOT NULL AND (print_of=? OR id=?)",
        (pid, pid))]
    return sorted(rows, key=lambda r: (paper_rank(r["paper"]), r["rel_path"]))


def _dedupe_titles(conn) -> None:
    """Folders like 'KeyChains' hold several variants with the same name, so number them.
    A pattern folder with a single PDF ('Wallet 2/pattern.pdf') takes the folder's name."""
    per_folder: dict[str, list] = defaultdict(list)
    for r in conn.execute("SELECT id, rel_path, title, collection, kind FROM patterns "
                          "WHERE missing=0 AND print_of IS NULL AND source<>'Imported'"):
        per_folder[str(Path(r["rel_path"]).parent)].append(r)
    for rows in per_folder.values():
        r = rows[0]
        if len(rows) == 1 and r["kind"] == "pattern" and r["collection"] and not DIFFICULTY_RE.match(r["collection"]):
            if r["title"] == clean_title(Path(r["rel_path"]).stem):  # untouched auto title
                conn.execute("UPDATE patterns SET title=? WHERE id=?", (r["collection"], r["id"]))

    groups: dict[tuple, list] = defaultdict(list)
    for r in conn.execute("SELECT id, rel_path, title, collection FROM patterns WHERE missing=0 AND print_of IS NULL"):
        groups[(r["collection"], clean_title(Path(r["rel_path"]).stem).lower())].append(r)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        for i, r in enumerate(sorted(rows, key=lambda r: r["rel_path"]), 1):
            stem = Path(r["rel_path"]).stem
            num = m.group(1) if (m := LEADING_NUM_RE.match(stem)) else str(i)
            base = clean_title(stem)
            wanted = f"{base} #{num}"
            if r["title"] in (base, wanted):  # don't override a title the user renamed
                conn.execute("UPDATE patterns SET title=? WHERE id=?", (wanted, r["id"]))
