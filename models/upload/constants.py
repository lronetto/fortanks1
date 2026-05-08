"""Constantes do domínio de arquivos (tabela `Uploads`)."""

TIPOS_UPLOAD = {
    0: "nao definido",
    1: "arquivei",
    2: "protocolo",
    3: "reembolso",
    4: "avulso",
    5: "certificado",
    6: "DUA",
    8: "foto equipamento",
    9: "imagem material",
    10: "foto transporte tanques",
    11: "xml sefaz distribuicao",
    12: "xml nota fiscal",
}
# tipo
# 0 - nao definido
# 1 - arquivei
# 2 - protocolo
# 3 - reembolso
# 4 - avulso
# 5 - certificado
# 6 - DUA
# 8 - foto equipamento (patrimônio / models.equipamento)
# 9 - imagem de cadastro de material (Materiais.dados_adicionais.imagem_upload_id)
# 10 - foto opcional do registro de transporte (TanquesTransportes.dados_adicionais.foto_upload_id)
# 11 - XML baixado da SEFAZ Distribuição DF-e / ADN (DocumentoSefaz.dados_adicionais.upload_id)
# 12 - XML da NF-e/CT-e/NFSe (`NotaFiscal.dados_adicionais.xml_upload_id`)

TIPO_UPLOAD_XML_NOTA_FISCAL = 12

NOME_TABELA = "Uploads"
