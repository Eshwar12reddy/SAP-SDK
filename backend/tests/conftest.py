import os

# Must be set before the app is imported: settings are read at import time.
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["CORS_ORIGINS"] = "https://staging.example.test"

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.api import chat as chat_api
from app.database import Base, get_session
from app.main import app
from app.services import memory_service


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine, monkeypatch):
    """HTTP client against the real FastAPI app backed by an in-memory SQLite database."""
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_session():
        async with sessions() as s:
            try:
                yield s
            except BaseException:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(chat_api, "Session", sessions)
    monkeypatch.setattr(memory_service, "Session", sessions)
    monkeypatch.setattr(database, "Session", sessions)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.sessions = sessions
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def fake_ai(monkeypatch):
    """Replace the OpenRouter-backed answer functions with deterministic fakes."""
    calls = []

    async def answer(db, cid, question, settings, response_language=None):
        calls.append(question)
        return f"echo: {question}"

    async def answer_stream(db, cid, question, settings, response_language=None):
        calls.append(question)
        for token in ("Hello", " ", "world"):
            yield token

    monkeypatch.setattr(chat_api, "answer", answer)
    monkeypatch.setattr(chat_api, "answer_stream", answer_stream)
    return calls


async def register_and_login(client, email="user@example.com", password="correct-horse-1"):
    r = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
