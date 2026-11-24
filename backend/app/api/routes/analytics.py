import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import UUID4, BaseModel, ConfigDict, ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.routes.auth import PrivateAuthRoute
from app.api.routes.reference import DatabaseSession
from app.database.base import utc_now
from app.database.session import start_write
from app.models import AnalyticsPageView, User
from app.services import analytics, auth

router = APIRouter(tags=["analytics"], route_class=PrivateAuthRoute)
logger = logging.getLogger(__name__)
MAX_EVENT_BYTES = 512
CRAWLER = re.compile(r"bot\b|crawl|spider|headless|preview|slurp", re.IGNORECASE)


class PageViewEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID4
    route_key: Literal[
        "home", "categories", "questions", "spreads", "shuffle", "reveal", "result",
        "history", "account", "login", "register", "privacy",
    ]


async def _admit_event(request: Request) -> PageViewEvent | None:
    # Required trusted Origin and JSON exclude cross-site browser form submissions.
    auth.check_origin(request, required=True)
    if request.headers.get("Sec-GPC") == "1":
        return None
    agent = request.headers.get("User-Agent", "")
    if not agent or CRAWLER.search(agent):
        return None
    if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Expected a JSON page view")
    if not request.app.state.page_view_limit.admit(request):
        raise HTTPException(429, "Too many page views", headers={"Retry-After": "60"})

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_EVENT_BYTES:
            raise HTTPException(413, "Page view payload too large")
        body.extend(chunk)
    try:
        return PageViewEvent.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, "Invalid page view") from None


@router.post("/analytics/page-view", status_code=204)
def page_view(
    request: Request, response: Response, session: DatabaseSession,
    event: Annotated[PageViewEvent | None, Depends(_admit_event)],
) -> None:
    if event is None:
        return

    now = utc_now()
    report_day = analytics.report_time(now).date()
    event_id = str(event.event_id)
    try:
        with session.begin():
            start_write(session)
            if session.get(AnalyticsPageView, event_id) is not None:
                return
            session.add(AnalyticsPageView(
                event_id=event_id,
                report_day=report_day,
                route_key=event.route_key,
                browser_hash=analytics.browser_hash(request, response, now),
                signed_in=auth.active_session(session, request) is not None,
                created_at=now,
            ))
    except IntegrityError:
        # A concurrent retry can win the primary-key insert.
        if session.get(AnalyticsPageView, event_id) is None:
            raise
        session.rollback()
    if request.app.state.page_view_limit.claim_cleanup():
        try:
            analytics.purge_batch(session, report_day)
        except SQLAlchemyError as exc:
            logger.warning("Analytics retention cleanup failed: %s", type(exc).__name__)


@router.get("/admin/analytics")
def report(session: DatabaseSession, request: Request, days: Annotated[int, Query(ge=1, le=30)] = 7) -> dict:
    auth.check_origin(request)
    account = auth.active_session(session, request)
    if account is None:
        raise HTTPException(401, "Authentication required")
    user = session.get(User, account.user_id)
    if user is None or user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    if days not in (1, 7, 30):
        raise HTTPException(422, "Choose a 1, 7 or 30 day range")
    return analytics.summarize(session, analytics.report_time(utc_now()).date(), days)
