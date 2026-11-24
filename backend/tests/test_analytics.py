from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import analytics as analytics_routes
from app.models import AnalyticsPageView, User
from app.services import analytics
from test_accounts import ORIGIN, PASSWORD, auth_settings, csrf, register
from test_reading_engine import app, client, database

REPORT = "/api/admin/analytics"
EVENT = "/api/analytics/page-view"


def track(client, route_key="home", event_id=None, **headers):
    return client.post(EVENT, headers={"Origin": ORIGIN, **headers}, json={
        "route_key": route_key, "event_id": event_id or str(uuid4()),
    })


def set_role(database, user_id, role):
    with Session(database) as session, session.begin():
        session.get(User, user_id).role = role


def test_only_current_database_admin_can_view_report(client, database):
    response = client.get(REPORT)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    email = f"{uuid4()}@example.test"
    response = client.post("/api/auth/register", headers=csrf(client), json={
        "email": email, "password": PASSWORD, "role": "admin",
    })
    assert response.status_code == 422
    user = register(client, email).json()
    assert user["role"] is None
    assert client.get(REPORT).status_code == 403

    set_role(database, user["id"], "admin")
    assert client.get("/api/auth/me").json()["role"] == "admin"
    assert client.get(REPORT, params={"days": 2}).status_code == 422
    response = client.get(REPORT)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"

    set_role(database, user["id"], None)
    assert client.get(REPORT).status_code == 403


def test_views_deduplicate_and_group_by_thailand_day(app, client, database, monkeypatch):
    now = datetime(2027, 1, 1, 16, 59, 0)
    monkeypatch.setattr(analytics_routes, "utc_now", lambda: now)
    event_id = str(uuid4())
    response = track(client, event_id=event_id)
    assert response.status_code == 204
    cookie = response.headers["Set-Cookie"]
    assert all(part in cookie for part in ("__Host-tarot-analytics", "HttpOnly", "Secure", "SameSite=lax", "Max-Age=60"))
    assert track(client, event_id=event_id).status_code == 204
    assert track(client, "categories").status_code == 204
    assert track(client, event_id=event_id, Origin="https://other.invalid").status_code == 403
    assert track(client, route_key="/reveal/private-id").status_code == 422

    with TestClient(app, base_url=ORIGIN) as other:
        assert track(other).status_code == 204
    account = register(client).json()
    assert track(client, "result").status_code == 204
    set_role(database, account["id"], "admin")

    # A refresh is a page view, but the browser counts once per Thai day.
    now += timedelta(minutes=1)
    assert track(client, "home").status_code == 204
    report = client.get(REPORT, params={"days": 7}).json()
    assert report["timezone"] == "Asia/Bangkok"
    assert (report["page_views"], report["browser_days"], report["signed_in_views"], report["guest_views"]) == (5, 3, 2, 3)
    assert report["daily"][-2:] == [
        {"day": "2027-01-01", "page_views": 4, "browser_days": 2},
        {"day": "2027-01-02", "page_views": 1, "browser_days": 1},
    ]
    assert report["top_pages"] == [
        {"route_key": "home", "page_views": 3},
        {"route_key": "categories", "page_views": 1},
        {"route_key": "result", "page_views": 1},
    ]
    today = client.get(REPORT, params={"days": 1}).json()
    assert (today["page_views"], today["browser_days"]) == (1, 1)


def test_collection_filters_and_limits_before_database(client, database, monkeypatch):
    monkeypatch.setattr(analytics, "CLIENT_PER_MINUTE", 1)
    now = datetime(2027, 2, 1, 4, 0, 0)
    monkeypatch.setattr(analytics_routes, "utc_now", lambda: now)
    event_id = str(uuid4())
    assert track(client, event_id=event_id, **{"Sec-GPC": "1"}).status_code == 204
    assert track(client, event_id=event_id, **{"User-Agent": "Googlebot"}).status_code == 204
    assert client.post(EVENT, json={"route_key": "home", "event_id": event_id}).status_code == 403
    with Session(database) as session:
        assert session.get(AnalyticsPageView, event_id) is None

    oversized = client.post(EVENT, headers={"Origin": ORIGIN}, json={"data": "x" * 512})
    assert oversized.status_code == 413
    assert track(client, event_id=event_id).status_code == 429
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(AnalyticsPageView).where(
            AnalyticsPageView.report_day == analytics.report_time(now).date(),
        )) == 0


def test_collection_purges_only_events_outside_thirty_calendar_days(client, database, monkeypatch):
    now = datetime(2027, 3, 15)
    monkeypatch.setattr(analytics_routes, "utc_now", lambda: now)
    records = [(str(uuid4()), now - timedelta(days=offset)) for offset in (30, 29)]
    with Session(database) as session, session.begin():
        for event_id, created in records:
            session.add(AnalyticsPageView(
                event_id=event_id, report_day=analytics.report_time(created).date(),
                route_key="home", browser_hash="a" * 64, signed_in=False, created_at=created,
            ))
    assert track(client).status_code == 204
    with Session(database) as session:
        assert session.get(AnalyticsPageView, records[0][0]) is None
        assert session.get(AnalyticsPageView, records[1][0]) is not None
