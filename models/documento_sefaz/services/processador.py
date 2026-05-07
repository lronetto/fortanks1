"""
Persistência de um XML baixado da SEFAZ:
  1. extrai dados do XML (emitente, valor, dhEmi)
  2. cria/encontra Fornecedor
  3. faz upload do XML como `Upload` (MinIO)
  4. grava `DocumentoSefaz` apontando para o Upload via `dados_adicionais.upload_id`
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from models.database import db
from models.fornecedor import Fornecedor
from models.upload import Upload
from utils.utils import dump_dados_json, parse_dados_json, set_dados_json_item

from ..constants import (
    DA_CNPJ_DESTINATARIO,
    DA_CNPJ_EMITENTE,
    DA_SCHEMA,
    DA_UPLOAD_ID,
    UPLOAD_TIPO_XML,
)
from ..entities import DocumentoSefaz

logger = logging.getLogger(__name__)

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_CTE = "http://www.portalfiscal.inf.br/cte"


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


def _extrair_nfe(xml_str: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Devolve (cnpj_emit, nome_emit, valor_total_str, dh_emi_str) de NFe ou resNFe."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None, None, None, None

    inf = root.find(f".//{{{NS_NFE}}}infNFe")
    if inf is not None:
        emit = inf.find(f"{{{NS_NFE}}}emit")
        cnpj = emit.findtext(f"{{{NS_NFE}}}CNPJ") if emit is not None else None
        nome = emit.findtext(f"{{{NS_NFE}}}xNome") if emit is not None else None
        ide = inf.find(f"{{{NS_NFE}}}ide")
        dh_emi = ide.findtext(f"{{{NS_NFE}}}dhEmi") if ide is not None else None
        total = inf.find(f".//{{{NS_NFE}}}ICMSTot")
        valor = total.findtext(f"{{{NS_NFE}}}vNF") if total is not None else None
        return cnpj, nome, valor, dh_emi

    res = root if root.tag.endswith("resNFe") else root.find(f".//{{{NS_NFE}}}resNFe")
    if res is not None:
        return (
            res.findtext(f"{{{NS_NFE}}}CNPJ"),
            res.findtext(f"{{{NS_NFE}}}xNome"),
            res.findtext(f"{{{NS_NFE}}}vNF"),
            res.findtext(f"{{{NS_NFE}}}dhEmi"),
        )
    return None, None, None, None


def _extrair_cte(xml_str: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Devolve (cnpj_emit, nome_emit, valor_total_str, dh_emi_str) de CTe ou resCTe."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None, None, None, None

    inf = root.find(f".//{{{NS_CTE}}}infCte")
    if inf is not None:
        emit = inf.find(f"{{{NS_CTE}}}emit")
        cnpj = emit.findtext(f"{{{NS_CTE}}}CNPJ") if emit is not None else None
        nome = emit.findtext(f"{{{NS_CTE}}}xNome") if emit is not None else None
        ide = inf.find(f"{{{NS_CTE}}}ide")
        dh_emi = ide.findtext(f"{{{NS_CTE}}}dhEmi") if ide is not None else None
        vprest = inf.find(f"{{{NS_CTE}}}vPrest")
        valor = vprest.findtext(f"{{{NS_CTE}}}vTPrest") if vprest is not None else None
        return cnpj, nome, valor, dh_emi

    res = root if root.tag.endswith("resCTe") else root.find(f".//{{{NS_CTE}}}resCTe")
    if res is not None:
        return (
            res.findtext(f"{{{NS_CTE}}}CNPJ"),
            res.findtext(f"{{{NS_CTE}}}xNome"),
            res.findtext(f"{{{NS_CTE}}}vTPrest"),
            res.findtext(f"{{{NS_CTE}}}dhEmi"),
        )
    return None, None, None, None


def _normalizar_nsu(nsu: Optional[str]) -> Optional[str]:
    """Pad com zeros à esquerda para garantir comparação lexicográfica = numérica."""
    if not nsu:
        return None
    return nsu.zfill(15)


def processar_xml(xml_baixado, *, sobrescrever: bool = False) -> Optional[DocumentoSefaz]:
    """
    Persiste um `XmlBaixado` (de `models.sefaz_distribuicao`) como
    `Upload` (MinIO) + `DocumentoSefaz` (DB).

    Retorna o `DocumentoSefaz` (já existente OU recém-criado). Idempotente
    pela `chave_acesso` quando ela está presente, a menos que
    `sobrescrever=True`.
    """
    chave = xml_baixado.chave or None
    if chave:
        existente = DocumentoSefaz.query.filter_by(chave_acesso=chave).first()
        if existente and not sobrescrever:
            return existente

    # Extrai do XML o que faltava no XmlBaixado (valor_total, nome_emit).
    if xml_baixado.tipo == "nfe":
        cnpj_emit, nome_emit, valor_str, dh_emi = _extrair_nfe(xml_baixado.xml)
    elif xml_baixado.tipo == "cte":
        cnpj_emit, nome_emit, valor_str, dh_emi = _extrair_cte(xml_baixado.xml)
    else:
        cnpj_emit, nome_emit, valor_str, dh_emi = None, None, None, None

    # Fornecedor a partir do emitente. Fornecedor.__init__ já faz find-or-create.
    fornecedor: Optional[Fornecedor] = None
    cnpj_para_fornecedor = cnpj_emit or xml_baixado.cnpj_emitente
    if cnpj_para_fornecedor:
        try:
            fornecedor = Fornecedor(
                nome=nome_emit or "(sem nome)",
                cnpj=cnpj_para_fornecedor,
                estado=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao criar/ler Fornecedor %s: %s", cnpj_para_fornecedor, exc)

    data_emissao = xml_baixado.data_emissao or _parse_dh(dh_emi)
    valor_total = _to_decimal(valor_str)
    nsu = _normalizar_nsu(xml_baixado.nsu)

    # 1) cria DocumentoSefaz primeiro pra ter id, depois faz Upload com pai_id correto.
    dados_iniciais = {
        DA_SCHEMA: xml_baixado.schema,
        DA_CNPJ_EMITENTE: xml_baixado.cnpj_emitente or cnpj_emit,
        DA_CNPJ_DESTINATARIO: xml_baixado.cnpj_destinatario,
    }
    doc = DocumentoSefaz(
        tipo=xml_baixado.tipo,
        data=data_emissao,
        fornecedor_id=fornecedor.id if fornecedor else None,
        valor_total=valor_total,
        dados_adicionais=dump_dados_json(dados_iniciais),
        nsu=nsu,
        chave_acesso=chave,
    )
    db.session.add(doc)
    db.session.commit()

    # 2) faz o upload do XML como blob (vai para MinIO se configurado).
    nome_arquivo = f"{xml_baixado.tipo}_{chave or nsu or doc.id}.xml"
    try:
        upload = Upload.registrar(
            pai="DocumentoSefaz",
            pai_id=doc.id,
            tipo=UPLOAD_TIPO_XML,
            filename=nome_arquivo,
            mimetype="application/xml",
            blob=xml_baixado.xml.encode("utf-8"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Upload falhou para doc %s: %s", doc.id, exc, exc_info=True)
        return doc  # mantém DocumentoSefaz; upload pode ser refeito depois

    # 3) grava upload_id em DocumentoSefaz.dados_adicionais.
    doc.dados_adicionais = set_dados_json_item(
        doc.dados_adicionais, DA_UPLOAD_ID, upload.id
    )
    db.session.add(doc)
    db.session.commit()
    return doc
