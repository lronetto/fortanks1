from datetime import datetime
from models.database import db

class Equipamento(db.Model):
    __tablename__ = 'equipamentos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # Veiculos, Maquinas, Ferramentas
    propriedade = db.Column(db.String(20), nullable=False)  # Propria, Alugada
    modelo = db.Column(db.String(100))
    numero_serie = db.Column(db.String(50))
    nota_fiscal = db.Column(db.String(50))
    data_aquisicao = db.Column(db.Date)
    status = db.Column(db.String(20), default='Ativo')  # Ativo, Em Manutenção, Inativo
    observacoes = db.Column(db.Text)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    manutencoes = db.relationship('Manutencao', backref='equipamento', lazy=True)
    checklists = db.relationship('ChecklistEquipamento', backref='equipamento', lazy=True)

class Manutencao(db.Model):
    __tablename__ = 'manutencoes'
    
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamentos.id'), nullable=False)
    tipo = db.Column(db.String(20))  # Preventiva, Corretiva
    descricao = db.Column(db.Text, nullable=False)
    data_inicio = db.Column(db.DateTime, nullable=False)
    data_fim = db.Column(db.DateTime)
    custo = db.Column(db.Numeric(10, 2))
    responsavel = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Pendente')  # Pendente, Em Andamento, Concluída
    observacoes = db.Column(db.Text)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChecklistModelo(db.Model):
    __tablename__ = 'checklist_modelos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    itens = db.relationship('ChecklistItem', backref='modelo', lazy=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChecklistItem(db.Model):
    __tablename__ = 'checklist_itens'
    
    id = db.Column(db.Integer, primary_key=True)
    modelo_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id'), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20))  # Sim/Não, Numérico, Texto
    obrigatorio = db.Column(db.Boolean, default=True)
    ordem = db.Column(db.Integer)

class ChecklistEquipamento(db.Model):
    __tablename__ = 'checklist_equipamentos'
    
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamentos.id'), nullable=False)
    modelo_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id'), nullable=False)
    data_checklist = db.Column(db.DateTime, nullable=False)
    responsavel = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Pendente')  # Pendente, Em Andamento, Concluído
    observacoes = db.Column(db.Text)
    respostas = db.relationship('ChecklistResposta', backref='checklist', lazy=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChecklistResposta(db.Model):
    __tablename__ = 'checklist_respostas'
    
    id = db.Column(db.Integer, primary_key=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey('checklist_equipamentos.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('checklist_itens.id'), nullable=False)
    resposta = db.Column(db.String(200))
    observacao = db.Column(db.Text)
    data_resposta = db.Column(db.DateTime, default=datetime.utcnow) 