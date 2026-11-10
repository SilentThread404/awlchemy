"""Incremental downloader for publicly shared Google Drive folders and files.

Walks a folder tree via Drive's embeddedfolderview page (no Google login or API
key needed, as long as the folder is shared as "anyone with the link"), mirrors
it into a local directory and records every downloaded file in a manifest so
later runs only fetch new files.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

MANIFEST_NAME = ".sync-manifest.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) awlchemy-sync/1.0"

FOLDER_RE = re.compile(r"/drive/(?:u/\d+/)?folders/([\w-]+)")
FILE_RE = re.compile(r"/file/d/([\w-]+)")
OPEN_ID_RE = re.compile(r"drive\.google\.com/(?:open|uc)\?(?:.*&)?id=([\w-]+)")
GDOC_RE = re.compile(r"docs\.google\.com/(document|spreadsheets|presentation)/d/([\w-]+)")
GDOC_EXPORT = {
    "document": "https://docs.google.com/document/d/{id}/export?format=pdf",
    "spreadsheets": "https://docs.google.com/spreadsheets/d/{id}/export?format=pdf",
    "presentation": "https://docs.google.com/presentation/d/{id}/export/pdf",
}
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

Log = Callable[[str], None]


@dataclass
class Entry:
    kind: str  # "folder", "file" or "gdoc"
    id: str
    title: str
    href: str
    gdoc_type: str | None = None


@dataclass
class SyncResult:
    downloaded: list[Path] = field(default_factory=list)
    skipped: int = 0
    failed: int = 0
    folder_title: str | None = None


class _FolderPageParser(HTMLParser):
    """Extracts (href, title) pairs from Drive's embeddedfolderview page."""

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[tuple[str, str]] = []
        self.folder_title: str | None = None
        self._href: str | None = None
        self._in_title_div = False
        self._in_page_title = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_page_title = True
        elif tag == "a" and a.get("href"):
            self._href = a["href"]
        elif tag == "div" and "flip-entry-title" in (a.get("class") or "") and self._href:
            self._in_title_div = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_page_title = False
        elif tag == "div" and self._in_title_div:
            self.entries.append((self._href, "".join(self._buf).strip()))
            self._in_title_div = False
        elif tag == "a":
            self._href = None

    def handle_data(self, data):
        if self._in_title_div:
            self._buf.append(data)
        elif self._in_page_title:
            self.folder_title = (self.folder_title or "") + data


def http_get(url: str, retries: int = 3):
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            return urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                raise RuntimeError(f"The server answered {e.code}. If this is a Google Drive link, "
                                   "check that it's shared as 'Anyone with the link'.") from e
            last_err = e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} attempts: {url} ({last_err})")


def parse_drive_link(link: str) -> tuple[str, str, str | None] | None:
    """Return (kind, id, gdoc_type) for a Drive/Docs link, or None if it isn't one."""
    if m := FOLDER_RE.search(link):
        return "folder", m.group(1), None
    if m := FILE_RE.search(link):
        return "file", m.group(1), None
    if m := GDOC_RE.search(link):
        return "gdoc", m.group(2), m.group(1)
    if m := OPEN_ID_RE.search(link):
        return "file", m.group(1), None
    return None


def list_folder(folder_id: str, log: Log = print) -> tuple[str | None, list[Entry]]:
    url = f"https://drive.google.com/embeddedfolderview?id={folder_id}"
    with http_get(url) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    parser = _FolderPageParser()
    parser.feed(page)

    entries: list[Entry] = []
    for href, title in parser.entries:
        title = html.unescape(title)
        parsed = parse_drive_link(href)
        if parsed is None:
            log(f"  ! skipping unrecognised entry: {title}")
            continue
        kind, eid, gtype = parsed
        entries.append(Entry(kind, eid, title, href, gdoc_type=gtype))
    title = html.unescape(parser.folder_title.strip()) if parser.folder_title else None
    return title, entries


def safe_name(name: str) -> str:
    name = INVALID_CHARS.sub("_", name).strip().rstrip(".")
    return name or "untitled"


def file_url(entry_kind: str, file_id: str, gdoc_type: str | None = None) -> str:
    if entry_kind == "gdoc":
        return GDOC_EXPORT[gdoc_type or "document"].format(id=file_id)
    return f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"


def download(url: str, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with http_get(url) as resp:
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" in ctype:
            snippet = resp.read(4000).decode("utf-8", errors="replace")
            hint = "quota exceeded, try again later" if "quota" in snippet.lower() else "got an HTML page instead of the file"
            raise RuntimeError(f"Drive refused the download ({hint})")
        size = 0
        with open(tmp, "wb") as fh:
            while chunk := resp.read(1024 * 256):
                fh.write(chunk)
                size += len(chunk)
    tmp.replace(dest)
    return size


def filename_from_headers(resp_headers, fallback: str) -> str:
    cd = resp_headers.get("Content-Disposition", "") or ""
    if m := re.search(r"filename\*=UTF-8''([^;]+)", cd):
        return safe_name(urllib.request.unquote(m.group(1)))
    if m := re.search(r'filename="?([^";]+)"?', cd):
        return safe_name(m.group(1))
    return fallback


def download_single_file(file_id: str, out_dir: Path, gdoc_type: str | None = None, log: Log = print) -> Path:
    """Download one Drive file (or export a Google Doc as PDF), keeping its original name."""
    kind = "gdoc" if gdoc_type else "file"
    url = file_url(kind, file_id, gdoc_type)
    out_dir.mkdir(parents=True, exist_ok=True)
    with http_get(url) as resp:
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" in ctype:
            raise RuntimeError("Drive returned a web page instead of the file. Check that the file is shared publicly.")
        name = filename_from_headers(resp.headers, f"{file_id}.pdf")
        if kind == "gdoc" and not name.lower().endswith(".pdf"):
            name += ".pdf"
        dest = out_dir / name
        tmp = dest.with_name(dest.name + ".part")
        with open(tmp, "wb") as fh:
            while chunk := resp.read(1024 * 256):
                fh.write(chunk)
    tmp.replace(dest)
    log(f"  + {name}")
    return dest


def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"files": {}}


def save_manifest(path: Path, manifest: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def sync_folder(
    folder_id: str,
    out_dir: Path,
    *,
    dry_run: bool = False,
    delay: float = 0.5,
    log: Log = print,
) -> SyncResult:
    """Mirror a shared Drive folder into out_dir, only downloading files not seen before."""
    if parsed := parse_drive_link(folder_id):
        folder_id = parsed[1]
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    known: dict = manifest["files"]
    result = SyncResult()

    seen_folders: set[str] = set()
    stack: list[tuple[str, Path]] = [(folder_id, Path())]

    while stack:
        fid, rel = stack.pop()
        if fid in seen_folders:
            continue
        seen_folders.add(fid)
        title, entries = list_folder(fid, log)
        if result.folder_title is None:
            result.folder_title = title
        log(f"[{rel.as_posix() or '/'}] {len(entries)} item(s)")
        time.sleep(delay)

        for e in entries:
            name = safe_name(e.title)
            if name.lower() in SKIP_NAMES:
                continue
            if e.kind == "folder":
                stack.append((e.id, rel / name))
                continue
            if e.kind == "gdoc" and not name.lower().endswith(".pdf"):
                name += ".pdf"

            rel_path = rel / name
            record = known.get(e.id)
            if record and (out_dir / record["path"]).exists():
                result.skipped += 1
                continue

            log(f"  + {rel_path.as_posix()}")
            if dry_run:
                result.downloaded.append(out_dir / rel_path)
                continue
            try:
                size = download(file_url(e.kind, e.id, e.gdoc_type), out_dir / rel_path)
            except Exception as ex:  # keep going; it will be retried next run
                result.failed += 1
                log(f"    ! failed: {ex}")
                continue
            known[e.id] = {
                "path": rel_path.as_posix(),
                "size": size,
                "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            save_manifest(manifest_path, manifest)
            result.downloaded.append(out_dir / rel_path)
            time.sleep(delay)

    verb = "would download" if dry_run else "downloaded"
    log(f"Done: {len(result.downloaded)} {verb}, {result.skipped} already present, {result.failed} failed.")
    return result
