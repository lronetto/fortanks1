from datetime import datetime
from models.database import db


class CronogramaFeriado(db.Model):
    __tablename__ = 'cronograma_feriados'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(32), nullable=False, default='nacional')
    uf = db.Column(db.String(2), nullable=True)
    municipio = db.Column(db.String(120), nullable=True)
    recorrente = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    observacao = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class CronogramaTanque(db.Model):
    __tablename__ = 'cronograma_tanques'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id'), nullable=False)
    data_inicio_prevista = db.Column(db.Date, nullable=True)
    data_fim_prevista = db.Column(db.Date, nullable=True)
    data_inicio_real = db.Column(db.Date, nullable=True)
    data_fim_real = db.Column(db.Date, nullable=True)
    observacao = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    contrato = db.relationship('Contrato', backref=db.backref('cronograma_tanques', lazy='dynamic'))
    tanque = db.relationship('Tanques', backref=db.backref('cronograma_tanques', lazy='dynamic'))


class CronogramaLinhaBase(db.Model):
    __tablename__ = 'cronograma_linhas_base'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    data_snapshot = db.Column(db.DateTime, nullable=False, default=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)

    contrato = db.relationship('Contrato', backref=db.backref('cronograma_linhas_base', lazy='dynamic'))
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])
    itens = db.relationship(
        'CronogramaLinhaBaseTanque',
        back_populates='linha_base',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )


class CronogramaLinhaBaseTanque(db.Model):
    __tablename__ = 'cronograma_linhas_base_tanques'

    id = db.Column(db.Integer, primary_key=True)
    linha_base_id = db.Column(db.Integer, db.ForeignKey('cronograma_linhas_base.id'), nullable=False)
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id'), nullable=False)
    data_inicio_prevista = db.Column(db.Date, nullable=True)
    data_fim_prevista = db.Column(db.Date, nullable=True)

    linha_base = db.relationship('CronogramaLinhaBase', back_populates='itens')
    tanque = db.relationship('Tanques')
