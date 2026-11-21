from functools import lru_cache

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine():
    # Lazy construction keeps liveness independent from configuration/connectivity.
    engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_recycle=1800)

    @event.listens_for(engine, "connect")
    def set_utc(dbapi_connection, _connection_record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")

    return engine


def get_session():
    factory = sessionmaker(bind=get_engine(), class_=Session, expire_on_commit=False)
    with factory() as session:
        yield session


def start_write(session: Session) -> None:
    # SQLite ignores FOR UPDATE. Reserve the write before reading.
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
