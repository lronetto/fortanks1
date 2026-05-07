"""
Download de XMLs fiscais (NFe, CTe, NFSe) usando o certificado A1 da
empresa, integrado ao pipeline `models.nota_fiscal.NotaFiscal`.

Submódulos:
    cert_utils         - carregamento e uso do certificado A1 (.pfx/.p12)
    nfe_distribuicao   - cliente SOAP do WS NFeDistribuicaoDFe
    cte_distribuicao   - cliente SOAP do WS CTeDistribuicaoDFe
    nfse_nacional      - cliente REST do ADN (NFSe Nacional)
    orquestrador       - função `baixar_e_importar` que faz o pipeline completo
"""

from .orquestrador import Resumo, baixar_e_importar

__all__ = ["Resumo", "baixar_e_importar"]
