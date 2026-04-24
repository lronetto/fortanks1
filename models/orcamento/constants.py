"""Constantes do domínio de orçamentos."""

TABELA_ORCAMENTOS = "Orcamentos"
TABELA_ITENS_ORCAMENTO = "OrcamentoItens"
TABELA_ITENS_ORCAMENTO_REFERENCIAS_MATERIAIS = "OrcamentoItensReferencias"

STATUS_ORCAMENTO_PADRAO = "Pendente"

# Configure os grupos usados no resumo de valores do orçamento.
GRUPOS_FABRICACAO = [
    # "FABRICACAO",
    
    "FABRICAÇÃO",
    "CONFECÇÃO",
    "CONFECÇÕES",
]

GRUPOS_MONTAGEM = [
    # "MONTAGEM",
    "CABEAMENTOS E TENSIONAMENTOS - MATERIAIS, FERRAM., EQUIPAM. e LOCAÇÕES",
    "SOLIDARIZAÇÃO - MATERIAIS, FERRAM., EQUIPAM. e LOCAÇÕES",
    "INJEÇÃO E ACABAMENTOS - MATERIAIS, FERRAM., EQUIPAM. e LOCAÇÕES",
    "MONTAGEM",
]

# Padrões na descrição do item (substring, case-insensitive).
# Têm prioridade sobre GRUPOS_* no resumo de valores.
PADROES_DESC_ITEM_FABRICACAO = [
    # "chapa",
    "FRETE",
]

PADROES_DESC_ITEM_MONTAGEM = [
    # "montagem",
]
