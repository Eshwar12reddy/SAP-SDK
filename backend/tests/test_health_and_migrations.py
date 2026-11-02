import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.database import Base

BACKEND = Path(__file__).resolve().parents[1]


async def test_liveness_needs_no_database(client):
    r = await client.get("/api/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_readiness_ok_when_database_migrated(client, db_engine, monkeypatch):
    from app.api import health
    monkeypatch.setattr(health, "engine", db_engine)
    async with db_engine.begin() as c:
        await c.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        await c.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    r = await client.get("/api/health/ready")
    assert r.status_code == 200 and r.json()["status"] == "ready"


async def test_readiness_503_when_not_migrated(client, db_engine, monkeypatch):
    from app.api import health
    monkeypatch.setattr(health, "engine", db_engine)
    r = await client.get("/api/health/ready")
    assert r.status_code == 503 and r.json()["migrations"] == "missing"


async def test_readiness_503_without_leaking_connection_details(client):
    # conftest points DATABASE_URL at an unreachable port with credentials "test:test"
    r = await client.get("/api/health/ready")
    assert r.status_code == 503 and r.json()["database"] == "unavailable"
    assert "test:test" not in r.text and "127.0.0.1" not in r.text


def _alembic(url, *args):
    env = {**os.environ, "ALEMBIC_DATABASE_URL": url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)


POSTGRES = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="set TEST_POSTGRES_URL to a disposable PostgreSQL database")


def _reset_disposable_db(url):
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))  # disposable test DB only
        c.execute(text("CREATE SCHEMA public"))
    return engine


@POSTGRES
def test_alembic_baseline_matches_models_and_downgrade_is_refused():
    url = os.environ["TEST_POSTGRES_URL"]
    engine = _reset_disposable_db(url)
    result = _alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    assert set(Base.metadata.tables) | {"alembic_version"} <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata) == []
    r = _alembic(url, "downgrade", "base")
    assert r.returncode != 0 and "Refusing to downgrade" in r.stderr
    assert "users" in inspect(engine).get_table_names()


@POSTGRES
def test_migrations_and_safe_baseline_on_postgres():
    """Runs scripts/migrate.py against a disposable DB: empty, legacy-with-data, and drifted."""
    url = os.environ["TEST_POSTGRES_URL"]
    engine = _reset_disposable_db(url)

    def run():
        return subprocess.run([sys.executable, "scripts/migrate.py"], cwd=BACKEND, env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True)

    assert run().returncode == 0
    with engine.begin() as c:
        c.execute(text("INSERT INTO users(email,password_hash) VALUES ('p@x.co','h')"))
        c.execute(text("DROP TABLE alembic_version"))  # simulate a legacy create_all database
    assert run().returncode == 0
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM users")) == 1
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
    with engine.begin() as c:
        c.execute(text("DROP TABLE alembic_version"))
        c.execute(text("ALTER TABLE messages DROP COLUMN role"))
    r = run()
    assert r.returncode == 2 and "ABORT" in r.stderr
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM users")) == 1
