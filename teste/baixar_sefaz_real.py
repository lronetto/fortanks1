#!/usr/bin/env python3
"""
Teste REAL de busca + download na SEFAZ usando `models.sefaz_distribuicao`.

Conecta com o certificado A1 da empresa, chama os WS Distribuição DF-e
(NFe/CTe) e o ADN (NFSe), e SALVA os XMLs em `.tmp/sefaz/<timestamp>/`.
NÃO toca no banco — usa apenas o modelo `BuscadorXMLs`.

Configuração (em `.env` na raiz do projeto, ou via variáveis de ambiente):

    SEFAZ_PFX=C:/caminho/empresa.pfx
    SEFAZ_SENHA=senhaA1
    SEFAZ_CNPJ=12345678000199
    SEFAZ_UF=35              # opcional (default 35=SP)
    SEFAZ_AMBIENTE=1         # opcional (1=prod, 2=homolog; default 1)
    SEFAZ_DATA_INICIO=2026-04-01   # opcional
    SEFAZ_DATA_FIM=2026-04-30      # opcional
    SEFAZ_MAX=2              # opcional (limita docs por tipo; 0=ilimitado)
    SEFAZ_INCLUIR_NFSE=1     # opcional (default 1)

Execução (na raiz do projeto, com venv ativo):

    python teste/baixar_sefaz_real.py
    python teste/baixar_sefaz_real.py --max 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Higieniza sys.path antes de importar o app (mesmo motivo dos
# scripts/atualizar_data_emissao_notas_xml.py: scripts/email sombra
# o stdlib `email`).
_script_dir = Path(__file__).resolve().parent
_root = _script_dir.parent
sys.path = [p for p in sys.path if Path(p).resolve() != _script_dir]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_root / ".env")

from models.sefaz_distribuicao import (  # noqa: E402
    BuscadorXMLs,
    CertificadoA1,
    LoteDownload,
    XmlBaixado,
)


PASTA_SAIDA_RAIZ = _root / ".tmp" / "sefaz"
ARQUIVO_CURSOR = PASTA_SAIDA_RAIZ / "_cursor.json"


def _ler_cursor() -> tuple[str, str]:
    """Devolve (nsu_nfe, nsu_cte) lidos do arquivo de cursor, ou ('0','0')."""
    if not ARQUIVO_CURSOR.exists():
        return "0", "0"
    try:
        d = json.loads(ARQUIVO_CURSOR.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.warning("Cursor corrompido (%s); ignorando.", exc)
        return "0", "0"
    return (d.get("nfe") or "0", d.get("cte") or "0")


def _gravar_cursor(nsu_nfe: str, nsu_cte: str) -> None:
    """Grava o cursor em .tmp/sefaz/_cursor.json para reutilizar na próxima run."""
    ARQUIVO_CURSOR.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_CURSOR.write_text(
        json.dumps(
            {
                "nfe": nsu_nfe,
                "cte": nsu_cte,
                "atualizado_em": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _env(nome: str, default: str | None = None, *, obrigatorio: bool = False) -> str | None:
    valor = os.getenv(nome, default)
    if obrigatorio and not valor:
        raise SystemExit(
            f"Variável {nome} não definida. Defina em .env ou exporte no shell."
        )
    return valor


def _data(nome: str, default: date | None = None) -> date | None:
    raw = os.getenv(nome)
    if not raw:
        return default
    return date.fromisoformat(raw)


def _gravar(pasta: Path, xml: XmlBaixado) -> Path:
    sub = pasta / xml.tipo
    sub.mkdir(parents=True, exist_ok=True)
    nome_base = xml.nsu or "sem-nsu"
    if xml.chave:
        nome_base = f"{nome_base}_{xml.chave}"
    arquivo = sub / f"{nome_base}.xml"
    arquivo.write_text(xml.xml, encoding="utf-8")
    return arquivo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max", dest="max_documentos", type=int, default=None,
        help="Limita docs por tipo (sobrepõe SEFAZ_MAX).",
    )
    parser.add_argument(
        "--saida", default=None,
        help="Pasta de saída (default: .tmp/sefaz/<timestamp>/).",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Apaga o cursor salvo (.tmp/sefaz/_cursor.json) e recomeça de NSU=0.",
    )
    parser.add_argument(
        "--nsu-nfe", default=None,
        help="Sobrepõe o cursor de NFe para esta execução (ex.: 000000000000050).",
    )
    parser.add_argument(
        "--nsu-cte", default=None,
        help="Sobrepõe o cursor de CTe para esta execução.",
    )
    parser.add_argument(
        "--filtrar-data", action="store_true",
        help="Aplica filtro por SEFAZ_DATA_INICIO/SEFAZ_DATA_FIM. "
             "Por default NÃO filtra: o cursor de NSU já é o 'filtro' natural "
             "(documentos novos desde a última execução). "
             "Eventos como cancelamento/CCe não têm dhEmi e seriam descartados pelo filtro.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    pfx = _env("SEFAZ_PFX", obrigatorio=True)
    senha = _env("SEFAZ_SENHA", obrigatorio=True)
    cnpj = _env("SEFAZ_CNPJ", obrigatorio=True)
    uf = int(_env("SEFAZ_UF", "35"))
    ambiente = int(_env("SEFAZ_AMBIENTE", "1"))
    data_inicio = _data("SEFAZ_DATA_INICIO", date(date.today().year, date.today().month, 1))
    data_fim = _data("SEFAZ_DATA_FIM", date.today())
    max_documentos = (
        args.max_documentos
        if args.max_documentos is not None
        else int(_env("SEFAZ_MAX", "0") or 0)
    )
    incluir_nfse = (_env("SEFAZ_INCLUIR_NFSE", "1") or "1") not in {"0", "false", "False"}

    if args.saida:
        pasta_saida = Path(args.saida)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pasta_saida = PASTA_SAIDA_RAIZ / timestamp
    pasta_saida.mkdir(parents=True, exist_ok=True)

    if args.reset and ARQUIVO_CURSOR.exists():
        ARQUIVO_CURSOR.unlink()
        print("[reset] cursor anterior apagado.")

    nsu_nfe, nsu_cte = _ler_cursor()
    if args.nsu_nfe:
        nsu_nfe = args.nsu_nfe
    if args.nsu_cte:
        nsu_cte = args.nsu_cte

    primeira = nsu_nfe == "0" and nsu_cte == "0"

    print("=" * 60)
    print(f"CNPJ        : {cnpj}")
    print(f"UF          : {uf}")
    print(f"Ambiente    : {ambiente} ({'PRODUCAO' if ambiente == 1 else 'HOMOLOGACAO'})")
    print(f"Periodo NFSe: {data_inicio} a {data_fim}  (NFe/CTe usam cursor de NSU)")
    print(f"Filtro data : {'SIM (--filtrar-data)' if args.filtrar_data else 'NÃO (recomendado)'}")
    print(f"Max/tipo    : {max_documentos or 'ilimitado'}")
    print(f"Cursor NFe  : {nsu_nfe}{'  [primeira execucao]' if primeira else ''}")
    print(f"Cursor CTe  : {nsu_cte}")
    print(f"Saida       : {pasta_saida}")
    print(f"Cursor file : {ARQUIVO_CURSOR}")
    print("=" * 60)

    cert = CertificadoA1(caminho_pfx=pfx, senha=senha)
    bus = BuscadorXMLs(cert, cnpj=cnpj, uf_autor=uf, ambiente=ambiente)

    # NFSe (ADN) precisa de intervalo. NFe/CTe usam o NSU como cursor — o
    # filtro de data é opcional, e quando aplicado descarta também eventos
    # (cancelamento, CCe, manifestação) que não têm dhEmi.
    lote: LoteDownload = bus.buscar(
        ultimo_nsu_nfe=nsu_nfe,
        ultimo_nsu_cte=nsu_cte,
        data_inicial=data_inicio if args.filtrar_data else None,
        data_final=data_fim if args.filtrar_data else None,
        incluir_nfse=incluir_nfse,
        max_documentos=max_documentos,
    )

    # Breakdown por schema (útil pra entender o que veio: NFe, evento, resumo, ...).
    contagem_schemas: dict[str, int] = {}
    for xml in lote:
        contagem_schemas[xml.schema or "(sem schema)"] = (
            contagem_schemas.get(xml.schema or "(sem schema)", 0) + 1
        )

    arquivos_gravados: list[Path] = []
    for xml in lote:
        arquivos_gravados.append(_gravar(pasta_saida, xml))

    # Persiste o cursor para a próxima execução. Se buscar() levantou,
    # caímos fora antes daqui — o cursor velho continua valendo.
    novo_nfe = lote.ultimo_nsu_nfe or nsu_nfe
    novo_cte = lote.ultimo_nsu_cte or nsu_cte
    _gravar_cursor(novo_nfe, novo_cte)

    print("\n===== Resultado =====")
    print(f"Filtro de data : {'ON (--filtrar-data)' if args.filtrar_data else 'OFF (cursor de NSU)'}")
    print(f"NFe baixadas   : {len(lote.nfe)}")
    print(f"CTe baixados   : {len(lote.cte)}")
    print(f"NFSe baixadas  : {len(lote.nfse)}")
    print(f"Total no disco : {len(arquivos_gravados)} arquivo(s)")
    if contagem_schemas:
        print("\nSchemas recebidos:")
        for schema, qtd in sorted(contagem_schemas.items(), key=lambda x: -x[1]):
            print(f"  {qtd:>4} x {schema}")
    print(f"\nCursor salvo em {ARQUIVO_CURSOR.relative_to(_root)}:")
    print(f"  NFe ultNSU = {novo_nfe}  (maxNSU = {lote.max_nsu_nfe})")
    print(f"  CTe ultNSU = {novo_cte}  (maxNSU = {lote.max_nsu_cte})")
    if novo_nfe == lote.max_nsu_nfe and lote.max_nsu_nfe != "0":
        print("  [NFe em dia: ultNSU == maxNSU]")
    if novo_cte == lote.max_nsu_cte and lote.max_nsu_cte != "0":
        print("  [CTe em dia: ultNSU == maxNSU]")
    print(f"\nArquivos em: {pasta_saida}")
    if arquivos_gravados:
        print("Primeiros 5:")
        for arq in arquivos_gravados[:5]:
            print(f"  - {arq.relative_to(_root)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
