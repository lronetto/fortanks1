from datetime import datetime
from models import db

class Peca(db.Model):
    __tablename__ = 'pecas'
    
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50), nullable=False)
    altura = db.Column(db.DECIMAL(10, 2), nullable=True)
    nome = db.Column(db.String(100), nullable=False)
    numero_sequencial = db.Column(db.Integer, nullable=False)
    numero_tanque = db.Column(db.Integer, nullable=True)
    volume = db.Column(db.DECIMAL(10, 2), nullable=True)
    data_prevista = db.Column(db.DateTime, nullable=True)
    data_concretagem = db.Column(db.DateTime, nullable=True)
    data_entrega = db.Column(db.DateTime, nullable=True)
    qualidade = db.Column(db.String(1000), nullable=True)
    
    # Relacionamento com tanque
    tanque_id = db.Column(db.Integer, db.ForeignKey('tanques.id', ondelete='CASCADE'), nullable=False)
    tanque = db.relationship('Tanque', backref=db.backref('pecas', lazy=True, cascade='all, delete-orphan'))
    
    # Relação com concretagens através da classe de associação    
    # Campos de auditoria
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def save(self):
        # Se for uma nova peça, atribui o próximo número sequencial
        if not self.id and not self.numero_sequencial:
            # Encontra o maior número sequencial para o tanque atual
            maior_sequencial = db.session.query(db.func.max(Peca.numero_sequencial))\
                .filter(Peca.tanque_id == self.tanque_id).scalar() or 0
            # Incrementa para obter o próximo número
            self.numero_sequencial = maior_sequencial + 1
            
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        db.session.delete(self)
        db.session.commit()
        return self
    
    def __repr__(self):
        return f'<Peca {self.nome} ({self.tipo}) - #{self.numero_sequencial}>' 
    
    def is_PF(self):
        return self.tipo == 'PF'
    