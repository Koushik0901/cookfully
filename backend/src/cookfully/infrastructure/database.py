from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cookfully.infrastructure.config import Settings


def create_database_engine(settings: Settings, *, echo: bool = False) -> Engine:
    options: dict[str, object] = {
        "pool_pre_ping": True,
        "echo": echo,
    }
    # SQLite uses a different pool implementation and rejects PostgreSQL pool
    # sizing arguments. Production/PostgreSQL gets a bounded pool so concurrent
    # API requests and worker jobs do not serialize behind SQLAlchemy's default
    # five-connection pool.
    if not settings.database_url.startswith("sqlite"):
        options.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            pool_recycle=settings.database_pool_recycle_seconds,
        )
    return create_engine(settings.database_url, **options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def session_dependency(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        yield session
