from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.base import utc_now
from app.models import AIUsageLog, AuthSession, Reading, User, UserIdSequence
from scripts.renumber_users import remap_accounts
from test_accounts import auth_settings, register
from test_reading_engine import PRESET, app, client, database


def test_remap_preserves_account_links_and_registration_continues_at_four(client, database):
    if database.dialect.name != "sqlite":
        pytest.skip("Offline account remap test requires SQLite")

    with Session(database) as session, session.begin():
        session.add_all([
            User(id=1, email="admin@example.test", password_hash="unused", role="admin"),
            User(id=30001, email="second@example.test", password_hash="second-hash"),
            User(id=120001, email="third@example.test", password_hash="third-hash"),
        ])
        session.get(UserIdSequence, 1).last_id = 120001
        session.flush()
        reading = Reading(user_id=30001, **PRESET)
        session.add_all([
            reading,
            AuthSession(token_hash="c" * 64, user_id=120001, expires_at=utc_now() + timedelta(days=1)),
            AIUsageLog(provider="test", model="test", status="success", quota_scope="user:30001"),
        ])
        session.flush()
        reading_id = reading.id

    with database.connect() as connection:
        assert remap_accounts(connection)["users"] == 3
        assert tuple(connection.scalars(select(User.id).order_by(User.id))) == (1, 30001, 120001)
        connection.rollback()

        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            with connection.begin():
                assert remap_accounts(connection, apply=True)["users"] == 3
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()

        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []

    with Session(database) as session:
        assert session.get(User, 1).role == "admin"
        assert session.get(User, 2).password_hash == "second-hash"
        assert session.get(User, 3).password_hash == "third-hash"
        assert session.get(Reading, reading_id).user_id == 2
        assert session.get(AuthSession, "c" * 64).user_id == 3
        assert session.scalar(select(AIUsageLog.quota_scope).where(
            AIUsageLog.quota_scope.is_not(None),
        )) == "user:2"

    assert register(client).json()["id"] == 4
