from collections.abc import Callable, Iterator
from contextlib import suppress
from io import BytesIO
from uuid import uuid4

import pytest
from hypothesis import settings
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models import Base

# Property tests: a hung example fails the test, never the machine's clock, so no per-example
# deadline. Pull requests use `--hypothesis-profile=ci`, which replays the same examples every
# time (a rare random failure must not block unrelated work); pushes to main and local runs
# explore fresh ones, and Hypothesis prints the failing example so it can be pinned as a test.
settings.register_profile("default", deadline=None)
settings.register_profile("ci", deadline=None, derandomize=True, print_blob=True)
settings.load_profile("default")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Create the shared extensions once, before any xdist worker starts.

    `CREATE EXTENSION IF NOT EXISTS` is not safe to run concurrently: two workers that both see
    the extension missing collide on the catalog's unique index. Only the controller process
    (no `workerinput`) runs this; workers then find the extensions already installed.
    """

    if hasattr(session.config, "workerinput"):
        return
    engine = create_engine(Settings().database_url)
    try:
        # Without a database the DB-backed tests report their own, clearer, error.
        with suppress(Exception), engine.begin() as connection:
            for extension in ("citext", "btree_gist", "vector"):
                connection.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))
    finally:
        engine.dispose()


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
