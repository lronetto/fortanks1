"""Remove tabela ConcretoConcretagensTanques (associação não é mais modelada).

Revision ID: drop_concretagens_tanques_001
Revises: tanques_transportes_001
Create Date: 2026-04-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "drop_concretagens_tanques_001"
down_revision = "tanques_transportes_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("ConcretoConcretagensTanques"):
        op.drop_table("ConcretoConcretagensTanques")


def downgrade():
    op.create_table(
        "ConcretoConcretagensTanques",
        sa.Column("concretagem_id", sa.Integer(), nullable=False),
        sa.Column("tanque_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["concretagem_id"],
            ["ConcretoConcretagens.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tanque_id"],
            ["Tanques.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("concretagem_id", "tanque_id"),
    )
