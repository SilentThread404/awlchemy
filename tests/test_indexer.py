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


import pytest


@pytest.mark.parametrize("stem, paper", [
    ("Sling Bag A4", "A4"), ("Belt US_Letter", "Letter"), ("Card_Holder_No_1(LETTER)", "Letter"),
    ("Cash_Envelope_Pattern(A4-Size-Print)", "A4"), ("tote-bag-template-set_letter", "Letter"),
    ("cuff_bracelet_pack--A4", "A4"), ("Trifold_PDF(A4-printer-paper-size)", "A4"),
    ("money-clip-bi-fold-wallet-LETER", "Letter"), ("messenger_bag_no_1-A4--Print_PDF", "A4"),
    ("Card_Case_PDF-(DOUBLE-DECK-A4)", "A4"), ("Mini A5 wallet", None), ("Card Holder", None),
    ("Journal(Passport)-A4-Square-Corners", "A4"), ("MAKER-A5_Notebook_Cover(A4-Size)", "A4"),
])
def test_paper_size_in_file_names(stem, paper):
    assert indexer.paper_size(stem) == paper


def test_macos_junk_in_zips_is_skipped_and_a_bad_zip_does_not_stop_the_scan():
    root = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(root / "good.zip", "w") as zf:
        zf.writestr("Wallet(A4).pdf", b"%PDF")
        zf.writestr("__MACOSX/._Wallet(A4).pdf", b"junk")
        zf.writestr("._Wallet(A4).pdf", b"junk")
    (root / "broken.zip").write_bytes(b"not a zip")
    lines = []
    indexer.extract_zips(root, log=lines.append)
    assert [p.name for p in (root / "good").rglob("*")] == ["Wallet(A4).pdf"]
    assert any("could not unzip broken.zip" in l for l in lines) and not (root / "broken").exists()


def test_paper_size_folders_are_skipped_when_grouping():
    a = indexer.pattern_folder(Path("Src/Notebook/A4 Size Printer/Two Cord/x(A4-Size).pdf"))
    b = indexer.pattern_folder(Path("Src/Notebook/Letter Size Printer/Two Cord/x(Letter-Size).pdf"))
    assert a == b == Path("Src/Notebook/Two Cord")
    assert indexer.without_paper("Card_Case_PDF-(DOUBLE-DECK-A4)") == "Card_Case_PDF-(DOUBLE-DECK)"
    assert indexer.without_paper("Journal(Passport)-A4-Square-Corners") == "Journal(Passport) Square-Corners"
