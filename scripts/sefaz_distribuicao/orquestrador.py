"""
Orquestra as três consultas (NFe, CTe, NFSe Nacional) e ingere cada
XML pelo pipeline existente do sfortanks (`models.nota_fiscal.NotaFiscal`).

Uso típico (dentro de uma rota Flask, já com app/db context ativos):

    from scripts.sefaz_distribuicao import baixar_e_importar
    from datetime import date

    resumo = baixar_e_importar(
        caminho_pfx="/etc/certs/empresa.pfx",
        senha_certificado="senhaA1",
        cnpj="12345678000199",
        data_inicial=date(2026, 4, 1),
        data_final=date(2026, 4, 30),
        uf_autor=35,
    )

Uso em script standalone (ver `cli.py`): cria-se primeiro o app Flask
para que `db.session` funcione fora do request.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from . import cte_distribuicao, nfe_distribuicao, nfse_nacional
from .cert_utils import CertificadoA1
from .nfe_distribuicao import DocumentoXML, filtrar_por_data

log = logging.getLogger(__name__)


@dataclass
class Resumo:
    """Estatísticas e listas de chaves processadas em uma execução."""

    nfe_baixadas: int = 0
    nfe_importadas: int = 0
    nfe_ja_existentes: int = 0
    nfe_erro: int = 0

    cte_baixados: int = 0
    cte_importados: int = 0
    cte_ja_existentes: int = 0
    cte_erro: int = 0

    nfse_baixadas: int = 0
    nfse_importadas: int = 0
    nfse_ja_existentes: int = 0
    nfse_erro: int = 0

    chaves_importadas: List[str] = field(default_factory=list)
    chaves_existentes: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)

    @property
    def total_baixadas(self) -> int:
        return self.nfe_baixadas + self.cte_baixados + self.nfse_baixadas

    @property
    def total_importadas(self) -> int:
        return self.nfe_importadas + self.cte_importados + self.nfse_importadas


def _xml_para_base64(xml: str) -> str:
    """O construtor de NotaFiscal espera xml_data em base64 (UTF-8)."""
    return base64.b64encode(xml.encode("utf-8")).decode("ascii")


def _ingerir(xml: str, chave_provavel: Optional[str], resumo: Resumo, tipo_label: str) -> None:
    """
    Importa um XML pelo pipeline existente: `NotaFiscal(xml_data=xml_b64)`.

    O construtor faz: detecta tipo, parseia, persiste no banco e popula `id`.
    Se a chave já existir, ele apenas referencia o registro existente.
    """
    # Import local para não exigir contexto Flask quando alguém só usa
    # os clientes nfe_distribuicao/cte_distribuicao isoladamente.
    from models.nota_fiscal import NotaFiscal

    chave_log = chave_provavel or "(sem chave)"
    try:
        nf = NotaFiscal(xml_data=_xml_para_base64(xml))
    except Exception as exc:  # noqa: BLE001
        log.error("Falha ao importar %s %s: %s", tipo_label, chave_log, exc, exc_info=True)
        resumo.erros.append(f"{tipo_label} {chave_log}: {exc}")
        if tipo_label == "nfe":
            resumo.nfe_erro += 1
        elif tipo_label == "cte":
            resumo.cte_erro += 1
        else:
            resumo.nfse_erro += 1
        return

    chave_real = getattr(nf, "chave_acesso", None) or chave_log
    ja_existia = bool(getattr(nf, "logs", {}).get("existente"))
    foi_inserida = bool(getattr(nf, "logs", {}).get("inserido"))

    if ja_existia and not foi_inserida:
        resumo.chaves_existentes.append(chave_real)
        if tipo_label == "nfe":
            resumo.nfe_ja_existentes += 1
        elif tipo_label == "cte":
            resumo.cte_ja_existentes += 1
        else:
            resumo.nfse_ja_existentes += 1
    elif getattr(nf, "id", None):
        resumo.chaves_importadas.append(chave_real)
        if tipo_label == "nfe":
            resumo.nfe_importadas += 1
        elif tipo_label == "cte":
            resumo.cte_importados += 1
        else:
            resumo.nfse_importadas += 1
    else:
        resumo.erros.append(f"{tipo_label} {chave_log}: NotaFiscal não persistiu (sem id)")
        if tipo_label == "nfe":
            resumo.nfe_erro += 1
        elif tipo_label == "cte":
            resumo.cte_erro += 1
        else:
            resumo.nfse_erro += 1


def baixar_e_importar(
    caminho_pfx: str,
    senha_certificado: str,
    cnpj: str,
    data_inicial: date,
    data_final: date,
    *,
    uf_autor: int = 35,
    ambiente: int = 1,
    incluir_nfse: bool = True,
    nsu_inicial_nfe: str = "0",
    nsu_inicial_cte: str = "0",
) -> Resumo:
    """
    Baixa NFe + CTe (Distribuição DF-e) + NFSe Nacional (ADN) do CNPJ
    no período, e importa cada XML pelo pipeline `NotaFiscal(xml_data=...)`.

    PRÉ-REQUISITO: deve ser chamada dentro de um Flask `app_context()`,
    para que `db.session` esteja disponível.
    """
    cert = CertificadoA1(caminho_pfx=caminho_pfx, senha=senha_certificado)
    cnpj = "".join(filter(str.isdigit, cnpj)).zfill(14)
    resumo = Resumo()

    # --- NFe -----------------------------------------------------------
    log.info("=== NFeDistribuicaoDFe (CNPJ %s) ===", cnpj)
    todas_nfe: List[DocumentoXML] = []
    for pagina in nfe_distribuicao.consultar(
        cert, cnpj, uf_autor=uf_autor, ambiente=ambiente, nsu_inicial=nsu_inicial_nfe
    ):
        todas_nfe.extend(pagina.documentos)
    nfe_no_periodo = filtrar_por_data(todas_nfe, data_inicial, data_final)
    resumo.nfe_baixadas = len(nfe_no_periodo)
    log.info("NFe: %d documentos no período (de %d totais).", len(nfe_no_periodo), len(todas_nfe))
    for doc in nfe_no_periodo:
        _ingerir(doc.xml, doc.chave, resumo, tipo_label="nfe")

    # --- CTe -----------------------------------------------------------
    log.info("=== CTeDistribuicaoDFe (CNPJ %s) ===", cnpj)
    todas_cte: List[DocumentoXML] = []
    for pagina in cte_distribuicao.consultar(
        cert, cnpj, uf_autor=uf_autor, ambiente=ambiente, nsu_inicial=nsu_inicial_cte
    ):
        todas_cte.extend(pagina.documentos)
    cte_no_periodo = filtrar_por_data(todas_cte, data_inicial, data_final)
    resumo.cte_baixados = len(cte_no_periodo)
    log.info("CTe: %d documentos no período (de %d totais).", len(cte_no_periodo), len(todas_cte))
    for doc in cte_no_periodo:
        _ingerir(doc.xml, doc.chave, resumo, tipo_label="cte")

    # --- NFSe Nacional -------------------------------------------------
    if incluir_nfse:
        log.info("=== ADN NFSe Nacional (CNPJ %s) ===", cnpj)
        try:
            nfses = nfse_nacional.baixar_periodo(
                cert, cnpj, data_inicial, data_final, ambiente=ambiente
            )
            resumo.nfse_baixadas = len(nfses)
            log.info("NFSe: %d documentos no período.", len(nfses))
            for n in nfses:
                _ingerir(n.xml, n.chave_acesso, resumo, tipo_label="nfse")
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "ADN indisponível ou município não aderente ao Sistema Nacional "
                "NFS-e (CNPJ %s): %s",
                cnpj,
                exc,
            )
            resumo.erros.append(f"NFSe ADN: {exc}")

    log.info(
        "Resumo: baixadas=%d importadas=%d existentes=%d erros=%d",
        resumo.total_baixadas,
        resumo.total_importadas,
        len(resumo.chaves_existentes),
        len(resumo.erros),
    )
    return resumo
