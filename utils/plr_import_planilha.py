"""
Utilitário para leitura da planilha "Acompanhamento Mensal - MOD" e extração
das avaliações PLR por aba (formato MES ANO: ex. AGO 2025).
Cabeçalho na linha 32 (0-based: 31), dados a partir da linha 34 (0-based: 33).
Colunas: 0=CPF, 4=EQUIPE, 5=OBRA, 12=Assiduidade, 13=Zero Acidente,
         14=Segurança/Limpeza/Organização, 15=Prazo.
"""
import re
from datetime import date
from typing import List, Dict, Any, Optional, Tuple

# Mapeamento nome da aba -> (mes, ano). Ex: "AGO 2025" -> (8, 2025)
MESES_ABREV = {
    'JAN': 1, 'FEV': 2, 'MAR': 3, 'ABR': 4, 'MAI': 5, 'JUN': 6,
    'JUL': 7, 'AGO': 8, 'SET': 9, 'OUT': 10, 'NOV': 11, 'DEZ': 12,
}

# Linha do cabeçalho (0-based) e primeira linha de dados
HEADER_ROW = 31
DATA_START_ROW = 33

# Colunas (0-based)
COL_CPF = 0
COL_EQUIPE = 4
COL_OBRA = 5
COL_ASSIDUIDADE = 12
COL_ZERO_ACIDENTE = 13
COL_SEGURANCA = 14
COL_PRAZO = 15

# Critérios na ordem das colunas (tipo, peso %)
CRITERIOS = [
    ('Assiduidade', 0.30),
    ('Zero Acidente', 0.15),
    ('Segurança, Limpeza, Organização', 0.25),
    ('Prazo', 0.30),
]


def _normalizar_cpf(val: Any) -> Optional[str]:
    """Extrai apenas dígitos do CPF. Retorna None se vazio ou inválido."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() == 'nan':
        return None
    dig = re.sub(r'\D', '', s)
    return dig if len(dig) == 11 else None


def _parse_sheet_name(nome: str) -> Optional[Tuple[int, int]]:
    """Retorna (mes, ano) se a aba for no formato 'MES ANO' (ex: AGO 2025)."""
    nome = nome.strip().upper()
    match = re.match(r'^([A-Z]{3})\s*(\d{4})$', nome)
    if not match:
        return None
    mes_abrev, ano_str = match.groups()
    mes = MESES_ABREV.get(mes_abrev)
    if mes is None:
        return None
    try:
        ano = int(ano_str)
        if ano < 2000 or ano > 2100:
            return None
        return (mes, ano)
    except ValueError:
        return None


def _cell_value(book, sheet, row: int, col: int):
    """Retorna o valor da célula (row/col 0-based)."""
    if row >= sheet.nrows or col >= sheet.ncols:
        return None
    try:
        cell = sheet.cell(row, col)
        if cell.ctype == 2:  # number
            return cell.value
        if cell.ctype == 1:  # text
            return (cell.value or '').strip() or None
        if cell.ctype == 0:  # empty
            return None
        return cell.value
    except Exception:
        return None


def _valor_nota(val: Any) -> Optional[float]:
    """Converte valor da célula para nota (float 0-10 ou None)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            v = float(val)
            return v if 0 <= v <= 100 else None  # planilha pode vir 0-100 ou 0-10
        except (TypeError, ValueError):
            return None
    s = str(val).strip().replace(',', '.')
    if not s or s.lower() == 'nan':
        return None
    try:
        v = float(s)
        return v if v >= 0 else None
    except ValueError:
        return None


def ler_avaliacoes_planilha_xls(caminho: str) -> List[Dict[str, Any]]:
    """
    Lê arquivo .xls e retorna lista de avaliações, uma por linha de cada aba
    no formato MES ANO.
    Cada item: {
        'cpf': str (11 dígitos),
        'equipe': str ou None,
        'obra': str ou None (código ex: 0015-00),
        'data': date (primeiro dia do mês da aba),
        'avaliacao': [{'tipo': str, 'valor': float, 'peso': float}, ...],
        'sheet_name': str,
    }
    """
    import xlrd

    resultado = []
    with xlrd.open_workbook(caminho) as book:
        for sheet in book.sheets():
            parsed = _parse_sheet_name(sheet.name)
            if not parsed:
                continue
            mes, ano = parsed
            data_avaliacao = date(ano, mes, 1)

            for row_idx in range(DATA_START_ROW, sheet.nrows):
                cpf_raw = _cell_value(book, sheet, row_idx, COL_CPF)
                cpf = _normalizar_cpf(cpf_raw)
                if not cpf:
                    continue

                equipe = _cell_value(book, sheet, row_idx, COL_EQUIPE)
                if equipe is not None and isinstance(equipe, float):
                    equipe = str(int(equipe)) if equipe == int(equipe) else str(equipe)
                obra_raw = _cell_value(book, sheet, row_idx, COL_OBRA)
                obra = None
                if obra_raw is not None:
                    obra = str(obra_raw).strip() or None
                if obra is not None and isinstance(obra_raw, (int, float)):
                    obra = str(int(obra_raw)) if obra_raw == int(obra_raw) else str(obra_raw)

                v1 = _valor_nota(_cell_value(book, sheet, row_idx, COL_ASSIDUIDADE))*100 if _valor_nota(_cell_value(book, sheet, row_idx, COL_ASSIDUIDADE)) is not None else None
                v2 = _valor_nota(_cell_value(book, sheet, row_idx, COL_ZERO_ACIDENTE))*100 if _valor_nota(_cell_value(book, sheet, row_idx, COL_ZERO_ACIDENTE)) is not None else None
                v3 = _valor_nota(_cell_value(book, sheet, row_idx, COL_SEGURANCA))*100 if _valor_nota(_cell_value(book, sheet, row_idx, COL_SEGURANCA)) is not None else None
                v4 = _valor_nota(_cell_value(book, sheet, row_idx, COL_PRAZO))*100 if _valor_nota(_cell_value(book, sheet, row_idx, COL_PRAZO)) is not None else None

                avaliacao = []
                for (tipo, peso), val in zip(CRITERIOS, [v1, v2, v3, v4]):
                    if val is not None:
                        avaliacao.append({'tipo': tipo, 'valor': val, 'peso': peso})

                if not avaliacao:
                    continue

                resultado.append({
                    'cpf': cpf,
                    'equipe': equipe,
                    'obra': obra,
                    'data': data_avaliacao,
                    'avaliacao': avaliacao,
                    'sheet_name': sheet.name,
                })
    return resultado
