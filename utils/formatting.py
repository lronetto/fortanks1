"""
Helpers de formatação compartilhados entre controllers.

Evita o uso de .strftime() inline espalhado pelo código — importe daqui.
"""
from datetime import datetime, date as date_type


def formatar_data_br(data, incluir_hora: bool = False) -> str:
    """Retorna data no formato brasileiro DD/MM/YYYY (ou DD/MM/YYYY HH:MM com incluir_hora=True)."""
    if not data:
        return ''
    fmt = '%d/%m/%Y %H:%M' if incluir_hora else '%d/%m/%Y'
    return data.strftime(fmt)


def formatar_data_hora_br(data) -> str:
    """Atalho para formatar_data_br com hora incluída (DD/MM/YYYY HH:MM)."""
    return formatar_data_br(data, incluir_hora=True)


def formatar_data_hora_completa_br(data) -> str:
    """Retorna data e hora completa no formato DD/MM/YYYY HH:MM:SS."""
    if not data:
        return ''
    return data.strftime('%d/%m/%Y %H:%M:%S')


def formatar_data_iso(data) -> str:
    """Retorna data no formato ISO YYYY-MM-DD (útil para inputs type=date e ordenação)."""
    if not data:
        return ''
    return data.strftime('%Y-%m-%d')


def formatar_data_hora_iso(data) -> str:
    """Retorna data e hora no formato ISO YYYY-MM-DD HH:MM:SS."""
    if not data:
        return ''
    return data.strftime('%Y-%m-%d %H:%M:%S')


def formatar_moeda(valor, simbolo: bool = True) -> str:
    """
    Formata valor numérico como moeda brasileira.

    Exemplos:
        formatar_moeda(1234.5)    → 'R$ 1.234,50'
        formatar_moeda(1234.5, simbolo=False) → '1.234,50'
    """
    if valor is None:
        valor = 0
    try:
        formatado = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatado}" if simbolo else formatado
    except (TypeError, ValueError):
        return 'R$ 0,00' if simbolo else '0,00'
