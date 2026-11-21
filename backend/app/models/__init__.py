"""Import all tables for Alembic metadata discovery."""

from app.models.entities import (
    AIUsageLog, AuthRateLimit, AuthSession, CardMeaning, Category, Question, Reading, ReadingCard, ReadingCreateKey,
    ReadingInterpretation, SpreadPosition, TarotCard, TarotSpread, User,
)

__all__ = [
    "AIUsageLog", "AuthRateLimit", "AuthSession", "CardMeaning", "Category", "Question", "Reading", "ReadingCard", "ReadingCreateKey",
    "ReadingInterpretation", "SpreadPosition", "TarotCard", "TarotSpread", "User",
]
