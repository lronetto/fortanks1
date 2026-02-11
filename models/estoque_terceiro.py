from datetime import datetime
from models.database import db
from sqlalchemy.orm import relationship
from decimal import Decimal


class EstoqueTerceiro(db.Model):
    """
    Modelo para representar estoques de terceiros importados via planilha
    """
    __tablename__ = 'EstoqueTerceiro'
    
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    codigo_erp = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(50), nullable=True)
    unidade = db.Column(db.String(20), nullable=True)
    quantidade = db.Column(db.Numeric(15, 4), nullable=False, default=0)
    ValorUnitario = db.Column(db.Numeric(15, 4), nullable=True)
    ValorTotal = db.Column(db.Numeric(15, 4), nullable=True)
    
    # Controle de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    usuario = relationship('Usuario', foreign_keys=[usuario_id])
    
    def to_dict(self):
        """
        Converte o registro para dicionário
        """
        return {
            'id': self.id,
            'data': self.data.isoformat() if self.data else None,
            'codigo_erp': self.codigo_erp,
            'tipo': self.tipo,
            'unidade': self.unidade,
            'quantidade': float(self.quantidade) if self.quantidade else 0,
            'ValorUnitario': float(self.ValorUnitario) if self.ValorUnitario else 0,
            'ValorTotal': float(self.ValorTotal) if self.ValorTotal else 0,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
        }
    
    def save(self):
        """
        Salva o registro no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o registro do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def __repr__(self):
        """
        Representação em string do registro
        """
        return f'<EstoqueTerceiro {self.codigo_erp} - Qtd: {self.quantidade} - Data: {self.data}>'
