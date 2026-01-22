from datetime import datetime
from models.database import db

class Modulo(db.Model):
    """
    Modelo para representar módulos do sistema
    """
    __tablename__ = 'modulos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text, nullable=True)
    icone = db.Column(db.String(50), nullable=True)
    url = db.Column(db.String(200), nullable=True)
    ordem = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='Ativo')  # Ativo, Inativo
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    permissoes = db.relationship('Permissao', back_populates='modulo', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'icone': self.icone,
            'url': self.url,
            'ordem': self.ordem,
            'status': self.status,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None
        }
    
    def save(self):
        """Salva o módulo no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """Exclui o módulo do banco de dados"""
        db.session.delete(self)
        db.session.commit()
    
    def __repr__(self):
        return f'<Modulo {self.nome}>'


class Permissao(db.Model):
    """
    Modelo para representar permissões de acesso aos módulos
    """
    __tablename__ = 'permissoes'
    
    id = db.Column(db.Integer, primary_key=True)
    modulo_id = db.Column(db.Integer, db.ForeignKey('modulos.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'), nullable=True)
    cargo_id = db.Column(db.Integer, db.ForeignKey('cargos.id'), nullable=True)
    tipo_permissao = db.Column(db.String(20), nullable=False)  # usuario, departamento, cargo
    pode_visualizar = db.Column(db.Boolean, default=True)
    pode_criar = db.Column(db.Boolean, default=False)
    pode_editar = db.Column(db.Boolean, default=False)
    pode_excluir = db.Column(db.Boolean, default=False)
    pode_exportar = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='Ativo')  # Ativo, Inativo
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    modulo = db.relationship('Modulo', back_populates='permissoes', lazy=True)
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id], lazy=True)
    departamento = db.relationship('Departamento', foreign_keys=[departamento_id], lazy=True)
    cargo = db.relationship('Cargo', foreign_keys=[cargo_id], lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'modulo_id': self.modulo_id,
            'modulo_nome': self.modulo.nome if self.modulo else None,
            'usuario_id': self.usuario_id,
            'usuario_nome': self.usuario.nome if self.usuario else None,
            'departamento_id': self.departamento_id,
            'departamento_nome': self.departamento.nome if self.departamento else None,
            'cargo_id': self.cargo_id,
            'cargo_nome': self.cargo.nome if self.cargo else None,
            'tipo_permissao': self.tipo_permissao,
            'pode_visualizar': self.pode_visualizar,
            'pode_criar': self.pode_criar,
            'pode_editar': self.pode_editar,
            'pode_excluir': self.pode_excluir,
            'pode_exportar': self.pode_exportar,
            'status': self.status,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None
        }
    
    def save(self):
        """Salva a permissão no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """Exclui a permissão do banco de dados"""
        db.session.delete(self)
        db.session.commit()
    
    @staticmethod
    def verificar_permissao_completa(usuario, modulo_nome, acao='visualizar'):
        """
        Verifica se um usuário tem permissão para realizar uma ação em um módulo.
        
        A verificação segue a hierarquia de prioridade:
        1. Permissão específica do usuário (maior prioridade)
        2. Permissão do departamento do usuário (usuario.departamento_id)
        3. Permissão do cargo do usuário (usuario.cargo_id) (menor prioridade)
        
        O sistema utiliza diretamente os campos departamento_id e cargo_id 
        da tabela de usuários para verificar as permissões.
        
        Args:
            usuario: Instância do modelo Usuario (deve ter departamento_id e cargo_id)
            modulo_nome: Nome do módulo (ex: 'DASHBOARD', 'CLIENTES')
            acao: Ação a verificar ('visualizar', 'criar', 'editar', 'excluir', 'exportar')
        
        Returns:
            bool: True se o usuário tem permissão, False caso contrário
        
        Exemplo:
            >>> usuario = Usuario.query.first()
            >>> Permissao.verificar_permissao_completa(usuario, 'DASHBOARD', 'visualizar')
            True
        """
        try:
            # Buscar o módulo
            modulo = Modulo.query.filter_by(nome=modulo_nome, status='Ativo').first()
            if not modulo:
                return False
            
            # Mapear ação para campo
            campo_acao = f'pode_{acao}'
            if not hasattr(Permissao, campo_acao):
                return False
            
            # 1. Verificar permissão específica do usuário (maior prioridade)
            # Se o usuário tiver uma permissão individual, ela tem prioridade sobre tudo
            permissao_usuario = Permissao.query.filter_by(
                modulo_id=modulo.id,
                usuario_id=usuario.id,
                tipo_permissao='usuario',
                status='Ativo'
            ).first()
            
            if permissao_usuario:
                return getattr(permissao_usuario, campo_acao, False)
            
            # 2. Verificar permissão do departamento do usuário
            # Usa diretamente o departamento_id do usuário (campo da tabela usuarios)
            if usuario.departamento_id:
                permissao_departamento = Permissao.query.filter_by(
                    modulo_id=modulo.id,
                    departamento_id=usuario.departamento_id,  # Usa o departamento_id do usuário
                    tipo_permissao='departamento',
                    status='Ativo'
                ).first()
                
                if permissao_departamento:
                    return getattr(permissao_departamento, campo_acao, False)
            
            # 3. Verificar permissão do cargo do usuário (menor prioridade)
            # Usa diretamente o cargo_id do usuário (campo da tabela usuarios)
            if usuario.cargo_id:
                permissao_cargo = Permissao.query.filter_by(
                    modulo_id=modulo.id,
                    cargo_id=usuario.cargo_id,  # Usa o cargo_id do usuário
                    tipo_permissao='cargo',
                    status='Ativo'
                ).first()
                
                if permissao_cargo:
                    return getattr(permissao_cargo, campo_acao, False)
            
            # Nenhuma permissão encontrada
            return False
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erro ao verificar permissão: {str(e)}")
            return False
    
    def __repr__(self):
        tipo = self.tipo_permissao
        entidade = 'N/A'
        if tipo == 'usuario' and self.usuario:
            entidade = self.usuario.nome
        elif tipo == 'departamento' and self.departamento:
            entidade = self.departamento.nome
        elif tipo == 'cargo' and self.cargo:
            entidade = self.cargo.nome
        
        return f'<Permissao {self.modulo.nome if self.modulo else "N/A"} - {tipo}: {entidade}>'
