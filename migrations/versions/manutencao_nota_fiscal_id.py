"""manutencoes: nota_fiscal_id FK para NotaFiscal

Revision ID: manutencao_nf_001
Revises: add_protocolo_table
Create Date: 2026-04-01

"""
from alembic import op
import sqlalchemy as sa


revision = "manutencao_nf_001"
down_revision = "add_protocolo_table"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "manutencoes",
        sa.Column("nota_fiscal_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_manutencoes_nota_fiscal",
        "manutencoes",
        "NotaFiscal",
        ["nota_fiscal_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_manutencoes_nota_fiscal", "manutencoes", type_="foreignkey")
    op.drop_column("manutencoes", "nota_fiscal_id")
