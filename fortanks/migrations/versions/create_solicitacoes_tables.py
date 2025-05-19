"""create solicitacoes tables

Revision ID: create_solicitacoes_tables
Revises: 
Create Date: 2024-03-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'create_solicitacoes_tables'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Criar tabela de solicitações
    op.create_table('solicitacoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('numero', sa.String(20), nullable=False),
        sa.Column('data_solicitacao', sa.DateTime(), nullable=False, default=datetime.now),
        sa.Column('data_necessidade', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='Pendente'),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.Column('centro_custo_id', sa.Integer(), nullable=False),
        sa.Column('solicitante_id', sa.Integer(), nullable=False),
        sa.Column('aprovador_id', sa.Integer(), nullable=True),
        sa.Column('data_aprovacao', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['centro_custo_id'], ['centros_custo.id'], ),
        sa.ForeignKeyConstraint(['solicitante_id'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['aprovador_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('numero')
    )
    
    # Criar tabela de itens de solicitação
    op.create_table('itens_solicitacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('solicitacao_id', sa.Integer(), nullable=False),
        sa.Column('material_id', sa.Integer(), nullable=False),
        sa.Column('quantidade', sa.Numeric(10, 2), nullable=False),
        sa.Column('unidade', sa.String(20), nullable=False),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['solicitacao_id'], ['solicitacoes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['material_id'], ['materiais.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Criar índices
    op.create_index('idx_solicitacoes_numero', 'solicitacoes', ['numero'])
    op.create_index('idx_solicitacoes_status', 'solicitacoes', ['status'])
    op.create_index('idx_solicitacoes_data', 'solicitacoes', ['data_solicitacao'])
    op.create_index('idx_itens_solicitacao_solicitacao', 'itens_solicitacao', ['solicitacao_id'])
    op.create_index('idx_itens_solicitacao_material', 'itens_solicitacao', ['material_id'])

def downgrade():
    # Remover índices
    op.drop_index('idx_itens_solicitacao_material')
    op.drop_index('idx_itens_solicitacao_solicitacao')
    op.drop_index('idx_solicitacoes_data')
    op.drop_index('idx_solicitacoes_status')
    op.drop_index('idx_solicitacoes_numero')
    
    # Remover tabelas
    op.drop_table('itens_solicitacao')
    op.drop_table('solicitacoes') 