"""Keep trial/test conversations out of operational reporting.

Existing records deliberately remain non-test: a migration cannot reliably
infer whether an historic customer conversation was a trial run. Owners can
set ``stats_since`` to create a reversible reporting baseline instead.

Revision ID: 0016
Revises: 0015
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("test_mode_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "businesses",
        sa.Column("stats_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "process_cases",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("process_cases", "is_test")
    op.drop_column("businesses", "stats_since")
    op.drop_column("businesses", "test_mode_enabled")
