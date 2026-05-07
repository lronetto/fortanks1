"""URLs e namespaces dos serviços SEFAZ Nacional / ADN."""

# --- NFe Distribuição DF-e -------------------------------------------------
URL_NFE_PROD = (
    "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
)
URL_NFE_HOMOLOG = (
    "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
)
NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_NFE_WSDL = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"
SOAP_ACTION_NFE = (
    "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
)

# --- CTe Distribuição DF-e -------------------------------------------------
URL_CTE_PROD = (
    "https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx"
)
URL_CTE_HOMOLOG = (
    "https://hom1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx"
)
NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_CTE_WSDL = "http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe"
SOAP_ACTION_CTE = (
    "http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe/cteDistDFeInteresse"
)

# --- ADN NFSe Nacional -----------------------------------------------------
URL_ADN_PROD = "https://adn.nfse.gov.br/contribuintes"
URL_ADN_HOMOLOG = "https://adn.producaorestrita.nfse.gov.br/contribuintes"

# --- Comuns ---------------------------------------------------------------
NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
