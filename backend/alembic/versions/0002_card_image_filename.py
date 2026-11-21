"""Track each card's expected local artwork filename separately from availability."""
from alembic import op
import sqlalchemy as sa


revision = "0002_card_image_filename"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tarot_cards") as batch:
        batch.add_column(sa.Column("image_filename", sa.String(120), nullable=True))
        batch.create_unique_constraint("uq_tarot_cards_image_filename", ["image_filename"])


def downgrade():
    with op.batch_alter_table("tarot_cards") as batch:
        batch.drop_constraint("uq_tarot_cards_image_filename", type_="unique")
        batch.drop_column("image_filename")
