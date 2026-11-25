"""Allocate account IDs within the registration transaction."""

from alembic import op
import sqlalchemy as sa


revision = "0006_user_id_sequence"
down_revision = "0005_visitor_analytics"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_id_sequence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("last_id", sa.Integer(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.execute("INSERT INTO user_id_sequence (id, last_id) SELECT 1, COALESCE(MAX(id), 0) FROM users")


def downgrade():
    op.drop_table("user_id_sequence")
