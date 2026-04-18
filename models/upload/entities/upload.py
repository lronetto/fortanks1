"""ORM da tabela `Uploads` — binários e metadados de anexos."""
from __future__ import annotations

import base64
import logging
from datetime import datetime

from sqlalchemy import Text

from models.database import db

from ..constants import NOME_TABELA
from ..utils.armazenamento import normalizar_blob_para_armazenamento


class Upload(db.Model):
    __tablename__ = NOME_TABELA

    id = db.Column(db.Integer, primary_key=True)
    pai_id = db.Column(db.Integer, nullable=True)
    pai = db.Column(db.String(255), nullable=True)
    tipo = db.Column(db.Integer, nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    blob = db.Column(Text(length=4294967295), nullable=True)  # LONGTEXT
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    dados_adicionais = db.Column(db.Text, nullable=True)

    def __init__(
        self,
        pai=None,
        pai_id=None,
        tipo=None,
        filename=None,
        mimetype=None,
        blob=None,
        dados_adicionais=None,
    ):
        """Define campos; não persiste. Use `save()` ou `registrar()` para gravar."""
        self.pai = pai
        self.pai_id = pai_id
        self.tipo = tipo
        self.filename = filename
        self.mimetype = mimetype
        self.dados_adicionais = dados_adicionais
        self.blob = normalizar_blob_para_armazenamento(blob)

    def __repr__(self):
        return f"<Upload {self.id} - {self.filename}>"

    @classmethod
    def registrar(
        cls,
        pai=None,
        pai_id=None,
        tipo=None,
        filename=None,
        mimetype=None,
        blob=None,
        dados_adicionais=None,
    ):
        """
        Cria instância, persiste e retorna (substitui o antigo `Upload(...)` que fazia commit no __init__).
        """
        inst = cls(
            pai=pai,
            pai_id=pai_id,
            tipo=tipo,
            filename=filename,
            mimetype=mimetype,
            blob=blob,
            dados_adicionais=dados_adicionais,
        )
        inst.save()
        return inst

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "mimetype": self.mimetype,
            "uploaded_at": self.uploaded_at,
            "blob": self.blob,
        }

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            logging.exception("Erro ao salvar Upload: %s", e)
            db.session.rollback()
            raise

    def get_blob(self):
        """Retorna o blob decodificado (bytes)."""
        if self.blob:
            return base64.b64decode(self.blob)
        return None

    def delete(self):
        try:
            db.session.delete(self)
            db.session.commit()
        except Exception as e:
            logging.exception("Erro ao excluir Upload: %s", e)
            db.session.rollback()
            raise
