import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api import chat
from app.database import Conversation


class FakeRequestSession:
    def __init__(self, conversation=None, commit_error=None):
        self.conversation = conversation
        self.commit_error = commit_error
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, Conversation) and value.id is None:
                value.id = 37

    async def scalar(self, _query):
        return self.conversation

    async def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    async def rollback(self):
        self.rollbacks += 1


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class FakeStreamingSession(FakeRequestSession):
    def begin(self):
        return FakeTransaction()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_stale_or_foreign_conversation_id_is_rejected():
    db = FakeRequestSession(conversation=None)

    with pytest.raises(HTTPException) as error:
        await chat.ensure_conversation(db, user_id=2, conversation_id=37, title="hello", persist_user_message=False)

    assert error.value.status_code == 404
    assert db.commits == 0


@pytest.mark.asyncio
async def test_stream_preflight_commits_new_conversation_and_user_turn(monkeypatch):
    request_db = FakeRequestSession()
    stream_db = FakeStreamingSession(conversation=Conversation(id=37, owner_id=2, title="hello"))
    saved = []

    async def fake_save(_db, conversation_id, role, content):
        saved.append((conversation_id, role, content))

    async def fake_answer_stream(_db, _conversation_id, _question, _settings):
        yield "assistant chunk"

    monkeypatch.setattr(chat, "save", fake_save)
    monkeypatch.setattr(chat, "answer_stream", fake_answer_stream)
    monkeypatch.setattr(chat, "Session", lambda: stream_db)

    response = await chat.stream(SimpleNamespace(conversation_id=None, message="hello"), SimpleNamespace(id=2), request_db)
    body = "".join([chunk.decode() if isinstance(chunk, bytes) else chunk async for chunk in response.body_iterator])

    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {")]
    assert request_db.commits == 1
    assert saved[0] == (37, "user", "hello")
    assert saved[-1] == (37, "assistant", "assistant chunk")
    assert any(event.get("conversation_id") == 37 for event in events)
    assert any(event.get("done") is True for event in events)


@pytest.mark.asyncio
async def test_stream_preflight_rolls_back_when_initial_commit_fails(monkeypatch):
    db = FakeRequestSession(commit_error=SQLAlchemyError("commit failed"))

    async def fake_save(*_args):
        return None

    monkeypatch.setattr(chat, "save", fake_save)

    with pytest.raises(SQLAlchemyError):
        await chat.ensure_conversation(db, user_id=2, conversation_id=None, title="hello", persist_user_message=True)

    assert db.commits == 1
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_cancelled_stream_persists_nonempty_partial_response(monkeypatch):
    request_db = FakeRequestSession()
    stream_db = FakeStreamingSession(conversation=Conversation(id=37, owner_id=2, title="hello"))
    saved = []

    async def fake_save(_db, conversation_id, role, content):
        saved.append((conversation_id, role, content))
        return SimpleNamespace(id=99) if role == "user" else None

    async def cancelled_answer_stream(_db, _conversation_id, _question, _settings):
        yield "partial answer"
        raise asyncio.CancelledError()

    monkeypatch.setattr(chat, "save", fake_save)
    monkeypatch.setattr(chat, "answer_stream", cancelled_answer_stream)
    monkeypatch.setattr(chat, "Session", lambda: stream_db)

    response = await chat.stream(SimpleNamespace(conversation_id=None, message="hello"), SimpleNamespace(id=2), request_db)
    with pytest.raises(asyncio.CancelledError):
        await response.body_iterator.__anext__()
        await response.body_iterator.__anext__()
        await response.body_iterator.__anext__()

    assert (37, "user", "hello") in saved
    assert (37, "assistant", "partial answer") in saved
