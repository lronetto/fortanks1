"""Tabela equipamento_emprestimos (emprestimo a colaboradores)

Revision ID: equip_emprestimo_001
Revises: manutencao_nf_001
Create Date: 2026-04-01

"""
from alembic import op
import sqlalchemy as sa


revision = "equip_emprestimo_001"
down_revision = "manutencao_nf_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "EquipamentosEmprestimos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipamento_id", sa.Integer(), sa.ForeignKey("Equipamentos.id"), nullable=False),
        sa.Column("colaborador_id", sa.Integer(), sa.ForeignKey("colaboradores.id"), nullable=False),
        sa.Column("data_entrega", sa.DateTime(), nullable=False),
        sa.Column("data_recebimento", sa.DateTime(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("usuario_registro_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("data_cadastro", sa.DateTime(), nullable=True),
        sa.Column("data_atualizacao", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("EquipamentosEmprestimos")
