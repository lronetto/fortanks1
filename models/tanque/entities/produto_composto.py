"""Vínculo tanque × produto composto por tipo de peça."""

from datetime import datetime

from models.database import db


class TanquesProdutoComposto(db.Model):
    """
    Modelo para vincular tanques a produtos compostos
    Permite associar um produto composto específico a cada tanque
    """
    __tablename__ = 'TanquesProdutoComposto'

    id = db.Column(db.Integer, primary_key=True)
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id', ondelete='CASCADE'), nullable=False)
    tipo_peca = db.Column(db.String(50), nullable=False)
    produto_composto_id = db.Column(db.Integer, db.ForeignKey('ProdutoComposto.id', ondelete='CASCADE'), nullable=False)

    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamentos
    tanque = db.relationship('Tanques', backref='produtos_compostos_vinculados')
    produto_composto = db.relationship('ProdutoComposto', backref='tanques_vinculados')

    # Um tanque pode ter o mesmo produto composto para vários tipos de peça; duplicata = mesmo tanque+produto+tipo
    __table_args__ = (
        db.UniqueConstraint(
            'tanque_id', 'produto_composto_id', 'tipo_peca',
            name='uq_tanque_produto_composto_tipo',
        ),
    )

    def save(self):
        """Salva a vinculação no banco de dados"""
        db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        """Remove a vinculação do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self

    def __repr__(self):
        return f'<TanqueProdutoComposto Tanque: {self.tanque_id}, Produto: {self.produto_composto_id}>'
