"""
Persistência de um XML baixado da SEFAZ em DocumentoSefaz + Upload.

Refina o `tipo` a partir do schema do docZip (procNFe/resNFe/resEvento/
procEventoNFe/procCTe/resCTe/procEventoCTe) e extrai os campos certos
para cada caso (NFe completa, resumo, evento).

Dedupe por (tipo, nsu) — o mesmo documento e seus eventos compartilham
`chave_acesso` (chNFe), por isso a unicidade não pode ser na chave.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from models.database import db
from models.fornecedor import Fornecedor
from models.upload import minio_service
from utils.utils import dump_dados_json, set_dados_json_item

from ..constants import (
    DA_CNPJ_DESTINATARIO,
    DA_CNPJ_EMITENTE,
    DA_SCHEMA,
    DA_TP_EVENTO,
    DA_UPLOAD_ID,
    UPLOAD_TIPO_XML,
)
from ..entities import DocumentoSefaz

logger = logging.getLogger(__name__)

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_CTE = "http://www.portalfiscal.inf.br/cte"


# --------------------------------------------------------------------------
# Util de parsing
# --------------------------------------------------------------------------

def _parse_dh(dh: Optional[str]) -> Optional[datetime]:
    if not dh:
        return None
    try:
        return datetime.fromisoformat(dh)
    except ValueError:
        return None


def _to_decimal(valor: Optional[str]) -> Optional[Decimal]:
    if not valor:
        return None
    try:
        return Decimal(valor.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _normalizar_nsu(nsu: Optional[str]) -> Optional[str]:
    if not nsu:
        return None
    return nsu.zfill(15)


def _detectar_tipo(schema: str, xml_str: str, tipo_servico_default: str) -> str:
    """
    Refina o tipo do documento a partir do schema do docZip.

    Regras (case-insensitive sobre o schema):
        procNFe         -> 'nfe'
        resNFe          -> 'nfe_resumo'
        procEventoNFe   -> 'nfe_procEvento'
        procCTe         -> 'cte'
        resCTe          -> 'cte_resumo'
        procEventoCTe   -> 'cte_procEvento'
        resEvento       -> 'nfe_resEvento' ou 'cte_resEvento' (decidido pelo
                           namespace raiz do XML).
    Para schemas desconhecidos, retorna `tipo_servico_default`.
    """
    s = (schema or "").lower()
    if s.startswith("procnfe"):
        return "nfe"
    if s.startswith("resnfe"):
        return "nfe_resumo"
    if s.startswith("proceventonfe"):
        return "nfe_procEvento"
    if s.startswith("proccte"):
        return "cte"
    if s.startswith("rescte"):
        return "cte_resumo"
    if s.startswith("proceventocte"):
        return "cte_procEvento"
    if s.startswith("resevento"):
        try:
            root = ET.fromstring(xml_str)
            ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
            if ns == NS_CTE:
                return "cte_resEvento"
            return "nfe_resEvento"
        except ET.ParseError:
            return f"{tipo_servico_default}_resEvento"
    return tipo_servico_default


# --------------------------------------------------------------------------
# Extratores por formato
# --------------------------------------------------------------------------

def _extrair_nfe_completa(xml_str: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """procNFe: (cnpj_emit, nome_emit, valor_total, dh_emi)."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None, None, None, None
    inf = root.find(f".//{{{NS_NFE}}}infNFe")
    if inf is None:
        return None, None, None, None
    emit = inf.find(f"{{{NS_NFE}}}emit")
    cnpj = emit.findtext(f"{{{NS_NFE}}}CNPJ") if emit is not None else None
    nome = emit.findtext(f"{{{NS_NFE}}}xNome") if emit is not None else None
    ide = inf.find(f"{{{NS_NFE}}}ide")
    dh_emi = ide.findtext(f"{{{NS_NFE}}}dhEmi") if ide is not None else None
    total = inf.find(f".//{{{NS_NFE}}}ICMSTot")
    valor = total.findtext(f"{{{NS_NFE}}}vNF") if total is not None else None
    return cnpj, nome, valor, dh_emi


def _extrair_nfe_resumo(xml_str: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """resNFe v1.01: (cnpj, xNome, vNF, dhEmi)."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None, None, None, None
    res = root if root.tag.endswith("resNFe") else root.find(f".//{{{NS_NFE}}}resNFe")
    if res is None:
        return None, None, None, None
    return (
        res.findtext(f"{{{NS_NFE}}}CNPJ"),
        res.findtext(f"{{{NS_NFE}}}xNome"),
        res.findtext(f"{{{NS_NFE}}}vNF"),
        res.findtext(f"{{{NS_NFE}}}dhEmi"),
    )


def _extrair_cte_completa(xml_str: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None, None, None, None
    inf = root.find(f".//{{{NS_CTE}}}infCte")
    if inf is None:
        return None, None, None, None
    emit = inf.find(f"{{{NS_CTE}}}emit")
    cnpj = emit.findtext(f"{{{NS_CTE}}}CNPJ") if emit is not None else None
    nome = emit.findtext(f"{{{NS_CTE}}}xNome") if emit is not None else None
    ide = inf.find(f"{{{NS_CTE}}}ide")
    dh_emi = ide.findtext(f"{{{NS_CTE}}}dhEmi") if ide is not None else None
    vprest = inf.find(f"{{{NS_CTE}}}vPrest")
    valor = vprest.findtext(f"{{{NS_CTE}}}vTPrest") if vprest is not None else None
    return cnpj, nome, valor, dh_emi


def _extrair_cte_resumo(xml_str: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None, None, None, None
    res = root if root.tag.endswith("resCTe") else root.find(f".//{{{NS_CTE}}}resCTe")
    if res is None:
        return None, None, None, None
    return (
        res.findtext(f"{{{NS_CTE}}}CNPJ"),
        res.findtext(f"{{{NS_CTE}}}xNome"),
        res.findtext(f"{{{NS_CTE}}}vTPrest"),
        res.findtext(f"{{{NS_CTE}}}dhEmi"),
    )


def _extrair_evento(xml_str: str) -> dict:
    """
    Extrai chNFe, dhEvento, tpEvento e CNPJ de:
        - resEvento (xmlns NFe ou CTe)
        - procEventoNFe / procEventoCTe -> infEvento
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return {}

    for ns in (NS_NFE, NS_CTE):
        # 1) resEvento na raiz
        if root.tag in (f"{{{ns}}}resEvento",):
            return {
                "chave": (
                    root.findtext(f"{{{ns}}}chNFe")
                    or root.findtext(f"{{{ns}}}chCTe")
                ),
                "dh_evento": root.findtext(f"{{{ns}}}dhEvento"),
                "tp_evento": root.findtext(f"{{{ns}}}tpEvento"),
                "cnpj": root.findtext(f"{{{ns}}}CNPJ"),
            }
        # 2) procEvento -> evento -> infEvento
        infEvento = root.find(f".//{{{ns}}}infEvento")
        if infEvento is not None:
            return {
                "chave": (
                    infEvento.findtext(f"{{{ns}}}chNFe")
                    or infEvento.findtext(f"{{{ns}}}chCTe")
                ),
                "dh_evento": infEvento.findtext(f"{{{ns}}}dhEvento"),
                "tp_evento": infEvento.findtext(f"{{{ns}}}tpEvento"),
                "cnpj": infEvento.findtext(f"{{{ns}}}CNPJ"),
            }
    return {}


# --------------------------------------------------------------------------
# Função pública
# --------------------------------------------------------------------------

def processar_xml(xml_baixado, *, sobrescrever: bool = False) -> Optional[DocumentoSefaz]:
    """
    Persiste um `XmlBaixado` (de `models.sefaz_distribuicao`) como
    `Upload` (MinIO) + `DocumentoSefaz` (DB).

    Idempotente por (tipo, nsu). Quando `sobrescrever=True`, atualiza
    o registro existente em vez de retornar.
    """
    schema = xml_baixado.schema or ""
    tipo = _detectar_tipo(schema, xml_baixado.xml, xml_baixado.tipo)
    nsu = _normalizar_nsu(xml_baixado.nsu)

    # Dedupe por (tipo, nsu).
    if nsu:
        existente = (
            DocumentoSefaz.query.filter_by(tipo=tipo, nsu=nsu).first()
        )
        if existente and not sobrescrever:
            return existente

    # ----- extrai info conforme o subtipo -----
    is_evento = tipo.endswith("_resEvento") or tipo.endswith("_procEvento")
    cnpj_emit: Optional[str] = None
    nome_emit: Optional[str] = None
    valor_str: Optional[str] = None
    dh_str: Optional[str] = None
    chave: Optional[str] = xml_baixado.chave or None
    tp_evento: Optional[str] = None

    if is_evento:
        ev = _extrair_evento(xml_baixado.xml)
        chave = chave or ev.get("chave")
        dh_str = ev.get("dh_evento")
        tp_evento = ev.get("tp_evento")
        cnpj_emit = ev.get("cnpj")
    elif tipo == "nfe":
        cnpj_emit, nome_emit, valor_str, dh_str = _extrair_nfe_completa(xml_baixado.xml)
    elif tipo == "nfe_resumo":
        cnpj_emit, nome_emit, valor_str, dh_str = _extrair_nfe_resumo(xml_baixado.xml)
    elif tipo == "cte":
        cnpj_emit, nome_emit, valor_str, dh_str = _extrair_cte_completa(xml_baixado.xml)
    elif tipo == "cte_resumo":
        cnpj_emit, nome_emit, valor_str, dh_str = _extrair_cte_resumo(xml_baixado.xml)
    # outros: campos ficam None

    data_emissao = xml_baixado.data_emissao or _parse_dh(dh_str)
    valor_total = _to_decimal(valor_str)

    # ----- Fornecedor -----
    fornecedor: Optional[Fornecedor] = None
    cnpj_para_fornecedor = cnpj_emit or xml_baixado.cnpj_emitente
    if cnpj_para_fornecedor and nome_emit:
        try:
            fornecedor = Fornecedor(
                nome=nome_emit, cnpj=cnpj_para_fornecedor, estado=None
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha em Fornecedor %s: %s", cnpj_para_fornecedor, exc)
    elif cnpj_para_fornecedor:
        # Eventos não trazem nome — só busca, não cria.
        fornecedor = Fornecedor.query.filter_by(cnpj=cnpj_para_fornecedor).first()

    # ----- DocumentoSefaz -----
    dados_iniciais: dict = {
        DA_SCHEMA: schema,
        DA_CNPJ_EMITENTE: xml_baixado.cnpj_emitente or cnpj_emit,
        DA_CNPJ_DESTINATARIO: xml_baixado.cnpj_destinatario,
    }
    if tp_evento:
        dados_iniciais[DA_TP_EVENTO] = tp_evento

    if sobrescrever and nsu:
        doc = (
            DocumentoSefaz.query.filter_by(tipo=tipo, nsu=nsu).first()
            or DocumentoSefaz()
        )
    else:
        doc = DocumentoSefaz()
    doc.tipo = tipo
    doc.data = data_emissao
    doc.fornecedor_id = fornecedor.id if fornecedor else None
    doc.valor_total = valor_total
    doc.dados_adicionais = dump_dados_json(dados_iniciais)
    doc.nsu = nsu
    doc.chave_acesso = chave
    db.session.add(doc)
    db.session.commit()

    # ----- Upload do XML (DB + MinIO via service) -----
    nome_arquivo = f"{tipo}_{chave or nsu or doc.id}.xml"
    try:
        upload = minio_service.criar_e_enviar(
            pai="DocumentoSefaz",
            pai_id=doc.id,
            tipo=UPLOAD_TIPO_XML,
            filename=nome_arquivo,
            mimetype="application/xml",
            blob=xml_baixado.xml.encode("utf-8"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Upload falhou para doc %s: %s", doc.id, exc, exc_info=True)
        return doc

    doc.dados_adicionais = set_dados_json_item(
        doc.dados_adicionais, DA_UPLOAD_ID, upload.id
    )
    db.session.add(doc)
    db.session.commit()
    return doc
