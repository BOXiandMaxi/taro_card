import re
import secrets
from datetime import timedelta
from hashlib import sha256
from hmac import compare_digest, digest
from math import ceil

from fastapi import HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.base import utc_now
from app.database.session import start_write
from app.models import AuthRateLimit, AuthSession

SESSION_COOKIE = "tarot-session"
CSRF_COOKIE = "tarot-csrf"
TOKEN_PATTERN = re.compile(r"[0-9a-f]{64}")


def check_origin(request: Request, *, required: bool = False) -> None:
    if request.url.scheme != "https" and request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(403, "HTTPS required")
    origin = request.headers.get("origin")
    if origin is None and not required:
        return
    same_origin = f"{request.url.scheme}://{request.url.netloc}"
    if origin != same_origin and origin not in get_settings().cors_origins:
        raise HTTPException(403, "Origin not allowed")


def _secure(request: Request) -> bool:
    return get_settings().cookie_secure or request.url.scheme == "https"


def _cookie_name(request: Request, name: str) -> str:
    return f"__Host-{name}" if _secure(request) else name


def _cookie_token(request: Request, name: str) -> str | None:
    token = request.cookies.get(_cookie_name(request, name), "")
    return token if TOKEN_PATTERN.fullmatch(token) else None


def _set_cookie(request: Request, response: Response, name: str, token: str, max_age: int) -> None:
    response.set_cookie(
        _cookie_name(request, name), token, httponly=True, secure=_secure(request),
        samesite="lax", path="/", max_age=max_age,
    )


def _token_hash(token: str) -> str:
    return sha256(token.encode("ascii")).hexdigest()


def active_session(session: Session, request: Request) -> AuthSession | None:
    token = _cookie_token(request, SESSION_COOKIE)
    if token is None:
        return None
    return session.scalar(select(AuthSession).where(
        AuthSession.token_hash == _token_hash(token),
        AuthSession.expires_at > utc_now(),
        AuthSession.revoked_at.is_(None),
    ))


def _csrf_token(request: Request, account: AuthSession | None) -> str | None:
    if account is not None:
        return digest(bytes.fromhex(account.token_hash), b"tarot-session-csrf", "sha256").hex()
    return _cookie_token(request, CSRF_COOKIE)


def issue_csrf(request: Request, response: Response, account: AuthSession | None) -> str:
    token = _csrf_token(request, account)
    if token is None:
        token = secrets.token_hex(32)
        _set_cookie(request, response, CSRF_COOKIE, token, 3600)
    return token


def check_csrf(request: Request, account: AuthSession | None) -> None:
    check_origin(request, required=True)
    expected = _csrf_token(request, account)
    supplied = request.headers.get("X-CSRF-Token", "")
    if expected is None or not TOKEN_PATTERN.fullmatch(supplied) or not compare_digest(expected, supplied):
        raise HTTPException(403, "Invalid CSRF token")


def start_session(session: Session, request: Request, response: Response, user_id: int) -> None:
    revoke_session(session, request)
    token = secrets.token_hex(32)
    ttl = get_settings().session_ttl_seconds
    session.add(AuthSession(
        token_hash=_token_hash(token), user_id=user_id, expires_at=utc_now() + timedelta(seconds=ttl),
    ))
    _set_cookie(request, response, SESSION_COOKIE, token, ttl)


def revoke_session(session: Session, request: Request) -> None:
    token = _cookie_token(request, SESSION_COOKIE)
    if token is not None:
        session.execute(update(AuthSession).where(
            AuthSession.token_hash == _token_hash(token), AuthSession.revoked_at.is_(None),
        ).values(revoked_at=utc_now()))


def clear_session_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(
        _cookie_name(request, SESSION_COOKIE), path="/", httponly=True, secure=_secure(request), samesite="lax",
    )


def client_hash(request: Request, purpose: str) -> str:
    host = request.client.host if request.client else "unknown"
    secret = get_settings().secret_key.get_secret_value()
    return digest(secret.encode(), f"{purpose}:{host}".encode(), "sha256").hex()


def count_auth_attempt(session: Session, request: Request) -> None:
    settings = get_settings()
    key = client_hash(request, "auth")
    with session.begin():
        start_write(session)
        values = {"client_hash": key, "window_started_at": utc_now(), "attempts": 0}
        if session.get_bind().dialect.name == "mysql":
            insert = mysql_insert(AuthRateLimit).values(**values)
            session.execute(insert.on_duplicate_key_update(client_hash=key))
        else:
            insert = sqlite_insert(AuthRateLimit).values(**values)
            session.execute(insert.on_conflict_do_nothing(index_elements=["client_hash"]))
        counter = session.get(AuthRateLimit, key, with_for_update=True)
        now = utc_now()
        remaining = timedelta(seconds=settings.auth_window_seconds) - (now - counter.window_started_at)
        if remaining <= timedelta(0):
            counter.window_started_at = now
            counter.attempts = 0
        if counter.attempts >= settings.auth_attempt_limit:
            raise HTTPException(429, "Too many authentication attempts", headers={
                "Retry-After": str(max(1, ceil(remaining.total_seconds()))),
            })
        counter.attempts += 1
