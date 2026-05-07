"""
Domínio: Distribuição DF-e da SEFAZ + ADN NFS-e Nacional.

Modelo SEM acesso ao banco. Entrada: último NSU. Saída: LoteDownload
com arrays de XmlBaixado por tipo (NFe / CTe / NFSe), cada um com seu
próprio NSU.

A persistência (NotaFiscal, dados_adicionais, etc.) é responsabilidade
do orquestrador em `scripts.sefaz_distribuicao.orquestrador`.
"""
from .entities import LoteDownload, TipoDocumento, XmlBaixado
from .services.buscador import BuscadorXMLs
from .utils.cert_utils import CertificadoA1, materializar_pem

__all__ = [
    "BuscadorXMLs",
    "CertificadoA1",
    "LoteDownload",
    "TipoDocumento",
    "XmlBaixado",
    "materializar_pem",
]
