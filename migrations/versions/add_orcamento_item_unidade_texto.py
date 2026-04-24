"""Orcamento itens: adiciona coluna unidade texto.

Revision ID: orc_item_unidade_001
Revises: orcamento_vinculo_orcamento_001
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "orc_item_unidade_001"
down_revision = "orcamento_vinculo_orcamento_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    colunas_info = {c["name"]: c for c in inspector.get_columns("OrcamentoItens")}
    colunas = set(colunas_info.keys())

    if "unidade" not in colunas:
        op.add_column(
            "OrcamentoItens",
            sa.Column("unidade", sa.String(length=30), nullable=True),
        )

    coluna_quantidade = colunas_info.get("quantidade")
    if coluna_quantidade is not None:
        tipo_atual = coluna_quantidade.get("type")
        eh_decimal_10_2 = (
            isinstance(tipo_atual, sa.Numeric)
            and getattr(tipo_atual, "precision", None) == 10
            and getattr(tipo_atual, "scale", None) == 2
        )
        if not eh_decimal_10_2:
            op.alter_column(
                "OrcamentoItens",
                "quantidade",
                existing_type=tipo_atual if isinstance(tipo_atual, sa.types.TypeEngine) else sa.Integer(),
                type_=sa.Numeric(10, 2),
                existing_nullable=coluna_quantidade.get("nullable", True),
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    colunas_info = {c["name"]: c for c in inspector.get_columns("OrcamentoItens")}
    colunas = set(colunas_info.keys())

    coluna_quantidade = colunas_info.get("quantidade")
    if coluna_quantidade is not None:
        tipo_atual = coluna_quantidade.get("type")
        if not isinstance(tipo_atual, sa.Integer):
            op.alter_column(
                "OrcamentoItens",
                "quantidade",
                existing_type=tipo_atual if isinstance(tipo_atual, sa.types.TypeEngine) else sa.Numeric(10, 2),
                type_=sa.Integer(),
                existing_nullable=coluna_quantidade.get("nullable", True),
            )

    if "unidade" in colunas:
        op.drop_column("OrcamentoItens", "unidade")
