from datetime import datetime
from .database import db

class Unidade(db.Model):
    """Modelo para armazenar unidades de medida."""
    __tablename__ = 'unidades'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(10), nullable=False, unique=True)
    descricao = db.Column(db.String(100), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    padrao = db.Column(db.Boolean, default=False)
    
    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    materiais = db.relationship('Material', back_populates='unidade_obj', lazy=True)
    conversoes_origem = db.relationship(
        'ConversaoUnidade', 
        foreign_keys='ConversaoUnidade.unidade_origem_id',
        backref='unidade_origem_rel', 
        lazy=True
    )
    conversoes_destino = db.relationship(
        'ConversaoUnidade', 
        foreign_keys='ConversaoUnidade.unidade_destino_id',
        backref='unidade_destino_rel', 
        lazy=True
    )
    #nf_itens = db.relationship('NotaFiscalItem', backref='unidade_rel', lazy=True)
    
    def __repr__(self):
        return f"<Unidade {self.nome}>"
    
    @classmethod
    def obter_padrao(cls):
        """Retorna a unidade padrão do sistema"""
        return cls.query.filter_by(padrao=True).first()
    
    @classmethod
    def obter_por_nome(cls, nome):
        """Retorna uma unidade pelo seu nome"""
        return cls.query.filter(cls.nome.ilike(nome)).first()
    
    @classmethod
    def criar_unidades_padrao(cls):
        """Cria as unidades padrão do sistema se não existirem"""
        unidades_padrao = [
            {'nome': 'UN', 'descricao': 'Unidade', 'padrao': True},
            {'nome': 'KG', 'descricao': 'Quilograma'},
            {'nome': 'G', 'descricao': 'Grama'},
            {'nome': 'L', 'descricao': 'Litro'},
            {'nome': 'ML', 'descricao': 'Mililitro'},
            {'nome': 'M', 'descricao': 'Metro'},
            {'nome': 'CM', 'descricao': 'Centímetro'},
            {'nome': 'M²', 'descricao': 'Metro quadrado'},
            {'nome': 'M³', 'descricao': 'Metro cúbico'},
            {'nome': 'PCT', 'descricao': 'Pacote'},
            {'nome': 'CX', 'descricao': 'Caixa'},
            {'nome': 'PAR', 'descricao': 'Par'},
            {'nome': 'TON', 'descricao': 'Tonelada'},
            {'nome': 'GALÃO', 'descricao': 'Galão'},
        ]
        
        for unidade_data in unidades_padrao:
            # Verifica se a unidade já existe
            unidade = cls.query.filter(cls.nome.ilike(unidade_data['nome'])).first()
            if not unidade:
                # Cria a unidade se não existir
                unidade = cls(**unidade_data)
                db.session.add(unidade)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao criar unidades padrão: {str(e)}") 

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao
        }