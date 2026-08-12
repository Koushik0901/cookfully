from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cookfully.infrastructure.config import Settings


def create_database_engine(settings: Settings, *, echo: bool = False) -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True, echo=echo)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def session_dependency(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        yield session
