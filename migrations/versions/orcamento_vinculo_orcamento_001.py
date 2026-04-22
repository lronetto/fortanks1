"""Orcamentos: coluna de vínculo opcional a outro orçamento.

Revision ID: orcamento_vinculo_orcamento_001
Revises: orcamento_data_drop_material_001
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa


revision = "orcamento_vinculo_orcamento_001"
down_revision = "orcamento_data_drop_material_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    colunas = {c["name"] for c in inspector.get_columns("Orcamentos")}

    if "vinculado_a_orcamento_id" not in colunas:
        op.add_column(
            "Orcamentos",
            sa.Column("vinculado_a_orcamento_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_orcamentos_vinculo_orcamento",
            "Orcamentos",
            "Orcamentos",
            ["vinculado_a_orcamento_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    colunas = {c["name"] for c in inspector.get_columns("Orcamentos")}

    if "vinculado_a_orcamento_id" in colunas:
        for fk in inspector.get_foreign_keys("Orcamentos"):
            if fk.get("constrained_columns") == ["vinculado_a_orcamento_id"]:
                nome = fk.get("name") or "fk_orcamentos_vinculo_orcamento"
                op.drop_constraint(nome, "Orcamentos", type_="foreignkey")
                break
        op.drop_column("Orcamentos", "vinculado_a_orcamento_id")
