"""Unificar mes/ano em data na tabela cargos_salarios

Revision ID: cargos_salarios_data_001
Revises: efetivo_plr_data_001
Create Date: 2025-03-13

"""
from alembic import op
import sqlalchemy as sa


revision = 'cargos_salarios_data_001'
down_revision = 'efetivo_plr_data_001'
branch_labels = None
depends_on = None


def upgrade():
    # Adiciona coluna data (inicialmente permitindo nulo)
    with op.batch_alter_table('cargos_salarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data', sa.Date(), nullable=True))

    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        # AAAA-MM-01 a partir de ano/mes
        op.execute(sa.text(
            "UPDATE cargos_salarios "
            "SET data = date(ano || '-' || substr('0' || mes, -2) || '-01')"
        ))
    else:
        # PostgreSQL / outros com suporte a cast de texto para date
        op.execute(sa.text(
            "UPDATE cargos_salarios "
            "SET data = (ano::text || '-' || LPAD(mes::text, 2, '0') || '-01')::date"
        ))

    # Torna data obrigatória, cria nova unique e remove mes/ano
    with op.batch_alter_table('cargos_salarios', schema=None) as batch_op:
        batch_op.alter_column('data', existing_type=sa.Date(), nullable=False)
        batch_op.drop_constraint('uq_cargo_mes_ano', type_='unique')
        batch_op.create_unique_constraint('uq_cargo_data', ['cargo_id', 'data'])
        batch_op.drop_column('mes')
        batch_op.drop_column('ano')


def downgrade():
    # Recria mes/ano
    with op.batch_alter_table('cargos_salarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ano', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('mes', sa.Integer(), nullable=True))

    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        op.execute(sa.text(
            "UPDATE cargos_salarios "
            "SET ano = cast(strftime('%Y', data) as integer), "
            "    mes = cast(strftime('%m', data) as integer)"
        ))
    else:
        op.execute(sa.text(
            "UPDATE cargos_salarios "
            "SET ano = EXTRACT(YEAR FROM data)::integer, "
            "    mes = EXTRACT(MONTH FROM data)::integer"
        ))

    with op.batch_alter_table('cargos_salarios', schema=None) as batch_op:
        batch_op.alter_column('ano', nullable=False)
        batch_op.alter_column('mes', nullable=False)
        batch_op.drop_constraint('uq_cargo_data', type_='unique')
        batch_op.create_unique_constraint('uq_cargo_mes_ano', ['cargo_id', 'mes', 'ano'])
        batch_op.drop_column('data')

