import logging
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import check_password_hash as _werkzeug_check

from models.database import db

logger = logging.getLogger(__name__)

_argon2_hasher = None


def _get_argon2_hasher():
    global _argon2_hasher
    if _argon2_hasher is None:
        from argon2 import PasswordHasher
        _argon2_hasher = PasswordHasher()
    return _argon2_hasher


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
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'), nullable=False)
    cargo_id = db.Column(db.Integer, db.ForeignKey('cargos.id'), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_login = db.Column(db.DateTime)

    colaborador = db.relationship('Colaborador', back_populates='usuario', foreign_keys=[colaborador_id])
    departamento_rel = db.relationship('Departamento', back_populates='usuarios', foreign_keys=[departamento_id], lazy=True)
    cargo_rel = db.relationship('Cargo', back_populates='usuarios', foreign_keys=[cargo_id], lazy=True)
    
    @property
    def departamento(self):
        """Retorna o nome do departamento para compatibilidade"""
        return self.departamento_rel.nome if self.departamento_rel else ''
    
    @property
    def cargo(self):
        """Retorna o nome do cargo para compatibilidade"""
        return self.cargo_rel.nome if self.cargo_rel else ''

    @staticmethod
    def hash_password(password: str) -> str:
        """Gera hash da senha com Argon2id. Use esta função para novas senhas."""
        return _get_argon2_hasher().hash(password)

    @staticmethod
    def is_argon2_hash(pwhash: str) -> bool:
        """Retorna True se o hash armazenado é Argon2 (argon2id/argon2i/argon2d)."""
        return bool(pwhash and pwhash.strip().startswith("$argon2"))

    @staticmethod
    def check_password(pwhash: str, password: str) -> bool:
        """
        Verifica se a senha confere com o hash armazenado.
        Aceita hashes Argon2id (novos) e scrypt/pbkdf2 do Werkzeug (legado).
        """
        if not pwhash or not password:
            return False
        pwhash = pwhash.strip()
        if pwhash.startswith("$argon2"):
            try:
                from argon2.exceptions import VerifyMismatchError, InvalidHashError
                _get_argon2_hasher().verify(pwhash, password)
                return True
            except (VerifyMismatchError, InvalidHashError):
                return False
            except Exception as e:
                logger.warning("Erro ao verificar hash Argon2: %s", e)
                return False
        return _werkzeug_check(pwhash, password)

    def set_senha(self, senha):
        """Define a senha do usuário com hash (Argon2id)"""
        self.senha = Usuario.hash_password(senha)

    def verificar_senha(self, senha):
        """Verifica se a senha informada é correta (aceita Argon2id e hashes legados)"""
        return Usuario.check_password(self.senha, senha)

    def atualizar_ultimo_login(self):
        """Atualiza a data/hora do último login"""
        self.ultimo_login = datetime.utcnow()
        db.session.commit()

    def is_cargo(self,cargo):
        """Verifica se o usuário tem o cargo informado"""
        return self.colaborador.cargo.nome == cargo
    
    def is_departamento(self,departamento):
        """Verifica se o usuário tem o departamento informado"""
        return self.colaborador.departamento.nome == departamento
    
    @property
    def is_admin(self):
        """Verifica se o usuário é administrador"""
        return self.is_gerente_ou_superior
    
    @property
    def is_tst(self):
        """Verifica se o usuário é TST"""
        return self.cargo_rel and self.cargo_rel.nome.upper() == 'TST'
    
    @property
    def is_operacional(self):
        """Verifica se o usuário é operacional"""
        cargo_nome = self.cargo_rel.nome.lower() if self.cargo_rel else ''
        return cargo_nome in ['admin', 'operacional']

    @property
    def is_gerente_ou_superior(self):
        """Verifica se o usuário é gerente ou superior"""
        return True if self.cargo_rel and self.cargo_id in [4, 5, 16] else False
    
    @property
    def is_tecnico_superior(self):
        """Verifica se o usuário é técnico superior"""
        cargo_nome = self.cargo_rel.nome.lower() if self.cargo_rel else ''
        return cargo_nome in ['gerente', 'diretor', 'admin']
    
    def is_permissao(self, modulo, acao='visualizar'):
        """Verifica se o usuário tem permissão para o módulo informado"""
        try:
            from models.permissoes import Permissao
            return Permissao.verificar_permissao_completa(self, modulo, acao)
        except Exception:
            # Fallback para o sistema antigo se houver erro
            return self._verificar_permissao_antiga(modulo)
    
    def _verificar_permissao_antiga(self, modulo):
        """Sistema antigo de permissões (fallback)"""
        Tecnico = self.is_cargo('TÉCNICO DE EDIFICAÇÕES')
        Gestor = self.is_cargo('GESTOR DE DESENVOLVIMENTO') or \
                self.is_cargo('GESTOR DE FABRICA') or \
                self.is_cargo('ENGENHEIRO CIVIL')
        Usina = self.is_cargo('OPERADOR CENTRAL DE CONCRETO')
        Administrativo = self.is_cargo('ASSISTENTE ADMINISTRATIVO')
        Admin = self.is_departamento('ADMINISTRATIVO')
        
        if modulo == 'CARGO':
            if Gestor or Administrativo:
                return True
        if modulo =='CENTROCUSTO':
            if Gestor:
                return True
        if modulo == 'CLIENTE':
            if Gestor:
                return True
        if modulo == 'COLABORADOR':
            if Gestor or Administrativo:
                return True
        if modulo == 'CONCRETAGEM':
            if Gestor or Tecnico:
                return True
        if modulo == 'CONTRATO':
            if Gestor:
                return True
        if modulo == 'CONVERSAO':
            if Admin:
                return True
        if modulo == 'DADOSANALITICOS':
            if Gestor:
                return True
        if modulo == 'DEPARTAMENTO':
            if Admin:
                return True
        if modulo == 'ESTRUTURA':
            if Gestor:
                return True
        if modulo == 'EQUIPAMENTO':
            if Gestor or Tecnico or Usina:
                return True
        if modulo == 'ESTOQUE':
            if Gestor or Tecnico:
                return True
        if modulo == 'MATERIAL':
            if Tecnico or Gestor:
                return True
        if modulo == 'NOTA_FISCAL':
            if Gestor or Administrativo or Tecnico:
                return True
        if modulo == 'PECA':
            if Gestor or Tecnico:
                return True
        if modulo == 'PLANO_DE_CONTAS':
            if Gestor:
                return True
        if modulo == 'PRODUTO':
            if Gestor or Tecnico:
                return True
        if modulo == 'PROJETO':
            if Gestor or Tecnico:
                return True
        if modulo == 'RELATORIO_USINAGEM':
            if Tecnico or Usina:
                return True
        return False

    def __repr__(self):
        return f'<Usuario {self.email}>'
