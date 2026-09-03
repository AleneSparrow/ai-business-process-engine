"""Add the editable personal name to staff accounts.

Revision ID: 0019
Revises: 0018
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("staff_users", sa.Column("name", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("staff_users", "name")
