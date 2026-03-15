"""Unificar ano e mes em data na tabela PlrEfetivos

Revision ID: efetivo_plr_data_001
Revises: padronizar_plr_001
Create Date: 2025-03-13

"""
from alembic import op
import sqlalchemy as sa


revision = 'efetivo_plr_data_001'
down_revision = 'padronizar_plr_001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('PlrEfetivos', sa.Column('data', sa.Date(), nullable=True))
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        op.execute(sa.text(
            "UPDATE PlrEfetivos SET data = date(ano || '-' || substr('0' || mes, -2) || '-01')"
        ))
    else:
        op.execute(sa.text(
            "UPDATE \"PlrEfetivos\" SET data = (ano::text || '-' || LPAD(mes::text, 2, '0') || '-01')::date"
        ))
    op.alter_column(
        'PlrEfetivos',
        'data',
        existing_type=sa.Date(),
        nullable=False,
    )
    with op.batch_alter_table('PlrEfetivos', schema=None) as batch_op:
        batch_op.drop_column('mes')
        batch_op.drop_column('ano')


def downgrade():
    op.add_column('PlrEfetivos', sa.Column('ano', sa.Integer(), nullable=True))
    op.add_column('PlrEfetivos', sa.Column('mes', sa.Integer(), nullable=True))
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        op.execute(sa.text(
            "UPDATE PlrEfetivos SET ano = cast(strftime('%Y', data) as integer), mes = cast(strftime('%m', data) as integer)"
        ))
    else:
        op.execute(sa.text(
            "UPDATE \"PlrEfetivos\" SET ano = EXTRACT(YEAR FROM data)::integer, mes = EXTRACT(MONTH FROM data)::integer"
        ))
    op.alter_column('PlrEfetivos', 'ano', nullable=False)
    op.alter_column('PlrEfetivos', 'mes', nullable=False)
    with op.batch_alter_table('PlrEfetivos', schema=None) as batch_op:
        batch_op.drop_column('data')
