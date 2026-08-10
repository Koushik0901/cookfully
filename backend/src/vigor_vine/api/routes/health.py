from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import Engine, text

from vigor_vine import __version__

if TYPE_CHECKING:
    type RedisClient = Redis[str]
else:
    RedisClient = Redis

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    database: str
    broker: str
    version: str


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_redis(request: Request) -> RedisClient:
    client: RedisClient = request.app.state.redis
    return client


@router.get("/health", response_model=HealthResponse)
def health(
    engine: Annotated[Engine, Depends(get_engine)],
    redis_client: Annotated[RedisClient, Depends(get_redis)],
) -> HealthResponse:
    database = "ok"
    broker = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # health endpoint deliberately converts dependency errors to safe state
        database = "unavailable"
    try:
        redis_client.ping()
    except Exception:  # health endpoint deliberately converts dependency errors to safe state
        broker = "unavailable"
    return HealthResponse(
        status="ok" if database == broker == "ok" else "degraded",
        database=database,
        broker=broker,
        version=__version__,
    )
