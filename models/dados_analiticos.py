"""
Modelo para armazenamento de dados analíticos financeiros.
Este modelo armazena informações extraídas de relatórios financeiros para análise.
"""
import uuid
from datetime import datetime
from sqlalchemy import Index, UniqueConstraint, text

from .database import db

PL_RECOP = [118,5]
PL_00=[9,10,11,12,13,14,15,16,17,18,19,20,21,23,25,26,27]
PL_0201 = [33, 34, 35, 36, 37, 39, 40, 41, 120, 121, 124, 125, 163, 164, 165]
PL_0202 = [44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
           56, 57, 58, 59, 60, 61, 190, 62, 63, 64, 65, 66, 67]
PL_0203 = [73, 146, 122]
PL_0204 = [75, 76, 77, 78, 79, 80, 81, 82,
           83, 84, 133, 134, 135, 137, 138, 162]
PL_0205 = [86, 87, 88, 89, 90, 91, 92, 93, 94, 166]
PL_0206 = [96]
PL_0207 = [98, 99, 100, 101, 102, 103, 104,
           105, 106, 123, 158, 183, 184, 185, 186]
PL_0208 = [108, 109, 110, 119, 141, 168]
PL_0209 = [112, 113, 114, 115, 116, 117, 139, 140]
PL_0210 = [143, 144, 145]
PL_0211 = [38]
PL_0212 = [172, 173, 174, 175, 176, 177, 178, 179, 180, 182]
PL_0213 = [188]
PL_CUSTO = PL_0201+PL_0202+PL_0203+PL_0204+PL_0205 + \
    PL_0206+PL_0207+PL_0208+PL_0209+PL_0210+PL_0211+PL_0212+PL_0213+PL_00


class DadoAnalitico(db.Model):
    """
    Modelo para armazenamento de dados analíticos financeiros.
    Registra transações financeiras com informações como centro de custo,
    plano de conta, data, valor, histórico, etc.
    """
    __tablename__ = 'DadosAnaliticos'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Relacionamentos
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=True)
    plano_conta_id = db.Column(db.Integer, db.ForeignKey('planos_conta.id'), nullable=True)
    
    # Dados da transação
    data_pagamento = db.Column(db.Date, nullable=True, index=True)
    documento = db.Column(db.String(50), nullable=True, index=True)
    emitente = db.Column(db.String(255), nullable=True)
    debito_credito = db.Column(db.String(10), nullable=True)  # 'D' para débito, 'C' para crédito
    historico = db.Column(db.Text, nullable=True)
    liberado_por = db.Column(db.String(255), nullable=True)
    banco = db.Column(db.String(255), nullable=True)
    cheque = db.Column(db.String(50), nullable=True)
    valor = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    pago = db.Column(db.Boolean, default=False)
    
    # Metadados
    ano = db.Column(db.Integer, nullable=True, index=True)
    mes = db.Column(db.Integer, nullable=True, index=True)
    importado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    importado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Definir relacionamentos
    centro_custo = db.relationship('CentroCusto', backref=db.backref('dados_analiticos', lazy='dynamic'))
    plano_conta = db.relationship('PlanoConta', backref=db.backref('dados_analiticos', lazy='dynamic'))
    importador = db.relationship('Usuario', backref=db.backref('dados_analiticos_importados', lazy='dynamic'))
    
    # Índices para otimização
   # __table_args__ = (
    #    Index('idx_dados_analiticos_data', 'data_pagamento'),
    #    Index('idx_dados_analiticos_centro_custo', 'centro_custo_id'),
    #    Index('idx_dados_analiticos_plano_conta', 'plano_conta_id'),
    #    Index('idx_dados_analiticos_ano_mes', 'ano', 'mes'),
        #UniqueConstraint('documento', 'emitente', 'data_pagamento', 'valor', 
        #                name='uq_dados_analiticos_transacao'),
    #)
    
    def __init__(self, **kwargs):
        super(DadoAnalitico, self).__init__(**kwargs)
        
        # Extrair ano e mês da data de pagamento para facilitar consultas
        if self.data_pagamento:
            self.ano = self.data_pagamento.year
            self.mes = self.data_pagamento.month
    
    def save(self):
        """Salva o objeto no banco de dados."""
        if not self.data_pagamento:
            return False
            
        # Atualizar ano e mês
        self.ano = self.data_pagamento.year
        self.mes = self.data_pagamento.month
        
        db.session.add(self)
        try:
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e
    
    def delete(self):
        """Remove o objeto do banco de dados."""
        db.session.delete(self)
        try:
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e
    
    def to_dict(self):
        """Converte o objeto para um dicionário."""
        return {
            'id': self.id,
            'centro_custo_id': self.centro_custo_id,
            'centro_custo': self.centro_custo.nome if self.centro_custo else None,
            'plano_conta_id': self.plano_conta_id,
            'plano_conta': self.plano_conta.descricao if self.plano_conta else None,
            'data_pagamento': self.data_pagamento.strftime('%Y-%m-%d') if self.data_pagamento else None,
            'documento': self.documento,
            'emitente': self.emitente,
            'debito_credito': self.debito_credito,
            'historico': self.historico,
            'liberado_por': self.liberado_por,
            'banco': self.banco,
            'cheque': self.cheque,
            'valor': float(self.valor) if self.valor else 0,
            'pago': self.pago,
            'ano': self.ano,
            'mes': self.mes,
            'importado_em': self.importado_em.strftime('%Y-%m-%d %H:%M:%S') if self.importado_em else None
        }
    
    def __repr__(self):
        """Representação em string do objeto."""
        return f"<DadoAnalitico(id={self.id}, data='{self.data_pagamento}', valor={self.valor})>" 