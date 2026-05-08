NOME_TABELA = "documentos_sefaz"

# Convenção de Upload.tipo (ver models/upload/constants.py).
# 11 = XML baixado da SEFAZ Distribuição DF-e / ADN.
UPLOAD_TIPO_XML = 11

# Chaves canônicas em DocumentoSefaz.dados_adicionais (JSON).
DA_UPLOAD_ID = "upload_id"
DA_SCHEMA = "schema"
DA_CNPJ_EMITENTE = "cnpj_emitente"
DA_CNPJ_DESTINATARIO = "cnpj_destinatario"
DA_TP_EVENTO = "tpEvento"
# 1 = XML já promovido para `NotaFiscal` com sucesso (ver nota_fiscal.services).
DA_INSERIDO = "inserido"

# Documento completo (XML no `upload_id`); distinto de resumo/evento.
TIPOS_DOCUMENTO_XML_COMPLETO = ("nfe", "cte", "nfse")
