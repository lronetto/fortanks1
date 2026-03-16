"""add centro_custo_id em PedidosCompra

Revision ID: pedido_centro_custo_001
Revises: pedido_entregue_inicial_001
Create Date: 2026-03-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'pedido_centro_custo_001'
down_revision = 'pedido_entregue_inicial_001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'PedidosCompra',
        sa.Column('centro_custo_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_pedidoscompra_centro_custo',
        'PedidosCompra',
        'centros_custo',
        ['centro_custo_id'],
        ['id'],
    )


def downgrade():
    op.drop_constraint('fk_pedidoscompra_centro_custo', 'PedidosCompra', type_='foreignkey')
    op.drop_column('PedidosCompra', 'centro_custo_id')

