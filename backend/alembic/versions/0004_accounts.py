"""Add sessions, rate limits and durable reading creation and AI accounting."""
from alembic import op
import sqlalchemy as sa


revision = "0004_accounts"
down_revision = "0003_reading_engine"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
USAGE_FK = "fk_ai_usage_logs_reading_id_readings"
FK_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def upgrade():
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "auth_rate_limits",
        sa.Column("client_hash", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        **TABLE_OPTIONS,
    )
    op.create_table(
        "reading_create_keys",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        **TABLE_OPTIONS,
    )
    op.execute(sa.text(
        "INSERT INTO reading_create_keys (key_hash) "
        "SELECT create_key_hash FROM readings WHERE create_key_hash IS NOT NULL"
    ))
    with op.batch_alter_table("ai_usage_logs", naming_convention=FK_NAMING) as batch:
        batch.drop_constraint(USAGE_FK, type_="foreignkey")
        batch.alter_column("reading_id", existing_type=sa.String(36), existing_nullable=False, nullable=True)
        batch.create_foreign_key(USAGE_FK, "readings", ["reading_id"], ["id"], ondelete="SET NULL")
        batch.add_column(sa.Column("quota_scope", sa.String(70)))
    op.create_index("ix_ai_usage_logs_created_at", "ai_usage_logs", ["created_at"])
    op.create_index("ix_ai_usage_logs_quota_scope_created", "ai_usage_logs", ["quota_scope", "created_at"])


def downgrade():
    # Detached logs cannot be represented by the earlier schema.
    if op.get_context().as_sql:
        raise RuntimeError("Revision 0004 downgrade requires checking for detached usage logs")
    logs = sa.table("ai_usage_logs", sa.column("reading_id"))
    if op.get_bind().execute(sa.select(1).where(logs.c.reading_id.is_(None)).limit(1)).first():
        raise RuntimeError("Cannot downgrade while detached usage logs exist")
    op.drop_index("ix_ai_usage_logs_quota_scope_created", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_created_at", table_name="ai_usage_logs")
    with op.batch_alter_table("ai_usage_logs", naming_convention=FK_NAMING) as batch:
        batch.drop_constraint(USAGE_FK, type_="foreignkey")
        batch.alter_column("reading_id", existing_type=sa.String(36), existing_nullable=True, nullable=False)
        batch.create_foreign_key(USAGE_FK, "readings", ["reading_id"], ["id"], ondelete="CASCADE")
        batch.drop_column("quota_scope")
    op.drop_table("reading_create_keys")
    op.drop_table("auth_rate_limits")
    op.drop_table("auth_sessions")
