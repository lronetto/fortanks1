from datetime import datetime
from models.database import db

class Colaborador(db.Model):
    __tablename__ = 'colaboradores'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True)
    rg = db.Column(db.String(20))
    data_nascimento = db.Column(db.Date)
    data_admissao = db.Column(db.Date, nullable=False)
    data_demissao = db.Column(db.Date)
    #cargo = db.Column(db.String(100), nullable=False)
    cargo_id = db.Column(db.Integer, db.ForeignKey('cargos.id', ondelete='RESTRICT'), nullable=False)
    #departamento = db.Column(db.String(100), nullable=False)
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'))
    status = db.Column(db.String(20), nullable=False, default='Ativo')  # Ativo, Inativo, Afastado, Férias
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    endereco = db.Column(db.String(255))
    observacoes = db.Column(db.Text)
  

    usuario = db.relationship('Usuario', back_populates='colaborador')
    # Controle de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    #usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))

    def __repr__(self):
        return f'<Colaborador {self.nome}>'
    
    def save(self):
        if not self.id:
            db.session.add(self)
        db.session.commit()
        
    def delete(self):
        db.session.delete(self)
        db.session.commit()
    
    @property
    def esta_ativo(self):
        return self.status == 'Ativo'
    
    @property
    def idade(self):
        if self.data_nascimento:
            hoje = datetime.now().date()
            return hoje.year - self.data_nascimento.year - ((hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day))
        return None
    
    @property
    def tempo_empresa(self):
        if self.data_admissao:
            fim = self.data_demissao if self.data_demissao else datetime.now().date()
            anos = fim.year - self.data_admissao.year - ((fim.month, fim.day) < (self.data_admissao.month, self.data_admissao.day))
            return anos
        return None 