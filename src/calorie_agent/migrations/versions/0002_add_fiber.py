"""add dietary fiber to logged items and the food cache

Existing rows get 0.0, which reads as "not reported" — foods logged before fiber
tracking existed genuinely have no fiber figure, and 0 keeps SUM() totals valid.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default backfills existing rows; the column stays NOT NULL.
    op.add_column(
        "food_item",
        sa.Column("fiber_g", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "food_cache",
        sa.Column("fiber_100g", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("food_cache", "fiber_100g")
    op.drop_column("food_item", "fiber_g")
