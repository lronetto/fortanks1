from datetime import datetime
from models.database import db

class Reembolso(db.Model):
    __tablename__ = 'reembolsos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=False)
    data = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    numero_relatorio = db.Column(db.String(20), nullable=False, unique=True)

    usuario = db.relationship('Usuario', backref='reembolsos')
    centro_custo = db.relationship('CentroCusto', backref='reembolsos')
    documentos = db.relationship('ReembolsoDocumento', backref='reembolso', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Reembolso {self.id} - {self.numero_relatorio}>'

class ReembolsoDocumento(db.Model):
    __tablename__ = 'reembolso_documentos'
    id = db.Column(db.Integer, primary_key=True)
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=False)
    reembolso_id = db.Column(db.Integer, db.ForeignKey('reembolsos.id'), nullable=False)
    tipo = db.Column(db.Enum('nota', 'avulso', name='tipo_documento_reembolso'), nullable=False)
    nota_fiscal_id = db.Column(db.Integer, db.ForeignKey('nf_notas.id'), nullable=True)
    fornecedor = db.Column(db.String(100), nullable=True)
    ndocumento = db.Column(db.String(20), nullable=True)
    data_documento = db.Column(db.DateTime, nullable=True)
    descricao = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    anexos = db.relationship('ReembolsoAnexo', backref='documento', cascade='all, delete-orphan')
    nota_fiscal = db.relationship('NotaFiscal', backref='documentos_reembolso')

    def __repr__(self):
        return f'<ReembolsoDocumento {self.id} - {self.tipo}>'

class ReembolsoAnexo(db.Model):
    __tablename__ = 'reembolso_anexos'
    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(db.Integer, db.ForeignKey('reembolso_documentos.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    blob = db.Column(db.LargeBinary, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<ReembolsoAnexo {self.id} - {self.filename}>' 