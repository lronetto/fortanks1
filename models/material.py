from datetime import datetime
from models.database import db
from sqlalchemy.orm import relationship

class Material(db.Model):
    """
    Modelo para representar materiais
    """
    __tablename__ = 'materiais'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    codigo_erp = db.Column(db.String(50), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    plano_conta = db.Column(db.String(30), nullable=True)
    plano_conta_id = db.Column(db.Integer, db.ForeignKey('planos_conta.id'), nullable=True)
    plano_conta_obj = relationship('PlanoConta', back_populates='materiais',foreign_keys=[plano_conta_id])
    ncm = db.Column(db.String(15), nullable=True)
    mascara = db.Column(db.String(20), nullable=True)
    
    # Referência à tabela de unidades
    unidade_id = db.Column(db.Integer, db.ForeignKey('unidades.id'), nullable=True)
    
    categoria = db.Column(db.String(50), nullable=True)  # Adicionando campo categoria
    criado_em = db.Column(db.DateTime, default=datetime.now)

    #unidade = db.relationship('Unidade', back_populates='materiais', foreign_keys=[unidade_id])
    # Relacionamento com ItemSolicitacao - use backref para simplificar
    solicitacoes_itens = db.relationship('ItemSolicitacao', back_populates='material')
    # Renomeado para evitar conflito com o campo string 'unidade' e para maior clareza
    unidade_obj = db.relationship('Unidade', back_populates='materiais', foreign_keys=[unidade_id])
    
    # Relacionamento com grupos de materiais
    grupos = db.relationship('GrupoMaterial', secondary='materiais_grupos', back_populates='materiais')
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'unidade': self.unidade_obj.nome if self.unidade_obj else None,
            'unidade_id': self.unidade_id
        }
    
    def save(self):
        """
        Salva o material no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o material do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    @property
    def data_criacao(self):
        """
        Retorna a data de criação do material (para compatibilidade com código existente)
        """
        return self.criado_em
    
    def __repr__(self):
        """
        Representação em string do material
        """
        codigo_display = self.codigo or "Sem código"
        return f'<Material {codigo_display} - {self.nome}>'
    
    def get_unidade_nome(self):
        """
        Retorna o nome da unidade do material
        """
        # Se tiver unidade_obj, usa o nome dela
        if hasattr(self, 'unidade_obj') and self.unidade_obj:
            return self.unidade_obj.nome
        # Senão, usa o campo string unidade
        return self.unidade
    
    def tem_conversoes(self):
        """
        Verifica se o material possui conversões de unidades
        """
        # Se não tiver unidade definida, não tem conversões
        if not self.unidade_id and not self.unidade:
            return False
            
        # Verifica se tem conversões específicas para este material
        return len(getattr(self, 'conversoes_unidade', [])) > 0
