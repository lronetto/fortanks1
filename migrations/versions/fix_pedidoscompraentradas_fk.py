"""Corrige FK de PedidosCompraEntradas: pedido_item_id deve referenciar PedidosCompraItens.id

No banco estava referenciando PedidosCompra.id por engano.
Revision ID: fix_entradas_fk_001
Revises: pedido_centro_custo_001
Create Date: 2026-03-16

Idempotente: se a FK já apontar para ``PedidosCompraItens``, não altera; nomes de FK no MySQL podem diferir de ``ibfk_1``.
"""
from alembic import op
import sqlalchemy as sa

revision = "fix_entradas_fk_001"
down_revision = "pedido_centro_custo_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("PedidosCompraEntradas"):
        return

    fks = insp.get_foreign_keys("PedidosCompraEntradas")
    for fk in fks:
        cols = list(fk.get("constrained_columns") or [])
        if cols == ["pedido_item_id"] and fk.get("referred_table") == "PedidosCompraItens":
            return

    for fk in fks:
        cols = list(fk.get("constrained_columns") or [])
        if cols == ["pedido_item_id"] and fk.get("referred_table") == "PedidosCompra":
            op.drop_constraint(fk["name"], "PedidosCompraEntradas", type_="foreignkey")
            break

    insp = sa.inspect(bind)
    names = {fk["name"] for fk in insp.get_foreign_keys("PedidosCompraEntradas")}
    if "fk_pedidoscompraentradas_pedido_item" not in names:
        op.create_foreign_key(
            "fk_pedidoscompraentradas_pedido_item",
            "PedidosCompraEntradas",
            "PedidosCompraItens",
            ["pedido_item_id"],
            ["id"],
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("PedidosCompraEntradas"):
        return
    names = {fk["name"] for fk in insp.get_foreign_keys("PedidosCompraEntradas")}
    if "fk_pedidoscompraentradas_pedido_item" in names:
        op.drop_constraint(
            "fk_pedidoscompraentradas_pedido_item",
            "PedidosCompraEntradas",
            type_="foreignkey",
        )
    insp = sa.inspect(bind)
    names = {fk["name"] for fk in insp.get_foreign_keys("PedidosCompraEntradas")}
    if "PedidosCompraEntradas_ibfk_1" not in names:
        op.create_foreign_key(
            "PedidosCompraEntradas_ibfk_1",
            "PedidosCompraEntradas",
            "PedidosCompra",
            ["pedido_item_id"],
            ["id"],
        )
