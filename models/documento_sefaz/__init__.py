"""
Domínio: documentos fiscais baixados da SEFAZ Distribuição DF-e / ADN.

Tabela leve com os dados principais (tipo, data, fornecedor, valor_total,
nsu, dados_adicionais, data_criacao, chave_acesso) + o XML armazenado
como `Upload` no MinIO (id referenciado em `dados_adicionais.upload_id`).

Uso:

    from models.documento_sefaz import DocumentoSefaz
    from models.documento_sefaz.services import processar_xml

    doc = processar_xml(xml_baixado)
"""
from .entities import DocumentoSefaz
from .services import processar_xml

__all__ = ["DocumentoSefaz", "processar_xml"]
