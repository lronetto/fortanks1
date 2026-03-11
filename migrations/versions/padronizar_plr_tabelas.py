"""padronizar nomes das tabelas PLR (PlrModelos, PlrModelosDepartamentos, PlrAvaliacoes, PlrEfetivos)

Revision ID: padronizar_plr_001
Revises: efetivo_plr_001
Create Date: 2025-03-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'padronizar_plr_001'
down_revision = 'efetivo_plr_001'
branch_labels = None
depends_on = None


def upgrade():
    # Renomear coluna modelo_plr_id -> PlrModelo_id na tabela plr_colaboradores
    with op.batch_alter_table('plr_colaboradores', schema=None) as batch_op:
        batch_op.alter_column(
            'modelo_plr_id',
            new_column_name='PlrModelo_id',
            existing_type=sa.Integer(),
            nullable=True,
        )
    # Renomear coluna modelo_plr_id -> PlrModelo_id na tabela modelos_plr_departamentos
    with op.batch_alter_table('modelos_plr_departamentos', schema=None) as batch_op:
        batch_op.alter_column(
            'modelo_plr_id',
            new_column_name='PlrModelo_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
    # Renomear tabelas
    op.rename_table('modelos_plr_departamentos', 'PlrModelosDepartamentos')
    op.rename_table('plr_colaboradores', 'PlrAvaliacoes')
    op.rename_table('modelos_plr', 'PlrModelos')
    op.rename_table('efetivo_plr', 'PlrEfetivos')


def downgrade():
    op.rename_table('PlrEfetivos', 'efetivo_plr')
    op.rename_table('PlrModelos', 'modelos_plr')
    op.rename_table('PlrAvaliacoes', 'plr_colaboradores')
    op.rename_table('PlrModelosDepartamentos', 'modelos_plr_departamentos')
    with op.batch_alter_table('plr_colaboradores', schema=None) as batch_op:
        batch_op.alter_column(
            'PlrModelo_id',
            new_column_name='modelo_plr_id',
            existing_type=sa.Integer(),
            nullable=True,
        )
    with op.batch_alter_table('modelos_plr_departamentos', schema=None) as batch_op:
        batch_op.alter_column(
            'PlrModelo_id',
            new_column_name='modelo_plr_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
