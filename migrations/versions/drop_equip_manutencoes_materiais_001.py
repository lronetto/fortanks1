"""Remove tabela EquipamentosManutencoesMateriais (consumo passa a ser só JSON + movimentações).

Revision ID: drop_eq_manut_mat_001
Revises: manutencao_dados_adicionais_001
Create Date: 2026-04-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "drop_eq_manut_mat_001"
down_revision = "manutencao_dados_adicionais_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("EquipamentosManutencoesMateriais"):
        op.drop_table("EquipamentosManutencoesMateriais")


def downgrade():
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
