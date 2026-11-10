"""Build a small fake library that mimics a typical pattern-pack layout (difficulty folders, bonus guides)."""
import sys
from pathlib import Path
import pymupdf

home = Path(sys.argv[1])
lib = home / "library" / "Sample Patterns" / "Starter Pack"
easy = lib / "210+ LEATHERCRAFT PATTERNS" / "1. EASY"

def photo(w=640, h=480, color=(0.55, 0.33, 0.18)):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pix.set_rect(pix.irect, tuple(int(c * 255) for c in color))
    pix.set_rect(pymupdf.IRect(w//4, h//4, 3*w//4, 3*h//4), (60, 35, 20))
    return pix.tobytes("png")

text = Path(__file__).with_name("keyfob.txt").read_text()

def text_pdf(path, body, with_photo=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    if with_photo:
        page.insert_image(pymupdf.Rect(60, 40, 535, 400), stream=photo())
    page.insert_textbox(pymupdf.Rect(50, 420, 545, 820), body[:1500], fontsize=9)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_textbox(pymupdf.Rect(50, 50, 545, 820), body[1500:4500], fontsize=9)
    p3 = doc.new_page(width=595, height=842)
    p3.draw_rect(pymupdf.Rect(100, 100, 213, 327), color=(0, 0, 0))  # 40x80mm panel
    p3.insert_text((110, 90), "G1 FRONT PANEL 40 x 80 mm", fontsize=8)
    doc.save(path)

def image_pdf(path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=photo(1190, 1684, color))
    doc.save(path)

text_pdf(easy / "KeyChains" / "1_ Leather_Key_Fob_Pattern.pdf", text)
image_pdf(easy / "KeyChains" / "3_ Leather_Keychain.pdf", (0.4, 0.25, 0.15))
image_pdf(easy / "KeyChains" / "4_ Leather_Keychain.pdf", (0.6, 0.4, 0.2))
text_pdf(lib / "210+ LEATHERCRAFT PATTERNS" / "2. MEDIUM" / "Card Holder" / "Card_Holder.pdf", text.replace("KEY FOB", "CARD HOLDER"))
text_pdf(lib / "210+ LEATHERCRAFT PATTERNS" / "4. VERY HARD" / "Leather Backpack 17" / "Backpack.pdf", text.replace("KEY FOB", "BACKPACK"))
text_pdf(lib / "BONUS" / "1 - The Real Beginners Leathercraft Toolkit.pdf", "TOOLKIT GUIDE\n\n" + text, with_photo=False)
text_pdf(home / "library" / "Sample Patterns" / "README - Start Here.pdf", "README\n\n" + text, with_photo=False)
print("fixtures in", home)
