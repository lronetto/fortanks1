"""
Cliente do Web Service nacional `NFeDistribuicaoDFe`.

Funcionamento (resumo do MOC SEFAZ):
  - O serviço NÃO aceita filtro por intervalo de datas.
  - A consulta é feita por NSU (Número Sequencial Único). A cada chamada
    o servidor devolve até ~50 documentos a partir do `ultNSU` informado,
    junto com o `maxNSU` total. Repete-se até `ultNSU == maxNSU`.
  - Cada documento volta como `<docZip>` contendo o XML compactado
    (gzip) e codificado em base64.
  - Para filtrar por data inicial/final, fazemos isso *após* descompactar,
    olhando para `dhEmi` (NFe), `dhRecbto` (procEvento) etc.
  - O serviço retorna tanto NFes EMITIDAS pela empresa quanto aquelas
    em que a empresa figura como destinatária, transportadora ou
    autorizada (tag autXML).

Endpoints (Ambiente Nacional):
  Produção : https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx
  Homolog  : https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx
"""

from __future__ import annotations

import base64
import gzip
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterator, List, Optional
from xml.etree import ElementTree as ET

import requests

from .cert_utils import CertificadoA1, materializar_pem

log = logging.getLogger(__name__)

URL_PROD = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
URL_HOMOLOG = "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_WSDL = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"

SOAP_ACTION = (
    "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
)


@dataclass
class DocumentoXML:
    """Representa um documento devolvido pelo Distribuição DF-e."""

    nsu: str
    schema: str            # ex.: 'resNFe_v1.01.xsd', 'procNFe_v4.00.xsd'
    xml: str               # XML já descompactado (UTF-8)
    data_emissao: Optional[datetime] = None
    chave: Optional[str] = None
    cnpj_emitente: Optional[str] = None
    cnpj_destinatario: Optional[str] = None


@dataclass
class ResultadoConsulta:
    documentos: List[DocumentoXML] = field(default_factory=list)
    ultimo_nsu: str = "0"
    max_nsu: str = "0"


def _envelope_soap(cnpj: str, uf_autor: int, ult_nsu: str, ambiente: int) -> bytes:
    """Monta o envelope SOAP 1.2 da consulta por NSU."""
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:soap12="{NS_SOAP}">'
        f"<soap12:Body>"
        f'<nfeDistDFeInteresse xmlns="{NS_WSDL}">'
        f"<nfeDadosMsg>"
        f'<distDFeInt xmlns="{NS_NFE}" versao="1.01">'
        f"<tpAmb>{ambiente}</tpAmb>"
        f"<cUFAutor>{uf_autor}</cUFAutor>"
        f"<CNPJ>{cnpj}</CNPJ>"
        f"<distNSU><ultNSU>{int(ult_nsu):015d}</ultNSU></distNSU>"
        f"</distDFeInt>"
        f"</nfeDadosMsg>"
        f"</nfeDistDFeInteresse>"
        f"</soap12:Body>"
        f"</soap12:Envelope>"
    ).encode("utf-8")


def _parse_resposta(xml_resposta: bytes) -> ResultadoConsulta:
    """Extrai os docZip de uma resposta SOAP, descompactando o gzip."""
    root = ET.fromstring(xml_resposta)
    ret = root.find(f".//{{{NS_NFE}}}retDistDFeInt")
    if ret is None:
        raise RuntimeError(f"Resposta inesperada da SEFAZ:\n{xml_resposta!r}")

    cstat = ret.findtext(f"{{{NS_NFE}}}cStat", default="")
    xmotivo = ret.findtext(f"{{{NS_NFE}}}xMotivo", default="")
    ult_nsu = ret.findtext(f"{{{NS_NFE}}}ultNSU", default="0")
    max_nsu = ret.findtext(f"{{{NS_NFE}}}maxNSU", default="0")

    # 138 = Documento(s) localizado(s); 137 = Nenhum doc localizado
    if cstat not in {"137", "138"}:
        raise RuntimeError(f"SEFAZ rejeitou consulta: cStat={cstat} xMotivo={xmotivo}")

    documentos: List[DocumentoXML] = []
    for doc_zip in ret.findall(f".//{{{NS_NFE}}}docZip"):
        nsu = doc_zip.attrib.get("NSU", "")
        schema = doc_zip.attrib.get("schema", "")
        gz = base64.b64decode(doc_zip.text or "")
        xml_str = gzip.decompress(gz).decode("utf-8")
        documentos.append(_enriquecer(DocumentoXML(nsu=nsu, schema=schema, xml=xml_str)))

    return ResultadoConsulta(documentos=documentos, ultimo_nsu=ult_nsu, max_nsu=max_nsu)


def _enriquecer(doc: DocumentoXML) -> DocumentoXML:
    """Preenche chave, CNPJs e dhEmi quando for resumo/NFe completa."""
    try:
        root = ET.fromstring(doc.xml)
    except ET.ParseError:
        return doc

    inf = root.find(f".//{{{NS_NFE}}}infNFe")
    if inf is not None and inf.attrib.get("Id"):
        doc.chave = inf.attrib["Id"].replace("NFe", "")
        ide = inf.find(f"{{{NS_NFE}}}ide")
        if ide is not None:
            dh = ide.findtext(f"{{{NS_NFE}}}dhEmi")
            if dh:
                doc.data_emissao = _parse_dh(dh)
        emit = inf.find(f"{{{NS_NFE}}}emit")
        if emit is not None:
            doc.cnpj_emitente = emit.findtext(f"{{{NS_NFE}}}CNPJ")
        dest = inf.find(f"{{{NS_NFE}}}dest")
        if dest is not None:
            doc.cnpj_destinatario = dest.findtext(f"{{{NS_NFE}}}CNPJ")
        return doc

    res = root if root.tag.endswith("resNFe") else root.find(f".//{{{NS_NFE}}}resNFe")
    if res is not None:
        doc.chave = res.findtext(f"{{{NS_NFE}}}chNFe")
        doc.cnpj_emitente = res.findtext(f"{{{NS_NFE}}}CNPJ")
        dh = res.findtext(f"{{{NS_NFE}}}dhEmi")
        if dh:
            doc.data_emissao = _parse_dh(dh)
    return doc


def _parse_dh(dh: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(dh)
    except ValueError:
        return None


def consultar(
    cert: CertificadoA1,
    cnpj: str,
    *,
    uf_autor: int = 35,
    ambiente: int = 1,
    nsu_inicial: str = "0",
    timeout: int = 60,
    url: Optional[str] = None,
) -> Iterator[ResultadoConsulta]:
    """
    Itera as páginas do Distribuição DF-e até esgotar (ultNSU == maxNSU).

    Args:
        cert: certificado A1 da empresa.
        cnpj: 14 dígitos, somente números.
        uf_autor: código IBGE da UF do autor (35=SP, 33=RJ, 31=MG, ...).
        ambiente: 1 = produção, 2 = homologação.
        nsu_inicial: NSU a partir do qual buscar (use o último persistido
            para evitar baixar tudo de novo).
        url: força um endpoint específico (default: produção).
    """
    if url is None:
        url = URL_PROD if ambiente == 1 else URL_HOMOLOG

    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
        "SOAPAction": SOAP_ACTION,
    }

    with materializar_pem(cert) as (cert_path, key_path):
        ult_nsu = nsu_inicial
        while True:
            corpo = _envelope_soap(cnpj, uf_autor, ult_nsu, ambiente)
            log.info("NFeDistribuicaoDFe consulta ultNSU=%s", ult_nsu)
            resp = requests.post(
                url,
                data=corpo,
                headers=headers,
                cert=(cert_path, key_path),
                timeout=timeout,
            )
            resp.raise_for_status()
            resultado = _parse_resposta(resp.content)
            yield resultado

            if resultado.ultimo_nsu == resultado.max_nsu or not resultado.documentos:
                break
            ult_nsu = resultado.ultimo_nsu


def filtrar_por_data(
    documentos: List[DocumentoXML],
    data_inicial: date,
    data_final: date,
) -> List[DocumentoXML]:
    """Filtra documentos cuja data de emissão esteja no intervalo (inclusive)."""
    saida: List[DocumentoXML] = []
    for doc in documentos:
        if doc.data_emissao is None:
            continue
        d = doc.data_emissao.date()
        if data_inicial <= d <= data_final:
            saida.append(doc)
    return saida
