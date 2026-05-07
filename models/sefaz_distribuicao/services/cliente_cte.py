"""
Cliente do Web Service nacional `CTeDistribuicaoDFe`.

Mesmo padrão do NFeDistribuicaoDFe, com namespaces próprios do CTe.
Atende todos os papéis: emitente, tomador, remetente, destinatário,
expedidor, recebedor.

Endpoints (Ambiente Nacional):
  Produção : https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx
  Homolog  : https://hom1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx
"""

from __future__ import annotations

import base64
import gzip
import logging
from typing import Iterator, List, Optional
from xml.etree import ElementTree as ET

import requests

from ..utils.cert_utils import CertificadoA1, materializar_pem
from .cliente_nfe import DocumentoXML, ResultadoConsulta, _parse_dh

log = logging.getLogger(__name__)

URL_PROD = "https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx"
URL_HOMOLOG = "https://hom1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx"

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_WSDL = "http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe"

SOAP_ACTION = (
    "http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe/cteDistDFeInteresse"
)


def _envelope_soap(cnpj: str, uf_autor: int, ult_nsu: str, ambiente: int) -> bytes:
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:soap12="{NS_SOAP}">'
        f"<soap12:Body>"
        f'<cteDistDFeInteresse xmlns="{NS_WSDL}">'
        f"<cteDadosMsg>"
        f'<distDFeInt xmlns="{NS_CTE}" versao="1.00">'
        f"<tpAmb>{ambiente}</tpAmb>"
        f"<cUFAutor>{uf_autor}</cUFAutor>"
        f"<CNPJ>{cnpj}</CNPJ>"
        f"<distNSU><ultNSU>{int(ult_nsu):015d}</ultNSU></distNSU>"
        f"</distDFeInt>"
        f"</cteDadosMsg>"
        f"</cteDistDFeInteresse>"
        f"</soap12:Body>"
        f"</soap12:Envelope>"
    ).encode("utf-8")


def _enriquecer(doc: DocumentoXML) -> DocumentoXML:
    try:
        root = ET.fromstring(doc.xml)
    except ET.ParseError:
        return doc

    inf = root.find(f".//{{{NS_CTE}}}infCte")
    if inf is not None and inf.attrib.get("Id"):
        doc.chave = inf.attrib["Id"].replace("CTe", "")
        ide = inf.find(f"{{{NS_CTE}}}ide")
        if ide is not None:
            doc.data_emissao = _parse_dh(ide.findtext(f"{{{NS_CTE}}}dhEmi", ""))
        emit = inf.find(f"{{{NS_CTE}}}emit")
        if emit is not None:
            doc.cnpj_emitente = emit.findtext(f"{{{NS_CTE}}}CNPJ")
        dest = inf.find(f"{{{NS_CTE}}}dest")
        if dest is not None:
            doc.cnpj_destinatario = dest.findtext(f"{{{NS_CTE}}}CNPJ")
        return doc

    res = root if root.tag.endswith("resCTe") else root.find(f".//{{{NS_CTE}}}resCTe")
    if res is not None:
        doc.chave = res.findtext(f"{{{NS_CTE}}}chCTe")
        doc.cnpj_emitente = res.findtext(f"{{{NS_CTE}}}CNPJ")
        dh = res.findtext(f"{{{NS_CTE}}}dhEmi")
        if dh:
            doc.data_emissao = _parse_dh(dh)
    return doc


def _parse_resposta(xml_resposta: bytes) -> ResultadoConsulta:
    root = ET.fromstring(xml_resposta)
    ret = root.find(f".//{{{NS_CTE}}}retDistDFeInt")
    if ret is None:
        raise RuntimeError(f"Resposta inesperada da SEFAZ-CTe:\n{xml_resposta!r}")

    cstat = ret.findtext(f"{{{NS_CTE}}}cStat", default="")
    xmotivo = ret.findtext(f"{{{NS_CTE}}}xMotivo", default="")
    ult_nsu = ret.findtext(f"{{{NS_CTE}}}ultNSU", default="0")
    max_nsu = ret.findtext(f"{{{NS_CTE}}}maxNSU", default="0")

    if cstat == "656":
        raise RuntimeError(
            "SEFAZ-CTe aplicou bloqueio de Consumo Indevido (cStat=656). "
            "Aguarde 1 hora e use checkpoint de NSU (--checkpoint-dir / nsu_inicial) "
            "para não chamar com ultNSU=0 repetidamente."
        )
    if cstat not in {"137", "138"}:
        raise RuntimeError(f"SEFAZ-CTe rejeitou: cStat={cstat} xMotivo={xmotivo}")

    docs: List[DocumentoXML] = []
    for doc_zip in ret.findall(f".//{{{NS_CTE}}}docZip"):
        nsu = doc_zip.attrib.get("NSU", "")
        schema = doc_zip.attrib.get("schema", "")
        xml_str = gzip.decompress(base64.b64decode(doc_zip.text or "")).decode("utf-8")
        docs.append(_enriquecer(DocumentoXML(nsu=nsu, schema=schema, xml=xml_str)))

    return ResultadoConsulta(documentos=docs, ultimo_nsu=ult_nsu, max_nsu=max_nsu)


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
            log.info("CTeDistribuicaoDFe consulta ultNSU=%s", ult_nsu)
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
