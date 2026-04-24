"""Entidade de itens de orçamento."""

from datetime import datetime

from models.database import db
from models.orcamento.constants import TABELA_ITENS_ORCAMENTO
from models.orcamento.utils import normalizar_texto_item


class ItemOrcamento(db.Model):
    """Itens de um orçamento, com descrição textual e material opcional."""

    __tablename__ = TABELA_ITENS_ORCAMENTO

    id = db.Column(db.Integer, primary_key=True)
    orcamento_id = db.Column(db.Integer, db.ForeignKey("Orcamentos.id"), nullable=False)

    descricao_item = db.Column(db.String(255), nullable=True)
    unidade = db.Column(db.String(30), nullable=True)
    grupo = db.Column(db.Text, nullable=True)
    dados_adicionais = db.Column(db.Text, nullable=True)

    material_id = db.Column(db.Integer, db.ForeignKey("Materiais.id"), nullable=True)
    quantidade = db.Column(db.Numeric(28, 14), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    orcamento = db.relationship("Orcamento", back_populates="itens")
    material = db.relationship("Materiais", backref="itens_orcamento")

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def to_dict(self, incluir_referencias=False):
        data = {
            "id": self.id,
            "orcamento_id": self.orcamento_id,
            "descricao_item": self.descricao_item,
            "unidade": self.unidade,
            "grupo": self.grupo,
            "dados_adicionais": self.dados_adicionais,
            "material_id": self.material_id,
            "material_nome": self.material.nome if self.material else None,
            "quantidade": self.quantidade,
            "valor": float(self.valor) if self.valor is not None else None,
            "criado_em": self.criado_em,
            "atualizado_em": self.atualizado_em,
        }

        if incluir_referencias:
            from models.orcamento.services import buscar_referencias_por_texto_item

            referencias = buscar_referencias_por_texto_item(normalizar_texto_item(self.descricao_item))
            data["referencias_materiais"] = [referencia.to_dict() for referencia in referencias]

        return data

    def __repr__(self):
        return f"<ItemOrcamento {self.id} - Orcamento {self.orcamento_id}>"
