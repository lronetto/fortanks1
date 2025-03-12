# utils/formatters.py
import locale
from datetime import datetime

# Definir localização para formatação de números e datas
locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')


def format_currency(value):
    """
    Formata um valor para moeda brasileira (R$).

    Args:
        value: Valor numérico a ser formatado.

    Returns:
        str: Valor formatado como moeda (R$ 1.234,56)
    """
    try:
        if value is None:
            return "R$ 0,00"
        return locale.currency(float(value), grouping=True, symbol='R$')
    except (ValueError, TypeError):
        return "R$ 0,00"


def format_date(date, format_str='%d/%m/%Y'):
    """
    Formata uma data no padrão brasileiro.

    Args:
        date: Objeto datetime ou string em formato ISO.
        format_str: String de formato (padrão: dia/mês/ano)

    Returns:
        str: Data formatada ou string vazia se inválida
    """
    if not date:
        return ""

    try:
        if isinstance(date, str):
            # Tenta converter de ISO para datetime
            date = datetime.fromisoformat(date.replace('Z', '+00:00'))
        return date.strftime(format_str)
    except (ValueError, TypeError, AttributeError):
        return ""


def format_cnpj(cnpj):
    """
    Formata uma string CNPJ para o formato padrão XX.XXX.XXX/XXXX-XX.

    Args:
        cnpj: String com os números do CNPJ.

    Returns:
        str: CNPJ formatado ou a string original se inválido
    """
    if not cnpj:
        return ""

    # Remove caracteres não numéricos
    cnpj = ''.join(filter(str.isdigit, str(cnpj)))

    if len(cnpj) != 14:
        return cnpj

    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def format_cpf(cpf):
    """
    Formata uma string CPF para o formato padrão XXX.XXX.XXX-XX.

    Args:
        cpf: String com os números do CPF.

    Returns:
        str: CPF formatado ou a string original se inválido
    """
    if not cpf:
        return ""

    # Remove caracteres não numéricos
    cpf = ''.join(filter(str.isdigit, str(cpf)))

    if len(cpf) != 11:
        return cpf

    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def truncate_text(text, max_length=100, add_ellipsis=True):
    """
    Trunca um texto para o tamanho máximo, adicionando reticências se necessário.

    Args:
        text: Texto a ser truncado.
        max_length: Comprimento máximo.
        add_ellipsis: Se True, adiciona '...' ao final.

    Returns:
        str: Texto truncado
    """
    if not text:
        return ""

    text = str(text)
    if len(text) <= max_length:
        return text

    truncated = text[:max_length].rstrip()
    if add_ellipsis:
        truncated += "..."

    return truncated
