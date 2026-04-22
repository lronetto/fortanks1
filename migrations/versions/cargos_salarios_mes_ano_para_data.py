"""Unificar mes/ano em data na tabela cargos_salarios

Revision ID: cargos_salarios_data_001
Revises: efetivo_plr_data_001
Create Date: 2025-03-13

Idempotente se ``data`` já existir (schema alinhado ao modelo ``CargoSalario``).
MySQL/MariaDB: ``UPDATE`` com ``STR_TO_DATE`` em vez de sintaxe PostgreSQL.
"""
from alembic import op
import sqlalchemy as sa

revision = "cargos_salarios_data_001"
down_revision = "efetivo_plr_data_001"
branch_labels = None
depends_on = None


def _mysql_garante_indice_cargo_id_para_fk(inspector):
    """
    InnoDB pode usar o índice único (cargo_id, mes, ano) como suporte à FK ``cargo_id`` -> ``cargos``.
    Antes de dropar ``uq_cargo_mes_ano``, precisamos de um índice **não único** só em ``cargo_id``.
    """
    bind = op.get_bind()
    if bind.dialect.name not in ("mysql", "mariadb"):
        return
    for ix in inspector.get_indexes("cargos_salarios"):
        cols = list(ix.get("column_names") or [])
        if cols == ["cargo_id"] and not ix.get("unique", False):
            return
    names = {ix.get("name") for ix in inspector.get_indexes("cargos_salarios")}
    if "ix_cargos_salarios_cargo_id_fk" in names:
        return
    op.create_index(
        "ix_cargos_salarios_cargo_id_fk",
        "cargos_salarios",
        ["cargo_id"],
        unique=False,
    )


def _drop_mysql_fks_referenciando_cargos_salarios(bind):
    """Remove FKs de outras tabelas que apontam para ``cargos_salarios`` (se existirem)."""
    if bind.dialect.name not in ("mysql", "mariadb"):
        return
    rows = bind.execute(
        sa.text(
            """
            SELECT DISTINCT kcu.TABLE_NAME, rc.CONSTRAINT_NAME
            FROM information_schema.REFERENTIAL_CONSTRAINTS rc
            INNER JOIN information_schema.KEY_COLUMN_USAGE kcu
                ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
                AND rc.TABLE_NAME = kcu.TABLE_NAME
                AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
            WHERE rc.CONSTRAINT_SCHEMA = DATABASE()
              AND rc.REFERENCED_TABLE_NAME = 'cargos_salarios'
            """
        )
    ).fetchall()
    for table_name, constraint_name in rows:
        bind.execute(
            sa.text(f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{constraint_name}`")
        )


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("cargos_salarios"):
        return

    cols = {c["name"] for c in insp.get_columns("cargos_salarios")}
    if "data" in cols and "mes" not in cols and "ano" not in cols:
        return

    if "data" not in cols:
        with op.batch_alter_table("cargos_salarios", schema=None) as batch_op:
            batch_op.add_column(sa.Column("data", sa.Date(), nullable=True))

    dialect = bind.dialect.name
    if "mes" in cols and "ano" in cols:
        if dialect == "sqlite":
            op.execute(
                sa.text(
                    "UPDATE cargos_salarios "
                    "SET data = date(ano || '-' || substr('0' || mes, -2) || '-01') "
                    "WHERE data IS NULL"
                )
            )
        elif dialect in ("mysql", "mariadb"):
            op.execute(
                sa.text(
                    "UPDATE cargos_salarios SET `data` = STR_TO_DATE(CONCAT(`ano`, '-', LPAD(`mes`, 2, '0'), '-01'), '%Y-%m-%d') "
                    "WHERE `ano` IS NOT NULL AND `mes` IS NOT NULL AND `data` IS NULL"
                )
            )
        else:
            op.execute(
                sa.text(
                    "UPDATE cargos_salarios "
                    "SET data = (ano::text || '-' || LPAD(mes::text, 2, '0') || '-01')::date "
                    "WHERE data IS NULL"
                )
            )

    op.alter_column(
        "cargos_salarios",
        "data",
        existing_type=sa.Date(),
        nullable=False,
    )

    insp = sa.inspect(bind)
    uqs = {c["name"] for c in insp.get_unique_constraints("cargos_salarios")}

    if "uq_cargo_mes_ano" in uqs:
        _mysql_garante_indice_cargo_id_para_fk(insp)
        insp = sa.inspect(bind)
        _drop_mysql_fks_referenciando_cargos_salarios(bind)

    with op.batch_alter_table("cargos_salarios", schema=None) as batch_op:
        if "uq_cargo_mes_ano" in uqs:
            batch_op.drop_constraint("uq_cargo_mes_ano", type_="unique")
        if "uq_cargo_data" not in uqs:
            batch_op.create_unique_constraint("uq_cargo_data", ["cargo_id", "data"])
        if "mes" in cols:
            batch_op.drop_column("mes")
        if "ano" in cols:
            batch_op.drop_column("ano")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("cargos_salarios"):
        return

    cols = {c["name"] for c in insp.get_columns("cargos_salarios")}
    if "ano" in cols and "mes" in cols:
        return
    if "data" not in cols:
        return

    with op.batch_alter_table("cargos_salarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ano", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("mes", sa.Integer(), nullable=True))

    dialect = bind.dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                "UPDATE cargos_salarios "
                "SET ano = cast(strftime('%Y', data) as integer), "
                "    mes = cast(strftime('%m', data) as integer)"
            )
        )
    elif dialect in ("mysql", "mariadb"):
        op.execute(
            sa.text(
                "UPDATE cargos_salarios SET `ano` = YEAR(`data`), `mes` = MONTH(`data`)"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE cargos_salarios "
                "SET ano = EXTRACT(YEAR FROM data)::integer, "
                "    mes = EXTRACT(MONTH FROM data)::integer"
            )
        )

    insp = sa.inspect(bind)
    uqs = {c["name"] for c in insp.get_unique_constraints("cargos_salarios")}

    with op.batch_alter_table("cargos_salarios", schema=None) as batch_op:
        batch_op.alter_column("ano", nullable=False)
        batch_op.alter_column("mes", nullable=False)
        if "uq_cargo_data" in uqs:
            batch_op.drop_constraint("uq_cargo_data", type_="unique")
        if "uq_cargo_mes_ano" not in uqs:
            batch_op.create_unique_constraint("uq_cargo_mes_ano", ["cargo_id", "mes", "ano"])
        batch_op.drop_column("data")
