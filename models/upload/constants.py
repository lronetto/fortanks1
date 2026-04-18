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

NOME_TABELA = "Uploads"
