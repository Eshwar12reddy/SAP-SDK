from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import Settings
from app.main import limiter
from tests.conftest import register_and_login

SECRET = "test-secret-" + "x" * 40


async def test_register_login_and_protected_call(client):
    headers = await register_and_login(client)
    r = await client.get("/api/conversations", headers=headers)
    assert r.status_code == 200 and r.json() == []


async def test_duplicate_registration_is_conflict_and_email_case_insensitive(client):
    await register_and_login(client, "A@Example.com")
    r = await client.post("/api/auth/register", json={"email": "a@example.com", "password": "correct-horse-1"})
    assert r.status_code == 409


async def test_wrong_password_and_unknown_user_share_one_message(client):
    await register_and_login(client)
    bad = await client.post("/api/auth/login", json={"email": "user@example.com", "password": "wrong-password"})
    unknown = await client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()


async def test_passwords_are_stored_hashed(client):
    await register_and_login(client)
    from sqlalchemy import select
    from app.database import User
    async with client.sessions() as s:
        user = await s.scalar(select(User))
    assert user.password_hash != "correct-horse-1" and user.password_hash.startswith("$argon2")


@pytest.mark.parametrize("payload", [
    {"email": "a@b.co", "password": "short"},
    {"email": "a@b.co", "password": "x" * 129},
    {"email": "a@b.co"},
    {},
])
async def test_invalid_auth_input_is_422(client, payload):
    assert (await client.post("/api/auth/register", json=payload)).status_code == 422


@pytest.mark.parametrize("header", [None, "", "Token abc", "Bearer ", "Bearer not-a-jwt"])
async def test_missing_or_malformed_token_is_401(client, header):
    headers = {} if header is None else {"Authorization": header}
    assert (await client.get("/api/conversations", headers=headers)).status_code == 401


async def test_expired_token_is_rejected(client):
    await register_and_login(client)
    token = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=5)}, SECRET, algorithm="HS256")
    assert (await client.get("/api/conversations", headers={"Authorization": f"Bearer {token}"})).status_code == 401


async def test_token_signed_with_other_secret_or_alg_none_is_rejected(client):
    await register_and_login(client)
    forged = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "y" * 40, algorithm="HS256")
    none_alg = jwt.encode({"sub": "1"}, None, algorithm="none")
    for token in (forged, none_alg):
        assert (await client.get("/api/conversations", headers={"Authorization": f"Bearer {token}"})).status_code == 401


async def test_token_for_unknown_user_is_rejected(client):
    token = jwt.encode({"sub": "9999", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, SECRET, algorithm="HS256")
    assert (await client.get("/api/conversations", headers={"Authorization": f"Bearer {token}"})).status_code == 401


async def test_auth_rate_limit_kicks_in(client):
    limiter.enabled = True
    limiter.reset()
    try:
        codes = [(await client.post("/api/auth/login", json={"email": "x@y.co", "password": "wrong-password"})).status_code for _ in range(12)]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert codes[:10] == [401] * 10 and 429 in codes[10:]


@pytest.mark.parametrize("secret", ["", "change-me", "short", "replace-with-a-long-random-secret"])
def test_weak_jwt_secrets_are_refused(secret):
    with pytest.raises(ValueError):
        Settings(jwt_secret=secret, _env_file=None)


def test_jwt_secret_has_no_default(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


async def test_cors_only_allows_configured_origins(client):
    ok = await client.options("/api/health", headers={"Origin": "https://staging.example.test", "Access-Control-Request-Method": "GET"})
    bad = await client.options("/api/health", headers={"Origin": "http://192.168.1.5:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "https://staging.example.test"
    assert "access-control-allow-origin" not in bad.headers
