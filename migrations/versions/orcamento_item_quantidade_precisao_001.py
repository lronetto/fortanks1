"""OrcamentoItens.quantidade: mais casas decimais (planilha calculada).

Revision ID: orc_item_qtd_prec_001
Revises: orc_item_unidade_001
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "orc_item_qtd_prec_001"
down_revision = "orc_item_unidade_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("OrcamentoItens"):
        return

    colunas_info = {c["name"]: c for c in inspector.get_columns("OrcamentoItens")}
    coluna_quantidade = colunas_info.get("quantidade")
    if coluna_quantidade is None:
        return

    tipo_atual = coluna_quantidade.get("type")
    op.alter_column(
        "OrcamentoItens",
        "quantidade",
        existing_type=tipo_atual if isinstance(tipo_atual, sa.types.TypeEngine) else sa.Numeric(10, 2),
        type_=sa.Numeric(28, 14),
        existing_nullable=coluna_quantidade.get("nullable", False),
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("OrcamentoItens"):
        return

    colunas_info = {c["name"]: c for c in inspector.get_columns("OrcamentoItens")}
    coluna_quantidade = colunas_info.get("quantidade")
    if coluna_quantidade is None:
        return

    tipo_atual = coluna_quantidade.get("type")
    op.alter_column(
        "OrcamentoItens",
        "quantidade",
        existing_type=tipo_atual if isinstance(tipo_atual, sa.types.TypeEngine) else sa.Numeric(28, 14),
        type_=sa.Numeric(10, 2),
        existing_nullable=coluna_quantidade.get("nullable", False),
    )
