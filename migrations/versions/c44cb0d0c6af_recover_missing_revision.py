"""Revisão ponte recuperada para alinhar histórico do Alembic.

Revision ID: c44cb0d0c6af
Revises: create_solicitacoes_tables
Create Date: 2026-04-20
"""


revision = "c44cb0d0c6af"
down_revision = "create_solicitacoes_tables"
branch_labels = None
depends_on = None


def upgrade():
    # Migração de ponte sem alterações de schema.
    pass


def downgrade():
    pass
