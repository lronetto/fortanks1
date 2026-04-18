"""Grupos de tanques e tabela de associação."""

from datetime import datetime

from models.database import db


# Tabela de associação entre tanques e grupos
tanques_grupos = db.Table(
    'TanquesGruposItens',
    db.Column('id', db.Integer, primary_key=True, autoincrement=True),
    db.Column('tanque_id', db.Integer, db.ForeignKey('Tanques.id'), primary_key=False),
    db.Column('grupo_id', db.Integer, db.ForeignKey('TanquesGrupos.id'), primary_key=False),
    db.Column('data_associacao', db.DateTime, default=datetime.now),
    db.PrimaryKeyConstraint('id'),
)


class TanquesGrupos(db.Model):
    """
    Modelo para representar grupos de tanques
    """
    __tablename__ = 'TanquesGrupos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text, nullable=True)
    cor = db.Column(db.String(7), nullable=True)  # Código hexadecimal da cor
    icone = db.Column(db.String(50), nullable=True)  # Classe do ícone (ex: fas fa-water)

    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamentos
    tanques = db.relationship('Tanques', secondary='TanquesGruposItens', back_populates='grupos')

    def __repr__(self):
        return f'<TanquesGrupos {self.id} - {self.nome}>'

    def to_dict(self):
        """
        Converte o grupo para dicionário
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'cor': self.cor,
            'icone': self.icone,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None,
            'total_tanques': len(self.tanques) if self.tanques else 0
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
        # Remove as associações com tanques primeiro
        db.session.execute(
            db.text("DELETE FROM tanques_grupos WHERE grupo_id = :grupo_id"),
            {"grupo_id": self.id}
        )
        db.session.delete(self)
        db.session.commit()

    @classmethod
    def get_all(cls):
        """
        Retorna todos os grupos
        """
        return cls.query.order_by(cls.nome).all()

    def adicionar_tanque(self, tanque):
        """
        Adiciona um tanque ao grupo
        """
        if tanque not in self.tanques:
            self.tanques.append(tanque)
            db.session.flush()  # Usar flush ao invés de commit para permitir rollback se necessário

    def remover_tanque(self, tanque):
        """
        Remove um tanque do grupo
        """
        if tanque in self.tanques:
            self.tanques.remove(tanque)
            db.session.commit()

    @property
    def total_tanques(self):
        """
        Retorna o total de tanques no grupo
        """
        return len(self.tanques) if self.tanques else 0
