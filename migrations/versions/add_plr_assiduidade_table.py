"""add PlrAssiduidade table

Revision ID: plr_assiduidade_001
Revises: padronizar_plr_001
Create Date: 2025-03-13

"""
from alembic import op
import sqlalchemy as sa

revision = 'plr_assiduidade_001'
down_revision = 'cargos_salarios_data_001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'PlrAssiduidade',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('colaborador_id', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('ano', sa.Integer(), nullable=False),
        sa.Column('faltas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['colaborador_id'], ['colaboradores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('colaborador_id', 'mes', 'ano', name='uq_plr_assiduidade_colab_mes_ano'),
    )


def downgrade():
    op.drop_table('PlrAssiduidade')
