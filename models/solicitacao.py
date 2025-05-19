from datetime import datetime
from models.database import db
from models.usuario import Usuario
from models.material import Material
from models.plano_conta import PlanoConta

class Solicitacao(db.Model):
    """
    Modelo para representar solicitações de materiais
    """
    __tablename__ = 'solicitacoes'
    
    id = db.Column(db.Integer, primary_key=True)
   
    data_solicitacao = db.Column(db.DateTime, default=datetime.now)
    data_necessidade = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Pendente')  # Pendente, Aprovada, Rejeitada, Cancelada
    observacoes = db.Column(db.Text, nullable=True)
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=False)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    aprovador_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    data_aprovacao = db.Column(db.DateTime, nullable=True)
    
    # Relacionamentos
    solicitante = db.relationship('Usuario', foreign_keys=[solicitante_id], backref='solicitacoes')
    aprovador = db.relationship('Usuario', foreign_keys=[aprovador_id])
    centro_custo = db.relationship('CentroCusto', backref='solicitacoes')
    itens = db.relationship('ItemSolicitacao', backref='solicitacao', cascade='all, delete-orphan')
    
    def save(self):
        """Salva a solicitação no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """Remove a solicitação do banco de dados"""
        db.session.delete(self)
        db.session.commit()
    
    def aprovar(self, aprovador_id):
        """Aprova a solicitação"""
        self.status = 'Aprovada'
        self.aprovador_id = aprovador_id
        self.data_aprovacao = datetime.now()
        self.save()
    
    def rejeitar(self, aprovador_id):
        """Rejeita a solicitação"""
        self.status = 'Rejeitada'
        self.aprovador_id = aprovador_id
        self.data_aprovacao = datetime.now()
        self.save()
    
    def cancelar(self):
        """Cancela a solicitação"""
        self.status = 'Cancelada'
        self.save()
    
    def __repr__(self):
        return f'<Solicitacao {self.numero}>'

class ItemSolicitacao(db.Model):
    """
    Modelo para representar itens de uma solicitação de materiais
    """
    __tablename__ = 'itens_solicitacao'
    
    id = db.Column(db.Integer, primary_key=True)
    solicitacao_id = db.Column(db.Integer, db.ForeignKey('solicitacoes.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)
    unidade = db.Column(db.String(20), nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    
    # Relacionamento com material
    material = db.relationship('Material', back_populates='itens_solicitacao')
    
    def save(self):
        """Salva o item no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """Remove o item do banco de dados"""
        db.session.delete(self)
        db.session.commit()
    
    def __repr__(self):
        return f'<ItemSolicitacao {self.id} - Material: {self.material_id}, Quantidade: {self.quantidade} {self.unidade}>' 