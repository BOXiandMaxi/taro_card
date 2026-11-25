import re
import secrets
from functools import lru_cache
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.routes.reference import DatabaseSession
from app.models import User, UserIdSequence
from app.services import auth


class PrivateAuthRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_response(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError as exc:
                # FastAPI normally echoes invalid input, which can contain passwords.
                errors = [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]
                response = JSONResponse({"detail": errors}, status_code=422)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            response.headers["Cache-Control"] = "no-store"
            return response

        return private_response


router = APIRouter(prefix="/auth", tags=["auth"], route_class=PrivateAuthRoute)
password_hasher = PasswordHasher()
EMAIL_LOCAL = re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class Credentials(BaseModel):
    email: str
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        local, _, domain = value.rpartition("@")
        labels = domain.split(".")
        if (
            len(value) > 254 or len(local) > 64 or not EMAIL_LOCAL.fullmatch(local)
            or len(labels) < 2 or not all(DOMAIN_LABEL.fullmatch(label) for label in labels)
        ):
            raise ValueError("Enter a valid email address")
        return value


class Registration(Credentials):
    model_config = ConfigDict(extra="forbid")

    password: SecretStr = Field(min_length=8, max_length=128)


class AccountResponse(BaseModel):
    id: int
    email: str
    role: Literal["admin"] | None = None

    @classmethod
    def from_user(cls, user: User) -> "AccountResponse":
        return cls(id=user.id, email=user.email, role="admin" if user.role == "admin" else None)


class CsrfResponse(BaseModel):
    csrf_token: str


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return password_hasher.hash(secrets.token_hex(32))


def _check_credentials_request(session: DatabaseSession, request: Request) -> None:
    with session.begin():
        auth.check_csrf(request, auth.active_session(session, request))
    auth.count_auth_attempt(session, request)


@router.get("/csrf", response_model=CsrfResponse)
def csrf(session: DatabaseSession, request: Request, response: Response):
    auth.check_origin(request)
    return CsrfResponse(csrf_token=auth.issue_csrf(request, response, auth.active_session(session, request)))


@router.post("/register", response_model=AccountResponse, status_code=201)
def register(payload: Registration, session: DatabaseSession, request: Request, response: Response):
    _check_credentials_request(session, request)
    password_hash = password_hasher.hash(payload.password.get_secret_value())
    try:
        with session.begin():
            # Lock the shared allocator through the end of registration so a
            # failed insert rolls back the allocation along with the account.
            max_user_id = select(func.coalesce(func.max(User.id), 0)).scalar_subquery()
            sequence = session.execute(update(UserIdSequence).where(UserIdSequence.id == 1).values(
                last_id=case(
                    (UserIdSequence.last_id < max_user_id, max_user_id),
                    else_=UserIdSequence.last_id,
                ) + 1,
            ))
            if sequence.rowcount != 1:
                raise RuntimeError("Missing account ID allocator. Apply the database migrations.")
            user_id = session.scalar(select(UserIdSequence.last_id).where(UserIdSequence.id == 1))
            user = User(id=user_id, email=payload.email, password_hash=password_hash)
            session.add(user)
            session.flush()
            auth.start_session(session, request, response, user.id)
            result = AccountResponse.from_user(user)
    except IntegrityError:
        if session.scalar(select(User.id).where(User.email == payload.email)) is not None:
            raise HTTPException(409, "Email already registered") from None
        raise
    return result


@router.post("/login", response_model=AccountResponse)
def login(payload: Credentials, session: DatabaseSession, request: Request, response: Response):
    _check_credentials_request(session, request)
    with session.begin():
        user = session.scalar(select(User).where(User.email == payload.email))
        password_hash = user.password_hash if user is not None else _dummy_hash()
        try:
            verified = password_hasher.verify(password_hash, payload.password.get_secret_value())
        except (VerificationError, InvalidHashError):
            verified = False
        if not verified or user is None:
            raise HTTPException(401, "Invalid email or password")
        auth.start_session(session, request, response, user.id)
        return AccountResponse.from_user(user)


@router.post("/logout", status_code=204)
def logout(session: DatabaseSession, request: Request, response: Response):
    with session.begin():
        account = auth.active_session(session, request)
        auth.check_csrf(request, account)
        auth.revoke_session(session, request)
    auth.clear_session_cookie(request, response)


@router.get("/me", response_model=AccountResponse)
def me(session: DatabaseSession, request: Request):
    auth.check_origin(request)
    account = auth.active_session(session, request)
    if account is None:
        raise HTTPException(401, "Authentication required")
    user = session.get(User, account.user_id)
    if user is None:
        raise HTTPException(401, "Authentication required")
    return AccountResponse.from_user(user)
