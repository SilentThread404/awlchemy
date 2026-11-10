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

    with TestClient(appmod.app) as c:
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


def test_general_chat_gets_library_overview(client):
    cid = client.post("/api/chats", json={"title": "g"}).json()["id"]
    stream(client, cid, "What should I make next?")
    assert "pattern library" in fake_claude.CALLS[-1][0]
