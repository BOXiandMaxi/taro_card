"""Count or purge guest readings older than the configured retention period."""
import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.readings import guest_cutoff
from app.database.base import utc_now
from app.database.session import get_engine, start_write
from app.models import Reading


def cleanup_guests(session: Session, *, apply: bool = False, batch_size: int = 500) -> int:
    cutoff = guest_cutoff(utc_now())
    expired = Reading.user_id.is_(None) & (Reading.created_at <= cutoff)
    if not apply:
        with session.begin():
            return session.scalar(select(func.count()).select_from(Reading).where(expired))

    deleted = 0
    while True:
        with session.begin():
            start_write(session)
            readings = list(session.scalars(
                select(Reading).where(expired).order_by(Reading.created_at, Reading.id)
                .limit(batch_size).with_for_update()
            ))
            for reading in readings:
                session.delete(reading)
        deleted += len(readings)
        if len(readings) < batch_size:
            return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete expired guest readings. The default counts them.")
    args = parser.parse_args()
    with Session(get_engine()) as session:
        count = cleanup_guests(session, apply=args.apply)
    print(f"Expired guest readings {'deleted' if args.apply else 'eligible for deletion'}: {count}")


if __name__ == "__main__":
    main()
