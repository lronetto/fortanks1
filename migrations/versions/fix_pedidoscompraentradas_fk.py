"""Corrige FK de PedidosCompraEntradas: pedido_item_id deve referenciar PedidosCompraItens.id

No banco estava referenciando PedidosCompra.id por engano.
Revision ID: fix_entradas_fk_001
Revises: pedido_centro_custo_001
Create Date: 2026-03-16

"""
from alembic import op


revision = 'fix_entradas_fk_001'
down_revision = 'pedido_centro_custo_001'
branch_labels = None
depends_on = None


def upgrade():
    # Remover FK errada (pedido_item_id -> PedidosCompra.id)
    op.drop_constraint(
        'PedidosCompraEntradas_ibfk_1',
        'PedidosCompraEntradas',
        type_='foreignkey'
    )
    # Criar FK correta (pedido_item_id -> PedidosCompraItens.id)
    op.create_foreign_key(
        'fk_pedidoscompraentradas_pedido_item',
        'PedidosCompraEntradas',
        'PedidosCompraItens',
        ['pedido_item_id'],
        ['id']
    )


def downgrade():
    op.drop_constraint(
        'fk_pedidoscompraentradas_pedido_item',
        'PedidosCompraEntradas',
        type_='foreignkey'
    )
    op.create_foreign_key(
        'PedidosCompraEntradas_ibfk_1',
        'PedidosCompraEntradas',
        'PedidosCompra',
        ['pedido_item_id'],
        ['id']
    )
