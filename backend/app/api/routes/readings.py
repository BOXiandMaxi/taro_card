import re
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import digest
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.routes.reference import (
    CardResponse, CategoryResponse, DatabaseSession, QuestionResponse, SpreadPositionResponse, SpreadResponse,
)
from app.core.config import get_settings
from app.database.base import utc_now
from app.database.session import start_write
from app.models import Category, Question, Reading, ReadingCard, ReadingCreateKey, SpreadPosition, TarotCard, TarotSpread
from app.services import auth, interpretations
from app.services.interpretation_provider import get_provider
from app.services.interpretation_schema import InterpretationResult

router = APIRouter(prefix="/readings", tags=["readings"])
history_router = APIRouter(tags=["readings"])
ReferenceID = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]
DeckIndex = Annotated[int, Field(strict=True, ge=0, le=77)]
DRAWN_STATES = {"DRAWN", "INTERPRETING", "COMPLETED", "FAILED"}


class CreateReadingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: ReferenceID
    spread_id: ReferenceID
    question_id: ReferenceID | None = None
    custom_question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] | None = None

    @model_validator(mode="after")
    def validate_question_choice(self):
        if (self.question_id is None) == (self.custom_question is None):
            raise ValueError("Provide exactly one question_id or custom_question")
        return self


class DrawRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_indices: Annotated[list[DeckIndex], Field(min_length=3, max_length=10)]

    @model_validator(mode="after")
    def validate_distinct_indices(self):
        if len(set(self.selected_indices)) != len(self.selected_indices):
            raise ValueError("selected_indices must be distinct")
        return self


class RevealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_number: Annotated[int, Field(strict=True, ge=1, le=10)]


class ReadingCardMeaningResponse(BaseModel):
    keywords: list[str]
    description: str


class ReadingCardResponse(BaseModel):
    position_number: int
    position: SpreadPositionResponse
    revealed: bool = False
    card: CardResponse | None = None
    orientation: Literal["upright", "reversed"] | None = None
    meaning: ReadingCardMeaningResponse | None = None


class ReadingResponse(BaseModel):
    id: str
    status: str
    category_id: int
    requested_card_count: int | None
    question: QuestionResponse | None
    question_text: str | None
    spread: SpreadResponse
    cards: list[ReadingCardResponse]


class ReadingDetailsResponse(ReadingResponse):
    category: CategoryResponse
    created_at: datetime
    interpretation: InterpretationResult | None = None
    interpretation_source: Literal["ai", "database"] | None = None


class HistoryReadingResponse(ReadingResponse):
    category: CategoryResponse
    created_at: datetime
    interpretation_summary: str | None


def _key_digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


def _create_key(header: str | None) -> bytes | None:
    if header is None:
        return None
    # A first-request retry has no cookie. Its key must be an unguessable credential.
    try:
        key = UUID(header)
    except ValueError:
        raise HTTPException(422, "Idempotency-Key must be a random UUIDv4") from None
    if key.version != 4 or str(key) != header.lower():
        raise HTTPException(422, "Idempotency-Key must be a random UUIDv4")
    return key.bytes


def _cookie_name(reading_id: str, secure: bool) -> str:
    prefix = "__Secure-" if secure else ""
    return f"{prefix}tarot-reading-{reading_id}"


def _retry_capability(key: bytes, reading_id: str) -> str:
    return digest(key, f"tarot-reading-cookie:{reading_id}".encode("ascii"), "sha256").hex()


def _set_capability(response: Response, request: Request, reading_id: str, token: str):
    response.set_cookie(
        _cookie_name(reading_id, request.url.scheme == "https"), token,
        secure=request.url.scheme == "https", httponly=True, samesite="lax",
        path=f"/api/readings/{reading_id}",
        max_age=get_settings().guest_reading_retention_days * 86400,
    )


def _clear_capability(response: Response, request: Request, reading_id: str) -> None:
    secure = request.url.scheme == "https"
    response.delete_cookie(
        _cookie_name(reading_id, secure), secure=secure, httponly=True, samesite="lax",
        path=f"/api/readings/{reading_id}",
    )


def guest_cutoff(now: datetime) -> datetime:
    return now - timedelta(days=get_settings().guest_reading_retention_days)


def _owned_reading(session: Session, request: Request, reading_id: str, *, lock: bool = False) -> Reading:
    account = auth.active_session(session, request)
    if account is not None and lock:
        auth.check_csrf(request, account)
    return _accessible_reading(session, request, reading_id, account.user_id if account else None, lock=lock)


def _accessible_reading(
    session: Session, request: Request, reading_id: str, user_id: int | None, *,
    lock: bool = False, allow_guest: bool = True,
) -> Reading:
    token = request.cookies.get(_cookie_name(reading_id, request.url.scheme == "https")) if allow_guest else None
    if token is None and user_id is None:
        raise HTTPException(401, "Reading capability required")
    access = []
    if user_id is not None:
        access.append(Reading.user_id == user_id)
    if token is not None and re.fullmatch(r"[0-9a-f]{64}", token):
        access.append(
            Reading.user_id.is_(None) & (Reading.anonymous_capability_hash == _key_digest(token))
            & (Reading.created_at > guest_cutoff(utc_now()))
        )
    if not access:
        raise HTTPException(404, "Reading not found")
    query = select(Reading).where(Reading.id == reading_id, or_(*access))
    reading = session.scalar(query.with_for_update() if lock else query)
    if reading is None:
        raise HTTPException(404, "Reading not found")
    return reading


def _shuffled_deck(session: Session) -> list[int]:
    deck = list(session.scalars(select(TarotCard.id).order_by(TarotCard.id)))
    if deck != list(range(1, 79)):
        raise HTTPException(503, "Tarot deck is unavailable")
    for end in range(len(deck) - 1, 0, -1):
        index = secrets.randbelow(end + 1)
        deck[end], deck[index] = deck[index], deck[end]
    return deck


def _has_valid_positions(spread: TarotSpread) -> bool:
    return (
        spread.card_count in (3, 5, 10)
        and [position.position_number for position in spread.positions] == list(range(1, spread.card_count + 1))
    )


def _reading_response(
    session: Session, reading: Reading, *, status: str | None = None, show_reveals: bool = False,
) -> ReadingResponse:
    effective_status = status or reading.status
    spread = session.get(TarotSpread, reading.spread_id)
    question = session.get(Question, reading.question_id) if reading.question_id is not None else None
    cards = []
    if effective_status != "CREATED":
        cards_by_position = {card.position_id: card for card in reading.cards}
        cards = [
            _card_response(session, position, cards_by_position[position.id], show_reveals)
            for position in spread.positions if position.id in cards_by_position
        ]
    return ReadingResponse(
        id=reading.id, status=effective_status, category_id=reading.category_id,
        requested_card_count=reading.requested_card_count,
        question=QuestionResponse.model_validate(question) if question else None,
        question_text=reading.custom_question,
        spread=SpreadResponse.model_validate(spread), cards=cards,
    )


def _card_response(session: Session, position: SpreadPosition, item: ReadingCard, show_reveals: bool) -> ReadingCardResponse:
    revealed = show_reveals and item.revealed_at is not None
    card = session.get(TarotCard, item.card_id, options=[joinedload(TarotCard.meaning)]) if revealed else None
    meaning = None
    if card is not None and card.meaning is not None:
        source = card.meaning
        if item.orientation == "reversed":
            meaning = ReadingCardMeaningResponse(keywords=source.reversed_keywords, description=source.reversed_description)
        else:
            meaning = ReadingCardMeaningResponse(keywords=source.upright_keywords, description=source.upright_description)
    return ReadingCardResponse(
        position_number=position.position_number, position=SpreadPositionResponse.model_validate(position),
        revealed=revealed,
        card=CardResponse.model_validate(card) if revealed else None,
        orientation=item.orientation if revealed else None,
        meaning=meaning,
    )


def _create_retry(
    session: Session, reading: Reading, payload: CreateReadingRequest, key: bytes, response: Response, request: Request,
    user_id: int | None,
) -> ReadingResponse:
    if reading.user_id != user_id or (user_id is None and reading.created_at <= guest_cutoff(utc_now())):
        raise HTTPException(409, "Idempotency-Key is unavailable")
    replayed = CreateReadingRequest(
        category_id=reading.category_id, question_id=reading.question_id,
        custom_question=reading.custom_question, spread_id=reading.spread_id,
    )
    if replayed != payload:
        raise HTTPException(409, "Idempotency-Key was used with different reading parameters")
    result = _reading_response(session, reading, status="CREATED")
    if user_id is None:
        _set_capability(response, request, reading.id, _retry_capability(key, reading.id))
    return result


@router.post("", response_model=ReadingResponse, status_code=201)
def create_reading(
    payload: CreateReadingRequest, session: DatabaseSession, request: Request, response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    auth.check_origin(request)
    response.headers["Cache-Control"] = "no-store"
    key = _create_key(idempotency_key)
    key_hash = sha256(key).hexdigest() if key is not None else None
    key_query = None
    if key_hash is not None:
        key_query = select(Reading).where(Reading.create_key_hash == key_hash)

    try:
        with session.begin():
            start_write(session)
            account = auth.active_session(session, request)
            if account is not None:
                auth.check_csrf(request, account)
            user_id = account.user_id if account is not None else None
            existing = session.scalar(key_query) if key_query is not None else None
            if existing is not None:
                return _create_retry(session, existing, payload, key, response, request, user_id)
            if key_hash is not None:
                session.add(ReadingCreateKey(key_hash=key_hash))
                session.flush()
            if session.get(Category, payload.category_id) is None:
                raise HTTPException(422, "Unknown category")
            if payload.question_id is not None:
                question = session.get(Question, payload.question_id)
                if question is None or question.category_id != payload.category_id:
                    raise HTTPException(422, "Question does not belong to the category")
            spread = session.get(TarotSpread, payload.spread_id)
            if spread is None:
                raise HTTPException(422, "Unknown spread")
            if not _has_valid_positions(spread):
                raise HTTPException(503, "Spread positions are unavailable")
            reading_id = str(uuid4())
            token = None
            if user_id is None:
                token = secrets.token_hex(32) if key is None else _retry_capability(key, reading_id)
            reading = Reading(
                **payload.model_dump(), id=reading_id, user_id=user_id, deck_order=_shuffled_deck(session),
                requested_card_count=spread.card_count,
                anonymous_capability_hash=_key_digest(token) if token is not None else None, create_key_hash=key_hash,
            )
            session.add(reading)
            session.flush()
            result = _reading_response(session, reading, status="CREATED")
    except IntegrityError:
        # A concurrent insert may have won the unique key. Read in a fresh transaction.
        if key_query is not None:
            with session.begin():
                account = auth.active_session(session, request)
                if account is not None:
                    auth.check_csrf(request, account)
                existing = session.scalar(key_query)
                if existing is not None:
                    user_id = account.user_id if account is not None else None
                    return _create_retry(session, existing, payload, key, response, request, user_id)
                if session.get(ReadingCreateKey, key_hash) is not None:
                    raise HTTPException(409, "Idempotency-Key is unavailable") from None
        raise
    if token is not None:
        _set_capability(response, request, result.id, token)
    return result


@router.get("/{id}", response_model=ReadingDetailsResponse, response_model_exclude_unset=True)
def get_reading(id: UUID, session: DatabaseSession, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    reading = _owned_reading(session, request, str(id))
    category = session.get(Category, reading.category_id)
    result = ReadingDetailsResponse(
        **_reading_response(session, reading, show_reveals=True).model_dump(),
        category=CategoryResponse.model_validate(category),
        created_at=reading.created_at.replace(tzinfo=timezone.utc),
    )
    if reading.user_id is not None and reading.status == "COMPLETED":
        spread = session.get(TarotSpread, reading.spread_id)
        positions = interpretations.revealed_positions(reading, spread)
        if positions is not None:
            cached = _cached_interpretation(session, reading.id, positions)
            if cached is not None:
                result.interpretation = cached
                result.interpretation_source = reading.interpretation.source
    return result


@history_router.get("/history", response_model=list[HistoryReadingResponse])
def get_history(session: DatabaseSession, request: Request, response: Response):
    auth.check_origin(request)
    account = auth.active_session(session, request)
    if account is None:
        raise HTTPException(401, "Authentication required", headers={"Cache-Control": "no-store"})
    response.headers["Cache-Control"] = "no-store"
    history = session.scalars(
        select(Reading).where(Reading.user_id == account.user_id)
        .options(selectinload(Reading.cards), selectinload(Reading.interpretation))
        .order_by(Reading.created_at.desc(), Reading.id.desc())
    )
    results = []
    for reading in history:
        details = _reading_response(session, reading, show_reveals=True)
        category = session.get(Category, reading.category_id)
        cached = reading.interpretation.result if reading.interpretation else None
        summary = cached.get("overall_summary") if isinstance(cached, dict) else None
        results.append(HistoryReadingResponse(
            **details.model_dump(), category=CategoryResponse.model_validate(category),
            created_at=reading.created_at.replace(tzinfo=timezone.utc),
            interpretation_summary=summary if isinstance(summary, str) else None,
        ))
    return results


@router.delete("/{id}", status_code=204)
def delete_reading(id: UUID, session: DatabaseSession, request: Request, response: Response):
    auth.check_origin(request)
    with session.begin():
        start_write(session)
        reading = _owned_reading(session, request, str(id), lock=True)
        guest = reading.user_id is None
        session.delete(reading)
    if guest:
        _clear_capability(response, request, str(id))
    response.headers["Cache-Control"] = "no-store"


@router.post("/{id}/draw", response_model=ReadingResponse)
def draw_reading(id: UUID, payload: DrawRequest, session: DatabaseSession, request: Request, response: Response):
    auth.check_origin(request)
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        start_write(session)
        reading = _owned_reading(session, request, str(id), lock=True)
        if reading.selected_indices is not None:
            if reading.selected_indices != payload.selected_indices:
                raise HTTPException(409, "Reading already has a different ordered selection")
            return _reading_response(session, reading, status="DRAWN")
        if reading.status != "CREATED" or reading.deck_order is None or reading.cards:
            raise HTTPException(409, "Reading cannot be drawn")
        spread = session.get(TarotSpread, reading.spread_id)
        if not _has_valid_positions(spread):
            raise HTTPException(503, "Spread positions are unavailable")
        if len(payload.selected_indices) != spread.card_count:
            raise HTTPException(422, f"Select exactly {spread.card_count} indices")
        reversed_enabled = get_settings().reversed_cards_enabled
        reading.cards = [
            ReadingCard(
                position_id=position.id, card_id=reading.deck_order[index],
                orientation="reversed" if reversed_enabled and secrets.randbelow(2) else "upright",
            )
            for position, index in zip(spread.positions, payload.selected_indices, strict=True)
        ]
        reading.selected_indices = payload.selected_indices
        reading.status = "DRAWN"
        return _reading_response(session, reading, status="DRAWN")


@router.post("/{id}/reveal", response_model=ReadingCardResponse)
def reveal_card(id: UUID, payload: RevealRequest, session: DatabaseSession, request: Request, response: Response):
    auth.check_origin(request)
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        start_write(session)
        reading = _owned_reading(session, request, str(id), lock=True)
        if reading.status not in DRAWN_STATES:
            raise HTTPException(409, "Draw cards before revealing a position")
        spread = session.get(TarotSpread, reading.spread_id)
        if not _has_valid_positions(spread):
            raise HTTPException(503, "Spread positions are unavailable")
        if payload.position_number > spread.card_count:
            raise HTTPException(422, "Position does not belong to the spread")
        position = spread.positions[payload.position_number - 1]
        card = next((item for item in reading.cards if item.position_id == position.id), None)
        if card is None:
            raise HTTPException(409, "Reading is missing this position")
        if card.revealed_at is None:
            card.revealed_at = utc_now()
        return _card_response(session, position, card, show_reveals=True)


def _interpretation_positions(
    session: Session, reading: Reading,
) -> tuple[TarotSpread, list[tuple[SpreadPosition, ReadingCard]]]:
    if reading.status not in DRAWN_STATES:
        raise HTTPException(409, "Reveal all cards before interpreting")
    spread = session.get(TarotSpread, reading.spread_id)
    if spread is None or not _has_valid_positions(spread):
        raise HTTPException(503, "Spread positions are unavailable")
    positions = interpretations.revealed_positions(reading, spread)
    if positions is None:
        raise HTTPException(409, "Reveal all cards before interpreting")
    return spread, positions


def _cached_interpretation(
    session: Session, reading_id: str, positions: list[tuple[SpreadPosition, ReadingCard]],
) -> InterpretationResult | None:
    try:
        return interpretations.cached_result(session, reading_id, positions)
    except ValueError:
        raise HTTPException(503, "Cached interpretation is unavailable") from None


def _interpretation_user_id(session: Session, request: Request, *, write: bool = False) -> int:
    account = auth.active_session(session, request)
    if account is None:
        raise HTTPException(401, "Authentication required", headers={"Cache-Control": "no-store"})
    if write:
        auth.check_csrf(request, account)
    return account.user_id


@router.get("/{id}/interpretation", response_model=InterpretationResult)
def get_interpretation(id: UUID, session: DatabaseSession, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    user_id = _interpretation_user_id(session, request)
    reading = _accessible_reading(session, request, str(id), user_id, allow_guest=False)
    _, positions = _interpretation_positions(session, reading)
    result = _cached_interpretation(session, reading.id, positions)
    if result is None:
        raise HTTPException(404, "Interpretation not found")
    return result


@router.post("/{id}/interpret", response_model=InterpretationResult)
def interpret_reading(id: UUID, session: DatabaseSession, request: Request, response: Response):
    auth.check_origin(request)
    response.headers["Cache-Control"] = "no-store"
    reading_id = str(id)
    settings = get_settings()
    with session.begin():
        user_id = _interpretation_user_id(session, request, write=True)
    with session.begin():
        start_write(session)
        # Lock the reading before the first consistent read on MySQL.
        reading = _accessible_reading(session, request, reading_id, user_id, lock=True)
        spread, positions = _interpretation_positions(session, reading)
        cached = _cached_interpretation(session, reading_id, positions)
        recovering = reading.status == "INTERPRETING"
        if cached is None and recovering and utc_now() - reading.updated_at < interpretations.CLAIM_MAX_AGE:
            raise HTTPException(409, "Interpretation is in progress", headers={"Retry-After": "2"})

        if reading.user_id is None:
            reading.user_id = user_id
            reading.anonymous_capability_hash = None
            _clear_capability(response, request, reading_id)
        if cached is not None:
            return cached

        try:
            payload = interpretations.load_input(session, reading, spread, positions)
        except (KeyError, ValueError):
            raise HTTPException(503, "Interpretation data is unavailable") from None
        provider = get_provider(settings) if not recovering else None
        if provider is None or settings.ai_daily_request_limit == 0:
            result = interpretations.database_interpretation(payload)
            interpretations.save_result(session, reading, result, model=None)
            return result
        reading.status = "INTERPRETING"
        quota_scope = f"user:{user_id}"

    generated = interpretations.generate(session, reading_id, payload, provider, settings, quota_scope)
    result = generated or interpretations.database_interpretation(payload)
    with session.begin():
        start_write(session)
        session.expire_all()
        reading = session.get(Reading, reading_id, with_for_update=True)
        if reading is None:
            raise HTTPException(404, "Reading not found")
        _, positions = _interpretation_positions(session, reading)
        cached = _cached_interpretation(session, reading_id, positions)
        if cached is not None:
            return cached
        interpretations.save_result(session, reading, result, model=provider.model if generated is not None else None)
    return result
