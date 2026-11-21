"""Count or purge expired sessions and authentication rate-limit windows."""
import argparse
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.base import utc_now
from app.database.session import get_engine, start_write
from app.models import AuthRateLimit, AuthSession


def cleanup_auth(session: Session, *, apply: bool = False, batch_size: int = 500) -> tuple[int, int]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    now = utc_now()
    session_expired = AuthSession.expires_at <= now
    rate_expired = AuthRateLimit.window_started_at <= now - timedelta(
        seconds=get_settings().auth_window_seconds,
    )
    if not apply:
        with session.begin():
            return (
                session.scalar(select(func.count()).select_from(AuthSession).where(session_expired)),
                session.scalar(select(func.count()).select_from(AuthRateLimit).where(rate_expired)),
            )

    removed = []
    for model, condition, order in (
        (AuthSession, session_expired, AuthSession.expires_at),
        (AuthRateLimit, rate_expired, AuthRateLimit.window_started_at),
    ):
        count = 0
        while True:
            with session.begin():
                start_write(session)
                rows = list(session.scalars(
                    select(model).where(condition).order_by(order).limit(batch_size).with_for_update(),
                ))
                for row in rows:
                    session.delete(row)
            count += len(rows)
            if len(rows) < batch_size:
                removed.append(count)
                break
    return tuple(removed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete expired rows; default only counts them.")
    args = parser.parse_args()
    with Session(get_engine()) as session:
        sessions, limits = cleanup_auth(session, apply=args.apply)
    print(f"Expired sessions: {sessions}; expired auth rate-limit rows: {limits}")


if __name__ == "__main__":
    main()
