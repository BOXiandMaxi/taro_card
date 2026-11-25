"""One-time remap of the three existing production account IDs."""

import argparse
from getpass import getpass

from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.models import AIUsageLog, AuthSession, Reading, User, UserIdSequence


EXPECTED_IDS = (1, 30001, 120001)
ID_MAP = {30001: 2, 120001: 3}
TARGET_IDS = (1, 2, 3)
USER_REFERENCES = (AuthSession.__table__.c.user_id, Reading.__table__.c.user_id)
SCOPE = AIUsageLog.__table__.c.quota_scope


def check_references(connection):
    actual = set(connection.execute(text("""
        SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE REFERENCED_TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME = 'users'
    """)).tuples())
    expected = {
        (connection.engine.url.database, column.table.name, column.name, "id")
        for column in USER_REFERENCES
    }
    if actual != expected:
        raise ValueError("The actual foreign keys differ from the expected account references.")


def _count(connection, table, condition=True):
    return connection.scalar(select(func.count()).select_from(table).where(condition))


def _validate_links(connection):
    for column in USER_REFERENCES:
        if _count(connection, column.table, column.is_not(None) & column.not_in(select(User.id))):
            raise ValueError(f"Orphan account reference found in {column.table.name}.")


def _snapshot(connection, ids):
    if tuple(connection.scalars(select(User.id).order_by(User.id))) != ids:
        raise ValueError(f"Expected exactly these account IDs: {ids}.")
    sequence = list(connection.execute(select(UserIdSequence.id, UserIdSequence.last_id)).tuples())
    if len(sequence) != 1 or sequence[0][0] != 1:
        raise ValueError("Apply the account ID allocator migration first.")
    _validate_links(connection)
    tables = (User.__table__, *(column.table for column in USER_REFERENCES), SCOPE.table)
    totals = {table.name: _count(connection, table) for table in tables}
    references = {
        column.table.name: [_count(connection, column.table, column == user_id) for user_id in ids]
        for column in USER_REFERENCES
    }
    scopes = [_count(connection, SCOPE.table, SCOPE == f"user:{user_id}") for user_id in ids]
    return totals, references, scopes, sequence[0][1]


def remap_accounts(connection, *, apply=False):
    """Require an open transaction and session FK checks disabled for apply."""
    if apply:
        # Take the lock used by registration before checking the account IDs.
        lock = connection.execute(update(UserIdSequence).where(UserIdSequence.id == 1).values(
            last_id=UserIdSequence.last_id + 1,
        ))
        if lock.rowcount != 1:
            raise ValueError("Apply the account ID allocator migration first.")
    before_totals, before_references, before_scopes, _ = _snapshot(connection, EXPECTED_IDS)
    if _count(connection, SCOPE.table, SCOPE.in_(["user:2", "user:3"])):
        raise ValueError("Destination account IDs already have quota history.")
    if not apply:
        return before_totals

    for old_id, new_id in ID_MAP.items():
        result = connection.execute(update(User).where(User.id == old_id).values(id=new_id))
        if result.rowcount != 1:
            raise ValueError("An account changed during the remap.")
        for column in USER_REFERENCES:
            connection.execute(update(column.table).where(column == old_id).values({column: new_id}))
        connection.execute(update(AIUsageLog).where(SCOPE == f"user:{old_id}").values(
            quota_scope=f"user:{new_id}",
        ))
    connection.execute(update(UserIdSequence).where(UserIdSequence.id == 1).values(last_id=3))

    totals, references, scopes, last_id = _snapshot(connection, TARGET_IDS)
    if (
        (totals, references, scopes, last_id) != (before_totals, before_references, before_scopes, 3)
        or _count(connection, SCOPE.table, SCOPE.in_(["user:30001", "user:120001"]))
    ):
        raise ValueError("Account ID remap verification failed.")
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the verified remap during maintenance.")
    args = parser.parse_args()
    try:
        url = make_url(getpass("TiDB SQLAlchemy DATABASE_URL: "))
        if url.drivername != "mysql+pymysql" or url.database != "tarot_reading":
            raise ValueError("Connect to the tarot_reading database using mysql+pymysql.")
        engine = create_engine(url, hide_parameters=True, poolclass=NullPool)
    except (SQLAlchemyError, ValueError):
        parser.exit(1, "Check the TiDB URL and database name.\n")

    try:
        with engine.connect() as connection:
            if "tidb" not in connection.scalar(text("SELECT VERSION()")).lower():
                raise ValueError("This tool requires TiDB.")
            if connection.scalar(text("SELECT @@SESSION.foreign_key_checks")) != 1:
                raise ValueError("The connection must start with foreign key checks enabled.")
            connection.rollback()
            if args.apply:
                # Preflight must see a registration committed while waiting for the lock.
                connection.execution_options(isolation_level="READ COMMITTED")
                connection.execute(text("SET SESSION tidb_txn_mode = 'pessimistic'"))
                connection.commit()
            try:
                with connection.begin():
                    check_references(connection)
                    if args.apply:
                        connection.execute(text("SET SESSION foreign_key_checks = 0"))
                    totals = remap_accounts(connection, apply=args.apply)
                    if args.apply:
                        connection.execute(text("SET SESSION foreign_key_checks = 1"))
            finally:
                if args.apply:
                    connection.execute(text("SET SESSION foreign_key_checks = 1"))
                    connection.rollback()
    except ValueError as error:
        parser.exit(1, f"Stopped. {error}\n")
    except SQLAlchemyError:
        parser.exit(1, "Database operation failed. Verify current IDs before retrying.\n")
    finally:
        engine.dispose()

    mode = "Committed" if args.apply else "Dry run passed"
    print(f"{mode}. Account IDs {EXPECTED_IDS} -> {TARGET_IDS}. Row counts: {totals}")


if __name__ == "__main__":
    main()
