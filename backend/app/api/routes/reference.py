from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database.session import get_session
from app.models import Category, Question, TarotCard, TarotSpread

router = APIRouter(tags=["reference"])
DatabaseSession = Annotated[Session, Depends(get_session)]


class ReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryResponse(ReferenceResponse):
    id: int
    slug: str
    name_th: str


class QuestionResponse(ReferenceResponse):
    id: int
    category_id: int
    prompt_th: str
    display_order: int
    recommended_spread_id: int | None


class SpreadPositionResponse(ReferenceResponse):
    id: int
    spread_id: int
    position_number: int
    meaning_th: str


class SpreadResponse(ReferenceResponse):
    id: int
    slug: str
    name_th: str
    card_count: int
    positions: list[SpreadPositionResponse]


class CardResponse(ReferenceResponse):
    id: int
    slug: str
    name_en: str
    name_th: str
    arcana: str
    suit: str | None
    rank: int
    image_filename: str | None
    image_path: str | None


class CardMeaningResponse(ReferenceResponse):
    upright_keywords: list[str]
    upright_description: str
    reversed_keywords: list[str]
    reversed_description: str
    love_meaning: str
    career_meaning: str
    finance_meaning: str
    daily_life_meaning: str
    general_guidance_meaning: str


class CardDetailResponse(CardResponse):
    meaning: CardMeaningResponse | None


@router.get("/categories", response_model=list[CategoryResponse])
def get_categories(session: DatabaseSession):
    return session.scalars(select(Category).order_by(Category.id)).all()


@router.get("/questions", response_model=list[QuestionResponse])
def get_questions(session: DatabaseSession, category_id: Annotated[int | None, Query(gt=0)] = None):
    statement = select(Question).order_by(Question.category_id, Question.display_order)
    if category_id is not None:
        statement = statement.where(Question.category_id == category_id)
    return session.scalars(statement).all()


@router.get("/spreads", response_model=list[SpreadResponse])
def get_spreads(session: DatabaseSession):
    statement = select(TarotSpread).options(selectinload(TarotSpread.positions)).order_by(TarotSpread.id)
    return session.scalars(statement).all()


@router.get("/cards", response_model=list[CardResponse])
def get_cards(session: DatabaseSession):
    return session.scalars(select(TarotCard).order_by(TarotCard.id)).all()


@router.get("/cards/{id}", response_model=CardDetailResponse)
def get_card(id: int, session: DatabaseSession):
    card = session.get(TarotCard, id, options=[joinedload(TarotCard.meaning)])
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card
