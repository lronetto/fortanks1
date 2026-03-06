"""add plr and cargo_salario tables

Revision ID: plr_cargo_salario_001
Revises: a16ac875e330
Create Date: 2025-03-04

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'plr_cargo_salario_001'
down_revision = 'a16ac875e330'
branch_labels = None
depends_on = None


def upgrade():
    # Tabela modelos_plr
    op.create_table('modelos_plr',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(150), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('ativo', sa.Boolean(), default=True),
        sa.Column('forma_calculo_colaborador', sa.String(100), nullable=True),
        sa.Column('pesos_colaboradores', sa.JSON(), nullable=True),
        sa.Column('forma_calculo_final', sa.String(100), nullable=True),
        sa.Column('config_calculo_final', sa.JSON(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Tabela associativa modelos_plr_departamentos
    op.create_table('modelos_plr_departamentos',
        sa.Column('modelo_plr_id', sa.Integer(), nullable=False),
        sa.Column('departamento_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['modelo_plr_id'], ['modelos_plr.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['departamento_id'], ['departamentos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('modelo_plr_id', 'departamento_id')
    )

    # Tabela plr_colaboradores
    op.create_table('plr_colaboradores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('modelo_plr_id', sa.Integer(), nullable=True),
        sa.Column('centro_custo_id', sa.Integer(), nullable=True),
        sa.Column('colaborador_id', sa.Integer(), nullable=False),
        sa.Column('equipe_alocada', sa.JSON(), nullable=True),
        sa.Column('avaliacao', sa.JSON(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['modelo_plr_id'], ['modelos_plr.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['centro_custo_id'], ['centros_custo.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['colaborador_id'], ['colaboradores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Tabela cargos_salarios
    op.create_table('cargos_salarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cargo_id', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('ano', sa.Integer(), nullable=False),
        sa.Column('salario', sa.Numeric(12, 2), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['cargo_id'], ['cargos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cargo_id', 'mes', 'ano', name='uq_cargo_mes_ano')
    )


def downgrade():
    op.drop_table('cargos_salarios')
    op.drop_table('plr_colaboradores')
    op.drop_table('modelos_plr_departamentos')
    op.drop_table('modelos_plr')
