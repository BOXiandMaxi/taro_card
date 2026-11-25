"""Import all tables for Alembic metadata discovery."""

from app.models.entities import (
    AIUsageLog, AnalyticsPageView, AuthRateLimit, AuthSession, CardMeaning, Category, Question, Reading,
    ReadingCard, ReadingCreateKey, ReadingInterpretation, SpreadPosition, TarotCard, TarotSpread, User, UserIdSequence,
)

__all__ = [
    "AIUsageLog", "AnalyticsPageView", "AuthRateLimit", "AuthSession", "CardMeaning", "Category", "Question", "Reading",
    "ReadingCard", "ReadingCreateKey", "ReadingInterpretation", "SpreadPosition", "TarotCard", "TarotSpread", "User", "UserIdSequence",
]
