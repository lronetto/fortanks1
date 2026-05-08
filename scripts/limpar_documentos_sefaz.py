#!/usr/bin/env python3
"""
Limpa DocumentoSefaz, Uploads associados e os objetos correspondentes
no MinIO. Use após o fix do bug do `_enviar_blob_para_minio` para
descartar registros gravados parcialmente.

Ordem (dentro de uma única transação no DB):
  1) lê dados_adicionais.storage de cada Upload em escopo
  2) `client.remove_objects(bucket, [keys])` no MinIO
  3) DELETE Upload (do escopo + órfãos quando sem --tipo)
  4) DELETE DocumentoSefaz

Uso:
    python scripts/limpar_documentos_sefaz.py --dry-run
    python scripts/limpar_documentos_sefaz.py
    python scripts/limpar_documentos_sefaz.py --tipo nfe
    python scripts/limpar_documentos_sefaz.py --sim
    python scripts/limpar_documentos_sefaz.py --sem-minio   # só DB
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Higieniza sys.path antes de importar o app — evita que `scripts/email`
# sombre o módulo stdlib `email`.
_script_dir = Path(__file__).resolve().parent
_root = _script_dir.parent
sys.path = [p for p in sys.path if Path(p).resolve() != _script_dir]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import app  # noqa: E402

from models.database import db  # noqa: E402
from models.documento_sefaz import DocumentoSefaz  # noqa: E402
from models.upload import Upload  # noqa: E402

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# MinIO
# --------------------------------------------------------------------------

def _bool_env(nome: str, default: bool = False) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return default
    return valor.strip().lower() in {"1", "true", "yes", "y", "on"}


def _conectar_minio():
    """Devolve client MinIO conectado, ou None se não configurado/indisponível."""
    endpoint = (os.getenv("MINIO_ENDPOINT") or "").strip()
    access = (os.getenv("MINIO_ACCESS_KEY") or "").strip()
    secret = (os.getenv("MINIO_SECRET_KEY") or "").strip()
    secure = _bool_env("MINIO_SECURE", default=False)
    if not (endpoint and access and secret):
        logger.warning("MinIO não configurado (.env) — pulando remoção de objetos.")
        return None
    try:
        from minio import Minio
    except Exception:
        logger.warning("Pacote 'minio' não instalado — pulando remoção de objetos.")
        return None
    return Minio(endpoint=endpoint, access_key=access, secret_key=secret, secure=secure)


def _agrupar_storage_por_bucket(uploads_id_da: list[tuple[int, str | None]]) -> dict[str, list[str]]:
    """
    Lê dados_adicionais.storage e devolve {bucket: [object_key, ...]}.
    Aceita dados_adicionais como string JSON ou dict.
    """
    por_bucket: dict[str, list[str]] = {}
    for _id, da in uploads_id_da:
        if not da:
            continue
        try:
            dados = json.loads(da) if isinstance(da, str) else da
        except Exception:
            continue
        storage = (dados or {}).get("storage") if isinstance(dados, dict) else None
        if not isinstance(storage, dict):
            continue
        if storage.get("provider") != "minio":
            continue
        bucket = (storage.get("bucket") or "").strip()
        key = (storage.get("object_key") or "").strip()
        if bucket and key:
            por_bucket.setdefault(bucket, []).append(key)
    return por_bucket


def _remover_no_minio(client, por_bucket: dict[str, list[str]], dry_run: bool) -> tuple[int, int]:
    """Devolve (apagados, falhas)."""
    if not por_bucket:
        return 0, 0
    if dry_run:
        for bucket, keys in por_bucket.items():
            print(f"  [dry-run] MinIO remover {len(keys)} objeto(s) de '{bucket}'")
        return sum(len(v) for v in por_bucket.values()), 0
    if not client:
        # Configuração ausente; conta como "falha" mas não bloqueia o resto.
        total = sum(len(v) for v in por_bucket.values())
        return 0, total

    from minio.deleteobjects import DeleteObject

    apagados = 0
    falhas = 0
    for bucket, keys in por_bucket.items():
        objetos = [DeleteObject(k) for k in keys]
        try:
            erros = list(client.remove_objects(bucket, objetos))
            for err in erros:
                falhas += 1
                logger.warning(
                    "MinIO falha bucket=%s key=%s: %s",
                    bucket, err.object_name, err.error_message,
                )
            apagados += max(0, len(keys) - falhas)
        except Exception as exc:  # noqa: BLE001
            logger.error("MinIO bucket=%s falhou inteiro: %s", bucket, exc, exc_info=True)
            falhas += len(keys)
    return apagados, falhas


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _confirmar(prompt: str) -> bool:
    try:
        resp = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return resp in {"s", "sim", "y", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tipo", choices=["nfe", "cte", "nfse"], default=None,
        help="Limpa apenas um tipo de documento (default: todos os subtipos).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Só mostra contagens e o que seria apagado; não toca em nada.",
    )
    parser.add_argument(
        "--sim", action="store_true",
        help="Não pede confirmação interativa (use com cuidado).",
    )
    parser.add_argument(
        "--sem-minio", action="store_true",
        help="Pula a remoção dos objetos no MinIO (apaga só DB).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with app.app_context():
        # ----- monta queries (sem materializar ainda) -----
        q_doc = DocumentoSefaz.query
        if args.tipo:
            # Inclui subtipos: tipo_servico='nfe' bate em nfe, nfe_resumo, nfe_resEvento, nfe_procEvento.
            q_doc = q_doc.filter(DocumentoSefaz.tipo.startswith(args.tipo))
        total_docs = q_doc.count()

        ids_docs = [r[0] for r in q_doc.with_entities(DocumentoSefaz.id).all()]
        if ids_docs:
            q_uploads = Upload.query.filter(
                Upload.pai == "DocumentoSefaz",
                Upload.pai_id.in_(ids_docs),
            )
        else:
            q_uploads = Upload.query.filter(Upload.id == -1)
        total_uploads = q_uploads.count()

        # Órfãos: pai='DocumentoSefaz' mas pai_id sem doc correspondente.
        # Só considera quando NÃO se filtrou por tipo (escopo total).
        if not args.tipo:
            q_orfaos = (
                Upload.query.filter(Upload.pai == "DocumentoSefaz")
                .filter(~Upload.pai_id.in_(db.session.query(DocumentoSefaz.id)))
            )
            total_orfaos = q_orfaos.count()
        else:
            q_orfaos = None
            total_orfaos = 0

        # ----- coleta storage info de TODOS os uploads em escopo -----
        uploads_id_da: list[tuple[int, str | None]] = []
        if total_uploads:
            uploads_id_da.extend(
                q_uploads.with_entities(Upload.id, Upload.dados_adicionais).all()
            )
        if total_orfaos and q_orfaos is not None:
            uploads_id_da.extend(
                q_orfaos.with_entities(Upload.id, Upload.dados_adicionais).all()
            )
        por_bucket = _agrupar_storage_por_bucket(uploads_id_da) if not args.sem_minio else {}
        total_objetos_minio = sum(len(v) for v in por_bucket.values())

        print("=" * 60)
        print(f"Tipo filtrado     : {args.tipo or 'TODOS'}")
        print(f"DocumentoSefaz    : {total_docs} linhas")
        print(f"Upload (escopo)   : {total_uploads} linhas")
        if not args.tipo:
            print(f"Upload órfãos     : {total_orfaos} linhas")
        if args.sem_minio:
            print(f"MinIO             : SKIP (--sem-minio)")
        else:
            print(f"MinIO objetos     : {total_objetos_minio} (em {len(por_bucket)} bucket(s))")
        print(f"Modo              : {'DRY-RUN' if args.dry_run else 'APAGA'}")
        print("=" * 60)

        if total_docs == 0 and total_uploads == 0 and total_orfaos == 0:
            print("Nada a apagar.")
            return 0

        if args.dry_run:
            # Ainda mostra o que seria removido do MinIO.
            if not args.sem_minio:
                _remover_no_minio(None, por_bucket, dry_run=True)
            return 0

        if not args.sim:
            if not _confirmar("Confirmar exclusão (DB + MinIO)? [s/N] "):
                print("Cancelado.")
                return 1

        # ----- 1) MinIO primeiro (se DB falhar depois, ainda dá pra reuploadar). -----
        apagados_minio = falhas_minio = 0
        if not args.sem_minio and por_bucket:
            client = _conectar_minio()
            apagados_minio, falhas_minio = _remover_no_minio(client, por_bucket, dry_run=False)
            print(f"MinIO: {apagados_minio} apagados, {falhas_minio} falhas.")

        # ----- 2) DB (bulk) -----
        apagados_uploads = q_uploads.delete(synchronize_session=False)
        apagados_orfaos = (
            q_orfaos.delete(synchronize_session=False) if q_orfaos is not None else 0
        )
        apagados_docs = q_doc.delete(synchronize_session=False)
        db.session.commit()

        print(
            f"DB: DocumentoSefaz={apagados_docs}, "
            f"Upload={apagados_uploads + apagados_orfaos}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
