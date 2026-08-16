"""Guard migration/model drift: schema built by `alembic upgrade head` must match
the ORM metadata for server-side defaults, because application inserts rely on them."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from cookfully.infrastructure.config import Settings

ROOT = Path(__file__).resolve().parents[2]

TIMESTAMP_COLUMNS = {
    "recipe_collections": ("created_at", "updated_at"),
    "grocery_shopping_stops": ("created_at", "updated_at"),
    "remembered_grocery_placements": ("created_at", "updated_at"),
}


@pytest.fixture
def migrated_database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A disposable schema migrated to head with Alembic (not metadata DDL)."""

    base_url = Settings().database_url
    schema = f"mig_{uuid4().hex}"
    admin_engine = create_engine(base_url)
    with admin_engine.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS "citext"'))
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS "btree_gist"'))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'CREATE DOMAIN "{schema}".citext AS public.citext'))
    url = make_url(base_url).update_query_dict({"options": f"-csearch_path={schema}"})
    isolated_url = url.render_as_string(hide_password=False)
    monkeypatch.setattr(
        "cookfully.infrastructure.config.get_settings",
        lambda: Settings(database_url=isolated_url),
    )
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(config, "head")
    try:
        yield isolated_url
    finally:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def test_migrated_schema_has_timestamp_server_defaults(migrated_database_url: str) -> None:
    engine = create_engine(migrated_database_url)
    inspector = inspect(engine)
    for table, columns in TIMESTAMP_COLUMNS.items():
        migrated = {column["name"]: column for column in inspector.get_columns(table)}
        for name in columns:
            assert migrated[name]["default"] is not None, (
                f"{table}.{name} has no server default after migrations; "
                "ORM inserts that omit timestamps will fail."
            )
    engine.dispose()
