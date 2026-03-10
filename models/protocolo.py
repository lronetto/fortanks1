"""
Modelo para representar Protocolos de Notas Fiscais.
Cada protocolo possui data e número; ao criar, o usuário pode importar PDFs
que são renomeados pela chave de acesso e vinculados às notas quando identificados.
"""
from datetime import datetime

from models.database import db


class Protocolo(db.Model):
    __tablename__ = "Protocolo"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    numero = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Protocolo {self.id} {self.data} {self.numero}>"

    def to_dict(self):
        return {
            "id": self.id,
            "data": self.data.isoformat() if self.data else None,
            "numero": self.numero,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
