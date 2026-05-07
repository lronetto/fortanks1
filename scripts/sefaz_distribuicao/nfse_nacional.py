"""
Cliente do ADN (Ambiente de Dados Nacional) - NFS-e Nacional.

LIMITAÇÃO IMPORTANTE: o ADN só atende a empresa quando o município de
incidência ISS é aderente ao Sistema Nacional NFS-e. Para municípios
fora do convênio, é necessário integrar com o webservice do próprio
município (não há padrão único - existem dezenas de provedores
diferentes: GINFES, ISSNet, ABRASF 2.x, próprios de SP/RJ/etc.).

Endpoints:
  Produção          : https://adn.nfse.gov.br/contribuintes/
  Produção restrita : https://adn.producaorestrita.nfse.gov.br/contribuintes/

Autenticação: mTLS com certificado A1/A3 ICP-Brasil (CNPJ do contribuinte
deve estar no certificado).
"""

from __future__ import annotations

import base64
import gzip
import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Literal, Optional

import requests

from .cert_utils import CertificadoA1, materializar_pem

log = logging.getLogger(__name__)

URL_PROD = "https://adn.nfse.gov.br/contribuintes"
URL_HOMOLOG = "https://adn.producaorestrita.nfse.gov.br/contribuintes"

Papel = Literal["PRESTADOR", "TOMADOR", "INTERMEDIARIO"]


@dataclass
class NFSe:
    chave_acesso: str
    papel: Papel
    xml: str


def _base_url(ambiente: int) -> str:
    return URL_PROD if ambiente == 1 else URL_HOMOLOG


def listar_chaves(
    cert: CertificadoA1,
    cnpj: str,
    data_inicial: date,
    data_final: date,
    *,
    papel: Papel = "TOMADOR",
    ambiente: int = 1,
    timeout: int = 60,
) -> List[str]:
    """
    Lista chaves de acesso das NFS-e em que o CNPJ é prestador / tomador /
    intermediário no intervalo informado.
    """
    base = _base_url(ambiente)
    url = f"{base}/NFSe"
    params = {
        "dEmiInicial": data_inicial.isoformat(),
        "dEmiFinal": data_final.isoformat(),
        "papel": papel,
        "inscricao": cnpj,
    }

    with materializar_pem(cert) as (cert_path, key_path):
        resp = requests.get(
            url,
            params=params,
            headers={"Accept": "application/json"},
            cert=(cert_path, key_path),
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()

    chaves: List[str] = []
    for item in payload if isinstance(payload, list) else payload.get("nfses", []):
        chave = item.get("chaveAcesso") or item.get("chave")
        if chave:
            chaves.append(chave)
    return chaves


def baixar_xml(
    cert: CertificadoA1,
    chave_acesso: str,
    *,
    ambiente: int = 1,
    timeout: int = 60,
) -> str:
    """Baixa o XML completo da NFSe pela chave de acesso."""
    base = _base_url(ambiente)
    url = f"{base}/NFSe/{chave_acesso}"

    with materializar_pem(cert) as (cert_path, key_path):
        resp = requests.get(
            url,
            headers={"Accept": "application/json"},
            cert=(cert_path, key_path),
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()

    if isinstance(body, dict):
        gz_b64 = body.get("xmlNFSe") or body.get("xml") or body.get("conteudo")
    else:
        gz_b64 = body
    if not gz_b64:
        raise RuntimeError(f"Resposta sem XML para chave {chave_acesso}: {body!r}")
    return gzip.decompress(base64.b64decode(gz_b64)).decode("utf-8")


def baixar_periodo(
    cert: CertificadoA1,
    cnpj: str,
    data_inicial: date,
    data_final: date,
    *,
    ambiente: int = 1,
    papeis: Optional[List[Papel]] = None,
    timeout: int = 60,
) -> List[NFSe]:
    """
    Baixa todas as NFS-e (emitidas pela empresa = papel PRESTADOR; emitidas
    contra a empresa = papel TOMADOR/INTERMEDIARIO) no período.
    """
    if papeis is None:
        papeis = ["PRESTADOR", "TOMADOR", "INTERMEDIARIO"]

    notas: List[NFSe] = []
    vistos: set[str] = set()
    for papel in papeis:
        log.info("ADN listar chaves papel=%s [%s..%s]", papel, data_inicial, data_final)
        chaves = listar_chaves(
            cert,
            cnpj,
            data_inicial,
            data_final,
            papel=papel,
            ambiente=ambiente,
            timeout=timeout,
        )
        for chave in chaves:
            if chave in vistos:
                continue
            vistos.add(chave)
            xml = baixar_xml(cert, chave, ambiente=ambiente, timeout=timeout)
            notas.append(NFSe(chave_acesso=chave, papel=papel, xml=xml))
    return notas
