"""Unificar ano e mes em data na tabela PlrEfetivos

Revision ID: efetivo_plr_data_001
Revises: padronizar_plr_001
Create Date: 2025-03-13

Idempotente: bancos já alinhados ao ORM (só coluna ``data``) não são alterados.
MySQL/MariaDB: ``UPDATE`` usa ``STR_TO_DATE`` (evita sintaxe exclusiva de PostgreSQL).
"""
from alembic import op
import sqlalchemy as sa

revision = "efetivo_plr_data_001"
down_revision = "padronizar_plr_001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("PlrEfetivos"):
        return

    cols = {c["name"] for c in insp.get_columns("PlrEfetivos")}
    # ORM atual: referência única em ``data``, sem ``ano``/``mes``.
    if "data" in cols and "ano" not in cols and "mes" not in cols:
        return

    if "data" not in cols:
        op.add_column("PlrEfetivos", sa.Column("data", sa.Date(), nullable=True))
        cols.add("data")

    dialect = bind.dialect.name
    if "ano" in cols and "mes" in cols:
        if dialect == "sqlite":
            op.execute(
                sa.text(
                    "UPDATE PlrEfetivos SET data = date(ano || '-' || substr('0' || mes, -2) || '-01') "
                    "WHERE data IS NULL"
                )
            )
        elif dialect in ("mysql", "mariadb"):
            op.execute(
                sa.text(
                    "UPDATE PlrEfetivos SET `data` = STR_TO_DATE(CONCAT(`ano`, '-', LPAD(`mes`, 2, '0'), '-01'), '%Y-%m-%d') "
                    "WHERE `ano` IS NOT NULL AND `mes` IS NOT NULL AND `data` IS NULL"
                )
            )
        else:
            op.execute(
                sa.text(
                    'UPDATE "PlrEfetivos" SET data = (ano::text || \'-\' || LPAD(mes::text, 2, \'0\') || \'-01\')::date '
                    "WHERE data IS NULL"
                )
            )

    op.alter_column(
        "PlrEfetivos",
        "data",
        existing_type=sa.Date(),
        nullable=False,
    )

    with op.batch_alter_table("PlrEfetivos", schema=None) as batch_op:
        if "mes" in cols:
            batch_op.drop_column("mes")
        if "ano" in cols:
            batch_op.drop_column("ano")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("PlrEfetivos"):
        return

    cols = {c["name"] for c in insp.get_columns("PlrEfetivos")}
    if "ano" in cols and "mes" in cols:
        return
    if "data" not in cols:
        return

    op.add_column("PlrEfetivos", sa.Column("ano", sa.Integer(), nullable=True))
    op.add_column("PlrEfetivos", sa.Column("mes", sa.Integer(), nullable=True))

    dialect = bind.dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                "UPDATE PlrEfetivos SET ano = cast(strftime('%Y', data) as integer), "
                "mes = cast(strftime('%m', data) as integer)"
            )
        )
    elif dialect in ("mysql", "mariadb"):
        op.execute(
            sa.text(
                "UPDATE PlrEfetivos SET `ano` = YEAR(`data`), `mes` = MONTH(`data`)"
            )
        )
    else:
        op.execute(
            sa.text(
                'UPDATE "PlrEfetivos" SET ano = EXTRACT(YEAR FROM data)::integer, '
                "mes = EXTRACT(MONTH FROM data)::integer"
            )
        )

    op.alter_column("PlrEfetivos", "ano", nullable=False)
    op.alter_column("PlrEfetivos", "mes", nullable=False)
    with op.batch_alter_table("PlrEfetivos", schema=None) as batch_op:
        batch_op.drop_column("data")
