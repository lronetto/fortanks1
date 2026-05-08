"""ajusta documentos_sefaz para subtipos e dedupe por (tipo, nsu)

Revision ID: documentos_sefaz_002
Revises: documentos_sefaz_001
Create Date: 2026-05-07

Mudanças:
  - tipo: VARCHAR(10) -> VARCHAR(20) (cabe nfe_procEvento etc.)
  - drop UNIQUE em chave_acesso (eventos compartilham chNFe com o doc original)
  - add UNIQUE (tipo, nsu)

A migration é defensiva: detecta se cada alteração já está aplicada
antes de executar (idempotente).
"""
from alembic import op
import sqlalchemy as sa


revision = 'documentos_sefaz_002'
down_revision = 'documentos_sefaz_001'
branch_labels = None
depends_on = None

TABELA = 'documentos_sefaz'
UQ_CHAVE = 'uq_documentos_sefaz_chave_acesso'
UQ_TIPO_NSU = 'uq_documentos_sefaz_tipo_nsu'


def _tem_constraint_unique(inspector, tabela: str, nome: str) -> bool:
    try:
        return any(c.get('name') == nome for c in inspector.get_unique_constraints(tabela))
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABELA):
        # Tabela não existe — provavelmente alguém pulou a 001. Nada a fazer aqui.
        return

    # 1) tipo VARCHAR(10) -> VARCHAR(20)
    cols = {c['name']: c for c in inspector.get_columns(TABELA)}
    tipo_col = cols.get('tipo')
    if tipo_col is not None:
        existing_type = tipo_col['type']
        existing_len = getattr(existing_type, 'length', None)
        if existing_len is None or existing_len < 20:
            op.alter_column(
                TABELA, 'tipo',
                existing_type=sa.String(existing_len) if existing_len else sa.String(),
                type_=sa.String(20),
                existing_nullable=False,
            )

    # 2) drop UNIQUE em chave_acesso (mantém o índice ix_*).
    if _tem_constraint_unique(inspector, TABELA, UQ_CHAVE):
        op.drop_constraint(UQ_CHAVE, TABELA, type_='unique')

    # 3) add UNIQUE (tipo, nsu) se ainda não existe.
    inspector = sa.inspect(bind)  # re-inspect após mudanças
    if not _tem_constraint_unique(inspector, TABELA, UQ_TIPO_NSU):
        op.create_unique_constraint(UQ_TIPO_NSU, TABELA, ['tipo', 'nsu'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABELA):
        return

    if _tem_constraint_unique(inspector, TABELA, UQ_TIPO_NSU):
        op.drop_constraint(UQ_TIPO_NSU, TABELA, type_='unique')

    inspector = sa.inspect(bind)
    if not _tem_constraint_unique(inspector, TABELA, UQ_CHAVE):
        try:
            op.create_unique_constraint(UQ_CHAVE, TABELA, ['chave_acesso'])
        except Exception:
            pass

    cols = {c['name']: c for c in inspector.get_columns(TABELA)}
    tipo_col = cols.get('tipo')
    if tipo_col is not None:
        existing_len = getattr(tipo_col['type'], 'length', None)
        if existing_len and existing_len > 10:
            op.alter_column(
                TABELA, 'tipo',
                existing_type=sa.String(existing_len),
                type_=sa.String(10),
                existing_nullable=False,
            )
