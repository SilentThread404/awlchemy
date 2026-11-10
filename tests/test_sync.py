"""Offline tests of the Google Drive mirror: page parsing and incremental behaviour."""
import io
import tempfile
from pathlib import Path

import pytest

from awlchemy import drive_sync as ds

PAGES = {
    "ROOT": """<html><head><title>Sample Patterns - Google Drive</title></head><body>
  <div class="flip-entry"><a href="https://drive.google.com/drive/folders/EASY" target="_blank"><div class="flip-entry-info"><div class="flip-entry-title">1. EASY</div></div></a></div>
  <div class="flip-entry"><a href="https://drive.google.com/file/d/README/view?usp=drive_web"><div class="flip-entry-title">README - Start Here.pdf</div></a></div>
  <div class="flip-entry"><a href="https://docs.google.com/document/d/GDOC/edit?usp=drive_web"><div class="flip-entry-title">Notes &amp; tips</div></a></div>
  <div class="flip-entry"><a href="https://drive.google.com/file/d/INI/view"><div class="flip-entry-title">desktop.ini</div></a></div></body></html>""",
    "EASY": """<html><head><title>1. EASY</title></head><body>
  <div class="flip-entry"><a href="https://drive.google.com/drive/folders/KEYS"><div class="flip-entry-title">KeyChains</div></a></div></body></html>""",
    "KEYS": """<html><body><div class="flip-entry"><a href="https://drive.google.com/file/d/FOB/view"><div class="flip-entry-title">1_ Leather_Key_Fob_Pattern.pdf</div></a></div>
  <div class="flip-entry"><a href="https://drive.google.com/file/d/K3/view"><div class="flip-entry-title">3_ Leather:Keychain?.pdf</div></a></div></body></html>""",
}


class Resp(io.BytesIO):
    def __init__(self, data, ctype):
        super().__init__(data)
        self.headers = {"Content-Type": ctype}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.fixture
def fake_drive(monkeypatch):
    fetched = []

    def fake_get(url, retries=3):
        if "embeddedfolderview" in url:
            return Resp(PAGES[url.split("id=")[1]].encode(), "text/html")
        fetched.append(url)
        return Resp(b"%PDF-1.4 fake", "application/pdf")

    monkeypatch.setattr(ds, "http_get", fake_get)
    return fetched


def rel(out, paths):
    return sorted(p.relative_to(out).as_posix() for p in paths)


def test_incremental_mirror(fake_drive):
    out = Path(tempfile.mkdtemp())
    quiet = dict(delay=0, log=lambda s: None)

    r1 = ds.sync_folder("https://drive.google.com/drive/folders/ROOT", out, **quiet)
    assert rel(out, r1.downloaded) == [
        "1. EASY/KeyChains/1_ Leather_Key_Fob_Pattern.pdf",
        "1. EASY/KeyChains/3_ Leather_Keychain_.pdf",  # unsafe characters replaced
        "Notes & tips.pdf",                             # Google Doc exported as PDF
        "README - Start Here.pdf",
    ]
    assert any("export?format=pdf" in u for u in fake_drive)
    assert not (out / "desktop.ini").exists()

    n = len(fake_drive)
    r2 = ds.sync_folder("ROOT", out, **quiet)
    assert r2.downloaded == [] and r2.skipped == 4 and len(fake_drive) == n

    (out / "1. EASY/KeyChains/1_ Leather_Key_Fob_Pattern.pdf").unlink()
    r3 = ds.sync_folder("ROOT", out, **quiet)
    assert [p.name for p in r3.downloaded] == ["1_ Leather_Key_Fob_Pattern.pdf"]


def test_refused_download_is_retried_later(fake_drive, monkeypatch):
    out = Path(tempfile.mkdtemp())
    real = ds.http_get

    def quota(url, retries=3):
        if "usercontent" in url:
            return Resp(b"<html>Google Drive - Quota exceeded</html>", "text/html")
        return real(url, retries)

    monkeypatch.setattr(ds, "http_get", quota)
    r = ds.sync_folder("ROOT", out, delay=0, log=lambda s: None)
    assert r.failed == 3 and [p.name for p in out.rglob("*.pdf")] == ["Notes & tips.pdf"]
    assert not list(out.rglob("*.part"))

    monkeypatch.setattr(ds, "http_get", real)  # quota reset: the three failures are fetched now
    assert len(ds.sync_folder("ROOT", out, delay=0, log=lambda s: None).downloaded) == 3
