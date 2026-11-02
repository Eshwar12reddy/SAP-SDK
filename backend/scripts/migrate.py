"""Safe database migration entrypoint (run by the `migrate` compose service).

1. Wait for PostgreSQL to accept connections.
2. Fresh database (no app tables)            -> alembic upgrade head.
3. alembic_version present                   -> alembic upgrade head.
4. App tables but no alembic_version (legacy
   database created by create_all)           -> verify the live schema matches the
   models/baseline; only if identical, `alembic stamp 0001`, then upgrade head.
   Any difference aborts with a non-zero exit code and changes nothing.

Never drops or truncates anything.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.database import Base

BASELINE = "0001"


def url() -> str:
    value = os.environ["DATABASE_URL"]
    return value.replace("postgresql://", "postgresql+psycopg://", 1) if value.startswith("postgresql://") else value


def wait_for_db(engine, attempts: int = 30) -> None:
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect():
                return
        except Exception as error:
            print(f"[migrate] database not ready ({attempt}/{attempts}): {type(error).__name__}", flush=True)
            time.sleep(2)
    sys.exit("[migrate] database never became ready")


def main() -> None:
    engine = create_engine(url(), pool_pre_ping=True)
    wait_for_db(engine)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))

    tables = set(inspect(engine).get_table_names())
    app_tables = tables & set(Base.metadata.tables)
    if "alembic_version" in tables:
        print("[migrate] alembic_version found: upgrading to head", flush=True)
    elif not app_tables:
        print("[migrate] empty database: creating schema from baseline", flush=True)
    else:
        print(f"[migrate] existing unversioned schema detected ({len(app_tables)} app tables); verifying equivalence", flush=True)
        with engine.connect() as connection:
            diffs = compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata)
        if diffs:
            print("[migrate] ABORT: live schema differs from the baseline. Nothing was changed.", file=sys.stderr)
            for diff in diffs:
                print(f"[migrate]   {diff}", file=sys.stderr)
            sys.exit(2)
        print(f"[migrate] schema identical to baseline: stamping {BASELINE} (no DDL executed)", flush=True)
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, "head")
    print("[migrate] done", flush=True)


if __name__ == "__main__":
    main()
