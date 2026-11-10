"""Pattern sources: the places your patterns come from.

Each source is mirrored into its own folder under library/, which the indexer
then scans. Two kinds are supported:

  * gdrive  a Google Drive folder shared as "anyone with the link"
            (incremental: only files not downloaded before are fetched)
  * folder  a folder on this computer or a network share, e.g. a Dropbox or
            OneDrive folder (incremental: only new or changed files are copied)
  * web     a public web page listing free patterns (see web_sync.py)

Sources are stored in data/settings.json under "sources", never in the code,
so the links to patterns you bought stay on your computer.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config, drive_sync, jobs, web_sync

Log = Callable[[str], None]
KINDS = ("gdrive", "folder", "web")
COPY_SUFFIXES = {".pdf", ".zip"}
RESERVED = {"imported"}  # library/Imported/ belongs to the importer


@dataclass
class SyncTotals:
    downloaded: list[Path] = field(default_factory=list)
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def detect_kind(location: str) -> str:
    parsed = drive_sync.parse_drive_link(location)
    if parsed and parsed[0] == "folder":
        return "gdrive"
    if parsed:
        raise ValueError("That's a link to a single file. Use Import for single files; a source must be a folder.")
    if location.lower().startswith(("http://", "https://")):
        return "web"
    if Path(location).expanduser().is_dir():
        return "folder"
    raise ValueError("Give a shared Google Drive folder link, a web page listing free patterns, "
                     "or the path of a folder on this computer.")


def target_dir(source: dict) -> Path:
    return config.LIBRARY_DIR / source["name"]


def list_sources() -> list[dict]:
    return list(config.load_settings().get("sources") or [])


def add_source(name: str, location: str, kind: str | None = None) -> dict:
    name = drive_sync.safe_name(name.strip())
    location = location.strip()
    if not name or name.lower() in RESERVED:
        raise ValueError(f"Pick another name: '{name}' is reserved.")
    kind = kind or detect_kind(location)
    if kind not in KINDS:
        raise ValueError(f"Unknown source type '{kind}'.")
    if kind == "folder":
        location = str(Path(location).expanduser().resolve())
        if Path(location).resolve() == config.LIBRARY_DIR.resolve() or config.LIBRARY_DIR.resolve() in Path(location).resolve().parents:
            raise ValueError("That folder is already inside the library; just use Re-scan.")
    current = list_sources()
    if any(s["name"].lower() == name.lower() for s in current):
        raise ValueError(f"There is already a source called '{name}'.")
    source = {"name": name, "kind": kind, "location": location, "enabled": True}
    config.save_settings({"sources": [*current, source]})
    return source


def starters() -> list[dict]:
    """The free catalogues the app offers to add, each marked with whether it's already a source."""
    have = {s["location"].rstrip("/").lower() for s in list_sources()}
    return [{**s, "added": s["location"].rstrip("/").lower() in have} for s in config.STARTER_SOURCES]


def add_starter(key: str) -> dict:
    s = next((s for s in config.STARTER_SOURCES if s["key"] == key), None)
    if s is None:
        raise ValueError(f"No starter pack called '{key}'.")
    return add_source(s["name"], s["location"], "web")


def remove_source(name: str) -> None:
    """Forget a source. Files already in library/<name>/ are kept."""
    current = list_sources()
    left = [s for s in current if s["name"].lower() != name.lower()]
    if len(left) == len(current):
        raise ValueError(f"No source called '{name}'.")
    config.save_settings({"sources": left})


def sync_all(log: Log = print, dry_run: bool = False, only: str | None = None) -> SyncTotals:
    totals = SyncTotals()
    chosen = [s for s in list_sources() if s.get("enabled", True) and (not only or s["name"].lower() == only.lower())]
    if only and not chosen:
        raise ValueError(f"No enabled source called '{only}'.")
    if not chosen:
        log("No pattern sources yet. Add a Google Drive folder or a local folder under Settings.")
    for i, s in enumerate(chosen, 1):
        log(f"Checking '{s['name']}' for new files…")
        jobs.report(log, source=s["name"], source_kind=s["kind"], source_index=i, source_count=len(chosen))
        try:
            if s["kind"] == "gdrive":
                r = drive_sync.sync_folder(s["location"], target_dir(s), dry_run=dry_run, log=log)
                totals.downloaded += r.downloaded
                totals.failed += r.failed
            elif s["kind"] == "web":
                r = web_sync.sync_catalogue(s["location"], target_dir(s), dry_run=dry_run, log=log)
                totals.downloaded += r.downloaded
                totals.failed += r.failed
            else:
                copied = mirror_folder(Path(s["location"]), target_dir(s), dry_run=dry_run, log=log)
                totals.downloaded += copied
        except Exception as ex:  # one broken source shouldn't stop the others
            totals.failed += 1
            totals.errors.append(f"{s['name']}: {ex}")
            log(f"  ! {s['name']}: {ex}")
    return totals


def mirror_folder(src: Path, dest: Path, *, dry_run: bool = False, log: Log = print) -> list[Path]:
    """Copy PDFs/ZIPs from src into dest, keeping the folder structure.
    A file is copied when it's new or its size or modification time changed."""
    if not src.is_dir():
        raise FileNotFoundError(f"Folder not found: {src}")
    jobs.report(log, phase="listing", folders=0, found=0, have=0)
    todo: list[tuple[Path, Path]] = []
    have = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in COPY_SUFFIXES:
            continue
        out = dest / f.relative_to(src)
        st = f.stat()
        if out.exists():
            ost = out.stat()
            if ost.st_size == st.st_size and int(ost.st_mtime) == int(st.st_mtime):
                have += 1
                continue
        todo.append((f, out))
    jobs.report(log, found=len(todo), have=have)

    jobs.report(log, phase="downloading", phase_started=time.time(), done=0, total=len(todo),
                failed=0, bytes=0, current="")
    copied: list[Path] = []
    got = 0
    for i, (f, out) in enumerate(todo):
        log(f"  + {out.relative_to(dest).as_posix()}")
        if not dry_run:
            jobs.report(log, current=out.name)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out)  # copy2 keeps the mtime, so the next run can skip it
            got += out.stat().st_size
        copied.append(out)
        jobs.report(log, done=i + 1, bytes=got)
    return copied
