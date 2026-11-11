"""End-to-end through the web API with Claude Code replaced by tests/fake_claude.py."""
import json
import time

import pytest
from fastapi.testclient import TestClient

import fake_claude
from awlchemy import config, jobs


@pytest.fixture(scope="module")
def client():
    fake_claude.install()
    config.save_settings({"auto_sync_on_start": False, "sources": []})
    from awlchemy import app as appmod

    with TestClient(appmod.app, base_url="http://127.0.0.1:8765") as c:
        wait(jobs.running("library"))
        yield c


def wait(job):
    while job and job.get("status") == "running":
        time.sleep(0.05)
        job = jobs.get(job["id"])
    return job


def stream(c, cid, text):
    body = c.post(f"/api/chats/{cid}/message", data={"text": text}).text
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def test_library_is_indexed(client):
    pats = client.get("/api/patterns").json()
    assert {"Easy", "Medium", "Very Hard"} <= {p["difficulty"] for p in pats}
    guides = client.get("/api/patterns", params={"kind": "guide"}).json()
    assert any("Toolkit" in g["title"] for g in guides)


def test_settings_never_expose_unknown_keys(client):
    config.save_settings({"anthropic_api_key": "sk-should-vanish"})
    s = client.get("/api/settings").json()
    assert "anthropic_api_key" not in s and "sources" in s


def test_guide_and_videos(client):
    fob = next(p for p in client.get("/api/patterns").json() if "Fob" in p["title"])
    job = wait(client.post(f"/api/patterns/{fob['id']}/guide").json())
    assert job["status"] == "done", job
    d = client.get(f"/api/patterns/{fob['id']}").json()
    assert len(d["guide"]["steps"]) == 3
    ids = {v["video_id"] for vs in d["videos"].values() for v in vs}
    assert ids and "AAAAAAAAAAA" not in ids  # invented URL not in search results is dropped


def test_chat_resumes_its_session(client):
    fob = next(p for p in client.get("/api/patterns").json() if "Fob" in p["title"])
    cid = client.post("/api/chats", json={"pattern_id": fob["id"], "title": "q"}).json()["id"]
    first = stream(client, cid, "Which leather?")
    assert first[-1]["type"] == "done" and first[-1]["sources"][0]["url"] == "https://example.com/leer"
    assert "page 1:" in fake_claude.CALLS[-1][0]
    stream(client, cid, "And which thread?")
    assert fake_claude.CALLS[-1][1].resume == "session-1"
    msgs = client.get(f"/api/chats/{cid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]


def test_other_host_names_are_refused(client):
    """DNS rebinding: a page on evil.example resolved to 127.0.0.1 sends Host: evil.example."""
    assert client.get("/api/settings", headers={"host": "evil.example:8765"}).status_code == 403
    assert client.get("/api/settings", headers={"host": "localhost:8765"}).status_code == 200


def test_cross_site_writes_are_refused(client):
    assert client.post("/api/sync", headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/reindex", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.post("/api/reindex", headers={"origin": "http://127.0.0.1:8765"}).status_code == 200
    wait(jobs.running("library"))


def test_settings_reject_a_non_list_toolkit(client):
    assert client.put("/api/settings", json={"toolkit": "awl"}).status_code == 400


def test_general_chat_gets_library_overview(client):
    cid = client.post("/api/chats", json={"title": "g"}).json()["id"]
    stream(client, cid, "What should I make next?")
    assert "pattern library" in fake_claude.CALLS[-1][0]


def test_paper_sizes_are_folded_into_their_pattern(client):
    """'Sling Bag A4/Letter/A1.pdf' sit next to the instructions: one card, sizes on the pattern page."""
    pats = client.get("/api/patterns").json()
    titles = [p["title"] for p in pats]
    assert not any(t.startswith("Sling Bag") and t != "Sling Bag 3" for t in titles), titles
    sling = next(p for p in pats if p["title"] == "Sling Bag 3")  # takes the folder's name
    assert sling["papers"] == ["A4", "Letter", "A1"]
    prints = client.get(f"/api/patterns/{sling['id']}").json()["prints"]
    assert [v["paper"] for v in prints] == ["A4", "Letter", "A1"]
    assert client.get(f"/files/{prints[0]['id']}/x.pdf").status_code == 200

    belt = [p for p in pats if p["collection"] == "Belt"]  # only paper sizes: the A4 copy is shown
    assert len(belt) == 1 and belt[0]["paper"] == "A4" and belt[0]["papers"] == ["A4", "Letter"]
    assert client.get("/api/stats").json()["total"] == len(client.get("/api/patterns", params={"kind": ""}).json())


def test_each_piece_of_a_sizes_only_download_gets_one_card(client):
    pats = [p for p in client.get("/api/patterns").json() if p["collection"] == "Traveler Set"]
    assert sorted(p["title"] for p in pats) == ["MAKER Traveler Cover", "MAKER Traveler Divider"]
    assert all(p["papers"] == ["A4", "Letter"] for p in pats)


def test_rename_and_rate_a_pattern(client):
    belt = next(p for p in client.get("/api/patterns").json() if p["collection"] == "Belt")
    assert client.patch(f"/api/patterns/{belt['id']}", json={"title": "  "}).status_code == 400
    assert client.patch(f"/api/patterns/{belt['id']}", json={"difficulty": "Impossible"}).status_code == 400
    out = client.patch(f"/api/patterns/{belt['id']}", json={"title": "Dress belt", "difficulty": "Easy"}).json()
    assert (out["title"], out["difficulty"]) == ("Dress belt", "Easy")
    wait(client.post("/api/reindex").json())  # a re-scan doesn't undo either
    again = client.get(f"/api/patterns/{belt['id']}").json()
    assert (again["title"], again["difficulty"]) == ("Dress belt", "Easy")


def test_the_teacher_sees_one_line_per_pattern_not_per_paper_size(client):
    cid = client.post("/api/chats", json={"title": "g"}).json()["id"]
    stream(client, cid, "What should I make next?")
    overview = fake_claude.CALLS[-1][0]
    assert overview.count("Sling Bag") == 1


def test_removing_a_source_with_its_patterns(client, tmp_path):
    import pymupdf

    for name in ("Pouch", "Strap"):
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), f"{name} pattern. " * 40)
        (tmp_path / name).mkdir()
        doc.save(tmp_path / name / f"{name}.pdf")
    wait(client.post("/api/sources", json={"name": "Temp", "location": str(tmp_path)}).json()["job"])
    mine = {p["title"]: p for p in client.get("/api/patterns", params={"source": "Temp"}).json()}
    assert set(mine) == {"Pouch", "Strap"}
    assert client.get("/api/sources").json()[0]["patterns"] == 2
    client.patch(f"/api/patterns/{mine['Pouch']['id']}", json={"notes": "used 1.4 mm veg-tan"})

    out = client.delete("/api/sources/temp", params={"delete_files": "true"}).json()
    assert out["sources"] == [] and (out["removed"], out["kept"]) == (1, 1)
    assert not (config.LIBRARY_DIR / "Temp").exists() and (tmp_path / "Pouch" / "Pouch.pdf").exists()
    assert client.get("/api/patterns", params={"source": "Temp"}).json() == []
    assert client.get(f"/api/patterns/{mine['Strap']['id']}").status_code == 404
    assert client.get(f"/api/patterns/{mine['Pouch']['id']}").json()["notes"] == "used 1.4 mm veg-tan"  # notes survive
