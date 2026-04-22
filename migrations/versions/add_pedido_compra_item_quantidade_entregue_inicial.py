"""add quantidade_entregue_inicial em PedidosCompraItens

Revision ID: pedido_entregue_inicial_001
Revises: plr_assiduidade_001
Create Date: 2026-03-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'pedido_entregue_inicial_001'
down_revision = 'plr_assiduidade_001'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("PedidosCompraItens"):
        return
    cols = {c["name"] for c in insp.get_columns("PedidosCompraItens")}
    if "quantidade_entregue_inicial" in cols:
        return
    op.add_column(
        "PedidosCompraItens",
        sa.Column("quantidade_entregue_inicial", sa.Numeric(15, 4), nullable=False, server_default="0"),
    )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("PedidosCompraItens") and "quantidade_entregue_inicial" in {
        c["name"] for c in insp.get_columns("PedidosCompraItens")
    }:
        op.drop_column("PedidosCompraItens", "quantidade_entregue_inicial")
