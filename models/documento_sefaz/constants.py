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
