"""Coluna dados_adicionais em EquipamentosManutencoes (JSON).

Revision ID: manutencao_dados_adicionais_001
Revises: eq_manut_materiais_001
Create Date: 2026-04-08

"""
from alembic import op
import sqlalchemy as sa


revision = "manutencao_dados_adicionais_001"
down_revision = "eq_manut_materiais_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("EquipamentosManutencoes"):
        return
    cols = {c["name"] for c in insp.get_columns("EquipamentosManutencoes")}
    if "dados_adicionais" in cols:
        return
    op.add_column(
        "EquipamentosManutencoes",
        sa.Column("dados_adicionais", sa.Text(), nullable=True),
    )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("EquipamentosManutencoes") and "dados_adicionais" in {
        c["name"] for c in insp.get_columns("EquipamentosManutencoes")
    }:
        op.drop_column("EquipamentosManutencoes", "dados_adicionais")
