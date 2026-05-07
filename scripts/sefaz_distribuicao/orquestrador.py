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
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import checkpoint, cte_distribuicao, nfe_distribuicao, nfse_nacional
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


def _gravar_em_disco(diretorio: str, sub: str, nome: str, xml: str) -> None:
    pasta = os.path.join(diretorio, sub)
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, f"{nome}.xml"), "w", encoding="utf-8") as fp:
        fp.write(xml)


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
    nsu_inicial_nfe: Optional[str] = None,
    nsu_inicial_cte: Optional[str] = None,
    dry_run: bool = False,
    pasta_saida: Optional[str] = None,
    max_documentos: int = 0,
    checkpoint_dir: Optional[Path] = None,
    resetar_checkpoint: bool = False,
) -> Resumo:
    """
    Baixa NFe + CTe (Distribuição DF-e) + NFSe Nacional (ADN) do CNPJ
    no período, e importa cada XML pelo pipeline `NotaFiscal(xml_data=...)`.

    PRÉ-REQUISITO: deve ser chamada dentro de um Flask `app_context()`,
    para que `db.session` esteja disponível (apenas quando `dry_run=False`).

    Args:
        dry_run: se True, NÃO chama `NotaFiscal()` — apenas baixa, conta e
            (opcionalmente) grava os XMLs em `pasta_saida`. Não toca no banco.
        pasta_saida: salva os XMLs em `pasta_saida/{nfe,cte,nfse}/<chave>.xml`.
        max_documentos: corta após N documentos por tipo (0 = ilimitado).
        nsu_inicial_nfe / nsu_inicial_cte: se fornecidos, sobrescrevem o
            checkpoint persistido. Use None para usar o checkpoint salvo
            (ou "0" na primeira execução).
        checkpoint_dir: pasta onde gravar o `ultNSU` por (CNPJ, tipo).
            Default: ~/.fortanks/sefaz_nsu/. Crucial para evitar bloqueio
            cStat=656 ("Consumo Indevido") da SEFAZ ao reusar ultNSU=0.
        resetar_checkpoint: se True, ignora e apaga checkpoint existente.
    """
    cert = CertificadoA1(caminho_pfx=caminho_pfx, senha=senha_certificado)
    cnpj = "".join(filter(str.isdigit, cnpj)).zfill(14)
    resumo = Resumo()

    if resetar_checkpoint:
        checkpoint.resetar(cnpj, "nfe", checkpoint_dir)
        checkpoint.resetar(cnpj, "cte", checkpoint_dir)

    if nsu_inicial_nfe is None:
        nsu_inicial_nfe = checkpoint.ler(cnpj, "nfe", checkpoint_dir)
    if nsu_inicial_cte is None:
        nsu_inicial_cte = checkpoint.ler(cnpj, "cte", checkpoint_dir)
    log.info("Checkpoints: NFe ultNSU=%s, CTe ultNSU=%s", nsu_inicial_nfe, nsu_inicial_cte)

    def _processar(xml: str, chave: Optional[str], tipo: str) -> None:
        if pasta_saida:
            _gravar_em_disco(pasta_saida, tipo, chave or "sem-chave", xml)
        if dry_run:
            return
        _ingerir(xml, chave, resumo, tipo_label=tipo)

    # --- NFe -----------------------------------------------------------
    log.info("=== NFeDistribuicaoDFe (CNPJ %s, ambiente=%d) ===", cnpj, ambiente)
    todas_nfe: List[DocumentoXML] = []
    for pagina in nfe_distribuicao.consultar(
        cert, cnpj, uf_autor=uf_autor, ambiente=ambiente, nsu_inicial=nsu_inicial_nfe
    ):
        todas_nfe.extend(pagina.documentos)
        # Persiste o NSU IMEDIATAMENTE para próxima execução não cair em cStat=656.
        if pagina.ultimo_nsu and pagina.ultimo_nsu != "0":
            checkpoint.gravar(cnpj, "nfe", pagina.ultimo_nsu, checkpoint_dir)
        if max_documentos and len(todas_nfe) >= max_documentos:
            log.info("NFe: limite de %d atingido, parando paginação.", max_documentos)
            break
    nfe_no_periodo = filtrar_por_data(todas_nfe, data_inicial, data_final)
    if max_documentos:
        nfe_no_periodo = nfe_no_periodo[:max_documentos]
    resumo.nfe_baixadas = len(nfe_no_periodo)
    log.info("NFe: %d documentos no período (de %d totais).", len(nfe_no_periodo), len(todas_nfe))
    for doc in nfe_no_periodo:
        _processar(doc.xml, doc.chave, "nfe")

    # --- CTe -----------------------------------------------------------
    log.info("=== CTeDistribuicaoDFe (CNPJ %s, ambiente=%d) ===", cnpj, ambiente)
    todas_cte: List[DocumentoXML] = []
    for pagina in cte_distribuicao.consultar(
        cert, cnpj, uf_autor=uf_autor, ambiente=ambiente, nsu_inicial=nsu_inicial_cte
    ):
        todas_cte.extend(pagina.documentos)
        if pagina.ultimo_nsu and pagina.ultimo_nsu != "0":
            checkpoint.gravar(cnpj, "cte", pagina.ultimo_nsu, checkpoint_dir)
        if max_documentos and len(todas_cte) >= max_documentos:
            log.info("CTe: limite de %d atingido, parando paginação.", max_documentos)
            break
    cte_no_periodo = filtrar_por_data(todas_cte, data_inicial, data_final)
    if max_documentos:
        cte_no_periodo = cte_no_periodo[:max_documentos]
    resumo.cte_baixados = len(cte_no_periodo)
    log.info("CTe: %d documentos no período (de %d totais).", len(cte_no_periodo), len(todas_cte))
    for doc in cte_no_periodo:
        _processar(doc.xml, doc.chave, "cte")

    # --- NFSe Nacional -------------------------------------------------
    if incluir_nfse:
        log.info("=== ADN NFSe Nacional (CNPJ %s, ambiente=%d) ===", cnpj, ambiente)
        try:
            nfses = nfse_nacional.baixar_periodo(
                cert, cnpj, data_inicial, data_final, ambiente=ambiente
            )
            if max_documentos:
                nfses = nfses[:max_documentos]
            resumo.nfse_baixadas = len(nfses)
            log.info("NFSe: %d documentos no período.", len(nfses))
            for n in nfses:
                _processar(n.xml, n.chave_acesso, "nfse")
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "ADN indisponível ou município não aderente ao Sistema Nacional "
                "NFS-e (CNPJ %s): %s",
                cnpj,
                exc,
            )
            resumo.erros.append(f"NFSe ADN: {exc}")

    log.info(
        "Resumo: baixadas=%d importadas=%d existentes=%d erros=%d (dry_run=%s)",
        resumo.total_baixadas,
        resumo.total_importadas,
        len(resumo.chaves_existentes),
        len(resumo.erros),
        dry_run,
    )
    return resumo
