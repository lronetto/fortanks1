"""Renomear tabela PLR de assiduidade para plural (PlrAssiduidades).

Revision ID: rename_plr_assiduidades_001
Revises: orc_item_qtd_prec_001

Compatível com instalações que já têm ``PlrAssiduidade`` (singular).
"""

import sqlalchemy as sa
from alembic import op

revision = "rename_plr_assiduidades_001"
down_revision = "orc_item_qtd_prec_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("PlrAssiduidade") and not insp.has_table("PlrAssiduidades"):
        op.rename_table("PlrAssiduidade", "PlrAssiduidades")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("PlrAssiduidades") and not insp.has_table("PlrAssiduidade"):
        op.rename_table("PlrAssiduidades", "PlrAssiduidade")
