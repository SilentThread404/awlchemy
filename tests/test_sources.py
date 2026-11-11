"""Pattern sources: adding/validating them and mirroring a local folder."""
import os
import tempfile
from pathlib import Path

import pytest

from awlchemy import config, sources


@pytest.fixture(autouse=True)
def no_sources():
    config.save_settings({"sources": []})
    yield
    config.save_settings({"sources": []})


def make_folder() -> Path:
    src = Path(tempfile.mkdtemp())
    (src / "2. MEDIUM" / "Wallet").mkdir(parents=True)
    (src / "2. MEDIUM" / "Wallet" / "wallet.pdf").write_bytes(b"%PDF-1.4 a")
    (src / "notes.txt").write_text("not a pattern")
    return src


def test_add_detects_kind_and_rejects_bad_input():
    folder = make_folder()
    assert sources.add_source("Local", str(folder))["kind"] == "folder"
    assert sources.add_source("Shared", "https://drive.google.com/drive/folders/abc123_-XYZ?usp=sharing")["kind"] == "gdrive"
    with pytest.raises(ValueError):
        sources.add_source("local", str(folder))           # duplicate name (case-insensitive)
    with pytest.raises(ValueError):
        sources.add_source("Imported", str(folder))        # reserved for the importer
    with pytest.raises(ValueError):
        sources.add_source("Nope", "C:/does/not/exist/anywhere")
    with pytest.raises(ValueError):
        sources.add_source("One file", "https://drive.google.com/file/d/abc/view")
    sources.remove_source("SHARED")
    assert [s["name"] for s in sources.list_sources()] == ["Local"]


def test_folder_mirror_is_incremental():
    folder = make_folder()
    sources.add_source("Local", str(folder))
    quiet = dict(log=lambda s: None)

    first = sources.sync_all(**quiet)
    dest = config.LIBRARY_DIR / "Local"
    assert [p.relative_to(dest).as_posix() for p in first.downloaded] == ["2. MEDIUM/Wallet/wallet.pdf"]
    assert not (dest / "notes.txt").exists()

    assert sources.sync_all(**quiet).downloaded == []

    f = folder / "2. MEDIUM" / "Wallet" / "wallet.pdf"
    f.write_bytes(b"%PDF-1.4 changed")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    (folder / "new.pdf").write_bytes(b"%PDF-1.4 b")
    assert sorted(p.name for p in sources.sync_all(**quiet).downloaded) == ["new.pdf", "wallet.pdf"]


def test_one_broken_source_does_not_stop_the_rest():
    good, bad = make_folder(), make_folder()
    sources.add_source("Bad", str(bad))
    sources.add_source("Good", str(good))
    for p in bad.rglob("*"):
        if p.is_file():
            p.unlink()
    for d in sorted(bad.rglob("*"), reverse=True):
        d.rmdir()
    bad.rmdir()
    r = sources.sync_all(log=lambda s: None)
    assert r.failed == 1 and r.errors[0].startswith("Bad")
    assert any(p.name == "wallet.pdf" for p in r.downloaded)


def test_legacy_single_drive_setting_becomes_a_source(tmp_path, monkeypatch):
    data = config._migrate({"drive_folder": "https://drive.google.com/drive/folders/OLD"})
    assert data["sources"][0]["kind"] == "gdrive" and data["sources"][0]["location"].endswith("/OLD")


def test_web_pages_are_not_sources_and_old_ones_are_dropped():
    with pytest.raises(ValueError):
        sources.add_source("Site", "https://patterns.example/templates/free/")
    old = {"sources": [{"name": "Old site", "kind": "web", "location": "https://patterns.example/", "enabled": True},
                       {"name": "Shared", "kind": "gdrive", "location": "https://drive.google.com/drive/folders/abc", "enabled": True}]}
    assert [s["name"] for s in config._migrate(old)["sources"]] == ["Shared"]


def test_removing_a_source_keeps_its_files_unless_asked():
    folder = make_folder()
    sources.add_source("Local", str(folder))
    sources.sync_all(log=lambda s: None)
    dest = config.LIBRARY_DIR / "Local"
    sources.remove_source("local")
    assert dest.exists() and folder.exists()
    sources.add_source("Local", str(folder))
    sources.remove_source("Local", delete_files=True)
    assert not dest.exists() and folder.exists()  # the mirror goes, never the user's own folder
