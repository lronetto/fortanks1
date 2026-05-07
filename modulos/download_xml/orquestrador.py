"""
Orquestra as três consultas (NFe, CTe, NFSe) e devolve um único pacote
de resultados, gravando cada XML em disco organizado por:

    saida/
      nfe/emitidas/<chave>.xml
      nfe/recebidas/<chave>.xml
      cte/emitidos/<chave>.xml
      cte/recebidos/<chave>.xml
      nfse/prestador/<chave>.xml
      nfse/tomador/<chave>.xml
      nfse/intermediario/<chave>.xml
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import List

from . import cte_distribuicao, nfe_distribuicao, nfse_nacional
from .cert_utils import CertificadoA1
from .nfe_distribuicao import DocumentoXML, filtrar_por_data

log = logging.getLogger(__name__)


@dataclass
class Pacote:
    nfe_emitidas: List[DocumentoXML] = field(default_factory=list)
    nfe_recebidas: List[DocumentoXML] = field(default_factory=list)
    cte_emitidos: List[DocumentoXML] = field(default_factory=list)
    cte_recebidos: List[DocumentoXML] = field(default_factory=list)
    nfse: List[nfse_nacional.NFSe] = field(default_factory=list)


def _separar_emitidas(
    docs: List[DocumentoXML], cnpj_alvo: str
) -> tuple[List[DocumentoXML], List[DocumentoXML]]:
    emitidas, recebidas = [], []
    for d in docs:
        if d.cnpj_emitente and d.cnpj_emitente.zfill(14) == cnpj_alvo.zfill(14):
            emitidas.append(d)
        else:
            recebidas.append(d)
    return emitidas, recebidas


def _gravar(diretorio: str, nome: str, conteudo: str) -> None:
    os.makedirs(diretorio, exist_ok=True)
    caminho = os.path.join(diretorio, nome)
    with open(caminho, "w", encoding="utf-8") as fp:
        fp.write(conteudo)


def baixar_xmls_periodo(
    caminho_pfx: str,
    senha_certificado: str,
    cnpj: str,
    data_inicial: date,
    data_final: date,
    *,
    uf_autor: int = 35,
    ambiente: int = 1,
    diretorio_saida: str = "./saida_xmls",
    incluir_nfse: bool = True,
) -> Pacote:
    """
    Faz o download dos XMLs de NFe, CTe e (opcionalmente) NFSe Nacional,
    para o CNPJ informado, no intervalo de datas.

    Args:
        caminho_pfx: caminho do arquivo .pfx ou .p12.
        senha_certificado: senha de acesso ao PFX.
        cnpj: 14 dígitos somente números.
        data_inicial / data_final: intervalo INCLUSIVO de emissão.
        uf_autor: código IBGE da UF (35=SP, 33=RJ, 31=MG, 41=PR, ...).
        ambiente: 1 = produção, 2 = homologação.
        diretorio_saida: pasta raiz onde os XMLs serão salvos.
        incluir_nfse: se True, tenta consultar o ADN (só funciona para
            municípios aderentes ao Sistema Nacional NFS-e).
    """
    cert = CertificadoA1(caminho_pfx=caminho_pfx, senha=senha_certificado)
    cnpj = "".join(filter(str.isdigit, cnpj)).zfill(14)
    pacote = Pacote()

    # --- NFe -----------------------------------------------------------
    log.info("===> NFe Distribuição DFe")
    todas_nfe: List[DocumentoXML] = []
    for pagina in nfe_distribuicao.consultar(
        cert, cnpj, uf_autor=uf_autor, ambiente=ambiente
    ):
        todas_nfe.extend(pagina.documentos)
    todas_nfe = filtrar_por_data(todas_nfe, data_inicial, data_final)
    emitidas, recebidas = _separar_emitidas(todas_nfe, cnpj)
    pacote.nfe_emitidas = emitidas
    pacote.nfe_recebidas = recebidas
    log.info("NFe: %d emitidas / %d recebidas", len(emitidas), len(recebidas))

    # --- CTe -----------------------------------------------------------
    log.info("===> CTe Distribuição DFe")
    todas_cte: List[DocumentoXML] = []
    for pagina in cte_distribuicao.consultar(
        cert, cnpj, uf_autor=uf_autor, ambiente=ambiente
    ):
        todas_cte.extend(pagina.documentos)
    todas_cte = filtrar_por_data(todas_cte, data_inicial, data_final)
    cte_emit, cte_receb = _separar_emitidas(todas_cte, cnpj)
    pacote.cte_emitidos = cte_emit
    pacote.cte_recebidos = cte_receb
    log.info("CTe: %d emitidos / %d recebidos", len(cte_emit), len(cte_receb))

    # --- NFSe Nacional -------------------------------------------------
    if incluir_nfse:
        log.info("===> NFSe Nacional (ADN)")
        try:
            pacote.nfse = nfse_nacional.baixar_periodo(
                cert, cnpj, data_inicial, data_final, ambiente=ambiente
            )
            log.info("NFSe: %d documentos", len(pacote.nfse))
        except Exception as exc:
            log.warning("Falha consultando ADN (município pode não ser aderente): %s", exc)

    # --- gravação em disco --------------------------------------------
    raiz = os.path.abspath(diretorio_saida)
    for grupo, docs in [
        ("nfe/emitidas", pacote.nfe_emitidas),
        ("nfe/recebidas", pacote.nfe_recebidas),
        ("cte/emitidos", pacote.cte_emitidos),
        ("cte/recebidos", pacote.cte_recebidos),
    ]:
        for d in docs:
            nome = f"{d.chave or d.nsu}.xml"
            _gravar(os.path.join(raiz, grupo), nome, d.xml)

    for nfse in pacote.nfse:
        _gravar(
            os.path.join(raiz, "nfse", nfse.papel.lower()),
            f"{nfse.chave_acesso}.xml",
            nfse.xml,
        )

    return pacote
