from datetime import datetime
from models.database import db
from sqlalchemy.orm import relationship

class GrupoMaterial(db.Model):
    """
    Modelo para representar grupos de materiais para inventário
    """
    __tablename__ = 'grupos_materiais'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text, nullable=True)
    codigo = db.Column(db.String(20), nullable=True, unique=True)
    ativo = db.Column(db.Boolean, default=True)
    cor = db.Column(db.String(7), nullable=True)  # Código hexadecimal da cor
    icone = db.Column(db.String(50), nullable=True)  # Classe do ícone (ex: fas fa-boxes)
    
    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    
    # Relacionamentos
    criado_por = relationship('Usuario', foreign_keys=[criado_por_id])
    materiais = relationship('Material', secondary='materiais_grupos', back_populates='grupos')
    
    def __repr__(self):
        return f'<GrupoMaterial {self.codigo or self.id} - {self.nome}>'
    
    def to_dict(self):
        """
        Converte o grupo para dicionário
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'codigo': self.codigo,
            'ativo': self.ativo,
            'cor': self.cor,
            'icone': self.icone,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None,
            'criado_por': self.criado_por.nome if self.criado_por else None,
            'total_materiais': len(self.materiais) if self.materiais else 0
        }
    
    def save(self):
        """
        Salva o grupo no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o grupo do banco de dados
        """
        # Remove as associações com materiais primeiro
        db.session.execute(
            db.text("DELETE FROM materiais_grupos WHERE grupo_id = :grupo_id"),
            {"grupo_id": self.id}
        )
        db.session.delete(self)
        db.session.commit()
    
    @classmethod
    def get_ativos(cls):
        """
        Retorna todos os grupos ativos
        """
        return cls.query.filter_by(ativo=True).order_by(cls.nome).all()
    
    @classmethod
    def get_por_codigo(cls, codigo):
        """
        Busca grupo por código
        """
        return cls.query.filter_by(codigo=codigo, ativo=True).first()
    
    def adicionar_material(self, material):
        """
        Adiciona um material ao grupo
        Verifica se já existe antes de adicionar para evitar duplicatas
        """
        # Verificar diretamente no banco de dados para evitar problemas de cache
        sql_check = "SELECT COUNT(*) FROM materiais_grupos WHERE material_id = :material_id AND grupo_id = :grupo_id"
        result = db.session.execute(
            db.text(sql_check),
            {"material_id": material.id, "grupo_id": self.id}
        ).fetchone()
        
        if result and result[0] > 0:
            # Material já está no grupo, não fazer nada
            return False
        
        # Adicionar o material
        self.materiais.append(material)
        db.session.commit()
        return True
    
    def remover_material(self, material):
        """
        Remove um material do grupo
        """
        if material in self.materiais:
            self.materiais.remove(material)
            db.session.commit()
    
    def get_materiais_ativos(self):
        """
        Retorna apenas os materiais ativos do grupo
        """
        return [material for material in self.materiais if material.ativo]
    
    @property
    def total_materiais(self):
        """
        Retorna o total de materiais no grupo
        """
        return len(self.materiais) if self.materiais else 0
    
    @property
    def total_materiais_ativos(self):
        """
        Retorna o total de materiais ativos no grupo
        """
        return len(self.get_materiais_ativos())


# Tabela de associação entre materiais e grupos
materiais_grupos = db.Table('materiais_grupos',
    db.Column('material_id', db.Integer, db.ForeignKey('materiais.id'), primary_key=True),
    db.Column('grupo_id', db.Integer, db.ForeignKey('grupos_materiais.id'), primary_key=True),
    db.Column('data_associacao', db.DateTime, default=datetime.now)
)
