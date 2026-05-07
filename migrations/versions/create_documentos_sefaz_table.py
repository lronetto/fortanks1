"""create documentos_sefaz table

Revision ID: documentos_sefaz_001
Revises: drop_eq_manut_mat_001, rename_plr_assiduidades_001, equip_emprestimo_001
Create Date: 2026-05-07

Esta migration faz duas coisas:
  1. Mescla os três heads divergentes existentes (drop_eq_manut_mat_001,
     rename_plr_assiduidades_001, equip_emprestimo_001) em um único head.
  2. Cria a tabela `documentos_sefaz` com FK para `fornecedores`,
     unique em `chave_acesso` e índices em campos consultados (tipo,
     data, nsu, fornecedor_id, data_criacao).
"""
from alembic import op
import sqlalchemy as sa


revision = 'documentos_sefaz_001'
down_revision = (
    'drop_eq_manut_mat_001',
    'rename_plr_assiduidades_001',
    'equip_emprestimo_001',
)
branch_labels = None
depends_on = None

TABELA = 'documentos_sefaz'


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABELA):
        return

    op.create_table(
        TABELA,
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=10), nullable=False),
        sa.Column('data', sa.DateTime(), nullable=True),
        sa.Column('fornecedor_id', sa.Integer(), nullable=True),
        sa.Column('valor_total', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('dados_adicionais', sa.Text(), nullable=True),
        sa.Column('nsu', sa.String(length=20), nullable=True),
        sa.Column('chave_acesso', sa.String(length=50), nullable=True),
        sa.Column('data_criacao', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['fornecedor_id'], ['fornecedores.id'],
            name='fk_documentos_sefaz_fornecedor',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chave_acesso', name='uq_documentos_sefaz_chave_acesso'),
    )

    op.create_index('ix_documentos_sefaz_tipo', TABELA, ['tipo'])
    op.create_index('ix_documentos_sefaz_data', TABELA, ['data'])
    op.create_index('ix_documentos_sefaz_fornecedor_id', TABELA, ['fornecedor_id'])
    op.create_index('ix_documentos_sefaz_nsu', TABELA, ['nsu'])
    op.create_index('ix_documentos_sefaz_chave_acesso', TABELA, ['chave_acesso'])
    op.create_index('ix_documentos_sefaz_data_criacao', TABELA, ['data_criacao'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABELA):
        return

    for nome in (
        'ix_documentos_sefaz_data_criacao',
        'ix_documentos_sefaz_chave_acesso',
        'ix_documentos_sefaz_nsu',
        'ix_documentos_sefaz_fornecedor_id',
        'ix_documentos_sefaz_data',
        'ix_documentos_sefaz_tipo',
    ):
        try:
            op.drop_index(nome, table_name=TABELA)
        except Exception:
            pass
    op.drop_table(TABELA)
