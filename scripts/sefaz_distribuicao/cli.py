#!/usr/bin/env python3
"""
CLI standalone para baixar XMLs de NFe/CTe/NFSe e importá-los pelo
pipeline `models.nota_fiscal.NotaFiscal`.

Execução (na raiz do projeto, com venv ativo):

    python -m scripts.sefaz_distribuicao.cli \
        --pfx /etc/certs/empresa.pfx \
        --senha 'senhaA1' \
        --cnpj 12345678000199 \
        --inicio 2026-04-01 \
        --fim    2026-04-30 \
        --uf 35
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

# Higieniza sys.path antes de importar o app (mesmo motivo do
# scripts/atualizar_data_emissao_notas_xml.py: evitar que `scripts/email`
# sombre o módulo stdlib `email`).
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
sys.path = [p for p in sys.path if os.path.abspath(p) not in {_script_dir, os.path.dirname(_script_dir)}]
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app  # noqa: E402

from scripts.sefaz_distribuicao.orquestrador import baixar_e_importar  # noqa: E402


def _parse_data(s: str) -> date:
    return date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Baixa XMLs de NFe, CTe e NFSe Nacional de um período "
        "e importa-os pelo pipeline NotaFiscal do sfortanks."
    )
    parser.add_argument("--pfx", required=True, help="Arquivo .pfx/.p12")
    parser.add_argument("--senha", required=True, help="Senha do certificado")
    parser.add_argument("--cnpj", required=True, help="CNPJ (14 dígitos)")
    parser.add_argument("--inicio", type=_parse_data, required=True, help="YYYY-MM-DD")
    parser.add_argument("--fim", type=_parse_data, required=True, help="YYYY-MM-DD")
    parser.add_argument("--uf", type=int, default=35, help="Código IBGE da UF (35=SP)")
    parser.add_argument("--ambiente", type=int, default=1, help="1=prod, 2=homolog")
    parser.add_argument(
        "--sem-nfse",
        action="store_true",
        help="Pula a consulta ao ADN (use se o município não é aderente).",
    )
    parser.add_argument(
        "--nsu-inicial-nfe", default="0",
        help="NSU a partir do qual buscar NFes (default 0 = tudo).",
    )
    parser.add_argument(
        "--nsu-inicial-cte", default="0",
        help="NSU a partir do qual buscar CTes (default 0 = tudo).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Baixa da SEFAZ mas NÃO chama NotaFiscal() (não persiste no banco). "
             "Use para validar certificado, autenticação, período e endpoints.",
    )
    parser.add_argument(
        "--saida", default=None,
        help="Pasta para gravar os XMLs baixados em <pasta>/{nfe,cte,nfse}/<chave>.xml. "
             "Útil em --dry-run para inspecionar o que veio da SEFAZ.",
    )
    parser.add_argument(
        "--max", dest="max_documentos", type=int, default=0,
        help="Limita o número de documentos por tipo (NFe/CTe/NFSe). 0=ilimitado. "
             "Use 1 ou 2 para um smoke-test rápido.",
    )
    parser.add_argument(
        "--checkpoint-dir", default=None,
        help="Pasta para gravar o ultNSU por (CNPJ, tipo). "
             "Default: ~/.fortanks/sefaz_nsu/. Evita bloqueio cStat=656.",
    )
    parser.add_argument(
        "--reset-checkpoint", action="store_true",
        help="Apaga o checkpoint salvo e força nova consulta a partir de NSU=0.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Quando o usuário não passa --nsu-inicial-*, manda None para o
    # orquestrador ler do arquivo de checkpoint.
    nsu_nfe = args.nsu_inicial_nfe if args.nsu_inicial_nfe != "0" else None
    nsu_cte = args.nsu_inicial_cte if args.nsu_inicial_cte != "0" else None
    checkpoint_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else None

    with app.app_context():
        resumo = baixar_e_importar(
            caminho_pfx=args.pfx,
            senha_certificado=args.senha,
            cnpj=args.cnpj,
            data_inicial=args.inicio,
            data_final=args.fim,
            uf_autor=args.uf,
            ambiente=args.ambiente,
            incluir_nfse=not args.sem_nfse,
            nsu_inicial_nfe=nsu_nfe,
            nsu_inicial_cte=nsu_cte,
            dry_run=args.dry_run,
            pasta_saida=args.saida,
            max_documentos=args.max_documentos,
            checkpoint_dir=checkpoint_dir,
            resetar_checkpoint=args.reset_checkpoint,
        )

    print("\n===== Resumo =====")
    print(f"NFe : baixadas={resumo.nfe_baixadas} importadas={resumo.nfe_importadas} "
          f"existentes={resumo.nfe_ja_existentes} erros={resumo.nfe_erro}")
    print(f"CTe : baixados={resumo.cte_baixados} importados={resumo.cte_importados} "
          f"existentes={resumo.cte_ja_existentes} erros={resumo.cte_erro}")
    print(f"NFSe: baixadas={resumo.nfse_baixadas} importadas={resumo.nfse_importadas} "
          f"existentes={resumo.nfse_ja_existentes} erros={resumo.nfse_erro}")
    if resumo.erros:
        print("\nErros:")
        for msg in resumo.erros[:20]:
            print(f"  - {msg}")
        if len(resumo.erros) > 20:
            print(f"  ... e mais {len(resumo.erros) - 20}")
    return 0 if not resumo.erros else 2


if __name__ == "__main__":
    sys.exit(main())
