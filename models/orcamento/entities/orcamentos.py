"""Entidade principal de orçamentos."""

from datetime import datetime

from models.database import db
from models.orcamento.constants import STATUS_ORCAMENTO_PADRAO, TABELA_ORCAMENTOS


class Orcamento(db.Model):
    """Modelo de orçamento."""

    __tablename__ = TABELA_ORCAMENTOS

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    data = db.Column(db.Date, nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default=STATUS_ORCAMENTO_PADRAO)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    dados_adicionais = db.Column(db.Text, nullable=True)
    vinculado_a_orcamento_id = db.Column(
        db.Integer,
        db.ForeignKey("Orcamentos.id", ondelete="SET NULL"),
        nullable=True,
    )

    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    contrato = db.relationship("Contrato", backref="orcamentos")
    usuario = db.relationship("Usuario", backref="orcamentos")

    orcamento_vinculo = db.relationship(
        "Orcamento",
        remote_side="Orcamento.id",
        foreign_keys=[vinculado_a_orcamento_id],
    )

    itens = db.relationship(
        "ItemOrcamento",
        back_populates="orcamento",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def to_dict(self, incluir_itens=False):
        data = {
            "id": self.id,
            "nome": self.nome,
            "data": self.data,
            "descricao": self.descricao,
            "status": self.status,
            "contrato_id": self.contrato_id,
            "vinculado_a_orcamento_id": self.vinculado_a_orcamento_id,
            "usuario_id": self.usuario_id,
            "criado_em": self.criado_em,
            "atualizado_em": self.atualizado_em,
        }

        if incluir_itens:
            data["itens"] = [item.to_dict() for item in self.itens.all()]

        return data

    def __repr__(self):
        return f"<Orcamento {self.id} - {self.nome}>"
