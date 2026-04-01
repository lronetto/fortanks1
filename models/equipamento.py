from datetime import datetime
from models.database import db

EQ_STATUS = [
        'Ativo',
        'Em Manutenção',
        'Aguardando Reparo',
        'Emprestado',
        'Inativo',

]
class Equipamento(db.Model):
    __tablename__ = 'Equipamentos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # Veiculos, Maquinas, Ferramentas
    propriedade = db.Column(db.String(20), nullable=False)  # Propria, Alugada
    modelo = db.Column(db.String(100))
    numero_serie = db.Column(db.String(50))
    nota_fiscal = db.Column(db.String(50))
    data_aquisicao = db.Column(db.Date)
    status = db.Column(db.String(20), default='Ativo')  # ver EQ_STATUS
    observacoes = db.Column(db.Text)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    dados_adicionais = db.Column(db.Text)
    # Relacionamentos
    manutencoes = db.relationship('Manutencao', backref='equipamento', lazy=True)
    checklists = db.relationship('ChecklistEquipamento', backref='equipamento', lazy=True)
    emprestimos = db.relationship(
        'EquipamentoEmprestimo',
        backref='equipamento',
        lazy=True,
    )

class EquipamentoEmprestimo(db.Model):
    """Registro de empréstimo de equipamento a colaborador (entrega / devolução)."""
    __tablename__ = 'EquipamentosEmprestimos'

    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('Equipamentos.id'), nullable=False)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=False)
    data_entrega = db.Column(db.DateTime, nullable=False)
    data_recebimento = db.Column(db.DateTime, nullable=True)
    observacoes = db.Column(db.Text)
    usuario_registro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    colaborador = db.relationship('Colaborador', backref='equipamentos_emprestimos')
    usuario_registro = db.relationship(
        'Usuario',
        foreign_keys=[usuario_registro_id],
    )


class Manutencao(db.Model):
    __tablename__ = 'EquipamentosManutencoes'
    
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('Equipamentos.id'), nullable=False)
    tipo = db.Column(db.String(20))  # Preventiva, Corretiva
    descricao = db.Column(db.Text, nullable=False)
    data_inicio = db.Column(db.DateTime, nullable=False)
    data_fim = db.Column(db.DateTime)
    custo = db.Column(db.Numeric(10, 2))
    responsavel = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Pendente')  # Pendente, Em Andamento, Concluída
    observacoes = db.Column(db.Text)
    nota_fiscal_id = db.Column(db.Integer, db.ForeignKey('NotaFiscal.id'), nullable=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    nota_fiscal_ref = db.relationship(
        'NotaFiscal',
        foreign_keys=[nota_fiscal_id],
    )

class ChecklistModelo(db.Model):
    __tablename__ = 'EquipamentosChecklistModelos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    itens = db.relationship('ChecklistItem', backref='modelo', lazy=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChecklistItem(db.Model):
    __tablename__ = 'EquipamentosChecklistItens'
    
    id = db.Column(db.Integer, primary_key=True)
    modelo_id = db.Column(db.Integer, db.ForeignKey('EquipamentosChecklistModelos.id'), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20))  # Sim/Não, Numérico, Texto
    obrigatorio = db.Column(db.Boolean, default=True)
    ordem = db.Column(db.Integer)

class ChecklistEquipamento(db.Model):
    __tablename__ = 'EquipamentosChecklistRegistros'
    
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('Equipamentos.id'), nullable=False)
    modelo_id = db.Column(db.Integer, db.ForeignKey('EquipamentosChecklistModelos.id'), nullable=False)
    modelo = db.relationship('ChecklistModelo', foreign_keys=[modelo_id])
    data_checklist = db.Column(db.DateTime, nullable=False)
    responsavel = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Pendente')  # Pendente, Em Andamento, Concluído
    observacoes = db.Column(db.Text)
    respostas = db.relationship('ChecklistResposta', backref='checklist', lazy=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChecklistResposta(db.Model):
    __tablename__ = 'EquipamentosChecklistRespostas'
    
    id = db.Column(db.Integer, primary_key=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey('EquipamentosChecklistRegistros.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('EquipamentosChecklistItens.id'), nullable=False)
    item = db.relationship('ChecklistItem', foreign_keys=[item_id])
    resposta = db.Column(db.String(200))
    observacao = db.Column(db.Text)
    data_resposta = db.Column(db.DateTime, default=datetime.utcnow) 