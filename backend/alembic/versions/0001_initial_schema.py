"""Initial eleven-table schema; no reference data or live initialization.

Revision ID: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    # SQLAlchemy supplies UTC values. No server-local CURRENT_TIMESTAMP defaults.
    return [sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False)]


def create_table(name, *columns):
    op.create_table(name, *columns, mysql_engine="InnoDB", mysql_charset="utf8mb4")


def upgrade():
    create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("email", name="uq_users_email"))
    create_table("tarot_cards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name_en", sa.String(100), nullable=False),
        sa.Column("name_th", sa.String(150), nullable=False),
        sa.Column("arcana", sa.String(5), nullable=False),
        sa.Column("suit", sa.String(10), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(500), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("slug", name="uq_tarot_cards_slug"),
        sa.CheckConstraint("id BETWEEN 1 AND 78", name=op.f("ck_tarot_cards_stable_id")),
        sa.CheckConstraint(
            "(arcana = 'major' AND suit IS NULL AND `rank` BETWEEN 0 AND 21) OR "
            "(arcana = 'minor' AND suit IS NOT NULL AND suit IN "
            "('wands', 'cups', 'swords', 'pentacles') AND `rank` BETWEEN 1 AND 14)",
            name=op.f("ck_tarot_cards_arcana_suit_rank")))
    op.create_index("ix_tarot_cards_arcana", "tarot_cards", ["arcana"])
    create_table("card_meanings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("tarot_cards.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("upright_keywords", sa.JSON(), nullable=False),
        sa.Column("upright_description", sa.Text(), nullable=False),
        sa.Column("reversed_keywords", sa.JSON(), nullable=False),
        sa.Column("reversed_description", sa.Text(), nullable=False),
        sa.Column("love_meaning", sa.Text(), nullable=False),
        sa.Column("career_meaning", sa.Text(), nullable=False),
        sa.Column("finance_meaning", sa.Text(), nullable=False),
        sa.Column("daily_life_meaning", sa.Text(), nullable=False),
        sa.Column("general_guidance_meaning", sa.Text(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("card_id", name="uq_card_meanings_card_id"))
    create_table("categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("name_th", sa.String(150), nullable=False),
        *timestamps(), sa.UniqueConstraint("slug", name="uq_categories_slug"))
    create_table("tarot_spreads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name_th", sa.String(150), nullable=False),
        sa.Column("card_count", sa.Integer(), nullable=False),
        *timestamps(), sa.UniqueConstraint("slug", name="uq_tarot_spreads_slug"),
        sa.CheckConstraint("card_count IN (3, 5, 10)", name=op.f("ck_tarot_spreads_card_count")))
    create_table("questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("prompt_th", sa.String(500), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("recommended_spread_id", sa.Integer(), sa.ForeignKey("tarot_spreads.id", ondelete="RESTRICT"), nullable=True),
        *timestamps(), sa.UniqueConstraint("category_id", "display_order", name="uq_questions_category_id"),
        sa.CheckConstraint("display_order > 0", name=op.f("ck_questions_display_order")))
    op.create_index("ix_questions_category_id", "questions", ["category_id"])
    op.create_index("ix_questions_recommended_spread_id", "questions", ["recommended_spread_id"])
    create_table("spread_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spread_id", sa.Integer(), sa.ForeignKey("tarot_spreads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position_number", sa.Integer(), nullable=False),
        sa.Column("meaning_th", sa.String(500), nullable=False),
        *timestamps(), sa.UniqueConstraint("spread_id", "position_number", name="uq_spread_positions_spread_id"),
        sa.CheckConstraint("position_number BETWEEN 1 AND 10", name=op.f("ck_spread_positions_position_number")))
    op.create_index("ix_spread_positions_spread_id", "spread_positions", ["spread_id"])
    create_table("readings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("custom_question", sa.String(1000), nullable=True),
        sa.Column("spread_id", sa.Integer(), sa.ForeignKey("tarot_spreads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="CREATED"),
        sa.Column("anonymous_capability_hash", sa.String(64), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("anonymous_capability_hash", name="uq_readings_anonymous_capability_hash"),
        sa.CheckConstraint("status IN ('CREATED','DRAWING','DRAWN','INTERPRETING','COMPLETED','FAILED')", name=op.f("ck_readings_status")),
        sa.CheckConstraint(
            "(question_id IS NOT NULL AND custom_question IS NULL) OR "
            "(question_id IS NULL AND custom_question IS NOT NULL AND char_length(trim(custom_question)) BETWEEN 1 AND 1000)",
            name=op.f("ck_readings_question_choice")),
        sa.CheckConstraint("user_id IS NOT NULL OR anonymous_capability_hash IS NOT NULL", name=op.f("ck_readings_access_required")))
    for column in ("category_id", "question_id", "spread_id"):
        op.create_index(f"ix_readings_{column}", "readings", [column])
    op.create_index("ix_readings_user_created", "readings", ["user_id", "created_at"])
    create_table("reading_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reading_id", sa.String(36), sa.ForeignKey("readings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("spread_positions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("tarot_cards.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("orientation", sa.String(8), nullable=False, server_default="upright"),
        *timestamps(),
        sa.UniqueConstraint("reading_id", "position_id", name="uq_reading_cards_reading_position"),
        sa.UniqueConstraint("reading_id", "card_id", name="uq_reading_cards_reading_card"),
        sa.CheckConstraint("orientation IN ('upright', 'reversed')", name=op.f("ck_reading_cards_orientation")))
    for column in ("reading_id", "position_id", "card_id"):
        op.create_index(f"ix_reading_cards_{column}", "reading_cards", [column])
    create_table("reading_interpretations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reading_id", sa.String(36), sa.ForeignKey("readings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("model", sa.String(150), nullable=True),
        *timestamps(), sa.UniqueConstraint("reading_id", name="uq_reading_interpretations_reading_id"),
        sa.CheckConstraint("source IN ('database', 'ai')", name=op.f("ck_reading_interpretations_source")))
    create_table("ai_usage_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reading_id", sa.String(36), sa.ForeignKey("readings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_estimate", sa.Numeric(14, 8), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("input_tokens >= 0 AND output_tokens >= 0 AND cost_estimate >= 0", name=op.f("ck_ai_usage_logs_nonnegative_usage")))
    op.create_index("ix_ai_usage_logs_reading_id", "ai_usage_logs", ["reading_id"])


def downgrade():
    # Destructive rollback is only performed by an explicit operator command.
    for table in ("ai_usage_logs", "reading_interpretations", "reading_cards", "readings",
                  "spread_positions", "questions", "tarot_spreads", "categories",
                  "card_meanings", "tarot_cards", "users"):
        op.drop_table(table)
