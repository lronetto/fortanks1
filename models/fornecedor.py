from datetime import datetime
from models.database import db


class Fornecedor(db.Model):
    """
    Modelo para representar Fornecedores
    """
    __tablename__ = 'fornecedores'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    cnpj = db.Column(db.String(20), unique=True, nullable=False)
    estado = db.Column(db.String(2), nullable=True)

    # Contatos e endereços armazenados em formato JSON (texto)
    contatos = db.Column(db.Text, nullable=True)
    enderecos = db.Column(db.Text, nullable=True)

    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamento com pedidos de compra
    pedidos_compra = db.relationship('PedidoCompra', back_populates='fornecedor', lazy='dynamic')

    def __init__(self, nome, cnpj, estado, contatos=None, enderecos=None):
        self.nome = nome
        self.cnpj = cnpj
        self.estado = estado
        self.contatos = contatos
        self.enderecos = enderecos
        fornecedor = Fornecedor.query.filter_by(cnpj=cnpj).first()
        if not fornecedor:
            self.save()
        else:
            self.id = fornecedor.id
            self.nome = fornecedor.nome
            self.cnpj = fornecedor.cnpj
            self.estado = fornecedor.estado
            self.contatos = fornecedor.contatos
            self.enderecos = fornecedor.enderecos
            self.ativo = fornecedor.ativo

    def save(self):
        """
        Salva o fornecedor no banco de dados
        """
        db.session.add(self)
        db.session.commit()

    def delete(self):
        """
        Remove o fornecedor do banco de dados
        """
        db.session.delete(self)
        db.session.commit()

    def to_dict(self):
        """
        Converte o objeto fornecedor para um dicionário
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'cnpj': self.cnpj,
            'estado': self.estado,
            'contatos': self.contatos,
            'enderecos': self.enderecos,
            'ativo': self.ativo,
            'criado_em': self.criado_em,
            'atualizado_em': self.atualizado_em,
        }

    def __repr__(self):
        return f'<Fornecedor {self.id} - {self.nome}>'

