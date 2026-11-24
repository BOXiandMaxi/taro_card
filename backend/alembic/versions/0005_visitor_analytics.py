"""Add optional user roles and first-party page views."""

from alembic import op
import sqlalchemy as sa


revision = "0005_visitor_analytics"
down_revision = "0004_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("role", sa.String(16), nullable=True))
    op.create_table(
        "analytics_page_views",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("report_day", sa.Date(), nullable=False),
        sa.Column("route_key", sa.String(16), nullable=False),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("signed_in", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_analytics_page_views_report_day", "analytics_page_views", ["report_day"])


def downgrade():
    op.drop_table("analytics_page_views")
    op.drop_column("users", "role")
