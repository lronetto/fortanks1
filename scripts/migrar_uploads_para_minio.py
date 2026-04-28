#!/usr/bin/env python3
"""
Migra blobs da tabela Uploads para bucket MinIO com checkpoint.

Uso basico:
  python scripts/migrar_uploads_para_minio.py --bucket uploads
  python scripts/migrar_uploads_para_minio.py --bucket uploads --dry-run
  python scripts/migrar_uploads_para_minio.py --bucket uploads --clear-blob

Variaveis de ambiente esperadas:
  MINIO_ENDPOINT
  MINIO_ACCESS_KEY
  MINIO_SECRET_KEY
  MINIO_SECURE (opcional: true/false, default false)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

_RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))


def _paths_iguais(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


if sys.path and _paths_iguais(sys.path[0], _DIR_SCRIPT):
    sys.path.pop(0)
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)
load_dotenv(os.path.join(_RAIZ, ".env"))

from app import app
from models.database import db
from models.upload import Upload


def _bool_env(nome: str, default: bool = False) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return default
    return valor.strip().lower() in {"1", "true", "yes", "y", "on"}


def _sanitizar_componente(chave: str) -> str:
    texto = str(chave or "").strip().lower()
    texto = re.sub(r"[^a-z0-9_.-]+", "-", texto)
    return texto.strip("-") or "sem-valor"


def _sanitizar_nome_arquivo(nome: str) -> str:
    base = os.path.basename(nome or "arquivo.bin")
    base = re.sub(r"[^a-zA-Z0-9_.-]+", "_", base)
    return base or "arquivo.bin"


def _parse_dados_adicionais(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        valor = json.loads(raw)
        if isinstance(valor, dict):
            return valor
    except Exception:
        return {"_raw": raw}
    return {}


def _decode_blob(blob_b64: str | None) -> bytes | None:
    if not blob_b64:
        return None
    try:
        return base64.b64decode(blob_b64, validate=True)
    except Exception:
        # Fallback para blobs historicos sem padding estrito.
        try:
            return base64.b64decode(blob_b64)
        except Exception:
            return None


def _carregar_checkpoint(caminho: str) -> int:
    if not os.path.exists(caminho):
        return 0
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return int(payload.get("last_id", 0))
    except Exception:
        return 0


def _salvar_checkpoint(caminho: str, last_id: int) -> None:
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    payload = {
        "last_id": int(last_id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _object_key(upload: Upload) -> str:
    pai = _sanitizar_componente(upload.pai or "sem-pai")
    pai_id = _sanitizar_componente(upload.pai_id or "sem-pai-id")
    filename = _sanitizar_nome_arquivo(upload.filename)
    return f"uploads/{pai}/{pai_id}/{upload.id}_{filename}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra Uploads.blob para MinIO.")
    parser.add_argument("--bucket", required=True, help="Bucket de destino no MinIO.")
    parser.add_argument("--batch-size", type=int, default=200, help="Quantidade por lote.")
    parser.add_argument("--start-id", type=int, default=0, help="ID inicial (exclusivo).")
    parser.add_argument("--max-registros", type=int, default=0, help="Limita quantidade total.")
    parser.add_argument(
        "--checkpoint-file",
        default=".tmp/minio_upload_migration_checkpoint.json",
        help="Arquivo com ultimo id processado.",
    )
    parser.add_argument("--ignore-checkpoint", action="store_true", help="Ignora checkpoint salvo.")
    parser.add_argument("--dry-run", action="store_true", help="Nao envia para MinIO nem salva no banco.")
    parser.add_argument("--clear-blob", action="store_true", help="Limpa coluna blob apos upload.")
    args = parser.parse_args()

    minio_endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
    minio_secure = _bool_env("MINIO_SECURE", default=False)

    if not args.dry_run:
        if not minio_endpoint or not minio_access_key or not minio_secret_key:
            print("MINIO_ENDPOINT, MINIO_ACCESS_KEY e MINIO_SECRET_KEY sao obrigatorios.")
            return 2
        try:
            from minio import Minio
            from minio.error import S3Error
        except ImportError:
            print("Dependencia ausente: instale com `uv sync` para incluir o pacote minio.")
            return 2
    else:
        Minio = None
        S3Error = Exception

    last_id = args.start_id
    if not args.ignore_checkpoint:
        last_id = max(last_id, _carregar_checkpoint(args.checkpoint_file))

    enviados = 0
    pulados = 0
    erros = 0
    processados = 0

    with app.app_context():
        client = None
        if not args.dry_run:
            client = Minio(
                endpoint=minio_endpoint,
                access_key=minio_access_key,
                secret_key=minio_secret_key,
                secure=minio_secure,
            )
            if not client.bucket_exists(args.bucket):
                client.make_bucket(args.bucket)

        while True:
            query = (
                Upload.query.filter(Upload.id > last_id)
                .order_by(Upload.id.asc())
                .limit(args.batch_size)
            )
            lote = query.all()
            if not lote:
                break

            for upload in lote:
                processados += 1
                last_id = upload.id
                if args.max_registros and processados > args.max_registros:
                    break

                if not upload.blob:
                    pulados += 1
                    _salvar_checkpoint(args.checkpoint_file, last_id)
                    continue

                dados_bytes = _decode_blob(upload.blob)
                if dados_bytes is None:
                    print(f"[ERRO] Upload id={upload.id}: blob invalido para base64.")
                    erros += 1
                    _salvar_checkpoint(args.checkpoint_file, last_id)
                    continue

                object_key = _object_key(upload)
                sha256 = hashlib.sha256(dados_bytes).hexdigest()
                tamanho = len(dados_bytes)
                metadados = _parse_dados_adicionais(upload.dados_adicionais)
                storage_atual = metadados.get("storage", {})

                # Evita reprocessar registro ja marcado como migrado para MinIO.
                if isinstance(storage_atual, dict) and storage_atual.get("provider") == "minio":
                    pulados += 1
                    _salvar_checkpoint(args.checkpoint_file, last_id)
                    continue

                etag = None
                if not args.dry_run:
                    try:
                        resultado = client.put_object(
                            bucket_name=args.bucket,
                            object_name=object_key,
                            data=io.BytesIO(dados_bytes),
                            length=tamanho,
                            content_type=upload.mimetype or "application/octet-stream",
                        )
                        etag = resultado.etag
                    except S3Error as exc:
                        print(f"[ERRO] Upload id={upload.id}: falha ao enviar para MinIO ({exc}).")
                        erros += 1
                        _salvar_checkpoint(args.checkpoint_file, last_id)
                        continue

                metadados["storage"] = {
                    "provider": "minio",
                    "bucket": args.bucket,
                    "object_key": object_key,
                    "etag": etag,
                    "size": tamanho,
                    "sha256": sha256,
                    "migrado_em": datetime.now(timezone.utc).isoformat(),
                }

                if not args.dry_run:
                    upload.dados_adicionais = json.dumps(metadados, ensure_ascii=False)
                    if args.clear_blob:
                        upload.blob = None
                    enviados += 1
                else:
                    enviados += 1

                _salvar_checkpoint(args.checkpoint_file, last_id)

            if not args.dry_run:
                try:
                    db.session.commit()
                except Exception as exc:
                    db.session.rollback()
                    print(f"[ERRO] Falha no commit do lote: {exc}")
                    return 1

            if args.max_registros and processados > args.max_registros:
                break

    print("----- Resumo migracao uploads -> MinIO -----")
    print(f"ultimo_id_processado: {last_id}")
    print(f"enviados: {enviados}")
    print(f"pulados: {pulados}")
    print(f"erros: {erros}")
    print(f"dry_run: {args.dry_run}")
    print(f"clear_blob: {args.clear_blob}")
    print(f"checkpoint: {args.checkpoint_file}")
    return 0 if erros == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
