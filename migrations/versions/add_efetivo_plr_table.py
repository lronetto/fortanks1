"""add efetivo_plr table

Revision ID: efetivo_plr_001
Revises: plr_cargo_salario_001
Create Date: 2025-03-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'efetivo_plr_001'
down_revision = 'plr_cargo_salario_001'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("efetivo_plr") or inspector.has_table("PlrEfetivos"):
        return

    op.create_table(
        'efetivo_plr',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ano', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('cpf', sa.String(20), nullable=True),
        sa.Column('nome', sa.String(200), nullable=True),
        sa.Column('funcao', sa.String(150), nullable=True),
        sa.Column('salario', sa.Numeric(12, 2), nullable=True),
        sa.Column('data_nascimento', sa.Date(), nullable=True),
        sa.Column('data_demissao', sa.Date(), nullable=True),
        sa.Column('secao', sa.String(150), nullable=True),
        sa.Column('data_admissao', sa.Date(), nullable=True),
        sa.Column('chapa', sa.String(50), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("efetivo_plr"):
        op.drop_table("efetivo_plr")
    elif inspector.has_table("PlrEfetivos"):
        op.drop_table("PlrEfetivos")
