"""add protocolo table

Revision ID: add_protocolo_table
Revises: a16ac875e330
Create Date: 2025-03-10

"""
from alembic import op
import sqlalchemy as sa


revision = "add_protocolo_table"
down_revision = "a16ac875e330"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "Protocolo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("numero", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("Protocolo")
