from datetime import datetime
from models.database import db


class CronogramaItem(db.Model):
    """Linha do cronograma (nome, ordem, peso, predecessor opcional, tanque opcional) por contrato."""

    __tablename__ = 'CronogramaItens'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    # Numeração tipo outline: 1, 1.1, 1.1.1 (texto)
    indice = db.Column(db.String(50), nullable=False, default='')
    # Chave derivada para ORDER BY (segmentos com zeros à esquerda)
    indice_sort = db.Column(db.String(200), nullable=False, default='')
    # Outro item do mesmo projeto que deve anteceder este (rede de dependências)
    predecessor_id = db.Column(db.Integer, db.ForeignKey('CronogramaItens.id'), nullable=True)
    peso = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id'), nullable=True)
    # Data de início planejada do item (opcional; matriz/previsto usam antes da data do tanque)
    data_inicio = db.Column(db.Date, nullable=True)

    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    contrato = db.relationship('Contrato', backref=db.backref('cronograma_itens', lazy='dynamic'))
    tanque = db.relationship('Tanques', backref=db.backref('cronograma_itens', lazy='dynamic'))
    predecessor = db.relationship(
        'CronogramaItem',
        remote_side='CronogramaItem.id',
        foreign_keys=[predecessor_id],
    )


class CronogramaCalendario(db.Model):
    """Calendário de planejamento: quais dias da semana são úteis + feriados vinculados."""

    __tablename__ = 'CronogramaCalendarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    observacao = db.Column(db.Text, nullable=True)
    seg_util = db.Column(db.Boolean, nullable=False, default=True)
    ter_util = db.Column(db.Boolean, nullable=False, default=True)
    qua_util = db.Column(db.Boolean, nullable=False, default=True)
    qui_util = db.Column(db.Boolean, nullable=False, default=True)
    sex_util = db.Column(db.Boolean, nullable=False, default=True)
    sab_util = db.Column(db.Boolean, nullable=False, default=False)
    dom_util = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    feriados = db.relationship(
        'CronogramaCalendarioFeriado',
        back_populates='calendario',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )


class CronogramaCalendarioFeriado(db.Model):
    __tablename__ = 'CronogramaCalendarioFeriados'
    __table_args__ = (
        db.UniqueConstraint('calendario_id', 'data', name='uq_cron_cal_feriado_data'),
    )

    id = db.Column(db.Integer, primary_key=True)
    calendario_id = db.Column(db.Integer, db.ForeignKey('CronogramaCalendarios.id'), nullable=False)
    data = db.Column(db.Date, nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    observacao = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    calendario = db.relationship('CronogramaCalendario', back_populates='feriados')


class CronogramaVinculoCalendario(db.Model):
    """Calendário aplicado a um prefixo de índice (itens no subárvore usam na matriz prevista)."""

    __tablename__ = 'CronogramaVinculosCalendario'
    __table_args__ = (
        db.UniqueConstraint('contrato_id', 'indice_prefixo', name='uq_cron_vinc_contrato_indice'),
    )

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    indice_prefixo = db.Column(db.String(50), nullable=False)
    indice_sort = db.Column(db.String(200), nullable=False, default='')
    calendario_id = db.Column(db.Integer, db.ForeignKey('CronogramaCalendarios.id'), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    contrato = db.relationship('Contrato', backref=db.backref('cronograma_vinculos_calendario', lazy='dynamic'))
    calendario = db.relationship('CronogramaCalendario', backref=db.backref('vinculos_cronograma', lazy='dynamic'))


class CronogramaTanque(db.Model):
    __tablename__ = 'CronogramaTanques'

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
    __tablename__ = 'CronogramaLinhasBase'

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
    __tablename__ = 'CronogramaLinhasBaseTanques'

    id = db.Column(db.Integer, primary_key=True)
    linha_base_id = db.Column(db.Integer, db.ForeignKey('CronogramaLinhasBase.id'), nullable=False)
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id'), nullable=False)
    data_inicio_prevista = db.Column(db.Date, nullable=True)
    data_fim_prevista = db.Column(db.Date, nullable=True)

    linha_base = db.relationship('CronogramaLinhaBase', back_populates='itens')
    tanque = db.relationship('Tanques')
