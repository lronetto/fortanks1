"""Modelo de PLR e tabela associativa com departamentos."""

from datetime import datetime

from sqlalchemy import JSON

from models.database import db
from models.plr.constants import TABELA_PLR_MODELOS, TABELA_PLR_MODELOS_DEPARTAMENTOS


modelos_plr_departamentos = db.Table(
    TABELA_PLR_MODELOS_DEPARTAMENTOS,
    db.Column(
        "PlrModelo_id",
        db.Integer,
        db.ForeignKey(f"{TABELA_PLR_MODELOS}.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "departamento_id",
        db.Integer,
        db.ForeignKey("departamentos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ModeloPLR(db.Model):
    """
    Modelo de PLR: nome, departamentos vinculados, forma de cálculo e pesos dos colaboradores,
    e forma de cálculo final.
    """

    __tablename__ = TABELA_PLR_MODELOS

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    forma_calculo_colaborador = db.Column(db.String(100), nullable=True)
    pesos_colaboradores = db.Column(JSON, nullable=True)
    forma_calculo_final = db.Column(db.String(100), nullable=True)
    config_calculo_final = db.Column(JSON, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    departamentos = db.relationship(
        "Departamento",
        secondary=modelos_plr_departamentos,
        backref=db.backref("PlrModelos", lazy="dynamic"),
        lazy="joined",
    )
    avaliacoes = db.relationship("PLRColaborador", backref="modelo_plr", lazy="dynamic")

    def __repr__(self):
        return f"<ModeloPLR {self.nome}>"

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao,
            "ativo": self.ativo,
            "forma_calculo_colaborador": self.forma_calculo_colaborador,
            "pesos_colaboradores": self.pesos_colaboradores,
            "forma_calculo_final": self.forma_calculo_final,
            "config_calculo_final": self.config_calculo_final,
            "departamento_ids": [d.id for d in self.departamentos],
        }
