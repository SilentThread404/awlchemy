"""Put the demo site together: the real frontend plus demo.js, which stands in for the server.

    python demo/build.py [output folder]      (default: demo/_site)

The output is plain static files, published to GitHub Pages by .github/workflows/demo.yml.
To look at it locally:  python -m http.server 8799 --directory demo/_site
Only the standard library is used, so this runs without installing the app.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent
STATIC = DEMO.parent / "awlchemy" / "static"

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' "
        "rx='7' fill='%237a4a2a'/%3E%3Cpath d='M9 23 L16 8 L23 23' stroke='%23f4e9dc' stroke-width='3' fill='none' "
        "stroke-linecap='round'/%3E%3Ccircle cx='16' cy='19' r='1.8' fill='%23f4e9dc'/%3E%3C/svg%3E")
ABOUT = ("Try Awlchemy in your browser: a leathercraft pattern library with a Claude-powered teacher that turns "
         "any PDF pattern into a build guide a beginner can follow. This demo uses made-up patterns.")


def swap(html: str, old: str, new: str) -> str:
    if old not in html:  # index.html changed: fail loudly instead of publishing a broken page
        raise SystemExit(f"demo/build.py: expected to find {old!r} in awlchemy/static/index.html")
    return html.replace(old, new)


def build(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = swap(html, 'href="/static/style.css"', 'href="style.css"')
    html = swap(html, '<script src="/static/app.js"></script>',
                '<script src="demo.js"></script>\n  <script src="app.js"></script>')
    html = swap(html, "<title>Awlchemy", "<title>Awlchemy demo")
    html = swap(html, "</title>", f'</title>\n  <meta name="description" content="{ABOUT}">\n'
                                  f'  <meta property="og:title" content="Awlchemy demo">\n'
                                  f'  <meta property="og:description" content="{ABOUT}">\n'
                                  f'  <link rel="icon" href="{ICON}">')
    (out / "index.html").write_text(html, encoding="utf-8", newline="\n")
    for src in (STATIC / "style.css", STATIC / "app.js", DEMO / "demo.js"):
        shutil.copyfile(src, out / src.name)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEMO / "_site"
    print("Demo site written to", build(target.resolve()))
