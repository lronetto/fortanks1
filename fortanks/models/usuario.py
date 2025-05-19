from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from models.database import db


class Usuario(db.Model, UserMixin):
    """
    Modelo de usuário do sistema.
    Implementa UserMixin para integração com Flask-Login.
    """
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'),nullable=True)
    departamento = db.Column(db.String(50), nullable=False)
    cargo = db.Column(db.Enum('colaborador', 'gerente', 'diretor',
                      'admin', 'Operacional', 'TST'), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_login = db.Column(db.DateTime)

    colaborador = db.relationship('Colaborador', back_populates='usuario',foreign_keys=[colaborador_id])

    def set_senha(self, senha):
        """Define a senha do usuário com hash"""
        self.senha = generate_password_hash(senha)

    def verificar_senha(self, senha):
        """Verifica se a senha informada é correta"""
        return check_password_hash(self.senha, senha)

    def atualizar_ultimo_login(self):
        """Atualiza a data/hora do último login"""
        self.ultimo_login = datetime.utcnow()
        db.session.commit()

    @property
    def is_admin(self):
        """Verifica se o usuário é administrador"""
        return self.cargo == 'admin'
    
    @property
    def is_tst(self):
        """Verifica se o usuário é administrador"""
        return self.cargo == 'TST'
    
    @property
    def is_operacional(self):
        """Verifica se o usuário é administrador"""
        return self.cargo in ['admin', 'Operacional']

    @property
    def is_gerente_ou_superior(self):
        """Verifica se o usuário é gerente ou superior"""
        return self.cargo in ['gerente', 'diretor', 'admin',]
    
    @property
    def is_tecnico_superior(self):
        """Verifica se o usuário é gerente ou superior"""
        return self.cargo in ['gerente', 'diretor', 'admin','']

    def __repr__(self):
        return f'<Usuario {self.email}>'
