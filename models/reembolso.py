from datetime import datetime
from models.database import db
from sqlalchemy import Text

class Reembolsos(db.Model):
    __tablename__ = 'Reembolsos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=False)
    data = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    numero_relatorio = db.Column(db.String(20), nullable=False, unique=True)
    dados_adicionais = db.Column(db.Text, nullable=True)

    usuario = db.relationship('Usuario', backref='reembolsos')
    centro_custo = db.relationship('CentroCusto', backref='reembolsos')
    documentos = db.relationship('ReembolsosDocumentos', backref='reembolso', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Reembolso {self.id} - {self.numero_relatorio}>'
    def to_dict(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'centro_custo_id': self.centro_custo_id,
            'data': self.data,
            'valor_total': self.valor_total,
            'numero_relatorio': self.numero_relatorio,
            'dados_adicionais': self.dados_adicionais
        }

class ReembolsosDocumentos(db.Model):
    __tablename__ = 'ReembolsosDocumentos'
    id = db.Column(db.Integer, primary_key=True)
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=True)
    reembolso_id = db.Column(db.Integer, db.ForeignKey('Reembolsos.id'), nullable=False)
    tipo = db.Column(db.Enum('nota', 'avulso', name='tipo_documento_reembolso'), nullable=False)
    nota_fiscal_id = db.Column(db.Integer, db.ForeignKey('NotaFiscal.id'), nullable=True)
    fornecedor = db.Column(db.String(100), nullable=True)
    ndocumento = db.Column(db.String(20), nullable=True)
    data_documento = db.Column(db.DateTime, nullable=True)
    descricao = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    nota_fiscal = db.relationship('NotaFiscal', backref='documentos_reembolso')
    centro_custo = db.relationship('CentroCusto', backref='documentos_reembolso')

    def __repr__(self):
        return f'<ReembolsosDocumentos {self.id} - {self.tipo}>'

    def to_dict(self):
        return {
            'id': self.id,
            'tipo': self.tipo,
            'nota_fiscal_id': self.nota_fiscal_id,
            'fornecedor': self.fornecedor,
            'ndocumento': self.ndocumento,
            'data_documento': self.data_documento,
            'descricao': self.descricao,
            'valor': self.valor,
            'nota_fiscal': self.nota_fiscal.to_dict() if self.nota_fiscal else None,
            'centro_custo': self.centro_custo.to_dict() if self.centro_custo else None,
        }

