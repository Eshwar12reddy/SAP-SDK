import json

from sqlalchemy import select

from app.database import Message
from tests.conftest import register_and_login


def sse_events(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]


async def test_chat_creates_and_persists_conversation(client, fake_ai):
    h = await register_and_login(client)
    r = await client.post("/api/chat", json={"message": "What is BRIM?"}, headers=h)
    assert r.status_code == 200
    cid = r.json()["conversation_id"]
    assert r.json()["answer"] == "echo: What is BRIM?"
    msgs = (await client.get(f"/api/conversations/{cid}/messages", headers=h)).json()
    assert msgs == [{"role": "user", "content": "What is BRIM?"}, {"role": "assistant", "content": "echo: What is BRIM?"}]
    assert [c["id"] for c in (await client.get("/api/conversations", headers=h)).json()] == [cid]


async def test_conversation_create_rename_delete(client):
    h = await register_and_login(client)
    c = (await client.post("/api/conversations", json={"title": "Mine"}, headers=h)).json()
    assert (await client.patch(f"/api/conversations/{c['id']}", json={"title": "Renamed"}, headers=h)).json()["title"] == "Renamed"
    assert (await client.delete(f"/api/conversations/{c['id']}", headers=h)).json() == {"deleted": True}
    assert (await client.get("/api/conversations", headers=h)).json() == []


async def test_users_cannot_access_each_others_conversations(client, fake_ai):
    a = await register_and_login(client, "a@example.com")
    b = await register_and_login(client, "b@example.com")
    cid = (await client.post("/api/chat", json={"message": "private question"}, headers=a)).json()["conversation_id"]
    assert (await client.get("/api/conversations", headers=b)).json() == []
    assert (await client.get(f"/api/conversations/{cid}/messages", headers=b)).status_code == 404
    assert (await client.patch(f"/api/conversations/{cid}", json={"title": "x"}, headers=b)).status_code == 404
    assert (await client.delete(f"/api/conversations/{cid}", headers=b)).status_code == 404
    assert (await client.post("/api/chat", json={"conversation_id": cid, "message": "hi"}, headers=b)).status_code == 404
    stream = await client.post("/api/chat/stream", json={"conversation_id": cid, "message": "hi"}, headers=b)
    assert any(e.get("error") == "Conversation not found" for e in sse_events(stream.text)) or stream.status_code == 404
    # the owner's history is untouched by the failed attempts
    assert len((await client.get(f"/api/conversations/{cid}/messages", headers=a)).json()) == 2


async def test_chat_requires_auth_and_validates_input(client, fake_ai):
    assert (await client.post("/api/chat", json={"message": "hi"})).status_code == 401
    h = await register_and_login(client)
    assert (await client.post("/api/chat", json={"message": ""}, headers=h)).status_code == 422
    assert (await client.post("/api/chat", json={"message": "x" * 12001}, headers=h)).status_code == 422
    assert (await client.post("/api/chat", json={}, headers=h)).status_code == 422
    assert (await client.post("/api/chat", content="not json", headers={**h, "Content-Type": "application/json"})).status_code == 422
    assert fake_ai == []


async def test_stream_emits_tokens_and_persists_answer(client, fake_ai):
    h = await register_and_login(client)
    r = await client.post("/api/chat/stream", json={"message": "stream please"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = sse_events(r.text)
    assert "".join(e["token"] for e in events if "token" in e) == "Hello world"
    assert any(e.get("done") for e in events) and r.text.rstrip().endswith("data: [DONE]")
    cid = events[0]["conversation_id"]
    msgs = (await client.get(f"/api/conversations/{cid}/messages", headers=h)).json()
    assert msgs[-1] == {"role": "assistant", "content": "Hello world"}


async def test_provider_failure_is_502_and_does_not_save_turn(client, monkeypatch):
    from app.api import chat as chat_api
    from app.services.openrouter_service import OpenRouterError

    async def boom(*_a, **_k):
        raise OpenRouterError("OpenRouter request timed out.")

    monkeypatch.setattr(chat_api, "answer", boom)
    h = await register_and_login(client)
    r = await client.post("/api/chat", json={"message": "hi"}, headers=h)
    assert r.status_code == 502 and "timed out" in r.json()["detail"]
    async with client.sessions() as s:
        assert (await s.scalars(select(Message))).all() == []


async def test_stream_provider_error_is_reported_in_band_and_turn_removed(client, monkeypatch):
    from app.api import chat as chat_api
    from app.services.openrouter_service import OpenRouterError

    async def failing_stream(*_a, **_k):
        raise OpenRouterError("Unable to connect to OpenRouter.")
        yield  # pragma: no cover

    monkeypatch.setattr(chat_api, "answer_stream", failing_stream)
    h = await register_and_login(client)
    r = await client.post("/api/chat/stream", json={"message": "hi"}, headers=h)
    assert r.status_code == 200
    assert any("error" in e for e in sse_events(r.text))
    async with client.sessions() as s:
        assert (await s.scalars(select(Message))).all() == []


async def test_edit_and_regenerate(client, fake_ai):
    h = await register_and_login(client)
    cid = (await client.post("/api/chat", json={"message": "first"}, headers=h)).json()["conversation_id"]
    r = await client.post(f"/api/conversations/{cid}/edit", json={"message_index": 0, "message": "edited"}, headers=h)
    assert r.json()["answer"] == "echo: edited"
    r = await client.post(f"/api/conversations/{cid}/regenerate", json={}, headers=h)
    assert r.status_code == 200
    msgs = (await client.get(f"/api/conversations/{cid}/messages", headers=h)).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[0]["content"] == "edited"
    assert (await client.post(f"/api/conversations/{cid}/edit", json={"message_index": 1, "message": "x"}, headers=h)).status_code == 400
