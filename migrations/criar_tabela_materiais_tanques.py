"""
Migração para criar tabela de relacionamento entre materiais e tanques
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'criar_tabela_materiais_tanques'
down_revision = None  # Ajuste conforme necessário
branch_labels = None
depends_on = None


def upgrade():
    """Criar tabela de relacionamento entre materiais e tanques"""
    
    # Criar tabela de relacionamento
    op.create_table('materiais_tanques',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('material_id', sa.Integer(), nullable=False),
        sa.Column('tanque_id', sa.Integer(), nullable=False),
        sa.Column('quantidade_total', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('placas_normais', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('placas_fecho', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('quantidade_bainhas', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('altura_total', sa.Float(), nullable=False),
        sa.Column('sistema', sa.String(length=10), nullable=False),
        sa.Column('quantidade_material', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['material_id'], ['materiais.id'], ),
        sa.ForeignKeyConstraint(['tanque_id'], ['tanques.id'], )
    )
    
    # Criar índices para melhor performance
    op.create_index('ix_materiais_tanques_material_id', 'materiais_tanques', ['material_id'])
    op.create_index('ix_materiais_tanques_tanque_id', 'materiais_tanques', ['tanque_id'])
    op.create_index('ix_materiais_tanques_sistema', 'materiais_tanques', ['sistema'])
    # Índice único para evitar duplicatas
    op.create_index('ix_materiais_tanques_unique', 'materiais_tanques', ['material_id', 'tanque_id'], unique=True)


def downgrade():
    """Remover tabela de relacionamento entre materiais e tanques"""
    
    # Remover índices
    op.drop_index('ix_materiais_tanques_unique', table_name='materiais_tanques')
    op.drop_index('ix_materiais_tanques_sistema', table_name='materiais_tanques')
    op.drop_index('ix_materiais_tanques_tanque_id', table_name='materiais_tanques')
    op.drop_index('ix_materiais_tanques_material_id', table_name='materiais_tanques')
    
    # Remover tabela
    op.drop_table('materiais_tanques')

