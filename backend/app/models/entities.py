from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, Timestamps, utc_now


class User(Timestamps, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(16))


class AnalyticsPageView(Base):
    __tablename__ = "analytics_page_views"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_day: Mapped[date] = mapped_column(Date, index=True)
    route_key: Mapped[str] = mapped_column(String(16))
    browser_hash: Mapped[str] = mapped_column(String(64))
    signed_in: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"

    client_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer)


class ReadingCreateKey(Base):
    __tablename__ = "reading_create_keys"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)


class TarotCard(Timestamps, Base):
    __tablename__ = "tarot_cards"
    __table_args__ = (
        CheckConstraint("id BETWEEN 1 AND 78", name="stable_id"),
        CheckConstraint(
            "(arcana = 'major' AND suit IS NULL AND `rank` BETWEEN 0 AND 21) OR "
            "(arcana = 'minor' AND suit IS NOT NULL AND suit IN "
            "('wands', 'cups', 'swords', 'pentacles') AND `rank` BETWEEN 1 AND 14)",
            name="arcana_suit_rank",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name_en: Mapped[str] = mapped_column(String(100))
    name_th: Mapped[str] = mapped_column(String(150))
    arcana: Mapped[str] = mapped_column(String(5), index=True)
    suit: Mapped[str | None] = mapped_column(String(10))
    rank: Mapped[int] = mapped_column(Integer)
    # Stable expected WebP name; image_path stays NULL until the local file is verified.
    image_filename: Mapped[str | None] = mapped_column(String(120), unique=True)
    # NULL explicitly means no verified artwork; UI renders a labeled placeholder.
    image_path: Mapped[str | None] = mapped_column(String(500))
    meaning: Mapped["CardMeaning | None"] = relationship(back_populates="card", uselist=False, passive_deletes=True)


class CardMeaning(Timestamps, Base):
    __tablename__ = "card_meanings"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("tarot_cards.id", ondelete="RESTRICT"), unique=True)
    upright_keywords: Mapped[list[str]] = mapped_column(JSON)
    upright_description: Mapped[str] = mapped_column(Text)
    reversed_keywords: Mapped[list[str]] = mapped_column(JSON)
    reversed_description: Mapped[str] = mapped_column(Text)
    love_meaning: Mapped[str] = mapped_column(Text)
    career_meaning: Mapped[str] = mapped_column(Text)
    finance_meaning: Mapped[str] = mapped_column(Text)
    daily_life_meaning: Mapped[str] = mapped_column(Text)
    general_guidance_meaning: Mapped[str] = mapped_column(Text)
    card: Mapped[TarotCard] = relationship(back_populates="meaning")


class Category(Timestamps, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name_th: Mapped[str] = mapped_column(String(150))


class TarotSpread(Timestamps, Base):
    __tablename__ = "tarot_spreads"
    __table_args__ = (CheckConstraint("card_count IN (3, 5, 10)", name="card_count"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name_th: Mapped[str] = mapped_column(String(150))
    card_count: Mapped[int] = mapped_column(Integer)
    positions: Mapped[list["SpreadPosition"]] = relationship(back_populates="spread", order_by="SpreadPosition.position_number", passive_deletes=True)


class Question(Timestamps, Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("category_id", "display_order"),
        CheckConstraint("display_order > 0", name="display_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    prompt_th: Mapped[str] = mapped_column(String(500))
    display_order: Mapped[int] = mapped_column(Integer)
    recommended_spread_id: Mapped[int | None] = mapped_column(ForeignKey("tarot_spreads.id", ondelete="RESTRICT"), index=True)


class SpreadPosition(Timestamps, Base):
    __tablename__ = "spread_positions"
    __table_args__ = (
        UniqueConstraint("spread_id", "position_number"),
        CheckConstraint("position_number BETWEEN 1 AND 10", name="position_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    spread_id: Mapped[int] = mapped_column(ForeignKey("tarot_spreads.id", ondelete="RESTRICT"), index=True)
    position_number: Mapped[int] = mapped_column(Integer)
    meaning_th: Mapped[str] = mapped_column(String(500))
    spread: Mapped[TarotSpread] = relationship(back_populates="positions")


class Reading(Timestamps, Base):
    __tablename__ = "readings"
    __table_args__ = (
        CheckConstraint("status IN ('CREATED','DRAWING','DRAWN','INTERPRETING','COMPLETED','FAILED')", name="status"),
        CheckConstraint(
            "(question_id IS NOT NULL AND custom_question IS NULL) OR "
            "(question_id IS NULL AND custom_question IS NOT NULL AND char_length(trim(custom_question)) BETWEEN 1 AND 1000)",
            name="question_choice",
        ),
        CheckConstraint("user_id IS NOT NULL OR anonymous_capability_hash IS NOT NULL", name="access_required"),
        Index("ix_readings_user_created", "user_id", "created_at"),
        Index("ix_readings_create_key_hash", "create_key_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # Account deletion is deliberately restricted pending a production retention policy.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"), index=True)
    custom_question: Mapped[str | None] = mapped_column(String(1000))
    spread_id: Mapped[int] = mapped_column(ForeignKey("tarot_spreads.id", ondelete="RESTRICT"), index=True)
    requested_card_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="CREATED", server_default="CREATED")
    anonymous_capability_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    create_key_hash: Mapped[str | None] = mapped_column(String(64))
    deck_order: Mapped[list[int] | None] = mapped_column(JSON(none_as_null=True))
    selected_indices: Mapped[list[int] | None] = mapped_column(JSON(none_as_null=True))
    cards: Mapped[list["ReadingCard"]] = relationship(back_populates="reading", passive_deletes="all")
    interpretation: Mapped["ReadingInterpretation | None"] = relationship(back_populates="reading", uselist=False, passive_deletes="all")


class ReadingCard(Timestamps, Base):
    __tablename__ = "reading_cards"
    __table_args__ = (
        UniqueConstraint("reading_id", "position_id", name="uq_reading_cards_reading_position"),
        UniqueConstraint("reading_id", "card_id", name="uq_reading_cards_reading_card"),
        CheckConstraint("orientation IN ('upright', 'reversed')", name="orientation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reading_id: Mapped[str] = mapped_column(ForeignKey("readings.id", ondelete="CASCADE"), index=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("spread_positions.id", ondelete="RESTRICT"), index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("tarot_cards.id", ondelete="RESTRICT"), index=True)
    orientation: Mapped[str] = mapped_column(String(8), default="upright", server_default="upright")
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reading: Mapped[Reading] = relationship(back_populates="cards")


class ReadingInterpretation(Timestamps, Base):
    __tablename__ = "reading_interpretations"
    __table_args__ = (CheckConstraint("source IN ('database', 'ai')", name="source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reading_id: Mapped[str] = mapped_column(ForeignKey("readings.id", ondelete="CASCADE"), unique=True)
    result: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(10))
    model: Mapped[str | None] = mapped_column(String(150))
    reading: Mapped[Reading] = relationship(back_populates="interpretation")


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0 AND cost_estimate >= 0", name="nonnegative_usage"),
        Index("ix_ai_usage_logs_quota_scope_created", "quota_scope", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reading_id: Mapped[str | None] = mapped_column(ForeignKey("readings.id", ondelete="SET NULL"), index=True)
    quota_scope: Mapped[str | None] = mapped_column(String(70))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(150))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_estimate: Mapped[Decimal] = mapped_column(Numeric(14, 8), default=Decimal("0"), server_default="0")
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
