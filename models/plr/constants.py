"""Constantes do domínio PLR (nomes de tabelas alinhados a __tablename__).

Tabelas físicas (PascalCase, prefixo ``Plr``): ``PlrModelos``, ``PlrModelosDepartamentos``,
``PlrAvaliacoes``, ``PlrEfetivos``, ``PlrAssiduidades``.
"""

TABELA_PLR_MODELOS = "PlrModelos"
TABELA_PLR_MODELOS_DEPARTAMENTOS = "PlrModelosDepartamentos"
TABELA_PLR_AVALIACOES = "PlrAvaliacoes"
TABELA_PLR_EFETIVOS = "PlrEfetivos"
TABELA_PLR_ASSIDUIDADES = "PlrAssiduidades"

# --- Planilha "Acompanhamento Mensal - MOD" (importação .xls / .xlsx) ---
# Mapeamento nome da aba -> mês (ex.: "AGO 2025" -> agosto).
PLR_PLANILHA_MOD_MESES_ABREV = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}
# Dados a partir da linha 34 (1-based) => índice 0-based 33 (cabeçalho na linha 32).
PLR_PLANILHA_MOD_DATA_START_ROW_IDX = 33
PLR_PLANILHA_MOD_COL_CPF = 0
PLR_PLANILHA_MOD_COL_EQUIPE = 4
PLR_PLANILHA_MOD_COL_OBRA = 5
PLR_PLANILHA_MOD_COL_ASSIDUIDADE = 12
PLR_PLANILHA_MOD_COL_ZERO_ACIDENTE = 13
PLR_PLANILHA_MOD_COL_SEGURANCA = 14
PLR_PLANILHA_MOD_COL_PRAZO = 15
PLR_PLANILHA_MOD_CRITERIOS = (
    ("Assiduidade", 0.30),
    ("Zero Acidente", 0.15),
    ("Segurança, Limpeza, Organização", 0.25),
    ("Prazo", 0.30),
)

# --- Salário atualizado (planilha MOD, col. X): modo "grupo" na exportação ---
# Com o checkbox "Salário por grupo" ativo, o valor vem de ``CargoSalario`` na data de
# fechamento usando o cargo de *referência*, conforme o grupo do cargo vigente (FID).
# Ex.: ``CARGO_AJUDANTE = 10``, ``CARGOS_AJUDANTE = (4, 5, 6)`` → quem está no cargo 4
# usa a tabela de salários do cargo 10. Ajuste os IDs aos ``cargos`` do seu banco.
CARGO_OFICIAL= 3
CARGO_AJUDANTE= 1
CARGOS_OFICIAL= [3,11,12,13,14]
CARGOS_AJUDANTE= [1,2,7,18]
