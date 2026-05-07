"""
Módulo para download de XMLs fiscais (NFe, CTe, NFSe) usando
certificado digital A1 (.pfx/.p12) da empresa.

Submódulos:
    cert_utils         - carregamento e uso do certificado A1
    nfe_distribuicao   - cliente SOAP do WS NFeDistribuicaoDFe
    cte_distribuicao   - cliente SOAP do WS CTeDistribuicaoDFe
    nfse_nacional      - cliente REST do ADN (NFSe Nacional)
    orquestrador       - função única que dispara as três consultas
"""

from .orquestrador import baixar_xmls_periodo

__all__ = ["baixar_xmls_periodo"]
