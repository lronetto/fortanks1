"""Avaliação PLR do colaborador."""

from datetime import datetime

from sqlalchemy import JSON, Text

from models.database import db
from models.plr.constants import TABELA_PLR_AVALIACOES, TABELA_PLR_MODELOS


class PLRColaborador(db.Model):
    """
    Avaliação PLR do colaborador: obra (centro de custo), equipe alocada (lista texto),
    colaborador, avaliação (JSON com um ou mais tipos) e data.
    """

    __tablename__ = TABELA_PLR_AVALIACOES

    id = db.Column(db.Integer, primary_key=True)
    PlrModelo_id = db.Column(
        db.Integer,
        db.ForeignKey(f"{TABELA_PLR_MODELOS}.id", ondelete="RESTRICT"),
        nullable=True,
    )
    centro_custo_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_custo.id", ondelete="SET NULL"),
        nullable=True,
    )
    colaborador_id = db.Column(
        db.Integer,
        db.ForeignKey("colaboradores.id", ondelete="CASCADE"),
        nullable=False,
    )
    equipe_alocada = db.Column(JSON, nullable=True)
    avaliacao = db.Column(JSON, nullable=False)
    data = db.Column(db.Date, nullable=False)
    observacoes = db.Column(Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    centro_custo = db.relationship("CentroCusto", backref=db.backref("plr_avaliacoes", lazy="dynamic"))
    colaborador = db.relationship("Colaborador", backref=db.backref("plr_avaliacoes", lazy="dynamic"))

    def __repr__(self):
        return f"<PLRColaborador colaborador_id={self.colaborador_id} data={self.data}>"

    def to_dict(self):
        return {
            "id": self.id,
            "PlrModelo_id": self.PlrModelo_id,
            "centro_custo_id": self.centro_custo_id,
            "centro_custo_nome": self.centro_custo.nome if self.centro_custo else None,
            "colaborador_id": self.colaborador_id,
            "colaborador_nome": self.colaborador.nome if self.colaborador else None,
            "equipe_alocada": self.equipe_alocada,
            "avaliacao": self.avaliacao,
            "data": self.data.isoformat() if self.data else None,
            "observacoes": self.observacoes,
        }

    def nota_media_avaliacao(self):
        """
        Retorna a média das avaliações. Se os itens tiverem 'peso', usa média ponderada;
        caso contrário, usa média aritmética.
        """
        if not self.avaliacao:
            return None
        if isinstance(self.avaliacao, list):
            soma_ponderada = 0.0
            soma_pesos = 0.0
            valores_simples = []
            for item in self.avaliacao:
                if isinstance(item, dict) and "valor" in item:
                    try:
                        v = float(item["valor"])
                    except (TypeError, ValueError):
                        continue
                    peso = item.get("peso")
                    if peso is not None:
                        try:
                            p = float(peso)
                            soma_ponderada += v * p
                            soma_pesos += p
                        except (TypeError, ValueError):
                            valores_simples.append(v)
                    else:
                        valores_simples.append(v)
                elif isinstance(item, (int, float)):
                    valores_simples.append(float(item))
            if soma_pesos > 0:
                return soma_ponderada / soma_pesos
            return sum(valores_simples) / len(valores_simples) if valores_simples else None
        if isinstance(self.avaliacao, dict) and "valor" in self.avaliacao:
            try:
                return float(self.avaliacao["valor"])
            except (TypeError, ValueError):
                pass
        return None
