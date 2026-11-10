"""ZIP extraction must stay inside the folder named after the archive."""
import tempfile
import zipfile
from pathlib import Path

from awlchemy import indexer


def test_zip_cannot_escape_into_a_sibling_folder():
    root = Path(tempfile.mkdtemp())
    z = root / "pack.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("ok/inside.txt", "fine")
        zf.writestr("../pack-evil/outside.txt", "nope")  # shares the "pack" prefix
        zf.writestr("../escape.txt", "nope")
    indexer.extract_zips(root, log=lambda _line: None)
    assert (root / "pack" / "ok" / "inside.txt").exists()
    assert not (root / "pack-evil").exists()
    assert not (root / "escape.txt").exists()
