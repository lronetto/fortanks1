from datetime import datetime
from models.database import db

class Cargo(db.Model):
    """
    Modelo para representar cargos dos colaboradores
    """
    __tablename__ = 'cargos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Ativo')  # Ativo, Inativo
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    colaboradores = db.relationship('Colaborador', backref='cargo', lazy=True)
    
    def save(self):
        if not self.id:
            db.session.add(self)
        db.session.commit()
        
    def delete(self):
        db.session.delete(self)
        db.session.commit()
        
    def __repr__(self):
        return f'<Cargo {self.nome}>' 