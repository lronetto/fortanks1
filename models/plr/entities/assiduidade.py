"""Assiduidade PLR por colaborador e mês."""

from datetime import datetime

from models.database import db
from models.plr.constants import TABELA_PLR_ASSIDUIDADE


class PlrAssiduidade(db.Model):
    """
    Faltas por colaborador por mês para cálculo de assiduidade na PLR.
    Regra: 1 falta = -10%, 2 = -20%, 3 = -30%, 4 ou mais = perde 100% do mês.
    """

    __tablename__ = TABELA_PLR_ASSIDUIDADE

    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(
        db.Integer,
        db.ForeignKey("colaboradores.id", ondelete="CASCADE"),
        nullable=False,
    )
    mes = db.Column(db.Integer, nullable=False)
    ano = db.Column(db.Integer, nullable=False)
    faltas = db.Column(db.Integer, nullable=False, default=0)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("colaborador_id", "mes", "ano", name="uq_plr_assiduidade_colab_mes_ano"),)

    colaborador = db.relationship("Colaborador", backref=db.backref("plr_assiduidade", lazy="dynamic"))

    def __repr__(self):
        return f"<PlrAssiduidade colaborador_id={self.colaborador_id} {self.mes}/{self.ano} faltas={self.faltas}>"

    def to_dict(self):
        return {
            "id": self.id,
            "colaborador_id": self.colaborador_id,
            "colaborador_nome": self.colaborador.nome if self.colaborador else None,
            "colaborador_cpf": self.colaborador.cpf if self.colaborador else None,
            "mes": self.mes,
            "ano": self.ano,
            "faltas": self.faltas,
        }
