from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models import Base


@pytest.fixture
def isolated_database_url() -> Iterator[str]:
    """Use a disposable PostgreSQL schema so tests never mutate the application schema."""

    base_url = Settings().database_url
    schema = f"test_{uuid4().hex}"
    admin_engine = create_engine(base_url)
    with admin_engine.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS "citext"'))
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS "btree_gist"'))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'CREATE DOMAIN "{schema}".citext AS public.citext'))
    url = make_url(base_url).update_query_dict({"options": f"-csearch_path={schema}"})
    isolated_url = url.render_as_string(hide_password=False)
    schema_engine = create_engine(isolated_url)
    Base.metadata.create_all(schema_engine)
    try:
        yield isolated_url
    finally:
        schema_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def session_factory(isolated_database_url: str) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(isolated_database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()
