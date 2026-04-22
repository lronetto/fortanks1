"""Tabela de associação entre materiais e grupos."""

from datetime import datetime

from models.database import db

from ..constants import TABELA_GRUPOS_ITENS

materiais_grupos = db.Table(
    TABELA_GRUPOS_ITENS,
    db.Column("id", db.Integer, primary_key=True, autoincrement=True),
    db.Column("material_id", db.Integer, db.ForeignKey("Materiais.id"), primary_key=False),
    db.Column("grupo_id", db.Integer, db.ForeignKey("MateriaisGrupos.id"), primary_key=False),
    db.Column("data_associacao", db.DateTime, default=datetime.now),
    db.PrimaryKeyConstraint("id"),
)
