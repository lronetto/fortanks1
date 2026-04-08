"""Cria tabela EquipamentosManutencoesMateriais (consumo de estoque na manutenção).

Encadeada em fix_entradas_fk_001 para ambientes cuja linha Alembic segue o ramo pedidos/PLR.

Revision ID: eq_manut_materiais_001
Revises: fix_entradas_fk_001
Create Date: 2026-04-08

"""
from alembic import op
import sqlalchemy as sa


revision = "eq_manut_materiais_001"
down_revision = "fix_entradas_fk_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "EquipamentosManutencoesMateriais",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("manutencao_id", sa.Integer(), nullable=False),
        sa.Column("estoque_id", sa.Integer(), nullable=False),
        sa.Column("quantidade", sa.Numeric(15, 4), nullable=False),
        sa.Column("valor_unitario", sa.Numeric(15, 4), nullable=True),
        sa.Column("movimentacao_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["estoque_id"],
            ["Estoque.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manutencao_id"],
            ["EquipamentosManutencoes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("EquipamentosManutencoesMateriais")
