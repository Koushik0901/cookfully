from collections.abc import Callable, Iterator
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
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
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS "vector"'))
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


@pytest.fixture
def onboarding_payload() -> dict[str, object]:
    return {"state": "pending", "version": 1}


@pytest.fixture
def recipe_image_bytes() -> Callable[[tuple[int, int]], bytes]:
    def build(size: tuple[int, int] = (2, 2)) -> bytes:
        buffer = BytesIO()
        Image.new("RGB", size, (62, 116, 74)).save(buffer, format="PNG")
        return buffer.getvalue()

    return build


@pytest.fixture
def collection_payload() -> dict[str, object]:
    return {"name": "Weeknight favourites", "position": 0, "version": 1}


@pytest.fixture
def shopping_stop_payload() -> dict[str, object]:
    return {"name": "Market", "position": 0, "version": 1}


@pytest.fixture
def completed_grocery_list_payload() -> dict[str, object]:
    return {"status": "completed", "version": 2, "items": []}
