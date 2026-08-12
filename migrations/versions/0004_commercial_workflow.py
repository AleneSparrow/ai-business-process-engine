"""Add tenant-scoped bookings, quotes, and payment requests.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VALUE = postgresql.JSONB(none_as_null=True).with_variant(sa.JSON(none_as_null=True), "sqlite")


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("lead_id", sa.String(128), nullable=False),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", JSON_VALUE, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            name="fk_bookings_tenant_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            name="fk_bookings_tenant_lead",
        ),
        sa.UniqueConstraint("business_id", "id", name="uq_bookings_business_id_id"),
        sa.UniqueConstraint("business_id", "case_id", name="uq_bookings_business_case"),
        sa.CheckConstraint("end_at > start_at", name="ck_bookings_time_order"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_bookings_timestamp_order"),
        sa.CheckConstraint("version >= 0", name="ck_bookings_version_nonnegative"),
        sa.CheckConstraint(
            "status IN ('PENDING','CONFIRMED','CANCELLED','RESCHEDULED','COMPLETED')",
            name="ck_bookings_known_status",
        ),
    )
    op.create_index(
        "ix_bookings_business_service_slot",
        "bookings",
        ["business_id", "service_id", "start_at", "end_at", "status"],
    )
    op.create_index("ix_bookings_business_lead", "bookings", ["business_id", "lead_id"])

    op.create_table(
        "quotes",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("lead_id", sa.String(128), nullable=False),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False),
        sa.Column("total", sa.Numeric(18, 2), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pricing_basis", JSON_VALUE, nullable=False),
        sa.Column("metadata", JSON_VALUE, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            name="fk_quotes_tenant_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            name="fk_quotes_tenant_lead",
        ),
        sa.UniqueConstraint("business_id", "id", name="uq_quotes_business_id_id"),
        sa.UniqueConstraint("business_id", "case_id", name="uq_quotes_business_case"),
        sa.CheckConstraint("subtotal >= 0 AND total >= subtotal", name="ck_quotes_amounts"),
        sa.CheckConstraint("valid_until > created_at", name="ck_quotes_validity"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_quotes_timestamp_order"),
        sa.CheckConstraint("version >= 0", name="ck_quotes_version_nonnegative"),
        sa.CheckConstraint(
            "status IN ('DRAFT','PRESENTED','ACCEPTED','REJECTED','EXPIRED','CANCELLED')",
            name="ck_quotes_known_status",
        ),
    )
    op.create_index(
        "ix_quotes_business_status_validity",
        "quotes",
        ["business_id", "status", "valid_until"],
    )
    op.create_index("ix_quotes_business_lead", "quotes", ["business_id", "lead_id"])

    op.create_table(
        "quote_lines",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("quote_id", sa.String(128), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id", "quote_id"],
            ["quotes.business_id", "quotes.id"],
            name="fk_quote_lines_tenant_quote",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("business_id", "quote_id", "position", name="uq_quote_lines_position"),
        sa.CheckConstraint("position > 0", name="ck_quote_lines_position_positive"),
        sa.CheckConstraint(
            "quantity > 0 AND unit_amount >= 0 AND line_total >= 0",
            name="ck_quote_lines_amounts",
        ),
    )
    op.create_index(
        "ix_quote_lines_business_quote", "quote_lines", ["business_id", "quote_id"]
    )

    op.create_table(
        "payment_requests",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("quote_id", sa.String(128)),
        sa.Column("booking_id", sa.String(128)),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payment_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", JSON_VALUE, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            name="fk_payment_requests_tenant_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "quote_id"],
            ["quotes.business_id", "quotes.id"],
            name="fk_payment_requests_tenant_quote",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "booking_id"],
            ["bookings.business_id", "bookings.id"],
            name="fk_payment_requests_tenant_booking",
        ),
        sa.UniqueConstraint("business_id", "id", name="uq_payment_requests_business_id_id"),
        sa.UniqueConstraint(
            "business_id",
            "case_id",
            "payment_type",
            name="uq_payment_requests_business_case_type",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_payment_requests_amount"),
        sa.CheckConstraint(
            "updated_at >= created_at", name="ck_payment_requests_timestamp_order"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_payment_requests_expiry"),
        sa.CheckConstraint("version >= 0", name="ck_payment_requests_version_nonnegative"),
        sa.CheckConstraint("payment_type IN ('DEPOSIT','FINAL')", name="ck_payment_requests_type"),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','PAID','FAILED','CANCELLED','EXPIRED')",
            name="ck_payment_requests_known_status",
        ),
    )
    op.create_index(
        "ix_payment_requests_business_status",
        "payment_requests",
        ["business_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_payment_requests_business_case", "payment_requests", ["business_id", "case_id"]
    )


def downgrade() -> None:
    op.drop_table("payment_requests")
    op.drop_table("quote_lines")
    op.drop_table("quotes")
    op.drop_table("bookings")
