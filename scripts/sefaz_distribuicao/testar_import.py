#!/usr/bin/env python3
"""
Testa SOMENTE a parte de ingestão (sem chamar a SEFAZ).

Pega um arquivo XML (ou todos os XMLs de uma pasta) e os passa pelo
mesmo pipeline usado pelo orquestrador: `NotaFiscal(xml_data=xml_b64)`.

Útil para validar que o módulo conversa corretamente com o
`models.nota_fiscal.NotaFiscal` antes de arriscar uma chamada real ao
WS Distribuição DF-e.

Uso (na raiz do projeto, com venv ativo):

    # Um arquivo só
    python -m scripts.sefaz_distribuicao.testar_import --xml /caminho/nfe.xml

    # Pasta inteira (recursivo)
    python -m scripts.sefaz_distribuicao.testar_import --pasta /caminho/xmls

    # Sem persistir no banco (rollback ao final)
    python -m scripts.sefaz_distribuicao.testar_import --xml /caminho/nfe.xml --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Higieniza sys.path para evitar conflito com `scripts/email` x stdlib `email`.
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
sys.path = [
    p for p in sys.path
    if os.path.abspath(p) not in {_script_dir, os.path.dirname(_script_dir)}
]
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app  # noqa: E402

from scripts.sefaz_distribuicao.orquestrador import Resumo, _ingerir  # noqa: E402


def _coletar_xmls(xml_arg: str | None, pasta_arg: str | None) -> list[Path]:
    arquivos: list[Path] = []
    if xml_arg:
        p = Path(xml_arg)
        if not p.is_file():
            raise SystemExit(f"Arquivo não encontrado: {p}")
        arquivos.append(p)
    if pasta_arg:
        base = Path(pasta_arg)
        if not base.is_dir():
            raise SystemExit(f"Pasta não encontrada: {base}")
        arquivos.extend(sorted(base.rglob("*.xml")))
    if not arquivos:
        raise SystemExit("Informe --xml ou --pasta.")
    return arquivos


def _detectar_tipo_label(xml_str: str) -> str:
    """Heurística simples para classificar o XML antes de chamar NotaFiscal."""
    head = xml_str[:4000].lower()
    if "infcte" in head or "ctenorm" in head or "cteproc" in head:
        return "cte"
    if "compnfse" in head or "tclistanfse" in head or "listanfse" in head or "<nfse" in head:
        return "nfse"
    return "nfe"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", help="Caminho de um arquivo XML")
    parser.add_argument("--pasta", help="Pasta com XMLs (busca recursiva)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Faz rollback no final (não persiste).",
    )
    parser.add_argument(
        "--limite", type=int, default=0,
        help="Processa no máximo N arquivos (0 = todos).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    arquivos = _coletar_xmls(args.xml, args.pasta)
    if args.limite:
        arquivos = arquivos[: args.limite]

    print(f"Vou processar {len(arquivos)} arquivo(s){' em DRY-RUN' if args.dry_run else ''}.\n")

    resumo = Resumo()
    with app.app_context():
        from models.database import db  # import local para respeitar o sys.path

        for caminho in arquivos:
            try:
                xml_str = caminho.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:  # noqa: BLE001
                print(f"  [erro leitura] {caminho}: {exc}")
                resumo.erros.append(f"{caminho}: {exc}")
                continue

            tipo = _detectar_tipo_label(xml_str)
            print(f"  -> {caminho.name} (detectado: {tipo})")
            _ingerir(xml_str, chave_provavel=caminho.stem, resumo=resumo, tipo_label=tipo)

        if args.dry_run:
            db.session.rollback()
            print("\n[dry-run] db.session.rollback() executado — nada foi persistido.")
        else:
            db.session.commit()

    print("\n===== Resumo =====")
    print(f"NFe : importadas={resumo.nfe_importadas} existentes={resumo.nfe_ja_existentes} erros={resumo.nfe_erro}")
    print(f"CTe : importados={resumo.cte_importados} existentes={resumo.cte_ja_existentes} erros={resumo.cte_erro}")
    print(f"NFSe: importadas={resumo.nfse_importadas} existentes={resumo.nfse_ja_existentes} erros={resumo.nfse_erro}")
    if resumo.chaves_importadas:
        print("\nChaves importadas:")
        for c in resumo.chaves_importadas[:10]:
            print(f"  + {c}")
        if len(resumo.chaves_importadas) > 10:
            print(f"  ... e mais {len(resumo.chaves_importadas) - 10}")
    if resumo.erros:
        print("\nErros:")
        for msg in resumo.erros[:10]:
            print(f"  - {msg}")
        if len(resumo.erros) > 10:
            print(f"  ... e mais {len(resumo.erros) - 10}")
    return 0 if not resumo.erros else 2


if __name__ == "__main__":
    sys.exit(main())
