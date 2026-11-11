"""Offline tests of the web catalogue mirror (free pattern sites)."""
import io
import tempfile
from pathlib import Path

import pytest

from awlchemy import config, sources
from awlchemy import web_sync as ws

SITE = "https://patterns.example"
PAGES = {
    "/templates/free-templates/": """<html><title>Free templates</title><body>
        <a href="/templates/">All templates</a>
        <a href="/templates/free-card-holder-pattern-pdf/">Card holder</a>
        <a href="/templates/free-wallet-patterns/">Wallet round-up</a>
        <a href="/shop/paid-bag/">Paid bag</a></body></html>""",
    "/templates/": """<html><body><a href="/templates/paid-only/">Paid</a></body></html>""",
    "/templates/free-card-holder-pattern-pdf/": """<html><title>Card holder | Site</title><body>
        <h1>Free Card Holder Pattern (DIY PDF) 🔥</h1>
        <a href="/download/11/?tmstv=123">Download</a><a href="/download/11/?tmstv=456">Again</a></body></html>""",
    "/templates/free-wallet-patterns/": """<html><body><h1>Free wallet patterns</h1>
        <a href="/templates/make-a-bifold-wallet/">Bifold</a></body></html>""",
    "/templates/make-a-bifold-wallet/": """<html><body><h1>Make a Bifold Wallet – Build Along Tutorial</h1>
        <a href="https://patterns.example/files/bifold.pdf">PDF</a></body></html>""",
    "/templates/paid-only/": """<html><body><h1>Paid</h1><a href="/download/99/">x</a></body></html>""",
}


class Resp(io.BytesIO):
    def __init__(self, data, headers):
        super().__init__(data)
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.fixture
def fake_site(monkeypatch):
    fetched = []

    def fake_get(url, retries=3):
        path = url.removeprefix(SITE)
        fetched.append(path)
        if path in PAGES:
            return Resp(PAGES[path].encode(), {"Content-Type": "text/html; charset=utf-8"})
        if path == "/download/11/":
            return Resp(b"PK fake zip", {"Content-Type": "application/zip",
                                         "Content-Disposition": 'attachment; filename="SITE-Card_Holder.zip"'})
        if path == "/files/bifold.pdf":
            return Resp(b"%PDF-1.4 fake", {"Content-Type": "application/pdf"})
        raise RuntimeError(f"unexpected fetch {url}")

    monkeypatch.setattr(ws, "http_get", fake_get)
    return fetched


def test_catalogue_mirror_is_incremental(fake_site):
    out = Path(tempfile.mkdtemp())
    r1 = ws.sync_catalogue(SITE + "/templates/free-templates/", out, delay=0, log=lambda s: None)
    assert sorted(p.relative_to(out).as_posix() for p in r1.downloaded) == [
        "Bifold Wallet/Bifold Wallet.pdf",        # how-to wording dropped from the name
        "Card Holder.zip",                        # named after the page, one download despite two links
    ]
    assert "/templates/paid-only/" not in fake_site  # the site's general index isn't followed
    assert "/shop/paid-bag/" not in fake_site        # nor pages outside the catalogue's section

    fake_site.clear()
    r2 = ws.sync_catalogue(SITE + "/templates/free-templates/", out, delay=0, log=lambda s: None)
    assert r2.downloaded == [] and r2.skipped == 2
    assert not any(p.startswith(("/download", "/files")) for p in fake_site)


def test_web_links_become_web_sources_and_starters_are_opt_in():
    assert sources.detect_kind("https://patterns.example/templates/free/") == "web"
    before = config.load_settings()["sources"]
    config.save_settings({"sources": []})
    try:
        offers = sources.starters()
        assert offers and not any(o["added"] for o in offers)  # offered, never added by default
        sources.add_starter(offers[0]["key"])
        assert sources.list_sources()[0]["kind"] == "web" and sources.starters()[0]["added"]
    finally:
        config.save_settings({"sources": before})
