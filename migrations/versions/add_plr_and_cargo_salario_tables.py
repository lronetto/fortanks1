"""add plr and cargo_salario tables

Revision ID: plr_cargo_salario_001
Revises: a16ac875e330
Create Date: 2025-03-04

Alinhado aos modelos em ``models/plr`` (tabelas ``PlrModelos``, ``PlrModelosDepartamentos``, ``PlrAvaliacoes``)
e a ``models/cargo_salario.CargoSalario`` (``cargos_salarios`` com mes/ano antes da migration ``cargos_salarios_data_001``).
"""
from alembic import op
import sqlalchemy as sa

revision = "plr_cargo_salario_001"
down_revision = "a16ac875e330"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- PLR: PlrModelos (legado possível: só ``modelos_plr`` sem renomear) ---
    if not inspector.has_table("PlrModelos") and not inspector.has_table("modelos_plr"):
        op.create_table(
            "PlrModelos",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("nome", sa.String(150), nullable=False),
            sa.Column("descricao", sa.Text(), nullable=True),
            sa.Column("ativo", sa.Boolean(), nullable=True),
            sa.Column("forma_calculo_colaborador", sa.String(100), nullable=True),
            sa.Column("pesos_colaboradores", sa.JSON(), nullable=True),
            sa.Column("forma_calculo_final", sa.String(100), nullable=True),
            sa.Column("config_calculo_final", sa.JSON(), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=True),
            sa.Column("atualizado_em", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    # Filhos com FK para ``PlrModelos.id`` só se essa tabela existir (não apenas ``modelos_plr``).
    legacy_somente_modelos_plr = inspector.has_table("modelos_plr") and not inspector.has_table(
        "PlrModelos"
    )

    # --- N:N modelo x departamento ---
    if not legacy_somente_modelos_plr and not inspector.has_table(
        "PlrModelosDepartamentos"
    ) and not inspector.has_table("modelos_plr_departamentos"):
        op.create_table(
            "PlrModelosDepartamentos",
            sa.Column("PlrModelo_id", sa.Integer(), nullable=False),
            sa.Column("departamento_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["PlrModelo_id"],
                ["PlrModelos.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["departamento_id"],
                ["departamentos.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("PlrModelo_id", "departamento_id"),
        )

    # --- Avaliações PLR ---
    if not legacy_somente_modelos_plr and not inspector.has_table("PlrAvaliacoes") and not inspector.has_table(
        "plr_colaboradores"
    ):
        op.create_table(
            "PlrAvaliacoes",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("PlrModelo_id", sa.Integer(), nullable=True),
            sa.Column("centro_custo_id", sa.Integer(), nullable=True),
            sa.Column("colaborador_id", sa.Integer(), nullable=False),
            sa.Column("equipe_alocada", sa.JSON(), nullable=True),
            sa.Column("avaliacao", sa.JSON(), nullable=False),
            sa.Column("data", sa.Date(), nullable=False),
            sa.Column("observacoes", sa.Text(), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=True),
            sa.Column("atualizado_em", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["PlrModelo_id"],
                ["PlrModelos.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["centro_custo_id"],
                ["centros_custo.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["colaborador_id"],
                ["colaboradores.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    # --- Cargo salário (schema inicial mes/ano; ``cargos_salarios_data_001`` evolui para ``data``) ---
    if not inspector.has_table("cargos_salarios"):
        op.create_table(
            "cargos_salarios",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("cargo_id", sa.Integer(), nullable=False),
            sa.Column("mes", sa.Integer(), nullable=False),
            sa.Column("ano", sa.Integer(), nullable=False),
            sa.Column("salario", sa.Numeric(12, 2), nullable=False),
            sa.Column("criado_em", sa.DateTime(), nullable=True),
            sa.Column("atualizado_em", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["cargo_id"], ["cargos.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cargo_id", "mes", "ano", name="uq_cargo_mes_ano"),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("cargos_salarios"):
        op.drop_table("cargos_salarios")

    for nome in ("PlrAvaliacoes", "plr_colaboradores"):
        if inspector.has_table(nome):
            op.drop_table(nome)

    for nome in ("PlrModelosDepartamentos", "modelos_plr_departamentos"):
        if inspector.has_table(nome):
            op.drop_table(nome)

    for nome in ("PlrModelos", "modelos_plr"):
        if inspector.has_table(nome):
            op.drop_table(nome)
