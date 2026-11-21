"""Persist private reading decks, ordered selections, and reveal state."""
from alembic import op
import sqlalchemy as sa


revision = "0003_reading_engine"
down_revision = "0002_card_image_filename"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("readings", sa.Column("create_key_hash", sa.String(64), nullable=True))
    op.add_column("readings", sa.Column("deck_order", sa.JSON(none_as_null=True), nullable=True))
    op.add_column("readings", sa.Column("selected_indices", sa.JSON(none_as_null=True), nullable=True))
    op.add_column("readings", sa.Column("requested_card_count", sa.Integer(), nullable=True))
    op.execute(sa.text(
        "UPDATE readings SET requested_card_count = "
        "(SELECT card_count FROM tarot_spreads WHERE tarot_spreads.id = readings.spread_id) "
        "WHERE requested_card_count IS NULL"
    ))
    op.create_index("ix_readings_create_key_hash", "readings", ["create_key_hash"], unique=True)
    op.add_column("reading_cards", sa.Column("revealed_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_index("ix_readings_create_key_hash", table_name="readings")
    with op.batch_alter_table("readings") as batch:
        batch.drop_column("selected_indices")
        batch.drop_column("requested_card_count")
        batch.drop_column("deck_order")
        batch.drop_column("create_key_hash")
    op.drop_column("reading_cards", "revealed_at")
