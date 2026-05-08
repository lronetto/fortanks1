"""
Serviço de armazenamento de Uploads no MinIO.

Centraliza:
  - upload (envio) de um ou vários `Upload` para o MinIO
  - exclusão (remoção do objeto + opcionalmente do registro DB)
  - construção/ingestão (criar `Upload` no DB e enviar pro MinIO num passo)

Idempotente em relação a registros já enviados (`Upload.dados_adicionais.storage`):
o método `enviar` pula uploads que já têm `storage.object_key`.

Configuração via env (igual ao usado pelo `Upload._enviar_blob_para_minio`):
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET_UPLOADS,
    MINIO_SECURE, MINIO_UPLOAD_WRITE_ENABLED, MINIO_CLEAR_BLOB_ON_WRITE
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from datetime import datetime
from typing import Iterable, Optional, Tuple

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Configuração e cliente
# --------------------------------------------------------------------------

def _bool_env(nome: str, default: bool = False) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return default
    return valor.strip().lower() in {"1", "true", "yes", "y", "on"}


def _conectar_client():
    """
    Devolve um client MinIO conectado, ou None se as envs não estão definidas
    ou o pacote `minio` não está instalado.
    """
    endpoint = (os.getenv("MINIO_ENDPOINT") or "").strip()
    access = (os.getenv("MINIO_ACCESS_KEY") or "").strip()
    secret = (os.getenv("MINIO_SECRET_KEY") or "").strip()
    secure = _bool_env("MINIO_SECURE", default=False)
    if not (endpoint and access and secret):
        return None
    try:
        from minio import Minio
    except Exception:
        logger.exception("Pacote `minio` indisponível.")
        return None
    return Minio(endpoint=endpoint, access_key=access, secret_key=secret, secure=secure)


def _bucket_default() -> str:
    return (os.getenv("MINIO_BUCKET_UPLOADS") or "sfortanks").strip()


# --------------------------------------------------------------------------
# Helpers de dados_adicionais.storage
# --------------------------------------------------------------------------

def _ler_dados_dict(upload) -> dict:
    da = upload.dados_adicionais
    if not da:
        return {}
    if isinstance(da, dict):
        return dict(da)
    try:
        d = json.loads(da)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _gravar_dados_dict(upload, dados: dict) -> None:
    upload.dados_adicionais = json.dumps(dados, ensure_ascii=False)


def _storage(upload) -> Optional[dict]:
    s = _ler_dados_dict(upload).get("storage")
    if isinstance(s, dict) and s.get("provider") == "minio":
        if s.get("bucket") and s.get("object_key"):
            return s
    return None


# --------------------------------------------------------------------------
# Envio
# --------------------------------------------------------------------------

def enviar(upload, *, client=None, bucket: Optional[str] = None,
           commit: bool = True) -> bool:
    """
    Envia o blob de UM `Upload` para o MinIO. Idempotente: se já existe
    `storage.object_key` em `dados_adicionais`, retorna True sem reenviar.

    Atualiza `upload.dados_adicionais` com o bloco `storage` (provider,
    bucket, object_key, etag, size, sha256, migrado_em). Se
    `MINIO_CLEAR_BLOB_ON_WRITE` estiver ativo, limpa `upload.blob`.
    """
    if not getattr(upload, "blob", None) or not getattr(upload, "id", None):
        return False
    if not _bool_env("MINIO_UPLOAD_WRITE_ENABLED", default=True):
        return False
    if _storage(upload):
        return True  # já enviado

    client = client or _conectar_client()
    if client is None:
        return False

    bucket = (bucket or _bucket_default()).strip()
    if not bucket:
        return False

    dados_bytes = upload.get_blob()
    if dados_bytes is None:
        return False

    object_key = upload._object_key_minio()
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        resultado = client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=io.BytesIO(dados_bytes),
            length=len(dados_bytes),
            content_type=upload.mimetype or "application/octet-stream",
        )
    except Exception:
        logger.exception("Falha ao enviar Upload id=%s para MinIO", upload.id)
        return False

    dados = _ler_dados_dict(upload)
    dados["storage"] = {
        "provider": "minio",
        "bucket": bucket,
        "object_key": object_key,
        "etag": resultado.etag,
        "size": len(dados_bytes),
        "sha256": hashlib.sha256(dados_bytes).hexdigest(),
        "migrado_em": datetime.utcnow().isoformat(),
    }
    _gravar_dados_dict(upload, dados)
    if _bool_env("MINIO_CLEAR_BLOB_ON_WRITE", default=True):
        upload.blob = None

    if commit:
        from models.database import db
        db.session.add(upload)
        db.session.commit()
    return True


def enviar_lote(uploads: Iterable, *, client=None,
                bucket: Optional[str] = None) -> Tuple[int, int]:
    """
    Envia uma lista de Uploads. Faz `db.session.commit()` UMA vez ao final
    (em vez de uma por item). Retorna (sucesso, falhas).
    """
    from models.database import db

    client = client or _conectar_client()
    sucesso = falhas = 0
    for u in uploads:
        ok = enviar(u, client=client, bucket=bucket, commit=False)
        if ok:
            sucesso += 1
        else:
            falhas += 1
    if sucesso:
        db.session.commit()
    return sucesso, falhas


# --------------------------------------------------------------------------
# Criar e enviar (atalho usado pelo processador)
# --------------------------------------------------------------------------

def criar_e_enviar(*, pai: str, pai_id: int, tipo: int, filename: str,
                   mimetype: str, blob, dados_adicionais=None,
                   client=None, bucket: Optional[str] = None):
    """
    Cria um `Upload` no DB (com 1º commit pra ganhar id), envia o blob
    para o MinIO e devolve o `Upload` já com `dados_adicionais.storage`.

    Equivalente ao antigo `Upload.registrar(...)` mas explicito sobre o
    uso do service.
    """
    from models.database import db
    from models.upload.entities import Upload

    inst = Upload(
        pai=pai,
        pai_id=pai_id,
        tipo=tipo,
        filename=filename,
        mimetype=mimetype,
        blob=blob,
        dados_adicionais=dados_adicionais,
    )
    db.session.add(inst)
    db.session.commit()
    enviar(inst, client=client, bucket=bucket, commit=True)
    return inst


# --------------------------------------------------------------------------
# Exclusão
# --------------------------------------------------------------------------

def _agrupar_storage_por_bucket(uploads: Iterable) -> dict[str, list[str]]:
    por_bucket: dict[str, list[str]] = {}
    for u in uploads:
        s = _storage(u)
        if not s:
            continue
        por_bucket.setdefault(s["bucket"], []).append(s["object_key"])
    return por_bucket


def excluir_lote(uploads: Iterable, *, client=None,
                 apagar_db: bool = False) -> Tuple[int, int]:
    """
    Remove em lote os objetos correspondentes no MinIO (batch por bucket).
    Quando `apagar_db=True`, também faz `db.session.delete(u)` para cada
    Upload (chamador é responsável pelo commit).

    Retorna (apagados_minio, falhas_minio).
    """
    from minio.deleteobjects import DeleteObject  # type: ignore

    uploads = list(uploads)
    por_bucket = _agrupar_storage_por_bucket(uploads)
    apagados = falhas = 0

    if por_bucket:
        client = client or _conectar_client()
        if client is None:
            falhas = sum(len(v) for v in por_bucket.values())
        else:
            for bucket, keys in por_bucket.items():
                try:
                    erros = list(
                        client.remove_objects(bucket, [DeleteObject(k) for k in keys])
                    )
                    for err in erros:
                        falhas += 1
                        logger.warning(
                            "MinIO falha bucket=%s key=%s: %s",
                            bucket, err.object_name, err.error_message,
                        )
                    apagados += max(0, len(keys) - falhas)
                except Exception:
                    logger.exception("MinIO bucket=%s falhou inteiro", bucket)
                    falhas += len(keys)

    if apagar_db and uploads:
        from models.database import db
        for u in uploads:
            db.session.delete(u)

    return apagados, falhas


def excluir(upload, *, client=None, apagar_db: bool = False) -> bool:
    apagados, falhas = excluir_lote([upload], client=client, apagar_db=apagar_db)
    return apagados > 0 and falhas == 0
