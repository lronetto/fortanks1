from datetime import datetime

from models.database import db


class DadosBancarios(db.Model):
    __tablename__ = "dados_bancarios"
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey("colaboradores.id"), nullable=False)
    pix = db.Column(db.String(100), nullable=True)
    banco = db.Column(db.String(100), nullable=True)
    agencia = db.Column(db.String(100), nullable=True)
    conta = db.Column(db.String(100), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    colaborador = db.relationship("Colaborador", back_populates="dados_bancarios")

    def __repr__(self):
        return f"<DadosBancarios {self.id}>"
