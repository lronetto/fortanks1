"""Remover coluna codigo de Materiais

Revision ID: remover_codigo_materiais_001
Revises: remover_codigo_erp_materiais_001
Create Date: 2026-04-16

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "remover_codigo_materiais_001"
down_revision = "remover_codigo_erp_materiais_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("Materiais")}
    if "codigo" not in cols:
        return

    with op.batch_alter_table("Materiais", schema=None) as batch_op:
        batch_op.drop_column("codigo")


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("Materiais")}
    if "codigo" in cols:
        return

    with op.batch_alter_table("Materiais", schema=None) as batch_op:
        batch_op.add_column(sa.Column("codigo", sa.String(length=50), nullable=True))

