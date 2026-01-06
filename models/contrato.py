from datetime import datetime
from models.database import db
from models.cliente import Cliente

class Contrato(db.Model):
    """
    Modelo para representar contratos
    """
    __tablename__ = 'contratos'
    
    id = db.Column(db.Integer, primary_key=True)
    #numero = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    estado = db.Column(db.Text,nullable=True)
    cidade = db.Column(db.Text,nullable=True)
    # Campos com referência ao modelo Cliente
    cliente_direto_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    cliente_final_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    
    data_base = db.Column(db.DateTime,nullable=True)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False)
    valor_mat = db.Column(db.Numeric(15, 2), nullable=False)
    valor_ser = db.Column(db.Numeric(15, 2), nullable=False)
    prazo_pagamento_mat = db.Column(db.Integer, nullable=True)
    prazo_pagamento_ser = db.Column(db.Integer, nullable=True)
    
    # Chaves estrangeiras
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=True)
    centro_custo = db.relationship('CentroCusto', back_populates='contratos',foreign_keys=[centro_custo_id])
    responsavel_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    
    # Datas de controle
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    ativo = db.Column(db.Boolean, default=True)
    # Relacionamentos
    tanques = db.relationship('Tanques', back_populates='contrato')
    cliente_direto = db.relationship('Cliente', foreign_keys=[cliente_direto_id], backref='contratos_como_cliente_direto')
    cliente_final = db.relationship('Cliente', foreign_keys=[cliente_final_id], backref='contratos_como_cliente_final')
    #centro_custo = db.relationship('CentroCusto', foreign_keys=[centro_custo_id], backref='contratos')
    
    def to_dict(self):
        """
        Converte o contrato para um dicionário
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'estado': self.estado,
            'cidade': self.cidade,
            'cliente_direto_id': self.cliente_direto_id,
            'cliente_final_id': self.cliente_final_id,  
            'data_base': self.data_base,
            'valor_total': self.valor_total,
            'valor_mat': self.valor_mat,
            'valor_ser': self.valor_ser,
            'prazo_pagamento_mat': self.prazo_pagamento_mat,
            'prazo_pagamento_ser': self.prazo_pagamento_ser,
            'centro_custo_id': self.centro_custo_id,
            'responsavel_id': self.responsavel_id,
            'data_cadastro': self.data_cadastro,
            'ultima_atualizacao': self.ultima_atualizacao
        }
    
    def save(self):
        """
        Salva o contrato no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o contrato do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def __repr__(self):
        """
        Representação em string do contrato
        """
        return f'<Contrato {self.numero} - {self.nome}>' 