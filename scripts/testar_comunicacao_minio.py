#!/usr/bin/env python3
"""
Teste de comunicacao com MinIO.

Valida:
1) Conexao/autenticacao
2) Acesso ao bucket (e criacao opcional)
3) Upload e download de objeto de teste
4) Remocao opcional do objeto de teste

Uso:
  python scripts/testar_comunicacao_minio.py --bucket uploads
  python scripts/testar_comunicacao_minio.py --bucket uploads --criar-bucket
  python scripts/testar_comunicacao_minio.py --bucket uploads --manter-objeto

Variaveis de ambiente:
  MINIO_ENDPOINT   (obrigatoria)
  MINIO_ACCESS_KEY (obrigatoria)
  MINIO_SECRET_KEY (obrigatoria)
  MINIO_SECURE     (opcional: true/false, default false)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from io import BytesIO

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


def _bool_env(nome: str, default: bool = False) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return default
    return valor.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Testa comunicacao com MinIO.")
    parser.add_argument("--bucket", required=True, help="Bucket de teste.")
    parser.add_argument(
        "--criar-bucket",
        action="store_true",
        help="Cria o bucket caso nao exista.",
    )
    parser.add_argument(
        "--manter-objeto",
        action="store_true",
        help="Nao remove o objeto de teste ao final.",
    )
    args = parser.parse_args()

    endpoint = (os.getenv("MINIO_ENDPOINT") or "").strip()
    access_key = (os.getenv("MINIO_ACCESS_KEY") or "").strip()
    secret_key = (os.getenv("MINIO_SECRET_KEY") or "").strip()
    secure = _bool_env("MINIO_SECURE", default=False)

    if not endpoint or not access_key or not secret_key:
        print("ERRO: Defina MINIO_ENDPOINT, MINIO_ACCESS_KEY e MINIO_SECRET_KEY.")
        return 2

    try:
        from minio import Minio
    except ImportError:
        print("ERRO: pacote `minio` nao instalado. Execute `uv sync`.")
        return 2

    print(f"Conectando em: {endpoint} (secure={secure})")
    client = Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )

    try:
        existe_bucket = client.bucket_exists(args.bucket)
    except Exception as exc:
        print(f"ERRO: Falha ao consultar bucket: {exc}")
        return 1

    if not existe_bucket:
        if not args.criar_bucket:
            print(
                f"ERRO: bucket `{args.bucket}` nao existe. "
                "Use --criar-bucket para criar automaticamente."
            )
            return 1
        try:
            client.make_bucket(args.bucket)
            print(f"Bucket criado: {args.bucket}")
        except Exception as exc:
            print(f"ERRO: Falha ao criar bucket `{args.bucket}`: {exc}")
            return 1
    else:
        print(f"Bucket OK: {args.bucket}")

    instante = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    object_name = f"healthcheck/minio_teste_{instante}.txt"
    payload = f"teste-minio:{instante}\n".encode("utf-8")
    hash_esperado = hashlib.sha256(payload).hexdigest()

    # Upload de teste
    try:
        resultado = client.put_object(
            bucket_name=args.bucket,
            object_name=object_name,
            data=BytesIO(payload),
            length=len(payload),
            content_type="text/plain; charset=utf-8",
        )
        print(f"Upload OK: {object_name} (etag={resultado.etag})")
    except Exception as exc:
        print(f"ERRO: Falha no upload de teste: {exc}")
        return 1

    # Download de teste + validacao de integridade
    response = None
    try:
        response = client.get_object(args.bucket, object_name)
        conteudo = response.read()
        hash_recebido = hashlib.sha256(conteudo).hexdigest()
        if hash_recebido != hash_esperado:
            print(
                "ERRO: hash do arquivo baixado difere do enviado "
                f"(esperado={hash_esperado}, recebido={hash_recebido})."
            )
            return 1
        print("Download OK e integridade validada.")
    except Exception as exc:
        print(f"ERRO: Falha no download de teste: {exc}")
        return 1
    finally:
        if response is not None:
            response.close()
            response.release_conn()

    # Limpeza
    if args.manter_objeto:
        print(f"Objeto mantido para inspecao: {object_name}")
    else:
        try:
            client.remove_object(args.bucket, object_name)
            print(f"Limpeza OK: {object_name} removido.")
        except Exception as exc:
            print(f"ALERTA: Falha ao remover objeto de teste: {exc}")
            return 1

    print("SUCESSO: comunicacao com MinIO validada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
