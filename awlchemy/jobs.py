"""Tiny in-process background job runner (sync, import, guide generation)."""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_exclusive: dict[str, str] = {}  # kind -> running job id (for jobs that must not overlap)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start(kind: str, fn: Callable[[Callable[[str], None]], Any], *, exclusive_key: str | None = None) -> dict:
    """Run fn(log) in a thread. If exclusive_key is set and such a job runs, return that one."""
    with _lock:
        if exclusive_key and (jid := _exclusive.get(exclusive_key)) and _jobs[jid]["status"] == "running":
            return public(_jobs[jid])
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "kind": kind, "status": "running", "log": [], "result": None,
               "error": None, "started_at": _now(), "finished_at": None}
        _jobs[jid] = job
        if exclusive_key:
            _exclusive[exclusive_key] = jid

    def log(line: str) -> None:
        job["log"].append(line)
        if len(job["log"]) > 500:
            del job["log"][:100]

    def run() -> None:
        try:
            job["result"] = fn(log)
            job["status"] = "done"
        except Exception as ex:
            job["error"] = str(ex) or ex.__class__.__name__
            job["status"] = "error"
            log(f"! {job['error']}")
            traceback.print_exc()
        finally:
            job["finished_at"] = _now()

    threading.Thread(target=run, daemon=True, name=f"job-{kind}").start()
    return public(job)


def get(jid: str) -> dict | None:
    job = _jobs.get(jid)
    return public(job) if job else None


def running(exclusive_key: str) -> dict | None:
    jid = _exclusive.get(exclusive_key)
    if jid and _jobs[jid]["status"] == "running":
        return public(_jobs[jid])
    return None


def public(job: dict) -> dict:
    return {**job, "log": job["log"][-60:]}
