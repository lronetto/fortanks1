"""
Helpers de validação e normalização de dados de entrada.

Centraliza limpeza de CNPJ/CPF/telefone que era duplicada inline nos controllers.

Uso:
    from utils.validation import limpar_cnpj, limpar_cpf

    cnpj = limpar_cnpj(request.form.get('cnpj'))  # '12.345.678/0001-90' → '12345678000190'
"""


def limpar_cnpj(cnpj: str | None) -> str:
    """Remove máscara do CNPJ, retornando apenas os 14 dígitos."""
    return "".join(c for c in (cnpj or '') if c.isdigit())


def limpar_cpf(cpf: str | None) -> str:
    """Remove máscara do CPF, retornando apenas os 11 dígitos."""
    return "".join(c for c in (cpf or '') if c.isdigit())


def limpar_telefone(telefone: str | None) -> str:
    """Remove máscara de telefone, retornando apenas dígitos."""
    return "".join(c for c in (telefone or '') if c.isdigit())


def limpar_numero(valor: str | None) -> str:
    """Remove qualquer caractere não-dígito de um campo numérico."""
    return "".join(c for c in (valor or '') if c.isdigit())


def str_para_decimal(valor: str | None, default=None):
    """
    Converte string numérica para Decimal, aceitando vírgula como separador decimal.

    Exemplos:
        '1.234,56' → Decimal('1234.56')
        '1234.56'  → Decimal('1234.56')
    """
    from decimal import Decimal, InvalidOperation
    if not valor:
        return default
    try:
        normalizado = str(valor).strip().replace('.', '').replace(',', '.')
        return Decimal(normalizado)
    except (InvalidOperation, ValueError):
        return default


def str_para_float(valor: str | None, default=None):
    """
    Converte string numérica para float, aceitando vírgula como separador decimal.
    """
    resultado = str_para_decimal(valor, default=None)
    if resultado is None:
        return default
    return float(resultado)
