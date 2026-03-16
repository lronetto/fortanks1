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
    op.add_column(
        'PedidosCompraItens',
        sa.Column('quantidade_entregue_inicial', sa.Numeric(15, 4), nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_column('PedidosCompraItens', 'quantidade_entregue_inicial')
