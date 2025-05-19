from datetime import datetime
from models.database import db

class PlanoConta(db.Model):
    """
    Modelo para representar Planos de Conta
    """
    __tablename__ = 'planos_conta'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.Integer, unique=True, nullable=False)
    descricao = db.Column(db.String(100), nullable=False)
    indice = db.Column(db.String(50), default='')
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    
    def save(self):
        """
        Salva o plano de conta no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o plano de conta do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def to_dict(self):
        """
        Converte o objeto plano de conta para um dicionário
        """
        return {
            'id': self.id,
            'codigo': self.codigo,
            'descricao': self.descricao,
            'indice': self.indice,
            'ativo': self.ativo,
            'criado_em': self.criado_em
        }
    
    def __repr__(self):
        """
        Representação em string do plano de conta
        """
        return f'<PlanoConta {self.codigo} - {self.descricao}>' 