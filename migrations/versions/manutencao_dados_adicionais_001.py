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
    op.add_column(
        "EquipamentosManutencoes",
        sa.Column("dados_adicionais", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("EquipamentosManutencoes", "dados_adicionais")
