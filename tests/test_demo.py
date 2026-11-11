"""The static demo site (demo/): it builds from the real frontend and answers what that frontend asks."""
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def build(out: Path) -> Path:
    spec = importlib.util.spec_from_file_location("demo_build", ROOT / "demo" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(out)


def test_demo_site_builds_from_the_real_frontend(tmp_path):
    site = build(tmp_path / "site")
    html = (site / "index.html").read_text(encoding="utf-8")
    assert "/static/" not in html  # GitHub Pages serves from a sub-path, so no absolute links
    assert html.index('src="demo.js"') < html.index('src="app.js"')  # the stand-in server must load first
    assert (site / "app.js").read_bytes() == (ROOT / "awlchemy" / "static" / "app.js").read_bytes()
    assert {p.name for p in site.iterdir()} == {"index.html", "style.css", "app.js", "demo.js", ".nojekyll"}


def test_demo_holds_nothing_real():
    """Made-up content only: no web links (so no invented shops or videos) apart from the project's own page."""
    js = (ROOT / "demo" / "demo.js").read_text(encoding="utf-8")
    links = set(re.findall(r"https?://[^\s\"'`)<]+", js))
    allowed = ("https://github.com/", "http://www.w3.org/", "http://demo.invalid",
               "https://drive.google.com/drive/folders/your-")
    assert all(u.startswith(allowed) for u in links), links


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node.js")
def test_demo_answers_every_call_the_frontend_makes():
    run = subprocess.run(["node", str(ROOT / "tests" / "demo_smoke.mjs"), str(ROOT / "demo" / "demo.js"),
                          str(ROOT / "awlchemy" / "static" / "app.js")], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
