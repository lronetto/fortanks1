"""adiciona data em orcamentos e remove material_id

Revision ID: orcamento_data_drop_material_001
Revises: orc_item_ref_mat_001
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa


revision = "orcamento_data_drop_material_001"
down_revision = "orc_item_ref_mat_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    colunas = {c["name"] for c in inspector.get_columns("Orcamentos")}

    if "data" not in colunas:
        op.add_column("Orcamentos", sa.Column("data", sa.Date(), nullable=True))

    if "material_id" in colunas:
        for fk in inspector.get_foreign_keys("Orcamentos"):
            if "material_id" in (fk.get("constrained_columns") or []):
                if fk.get("name"):
                    op.drop_constraint(fk["name"], "Orcamentos", type_="foreignkey")
                break
        op.drop_column("Orcamentos", "material_id")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    colunas = {c["name"] for c in inspector.get_columns("Orcamentos")}

    if "material_id" not in colunas:
        op.add_column(
            "Orcamentos",
            sa.Column("material_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "orcamentos_ibfk_2",
            "Orcamentos",
            "Materiais",
            ["material_id"],
            ["id"],
        )

    if "data" in colunas:
        op.drop_column("Orcamentos", "data")
