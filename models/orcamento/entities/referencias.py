"""Entidade de referência texto de item para material."""

from datetime import datetime

from models.database import db
from models.orcamento.constants import TABELA_ITENS_ORCAMENTO_REFERENCIAS_MATERIAIS


class ItemOrcamentoReferenciaMaterial(db.Model):
    """Mapeia o texto de item de orçamento para um material do sistema."""

    __tablename__ = TABELA_ITENS_ORCAMENTO_REFERENCIAS_MATERIAIS

    id = db.Column(db.Integer, primary_key=True)
    texto_item = db.Column(db.String(255), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("Materiais.id"), nullable=True)
    observacao = db.Column(db.String(255), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        db.UniqueConstraint("texto_item", "material_id", name="uq_item_orcamento_material_ref"),
    )

    material = db.relationship("Materiais", backref="itens_orcamento_referenciados")

    def to_dict(self):
        return {
            "id": self.id,
            "texto_item": self.texto_item,
            "material_id": self.material_id,
            "material_nome": self.material.nome if self.material else None,
            "observacao": self.observacao,
            "criado_em": self.criado_em,
            "atualizado_em": self.atualizado_em,
        }

    def __repr__(self):
        return f"<ItemOrcamentoReferenciaMaterial {self.id} - {self.texto_item}>"
