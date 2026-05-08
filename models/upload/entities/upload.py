"""ORM da tabela `Uploads` — binários e metadados de anexos."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
from datetime import datetime
from sqlalchemy.orm import defer
from sqlalchemy import Text

from models.database import db

from ..constants import NOME_TABELA
from ..utils.armazenamento import normalizar_blob_para_armazenamento
from logging import getLogger
logger = getLogger(__name__)
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

    def _bool_env(self, nome: str, default: bool = False) -> bool:
        valor = os.getenv(nome)
        if valor is None:
            return default
        return valor.strip().lower() in {"1", "true", "yes", "y", "on"}

    def _dados_adicionais_dict(self) -> dict:
        da = self.dados_adicionais
        if not da:
            return {}
        if isinstance(da, dict):
            return da
        try:
            dados = json.loads(da)
            if isinstance(dados, dict):
                return dados
        except Exception:
            pass
        return {"_raw": da}

    def _object_key_minio(self) -> str:
        pai = str(self.pai or "sem-pai").strip().lower()
        pai = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in pai).strip("-") or "sem-pai"
        pai_id = str(self.pai_id or "sem-pai-id").strip().lower()
        pai_id = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in pai_id).strip("-") or "sem-pai-id"
        nome = os.path.basename(self.filename or "arquivo.bin")
        nome = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in nome) or "arquivo.bin"
        return f"uploads/{pai}/{pai_id}/{self.id}_{nome}"

    def _enviar_blob_para_minio(self) -> bool:
        """Envia blob legado para MinIO. Delega para `services.minio_service.enviar`."""
        from models.upload.services.minio_service import enviar
        return enviar(self, commit=False)

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
            if self._enviar_blob_para_minio():
                db.session.add(self)
                db.session.commit()
        except Exception as e:
            logging.exception("Erro ao salvar Upload: %s", e)
            db.session.rollback()
            raise

    def _storage_config(self):
        """Retorna configuracao de storage salva em dados_adicionais."""
        if not self.dados_adicionais:
            return None
        raw = self.dados_adicionais
        dados = raw if isinstance(raw, dict) else None
        if dados is None:
            try:
                dados = json.loads(raw)
            except Exception:
                return None
        if not isinstance(dados, dict):
            return None
        storage = dados.get("storage")
        if not isinstance(storage, dict):
            return None
        if storage.get("provider") != "minio":
            return None
        if not storage.get("bucket") or not storage.get("object_key"):
            return None
        return storage

    def _buscar_blob_no_minio(self):
        """Baixa bytes do MinIO quando o upload ja foi migrado."""
        storage = self._storage_config()
        if not storage:
            return None

        endpoint = (os.getenv("MINIO_ENDPOINT") or "").strip()
        access_key = (os.getenv("MINIO_ACCESS_KEY") or "").strip()
        secret_key = (os.getenv("MINIO_SECRET_KEY") or "").strip()
        secure = (os.getenv("MINIO_SECURE") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        if not endpoint or not access_key or not secret_key:
            return None

        try:
            from minio import Minio
        except Exception:
            logging.exception("Cliente MinIO nao disponivel para leitura de Upload id=%s", self.id)
            return None

        client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        response = None
        try:
            response = client.get_object(storage["bucket"], storage["object_key"])
            return response.read()
        except Exception:
            logging.exception("Falha ao buscar Upload id=%s no MinIO", self.id)
            return None
        finally:
            if response is not None:
                response.close()
                response.release_conn()
    
    def get_blob(self):
        """Retorna bytes do arquivo: MinIO (novo) com fallback para blob legado."""
        conteudo_minio = self._buscar_blob_no_minio()
        logger.info(f'get_blob upload id: {self.id}')
        if conteudo_minio is not None:
            return conteudo_minio
        if self.blob:
            try:
                return base64.b64decode(self.blob)
            except Exception:
                logging.exception("Falha ao decodificar blob legado do Upload id=%s", self.id)
        return None
    def get_pdf(self,nota_id=None,id_upload=None):
        
        if nota_id:
            upload = Upload.query.options(defer(Upload.blob)).filter(Upload.pai_id == nota_id, Upload.pai == 'NotaFiscal', Upload.tipo == 1).first()
        elif id_upload:
            upload = Upload.query.options(defer(Upload.blob)).filter(Upload.id == id_upload).first()
        else:
            return None
        print(f'id: {nota_id}, id_upload: {id_upload}')
        if upload:
            return upload.get_blob()
        else:
            return None
    def delete(self):
        try:
            db.session.delete(self)
            db.session.commit()
        except Exception as e:
            logging.exception("Erro ao excluir Upload: %s", e)
            db.session.rollback()
            raise
