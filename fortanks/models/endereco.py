from datetime import datetime
from models.database import db

class Endereco(db.Model):
    """Modelo para representar endereços associados a clientes."""
    __tablename__ = 'enderecos'

    id = db.Column(db.Integer, primary_key=True)
    logradouro = db.Column(db.String(150), nullable=False)
    numero = db.Column(db.String(20))
    complemento = db.Column(db.String(100))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(2), nullable=False)
    cep = db.Column(db.String(10))
    tipo = db.Column(db.String(20), default='COMERCIAL')  # COMERCIAL, COBRANCA, ENTREGA, OUTRO
    principal = db.Column(db.Boolean, default=False)
    
    # Relação com o cliente
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id', ondelete='CASCADE'), nullable=False)
    
    # Dados de controle
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __init__(self, logradouro, cidade, estado, cliente_id, numero=None, complemento=None, 
                 bairro=None, cep=None, tipo='COMERCIAL', principal=False):
        self.logradouro = logradouro
        self.numero = numero
        self.complemento = complemento
        self.bairro = bairro
        self.cidade = cidade
        self.estado = estado
        self.cep = cep
        self.tipo = tipo
        self.principal = principal
        self.cliente_id = cliente_id

    def to_dict(self):
        """Converte o objeto para um dicionário."""
        return {
            'id': self.id,
            'logradouro': self.logradouro,
            'numero': self.numero,
            'complemento': self.complemento,
            'bairro': self.bairro,
            'cidade': self.cidade,
            'estado': self.estado,
            'cep': self.cep,
            'tipo': self.tipo,
            'principal': self.principal,
            'cliente_id': self.cliente_id,
            'criado_em': self.criado_em,
            'atualizado_em': self.atualizado_em
        }
    
    def endereco_completo(self):
        """Retorna o endereço formatado como texto completo."""
        partes = [self.logradouro]
        
        if self.numero:
            partes.append(f', {self.numero}')
        
        if self.complemento:
            partes.append(f' - {self.complemento}')
            
        if self.bairro:
            partes.append(f', {self.bairro}')
            
        return ''.join(partes)
    
    def cidade_estado(self):
        """Retorna cidade/estado formatados."""
        return f'{self.cidade}/{self.estado}'
    
    def __repr__(self):
        return f'<Endereco {self.id}: {self.logradouro}, {self.cidade}/{self.estado}>' 