"""Page-view counting and calendar dates for the Thailand report."""

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest, digest
from secrets import token_hex
from threading import Lock
from time import monotonic

from fastapi import Request, Response
from sqlalchemy import case, delete, distinct, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AnalyticsPageView
from app.services.auth import TOKEN_PATTERN, client_hash

REPORT_TIMEZONE = timezone(timedelta(hours=7), "Asia/Bangkok")
RETENTION_DAYS = 30
COOKIE_NAME = "tarot-analytics"
CLIENT_PER_MINUTE = 120
TOTAL_PER_MINUTE = 1000
CLEANUP_BATCH_SIZE = 1000


class PageViewLimit:
    """Bound writes and admission state per process without storing IPs in the database."""

    def __init__(self):
        self._lock = Lock()
        self._minute = -1
        self._total = 0
        self._clients: dict[str, int] = {}
        self._cleanup_minute = -1

    def admit(self, request: Request) -> bool:
        client = client_hash(request, "analytics")
        with self._lock:
            minute = int(monotonic() // 60)
            if minute != self._minute:
                self._minute = minute
                self._total = 0
                self._clients.clear()
            attempts = self._clients.get(client, 0)
            if self._total >= TOTAL_PER_MINUTE or attempts >= CLIENT_PER_MINUTE:
                return False
            self._total += 1
            self._clients[client] = attempts + 1
            return True

    def claim_cleanup(self) -> bool:
        with self._lock:
            minute = int(monotonic() // 60)
            if self._cleanup_minute == minute:
                return False
            self._cleanup_minute = minute
            return True


def report_time(now: datetime) -> datetime:
    return now.replace(tzinfo=timezone.utc).astimezone(REPORT_TIMEZONE)


def report_start(day: date, days: int = RETENTION_DAYS) -> date:
    return day - timedelta(days=days - 1)


def purge_batch(session: Session, day: date) -> int:
    views = AnalyticsPageView
    expired = views.report_day < report_start(day)
    with session.begin():
        ids = list(session.scalars(
            select(views.event_id).where(expired)
            .order_by(views.report_day, views.event_id).limit(CLEANUP_BATCH_SIZE)
        ))
        if not ids:
            return 0
        result = session.execute(delete(views).where(expired, views.event_id.in_(ids)))
        return result.rowcount


def _signature(day: date, token: str) -> str:
    secret = get_settings().secret_key.get_secret_value().encode()
    return digest(secret, f"analytics-cookie:{day.isoformat()}:{token}".encode(), "sha256").hex()


def browser_hash(request: Request, response: Response, now: datetime) -> str:
    local = report_time(now)
    day = local.date()
    secure = request.url.scheme == "https" or get_settings().cookie_secure
    name = f"__Host-{COOKIE_NAME}" if secure else COOKIE_NAME
    cookie = request.cookies.get(name, "")
    token, _, signature = cookie.partition(".")
    if not (
        TOKEN_PATTERN.fullmatch(token) and TOKEN_PATTERN.fullmatch(signature)
        and compare_digest(signature, _signature(day, token))
    ):
        token = token_hex(32)
        midnight = datetime.combine(day + timedelta(days=1), time.min, tzinfo=REPORT_TIMEZONE)
        response.set_cookie(
            name, f"{token}.{_signature(day, token)}",
            max_age=max(1, int((midnight - local).total_seconds())),
            httponly=True, secure=secure, samesite="lax", path="/",
        )
    return sha256(f"{day.isoformat()}:{token}".encode()).hexdigest()


def summarize(session: Session, day: date, days: int) -> dict:
    first = report_start(day, days)
    views = AnalyticsPageView
    within = views.report_day.between(first, day)
    counts = {
        visit_day: (page_views, browser_days, signed_in_views)
        for visit_day, page_views, browser_days, signed_in_views in session.execute(
            select(
                views.report_day,
                func.count(),
                func.count(distinct(views.browser_hash)),
                func.sum(case((views.signed_in.is_(True), 1), else_=0)),
            ).where(within).group_by(views.report_day)
        )
    }
    daily = []
    for offset in range(days):
        current = first + timedelta(days=offset)
        page_views, browser_days, _ = counts.get(current, (0, 0, 0))
        daily.append({"day": current, "page_views": page_views, "browser_days": browser_days})

    page_views = sum(row[0] for row in counts.values())
    signed_in_views = sum(row[2] for row in counts.values())
    page_count = func.count().label("page_views")
    pages = session.execute(
        select(views.route_key, page_count).where(within)
        .group_by(views.route_key).order_by(page_count.desc(), views.route_key)
    )
    return {
        "days": days,
        "timezone": REPORT_TIMEZONE.tzname(None),
        "page_views": page_views,
        "browser_days": sum(row[1] for row in counts.values()),
        "signed_in_views": signed_in_views,
        "guest_views": page_views - signed_in_views,
        "daily": daily,
        "top_pages": [{"route_key": route_key, "page_views": count} for route_key, count in pages],
    }
