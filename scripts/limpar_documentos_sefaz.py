#!/usr/bin/env python3
"""
Limpa DocumentoSefaz, Uploads associados e os objetos correspondentes
no MinIO usando `models.upload.minio_service.excluir_lote`.

Ordem:
  1) coleta uploads em escopo (filhos + órfãos)
  2) `minio_service.excluir_lote(uploads, apagar_db=True)` — remove objetos
     no MinIO (batch por bucket) e marca uploads como deletados na sessão
  3) DELETE bulk em DocumentoSefaz
  4) commit

Uso:
    python scripts/limpar_documentos_sefaz.py --dry-run
    python scripts/limpar_documentos_sefaz.py
    python scripts/limpar_documentos_sefaz.py --tipo nfe
    python scripts/limpar_documentos_sefaz.py --sim
    python scripts/limpar_documentos_sefaz.py --sem-minio   # só DB
"""
from __future__ import annotations

import argparse
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
from models.upload import Upload, minio_service  # noqa: E402

logger = logging.getLogger(__name__)


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
        help="Limpa apenas um tipo (todos os subtipos: nfe/nfe_resumo/...).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Só mostra contagens; não toca em nada.",
    )
    parser.add_argument(
        "--sim", action="store_true",
        help="Não pede confirmação interativa.",
    )
    parser.add_argument(
        "--sem-minio", action="store_true",
        help="Pula a remoção dos objetos no MinIO (apaga só DB).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with app.app_context():
        # ----- escopo de DocumentoSefaz -----
        q_doc = DocumentoSefaz.query
        if args.tipo:
            q_doc = q_doc.filter(DocumentoSefaz.tipo.startswith(args.tipo))
        total_docs = q_doc.count()
        ids_docs = [r[0] for r in q_doc.with_entities(DocumentoSefaz.id).all()]

        # ----- uploads filhos (pai='DocumentoSefaz' apontando para esses ids) -----
        if ids_docs:
            uploads_filhos = Upload.query.filter(
                Upload.pai == "DocumentoSefaz",
                Upload.pai_id.in_(ids_docs),
            ).all()
        else:
            uploads_filhos = []

        # ----- uploads órfãos: pai='DocumentoSefaz' com pai_id sem doc.
        #       Só considerados quando o escopo é total (sem --tipo).
        if not args.tipo:
            uploads_orfaos = (
                Upload.query.filter(Upload.pai == "DocumentoSefaz")
                .filter(~Upload.pai_id.in_(db.session.query(DocumentoSefaz.id)))
                .all()
            )
        else:
            uploads_orfaos = []

        uploads_para_apagar = uploads_filhos + uploads_orfaos
        total_uploads = len(uploads_para_apagar)

        # contagem de objetos MinIO em escopo (apenas pra exibir)
        if args.sem_minio:
            total_minio = 0
        else:
            total_minio = sum(
                len(v) for v in minio_service._agrupar_storage_por_bucket(
                    uploads_para_apagar
                ).values()
            )

        print("=" * 60)
        print(f"Tipo filtrado     : {args.tipo or 'TODOS'}")
        print(f"DocumentoSefaz    : {total_docs} linhas")
        print(f"Upload filhos     : {len(uploads_filhos)} linhas")
        if not args.tipo:
            print(f"Upload órfãos     : {len(uploads_orfaos)} linhas")
        if args.sem_minio:
            print("MinIO             : SKIP (--sem-minio)")
        else:
            print(f"MinIO objetos     : {total_minio}")
        print(f"Modo              : {'DRY-RUN' if args.dry_run else 'APAGA'}")
        print("=" * 60)

        if total_docs == 0 and total_uploads == 0:
            print("Nada a apagar.")
            return 0

        if args.dry_run:
            return 0

        if not args.sim:
            if not _confirmar("Confirmar exclusão (DB + MinIO)? [s/N] "):
                print("Cancelado.")
                return 1

        # ----- 1) MinIO + marca uploads pra delete -----
        apagar_minio = not args.sem_minio
        apagados, falhas = minio_service.excluir_lote(
            uploads_para_apagar,
            apagar_db=True,
        ) if apagar_minio else (0, 0)

        # Quando --sem-minio, ainda precisamos remover os Uploads do DB.
        if not apagar_minio:
            for u in uploads_para_apagar:
                db.session.delete(u)

        # ----- 2) DocumentoSefaz (bulk) -----
        apagados_docs = q_doc.delete(synchronize_session=False)

        db.session.commit()

        print(
            f"DB: DocumentoSefaz={apagados_docs}, Upload={total_uploads}\n"
            f"MinIO: {apagados} apagados, {falhas} falhas."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
