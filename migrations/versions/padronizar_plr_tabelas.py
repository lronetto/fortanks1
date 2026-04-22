"""padronizar nomes das tabelas PLR (PlrModelos, PlrModelosDepartamentos, PlrAvaliacoes, PlrEfetivos)

Revision ID: padronizar_plr_001
Revises: efetivo_plr_001
Create Date: 2025-03-11

Compatível com ``plr_cargo_salario_001`` já criando tabelas com nomes novos (sem ``plr_colaboradores`` / ``modelos_plr``).
"""
from alembic import op
import sqlalchemy as sa

revision = "padronizar_plr_001"
down_revision = "efetivo_plr_001"
branch_labels = None
depends_on = None


def _colunas(inspector, tabela: str) -> set[str]:
    if not inspector.has_table(tabela):
        return set()
    return {c["name"] for c in inspector.get_columns(tabela)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # --- Legado: plr_colaboradores + coluna modelo_plr_id ---
    if insp.has_table("plr_colaboradores") and not insp.has_table("PlrAvaliacoes"):
        if "modelo_plr_id" in _colunas(insp, "plr_colaboradores"):
            with op.batch_alter_table("plr_colaboradores", schema=None) as batch_op:
                batch_op.alter_column(
                    "modelo_plr_id",
                    new_column_name="PlrModelo_id",
                    existing_type=sa.Integer(),
                    nullable=True,
                )
        op.rename_table("plr_colaboradores", "PlrAvaliacoes")
    elif insp.has_table("PlrAvaliacoes"):
        cols = _colunas(insp, "PlrAvaliacoes")
        if "modelo_plr_id" in cols and "PlrModelo_id" not in cols:
            with op.batch_alter_table("PlrAvaliacoes", schema=None) as batch_op:
                batch_op.alter_column(
                    "modelo_plr_id",
                    new_column_name="PlrModelo_id",
                    existing_type=sa.Integer(),
                    nullable=True,
                )

    insp = sa.inspect(bind)

    # --- Legado: modelos_plr_departamentos ---
    if insp.has_table("modelos_plr_departamentos") and not insp.has_table(
        "PlrModelosDepartamentos"
    ):
        if "modelo_plr_id" in _colunas(insp, "modelos_plr_departamentos"):
            with op.batch_alter_table("modelos_plr_departamentos", schema=None) as batch_op:
                batch_op.alter_column(
                    "modelo_plr_id",
                    new_column_name="PlrModelo_id",
                    existing_type=sa.Integer(),
                    nullable=False,
                )
        op.rename_table("modelos_plr_departamentos", "PlrModelosDepartamentos")
    elif insp.has_table("PlrModelosDepartamentos"):
        cols = _colunas(insp, "PlrModelosDepartamentos")
        if "modelo_plr_id" in cols and "PlrModelo_id" not in cols:
            with op.batch_alter_table("PlrModelosDepartamentos", schema=None) as batch_op:
                batch_op.alter_column(
                    "modelo_plr_id",
                    new_column_name="PlrModelo_id",
                    existing_type=sa.Integer(),
                    nullable=False,
                )

    insp = sa.inspect(bind)

    if insp.has_table("modelos_plr") and not insp.has_table("PlrModelos"):
        op.rename_table("modelos_plr", "PlrModelos")

    insp = sa.inspect(bind)

    if insp.has_table("efetivo_plr") and not insp.has_table("PlrEfetivos"):
        op.rename_table("efetivo_plr", "PlrEfetivos")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("PlrEfetivos") and not insp.has_table("efetivo_plr"):
        op.rename_table("PlrEfetivos", "efetivo_plr")

    insp = sa.inspect(bind)

    if insp.has_table("PlrModelos") and not insp.has_table("modelos_plr"):
        op.rename_table("PlrModelos", "modelos_plr")

    insp = sa.inspect(bind)

    if insp.has_table("PlrModelosDepartamentos") and not insp.has_table(
        "modelos_plr_departamentos"
    ):
        tinha_plr_modelo_id = "PlrModelo_id" in _colunas(insp, "PlrModelosDepartamentos")
        op.rename_table("PlrModelosDepartamentos", "modelos_plr_departamentos")
        if tinha_plr_modelo_id:
            with op.batch_alter_table("modelos_plr_departamentos", schema=None) as batch_op:
                batch_op.alter_column(
                    "PlrModelo_id",
                    new_column_name="modelo_plr_id",
                    existing_type=sa.Integer(),
                    nullable=False,
                )

    insp = sa.inspect(bind)

    if insp.has_table("PlrAvaliacoes") and not insp.has_table("plr_colaboradores"):
        tinha_plr_modelo_id_av = "PlrModelo_id" in _colunas(insp, "PlrAvaliacoes")
        op.rename_table("PlrAvaliacoes", "plr_colaboradores")
        if tinha_plr_modelo_id_av:
            with op.batch_alter_table("plr_colaboradores", schema=None) as batch_op:
                batch_op.alter_column(
                    "PlrModelo_id",
                    new_column_name="modelo_plr_id",
                    existing_type=sa.Integer(),
                    nullable=True,
                )
