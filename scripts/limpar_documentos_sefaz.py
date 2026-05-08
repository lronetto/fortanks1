#!/usr/bin/env python3
"""
Limpa DocumentoSefaz e Uploads associados (caso o teste tenha gravado
linhas com o bug do MinIO antigo, antes da correção do `_enviar_blob_para_minio`).

DELETE em duas etapas:
  1) Upload  WHERE pai = 'DocumentoSefaz'
  2) DocumentoSefaz  (limpa tudo, ou filtra por --tipo nfe|cte|nfse)

Após rodar, basta executar `processar_sefaz` de novo: o cursor de NSU
volta a sair de MAX(NSU) (ou do seed em .env quando a tabela estiver
vazia).

Uso (na raiz do projeto, com venv ativo):

    # Ver o que seria apagado, sem apagar:
    python scripts/limpar_documentos_sefaz.py --dry-run

    # Apagar de fato (pede confirmação interativa):
    python scripts/limpar_documentos_sefaz.py

    # Só de um tipo:
    python scripts/limpar_documentos_sefaz.py --tipo nfe

    # Sem perguntar (cuidado):
    python scripts/limpar_documentos_sefaz.py --sim
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
from models.upload import Upload  # noqa: E402


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
        help="Limpa apenas um tipo de documento (default: todos).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Só mostra contagens; não apaga nada.",
    )
    parser.add_argument(
        "--sim", action="store_true",
        help="Não pede confirmação interativa (use com cuidado).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with app.app_context():
        q_doc = DocumentoSefaz.query
        if args.tipo:
            q_doc = q_doc.filter(DocumentoSefaz.tipo == args.tipo)
        total_docs = q_doc.count()

        # Uploads filhos: pai='DocumentoSefaz' e pai_id em (ids dos docs filtrados).
        ids_docs = [r.id for r in q_doc.with_entities(DocumentoSefaz.id).all()]
        if ids_docs:
            q_uploads = Upload.query.filter(
                Upload.pai == "DocumentoSefaz",
                Upload.pai_id.in_(ids_docs),
            )
        else:
            q_uploads = Upload.query.filter(Upload.id == -1)  # nada
        total_uploads = q_uploads.count()

        # Uploads órfãos com pai='DocumentoSefaz' mas pai_id apontando para doc inexistente.
        # (apaga só quando for --tipo None e --dry-run estiver desligado para evitar deletar fora do escopo.)
        q_orfaos = (
            Upload.query.filter(Upload.pai == "DocumentoSefaz")
            .filter(~Upload.pai_id.in_(db.session.query(DocumentoSefaz.id)))
        )
        total_orfaos = q_orfaos.count() if not args.tipo else 0

        print("=" * 60)
        print(f"Tipo filtrado     : {args.tipo or 'TODOS'}")
        print(f"DocumentoSefaz    : {total_docs} linhas")
        print(f"Upload (do escopo): {total_uploads} linhas")
        if not args.tipo:
            print(f"Upload órfãos     : {total_orfaos} linhas (pai_id sem DocumentoSefaz)")
        print(f"Modo              : {'DRY-RUN (não apaga)' if args.dry_run else 'APAGA'}")
        print("=" * 60)

        if total_docs == 0 and total_uploads == 0 and total_orfaos == 0:
            print("Nada a apagar.")
            return 0

        if args.dry_run:
            return 0

        if not args.sim:
            if not _confirmar("Confirmar exclusão? [s/N] "):
                print("Cancelado.")
                return 1

        # Ordem: 1) uploads do escopo, 2) órfãos (se não filtrou tipo), 3) docs.
        apagados_uploads = q_uploads.delete(synchronize_session=False)
        apagados_orfaos = q_orfaos.delete(synchronize_session=False) if not args.tipo else 0
        apagados_docs = q_doc.delete(synchronize_session=False)
        db.session.commit()

        print(
            f"Apagados: DocumentoSefaz={apagados_docs}, "
            f"Upload={apagados_uploads + apagados_orfaos}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
