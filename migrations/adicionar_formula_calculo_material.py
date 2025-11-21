"""
Migração para adicionar campo formula_calculo na tabela de materiais
A fórmula é universal e será aplicada a todos os tanques que usarem o material
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'adicionar_formula_calculo_material'
down_revision = None  # Ajuste conforme necessário
branch_labels = None
depends_on = None


def upgrade():
    """Adicionar campo formula_calculo na tabela de materiais"""
    
    # Adicionar coluna formula_calculo
    op.add_column('materiais', 
        sa.Column('formula_calculo', sa.String(length=500), nullable=True)
    )


def downgrade():
    """Remover campo formula_calculo da tabela de materiais"""
    
    # Remover coluna formula_calculo
    op.drop_column('materiais', 'formula_calculo')

