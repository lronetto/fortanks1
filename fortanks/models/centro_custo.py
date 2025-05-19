from datetime import datetime
from models.database import db

class CentroCusto(db.Model):
    """
    Modelo de Centro de Custo
    """
    __tablename__ = 'centros_custo'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    contratos = db.relationship('Contrato', back_populates='centro_custo', lazy=True)
    #solicitacoes = db.relationship('Solicitacao', backref='centro_custo', lazy=True)
    
    def __repr__(self):
        return f'<CentroCusto {self.codigo} - {self.nome}>' 