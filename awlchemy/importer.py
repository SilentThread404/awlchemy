"""Add patterns from outside the Drive subscription: uploaded files or links.

Supported links:
  * Google Drive folder  -> mirrored (incrementally) into library/Imported/<folder>
  * Google Drive file / Google Doc -> downloaded as PDF
  * Direct link to a .pdf or .zip
  * A web page that links to PDFs -> every linked PDF on the page is downloaded
Paid shops that need a login (Etsy, Gumroad...) can't be fetched. Download
those in the browser and drop the file into the app instead.
"""

from __future__ import annotations

import re
import shutil
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from . import config, drive_sync
from .drive_sync import http_get, safe_name

Log = Callable[[str], None]
MAX_PAGE_PDFS = 25


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def _target_dir(name: str | None, fallback: str) -> Path:
    folder = safe_name(name or fallback)[:80]
    d = config.IMPORT_DIR / folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_stream(url: str, dest_dir: Path, fallback_name: str, log: Log) -> Path:
    with http_get(url) as resp:
        name = drive_sync.filename_from_headers(resp.headers, fallback_name)
        dest = dest_dir / name
        tmp = dest.with_name(dest.name + ".part")
        with open(tmp, "wb") as fh:
            while chunk := resp.read(256 * 1024):
                fh.write(chunk)
    tmp.replace(dest)
    log(f"  + {dest.relative_to(config.LIBRARY_DIR).as_posix()}")
    return dest


def import_url(url: str, collection: str | None, log: Log = print) -> list[Path]:
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise ValueError("Please paste a full link starting with http:// or https://")

    if parsed := drive_sync.parse_drive_link(url):
        kind, fid, gtype = parsed
        if kind == "folder":
            title, _ = drive_sync.list_folder(fid, log)
            title = re.sub(r"\s*[-–]\s*Google Drive\s*$", "", title or "").strip()
            out = _target_dir(collection or title, f"Drive folder {fid[:8]}")
            log(f"Mirroring Drive folder into Imported/{out.name}")
            result = drive_sync.sync_folder(fid, out, log=log)
            return result.downloaded
        out = _target_dir(collection, "Single patterns")
        return [drive_sync.download_single_file(fid, out, gtype, log)]

    # Plain web link
    path_name = Path(urllib.parse.urlparse(url).path).name or "pattern"
    with http_get(url) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "pdf" in ctype or "zip" in ctype or "octet-stream" in ctype or path_name.lower().endswith((".pdf", ".zip")):
            pass  # handled below with a fresh stream
        else:
            page = resp.read(3_000_000).decode("utf-8", errors="replace")
            return _import_pdfs_from_page(url, page, collection, log)

    out = _target_dir(collection, "Single patterns")
    return [_save_stream(url, out, safe_name(path_name if "." in path_name else path_name + ".pdf"), log)]


def _import_pdfs_from_page(url: str, page: str, collection: str | None, log: Log) -> list[Path]:
    parser = _LinkParser()
    parser.feed(page)
    pdf_links = []
    for href in parser.links:
        absolute = urllib.parse.urljoin(url, href)
        if re.search(r"\.pdf($|\?)", absolute, re.I) and absolute not in pdf_links:
            pdf_links.append(absolute)
    if not pdf_links:
        raise ValueError(
            "That page doesn't link to any PDF directly. If the pattern is behind a login "
            "(Etsy, Gumroad, a shop account), download it in your browser and drop the file here instead."
        )
    title = re.sub(r"\s+", " ", parser.title).strip()
    out = _target_dir(collection or title, "Web patterns")
    log(f"Found {len(pdf_links)} PDF link(s) on the page")
    saved = []
    for link in pdf_links[:MAX_PAGE_PDFS]:
        name = safe_name(urllib.parse.unquote(Path(urllib.parse.urlparse(link).path).name))
        try:
            saved.append(_save_stream(link, out, name, log))
        except Exception as ex:
            log(f"  ! {name}: {ex}")
    return saved


def import_upload(filename: str, fileobj, collection: str | None) -> Path:
    name = safe_name(Path(filename).name)
    if not name.lower().endswith((".pdf", ".zip")):
        raise ValueError(f"{name}: only PDF or ZIP files can be added")
    out = _target_dir(collection, Path(name).stem)
    dest = out / name
    with open(dest, "wb") as fh:
        shutil.copyfileobj(fileobj, fh)
    return dest
