from datetime import datetime
from models.database import db

class Cliente(db.Model):
    """
    Modelo para representar Clientes (Pessoas Jurídicas)
    """
    __tablename__ = 'clientes'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cnpj = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    observacoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamento com Endereco
    enderecos = db.relationship('Endereco', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    
    def save(self):
        """
        Salva o cliente no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o cliente do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def to_dict(self):
        """
        Converte o objeto cliente para um dicionário
        """
        cliente_dict = {
            'id': self.id,
            'nome': self.nome,
            'cnpj': self.cnpj,
            'email': self.email,
            'telefone': self.telefone,
            'observacoes': self.observacoes,
            'ativo': self.ativo,
            'criado_em': self.criado_em,
            'atualizado_em': self.atualizado_em
        }
        
        # Adicionar o endereço principal, se houver
        endereco_principal = self.get_endereco_principal()
        if endereco_principal:
            cliente_dict['endereco'] = endereco_principal.to_dict()
        
        return cliente_dict
    
    def get_endereco_principal(self):
        """
        Retorna o endereço principal do cliente
        """
        return self.enderecos.filter_by(principal=True).first()
    
    def get_enderecos(self):
        """
        Retorna todos os endereços do cliente
        """
        return self.enderecos.all()
    
    def __repr__(self):
        """
        Representação em string do cliente
        """
        return f'<Cliente {self.id} - {self.nome}>' 