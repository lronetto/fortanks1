"""Leitura de cabeçalhos e CPF para importação de assiduidade (planilha PLR)."""

from models.colaborador import Colaborador

from .planilha_plr_calculo import MESES_ABREV


def parse_meses_do_header(header_row):
    """
    Lê os cabeçalhos da planilha (a partir da coluna 3) e retorna lista [(mes, ano), ...]
    extraídos de rótulos como 'JAN 2025', 'FEV 2025', 'MAR/2025', '01/2025', etc.
    """
    abrev_to_num = {abrev: i + 1 for i, abrev in enumerate(MESES_ABREV)}
    meses = []
    for cell_val in (header_row[2:] if len(header_row) > 2 else []):
        if cell_val is None:
            continue
        txt = str(cell_val).strip().upper()
        if not txt:
            continue
        parts = txt.replace('/', ' ').replace('-', ' ').split()
        if len(parts) == 2:
            label, ano_str = parts[0], parts[1]
            try:
                ano = int(ano_str)
            except ValueError:
                continue
            if label in abrev_to_num:
                meses.append((abrev_to_num[label], ano))
            else:
                try:
                    m = int(label)
                    if 1 <= m <= 12:
                        meses.append((m, ano))
                except ValueError:
                    continue
    return meses


def normalizar_cpf(cpf):
    """Retorna CPF apenas com dígitos para comparação."""
    if cpf is None:
        return ''
    return ''.join(c for c in str(cpf) if c.isdigit())


def mapa_cpf_colaborador():
    """Retorna dict cpf_normalizado -> Colaborador para todos os colaboradores."""
    colabs = Colaborador.query.all()
    return {normalizar_cpf(c.cpf): c for c in colabs if normalizar_cpf(c.cpf)}
