from datetime import datetime
from models.database import db
from sqlalchemy.orm import relationship

class Orcamento(db.Model):
    __tablename__ = 'orcamentos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Pendente')
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'))
    contrato = db.relationship('Contrato', backref='orcamentos')
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))

    usuario = db.relationship('Usuario', backref='orcamentos')


    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'))
    material = db.relationship('Material', backref='orcamentos')

class ItemOrcamento(db.Model):
    __tablename__ = 'itens_orcamento'
    id = db.Column(db.Integer, primary_key=True)
    orcamento_id = db.Column(db.Integer, db.ForeignKey('orcamentos.id'))
    orcamento = db.relationship('Orcamento', backref='itens_orcamento')
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'))
    material = db.relationship('Material', backref='itens_orcamento')
    quantidade = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)