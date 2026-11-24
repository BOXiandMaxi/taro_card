"""Count or purge page views outside the latest 30 Thai calendar days."""

import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.base import utc_now
from app.database.session import get_engine
from app.models import AnalyticsPageView
from app.services.analytics import CLEANUP_BATCH_SIZE, purge_batch, report_start, report_time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete expired rows. The default only counts them.")
    args = parser.parse_args()
    day = report_time(utc_now()).date()
    with Session(get_engine()) as session:
        if not args.apply:
            count = session.scalar(select(func.count()).select_from(AnalyticsPageView).where(
                AnalyticsPageView.report_day < report_start(day),
            ))
            print(f"Expired page views: {count}")
            return
        removed = 0
        while True:
            count = purge_batch(session, day)
            removed += count
            if count < CLEANUP_BATCH_SIZE:
                break
        print(f"Expired page views deleted: {removed}")


if __name__ == "__main__":
    main()
