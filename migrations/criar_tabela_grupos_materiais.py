"""
Migração para criar tabela de grupos de materiais
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'criar_tabela_grupos_materiais'
down_revision = None  # Ajuste conforme necessário
branch_labels = None
depends_on = None


def upgrade():
    """Criar tabela de grupos de materiais e tabela de associação"""
    
    # Criar tabela de grupos de materiais
    op.create_table('grupos_materiais',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('codigo', sa.String(length=20), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=True),
        sa.Column('cor', sa.String(length=7), nullable=True),
        sa.Column('icone', sa.String(length=50), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.Column('criado_por_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['criado_por_id'], ['usuarios.id'], ),
        sa.UniqueConstraint('codigo'),
        sa.UniqueConstraint('nome')
    )
    
    # Criar tabela de associação entre materiais e grupos
    op.create_table('materiais_grupos',
        sa.Column('material_id', sa.Integer(), nullable=False),
        sa.Column('grupo_id', sa.Integer(), nullable=False),
        sa.Column('data_associacao', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['grupo_id'], ['grupos_materiais.id'], ),
        sa.ForeignKeyConstraint(['material_id'], ['materiais.id'], ),
        sa.PrimaryKeyConstraint('material_id', 'grupo_id')
    )
    
    # Criar índices para melhor performance
    op.create_index('ix_grupos_materiais_nome', 'grupos_materiais', ['nome'])
    op.create_index('ix_grupos_materiais_codigo', 'grupos_materiais', ['codigo'])
    op.create_index('ix_grupos_materiais_ativo', 'grupos_materiais', ['ativo'])
    op.create_index('ix_materiais_grupos_material_id', 'materiais_grupos', ['material_id'])
    op.create_index('ix_materiais_grupos_grupo_id', 'materiais_grupos', ['grupo_id'])


def downgrade():
    """Remover tabela de grupos de materiais e tabela de associação"""
    
    # Remover índices
    op.drop_index('ix_materiais_grupos_grupo_id', table_name='materiais_grupos')
    op.drop_index('ix_materiais_grupos_material_id', table_name='materiais_grupos')
    op.drop_index('ix_grupos_materiais_ativo', table_name='grupos_materiais')
    op.drop_index('ix_grupos_materiais_codigo', table_name='grupos_materiais')
    op.drop_index('ix_grupos_materiais_nome', table_name='grupos_materiais')
    
    # Remover tabelas
    op.drop_table('materiais_grupos')
    op.drop_table('grupos_materiais')
