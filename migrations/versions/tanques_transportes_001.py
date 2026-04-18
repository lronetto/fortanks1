"""Tabela TanquesTransportes — registros de transporte em lote.

Revision ID: tanques_transportes_001
Revises: remover_codigo_materiais_001
Create Date: 2026-04-17

"""

import sqlalchemy as sa
from alembic import op


revision = "tanques_transportes_001"
down_revision = "remover_codigo_materiais_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "TanquesTransportes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nota", sa.Integer(), nullable=True),
        sa.Column("cte", sa.String(length=64), nullable=True),
        sa.Column("transportadora", sa.String(length=255), nullable=True),
        sa.Column("data_transporte", sa.Date(), nullable=True),
        sa.Column("pecas", sa.Text(), nullable=True),
        sa.Column("dados_adicionais", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_TanquesTransportes_nota"), "TanquesTransportes", ["nota"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_TanquesTransportes_nota"), table_name="TanquesTransportes")
    op.drop_table("TanquesTransportes")
