"""Parsing de XML fiscal (NF-e, CT-e, NFS-e)."""
from .xml_extracao import extrair_dados_xml_cte, extrair_dados_xml_nfe, extrair_dados_xml_nfse

__all__ = [
    "extrair_dados_xml_cte",
    "extrair_dados_xml_nfe",
    "extrair_dados_xml_nfse",
]
