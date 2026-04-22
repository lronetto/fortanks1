"""adiciona referencia texto de item de orcamento para material

Revision ID: orc_item_ref_mat_001
Revises: orcamento_rename_snake_to_domain_001
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa


revision = 'orc_item_ref_mat_001'
down_revision = 'orcamento_rename_snake_to_domain_001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'OrcamentoItens',
        sa.Column('descricao_item', sa.String(length=255), nullable=True),
    )

    op.create_table(
        'OrcamentoItensReferencias',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('texto_item', sa.String(length=255), nullable=False),
        sa.Column('material_id', sa.Integer(), nullable=True),
        sa.Column('observacao', sa.String(length=255), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['material_id'], ['Materiais.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('texto_item', 'material_id', name='uq_item_orcamento_material_ref'),
    )


def downgrade():
    op.drop_table('OrcamentoItensReferencias')
    op.drop_column('OrcamentoItens', 'descricao_item')
