"""Renomeia tabelas legadas de orçamento (snake_case) para nomes do domínio.

Revision ID: orcamento_rename_snake_to_domain_001
Revises: drop_concretagens_tanques_001
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa


revision = "orcamento_rename_snake_to_domain_001"
down_revision = "drop_concretagens_tanques_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _rename_if_needed(old: str, new: str) -> None:
        if not inspector.has_table(old):
            return
        if inspector.has_table(new):
            return
        op.rename_table(old, new)

    _rename_if_needed("orcamentos", "Orcamentos")
    _rename_if_needed("itens_orcamento", "OrcamentoItens")
    _rename_if_needed("itens_orcamento_referencias_materiais", "OrcamentoItensReferencias")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _rename_if_needed(old: str, new: str) -> None:
        if not inspector.has_table(old):
            return
        if inspector.has_table(new):
            return
        op.rename_table(old, new)

    _rename_if_needed("OrcamentoItensReferencias", "itens_orcamento_referencias_materiais")
    _rename_if_needed("OrcamentoItens", "itens_orcamento")
    _rename_if_needed("Orcamentos", "orcamentos")
