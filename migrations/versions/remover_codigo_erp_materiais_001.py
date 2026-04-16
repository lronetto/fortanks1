"""Remover coluna codigo_erp de Materiais

Revision ID: remover_codigo_erp_materiais_001
Revises: equip_emprestimo_001, drop_eq_manut_mat_001
Create Date: 2026-04-16

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "remover_codigo_erp_materiais_001"
down_revision = ("equip_emprestimo_001", "drop_eq_manut_mat_001")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("Materiais")}
    if "codigo_erp" not in cols:
        return

    with op.batch_alter_table("Materiais", schema=None) as batch_op:
        batch_op.drop_column("codigo_erp")


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("Materiais")}
    if "codigo_erp" in cols:
        return

    with op.batch_alter_table("Materiais", schema=None) as batch_op:
        batch_op.add_column(sa.Column("codigo_erp", sa.String(length=50), nullable=True))

