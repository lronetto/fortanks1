"""Efetivo PLR importado por período."""

from datetime import datetime

from models.database import db
from models.plr.constants import TABELA_PLR_EFETIVOS


class EfetivoPLR(db.Model):
    """
    Efetivo (quadro de funcionários) importado por período (data de referência = 1º dia do mês) para uso em PLR.
    Campos: data (referência mês/ano), cpf, nome, funcao, salario, data_nascimento, data_demissao, secao, data_admissao, chapa.
    """

    __tablename__ = TABELA_PLR_EFETIVOS

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    cpf = db.Column(db.String(20), nullable=True)
    nome = db.Column(db.String(200), nullable=True)
    funcao = db.Column(db.String(150), nullable=True)
    salario = db.Column(db.Numeric(12, 2), nullable=True)
    data_nascimento = db.Column(db.Date, nullable=True)
    data_demissao = db.Column(db.Date, nullable=True)
    secao = db.Column(db.String(150), nullable=True)
    data_admissao = db.Column(db.Date, nullable=True)
    chapa = db.Column(db.String(50), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<EfetivoPLR {self.data} {self.nome or self.cpf}>"

    def to_dict(self):
        return {
            "id": self.id,
            "data": self.data.isoformat() if self.data else None,
            "cpf": self.cpf,
            "nome": self.nome,
            "funcao": self.funcao,
            "salario": float(self.salario) if self.salario is not None else None,
            "data_nascimento": self.data_nascimento.isoformat() if self.data_nascimento else None,
            "data_demissao": self.data_demissao.isoformat() if self.data_demissao else None,
            "secao": self.secao,
            "data_admissao": self.data_admissao.isoformat() if self.data_admissao else None,
            "chapa": self.chapa,
        }
