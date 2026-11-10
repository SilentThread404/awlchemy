"""Mirror a public catalogue of free patterns on a website.

A catalogue is a page that links to one page per pattern, and each of those
pages links to its download (a PDF, a ZIP, or a /download/<id>/ link that
returns one). Category pages on the same site are followed one level deeper.
Every file is saved in a folder named after its pattern page, and a manifest
keyed by download link makes later checks fetch only new patterns.

Only use this for catalogues whose terms allow downloading for your own use.
The files stay in your library and are never shared.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from . import jobs
from .drive_sync import MANIFEST_NAME, SyncResult, filename_from_headers, http_get, load_manifest, safe_name, save_manifest

Log = Callable[[str], None]
DOWNLOAD_RE = re.compile(r"\.(pdf|zip)$|/download/\d+/?$", re.I)
MAX_PAGES = 120
# "Make a Leather Cash Envelope", "Bi-Fold Wallet Build Along Tutorial": how-to wording around the name.
HOWTO_RE = re.compile(r"^(how to )?(make|making) an? |\bbuild[- ]along( tutorial| video)?\b|\btutorial\b", re.I)
# Words that describe the download rather than the pattern: "Free 5 Pocket Card Holder Pattern (DIY PDF)".
FILLER_RE = re.compile(r"\((?:[^)]*)\)|\b(free|pdf|diy|pattern|patterns|template|templates|download|printable)\b", re.I)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title = ""
        self.h1 = ""
        self._in: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "a" and (href := dict(attrs).get("href")):
            self.links.append(href)
        elif tag == "title" and not self.title:
            self._in = "title"
        elif tag == "h1" and not self.h1:
            self._in = "h1"

    def handle_endtag(self, tag):
        if tag == self._in:
            self._in = None

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in == "h1":
            self.h1 += data


def _fetch_page(url: str) -> _PageParser:
    with http_get(url) as resp:
        if "html" not in (resp.headers.get("Content-Type") or "").lower():
            raise RuntimeError("not a web page")
        html = resp.read(3_000_000).decode("utf-8", errors="replace")
    parser = _PageParser()
    parser.feed(html)
    return parser


def _clean(url: str) -> str:
    """Absolute link without query or #fragment (download links carry a changing timestamp)."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def pattern_name(parser: _PageParser, url: str) -> str:
    """'Free 5 Pocket Card Holder Pattern (DIY PDF)' -> '5 Pocket Card Holder'."""
    raw = (parser.h1 or re.split(r"\s[|–-]\s", parser.title)[0] or Path(urllib.parse.urlsplit(url).path).name).strip()
    name = re.sub(r"[^\w\s&'’,.-]", " ", FILLER_RE.sub(" ", raw))  # drop emoji, dashes and symbols
    name = HOWTO_RE.sub(" ", name.strip())
    name = re.sub(r"\s+", " ", name).strip(" -:,.")
    return safe_name(name or raw)[:80]


def sync_catalogue(url: str, out_dir: Path, *, dry_run: bool = False, delay: float = 1.0, log: Log = print) -> SyncResult:
    start = urllib.parse.urlsplit(url)
    if start.scheme not in ("http", "https") or not start.netloc:
        raise ValueError("A web catalogue needs a full link starting with https://")
    first = start.path.strip("/").split("/")[0]
    section = f"/{first}/" if first else "/"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    known: dict = manifest["files"]
    result = SyncResult(folder_title=start.netloc)

    def same_section(link: str) -> bool:
        p = urllib.parse.urlsplit(link)
        return p.netloc == start.netloc and p.path.startswith(section) and not DOWNLOAD_RE.search(p.path)

    # Walk the catalogue and the pages it links to, collecting the downloads on each pattern page.
    jobs.report(log, phase="listing", folders=0, found=0, have=0)
    queue: list[tuple[str, int]] = [(_clean(url), 0)]
    seen: set[str] = set()
    pending: list[tuple[str, str]] = []  # (download link, pattern folder)
    claimed: set[str] = set()
    folders: dict[str, str] = {}  # pattern folder -> the page it came from
    while queue and len(seen) < MAX_PAGES:
        page_url, depth = queue.pop(0)
        if page_url in seen:
            continue
        seen.add(page_url)
        try:
            page = _fetch_page(page_url)
        except Exception as ex:  # one broken page shouldn't stop the rest
            log(f"  ! {page_url}: {ex}")
            continue
        links = list(dict.fromkeys(_clean(urllib.parse.urljoin(page_url, h)) for h in page.links))
        downloads = [l for l in links if DOWNLOAD_RE.search(urllib.parse.urlsplit(l).path) and l not in claimed]
        if downloads and depth > 0:
            folder = base = pattern_name(page, page_url)
            n = 2
            while folders.setdefault(folder, page_url) != page_url:  # two pages, same cleaned name
                folder, n = f"{base} {n}", n + 1
            for link in downloads:
                claimed.add(link)
                record = known.get(link)
                if record and (out_dir / record["path"]).exists():
                    result.skipped += 1
                else:
                    pending.append((link, folder))
            log(f"[{folder}] {len(downloads)} download(s)")
        # Follow the catalogue's links, and one level more from its free round-up pages
        # ("free-card-holder-templates"), but not from the site's general index or paid listings.
        if depth == 0 or (depth == 1 and not downloads and "free" in page_url.lower()):
            queue += [(l, depth + 1) for l in links if same_section(l) and l not in seen
                      and urllib.parse.urlsplit(l).path.rstrip("/") != section.rstrip("/")]
        jobs.report(log, folders=len(seen), found=len(pending), have=result.skipped)
        time.sleep(delay)

    jobs.report(log, phase="downloading", phase_started=time.time(), done=0, total=len(pending),
                failed=0, bytes=0, current="")
    got = 0
    for i, (link, folder) in enumerate(pending):
        log(f"  + {folder}")
        if dry_run:
            result.downloaded.append(out_dir / folder)
            continue
        jobs.report(log, current=folder)
        try:
            dest, size = _download(link, out_dir, folder)
        except Exception as ex:  # keep going; it will be retried next run
            result.failed += 1
            log(f"    ! failed: {ex}")
            jobs.report(log, done=i + 1, failed=result.failed)
            continue
        known[link] = {"path": dest.relative_to(out_dir).as_posix(), "size": size,
                       "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        save_manifest(manifest_path, manifest)
        result.downloaded.append(dest)
        got += size
        jobs.report(log, done=i + 1, bytes=got)
        time.sleep(delay)

    verb = "would download" if dry_run else "downloaded"
    log(f"Done: {len(result.downloaded)} {verb}, {result.skipped} already present, {result.failed} failed.")
    return result


def _download(link: str, out_dir: Path, name: str) -> tuple[Path, int]:
    """Save one download, named after its pattern. A ZIP goes straight into out_dir, because the
    indexer unzips it into a folder of the same name ('Card Holder.zip' -> 'Card Holder/'); a PDF
    gets a folder of its own. Fewer folder levels keep paths short enough for Windows."""
    with http_get(link) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "html" in ctype:
            raise RuntimeError("got a web page instead of the file")
        original = filename_from_headers(resp.headers, Path(urllib.parse.urlsplit(link).path).name)
        ext = Path(original).suffix.lower() or (".zip" if "zip" in ctype else ".pdf")
        if ext not in (".pdf", ".zip"):
            raise RuntimeError(f"not a PDF or ZIP ({original})")
        folder = out_dir if ext == ".zip" else out_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{name}{ext}"
        n = 2
        while dest.exists():  # a page with several downloads
            dest = folder / f"{name} {n}{ext}"
            n += 1
        tmp = dest.with_name(dest.name + ".part")
        size = 0
        with open(tmp, "wb") as fh:
            while chunk := resp.read(256 * 1024):
                fh.write(chunk)
                size += len(chunk)
    tmp.replace(dest)
    return dest, size
