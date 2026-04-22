"""aumentar_precisao_quantidade_produto_composto

Revision ID: a16ac875e330
Revises: c44cb0d0c6af
Create Date: 2025-07-30 16:14:39.864958

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a16ac875e330'
down_revision = 'c44cb0d0c6af'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("ProdComp_Item"):
        return

    colunas = {c["name"] for c in insp.get_columns("ProdComp_Item")}
    if "quantidade" not in colunas:
        return

    # Aumentar a precisão do campo quantidade na tabela ProdComp_Item
    # De Numeric(10, 5) para Numeric(15, 8) para permitir mais casas decimais
    op.alter_column(
        "ProdComp_Item",
        "quantidade",
        existing_type=sa.Numeric(precision=10, scale=5),
        type_=sa.Numeric(precision=15, scale=8),
        existing_nullable=False,
    )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("ProdComp_Item"):
        return

    colunas = {c["name"] for c in insp.get_columns("ProdComp_Item")}
    if "quantidade" not in colunas:
        return

    # Reverter para a precisão original
    op.alter_column(
        "ProdComp_Item",
        "quantidade",
        existing_type=sa.Numeric(precision=15, scale=8),
        type_=sa.Numeric(precision=10, scale=5),
        existing_nullable=False,
    )
