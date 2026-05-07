"""
Exemplo de uso do módulo download_xml.

Execução:
    python -m modulos.download_xml.exemplos.baixar_periodo \
        --pfx /caminho/empresa.pfx \
        --senha 'minhaSenha' \
        --cnpj 12345678000199 \
        --inicio 2026-04-01 \
        --fim    2026-04-30 \
        --uf 35
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from modulos.download_xml import baixar_xmls_periodo


def _parse_data(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Baixa XMLs de NFe, CTe e NFSe Nacional de um período"
    )
    parser.add_argument("--pfx", required=True, help="Arquivo .pfx/.p12")
    parser.add_argument("--senha", required=True, help="Senha do certificado")
    parser.add_argument("--cnpj", required=True, help="CNPJ (14 dígitos)")
    parser.add_argument("--inicio", type=_parse_data, required=True, help="YYYY-MM-DD")
    parser.add_argument("--fim", type=_parse_data, required=True, help="YYYY-MM-DD")
    parser.add_argument("--uf", type=int, default=35, help="Código IBGE da UF (35=SP)")
    parser.add_argument("--ambiente", type=int, default=1, help="1=prod, 2=homolog")
    parser.add_argument("--saida", default="./saida_xmls")
    parser.add_argument("--sem-nfse", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    pacote = baixar_xmls_periodo(
        caminho_pfx=args.pfx,
        senha_certificado=args.senha,
        cnpj=args.cnpj,
        data_inicial=args.inicio,
        data_final=args.fim,
        uf_autor=args.uf,
        ambiente=args.ambiente,
        diretorio_saida=args.saida,
        incluir_nfse=not args.sem_nfse,
    )

    print("\n===== Resumo =====")
    print(f"NFe emitidas    : {len(pacote.nfe_emitidas)}")
    print(f"NFe recebidas   : {len(pacote.nfe_recebidas)}")
    print(f"CTe emitidos    : {len(pacote.cte_emitidos)}")
    print(f"CTe recebidos   : {len(pacote.cte_recebidos)}")
    print(f"NFSe (ADN)      : {len(pacote.nfse)}")
    print(f"Salvo em        : {args.saida}")


if __name__ == "__main__":
    main()
