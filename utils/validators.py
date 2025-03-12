# utils/validators.py
import re
from datetime import datetime


def is_valid_email(email):
    """
    Valida se um email está no formato correto.

    Args:
        email: String com o email a ser validado.

    Returns:
        bool: True se o email é válido, False caso contrário.
    """
    if not email:
        return False

    # Expressão regular para validação básica de email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_cpf(cpf):
    """
    Valida se um CPF é válido (implementação básica).

    Args:
        cpf: String com o CPF a ser validado.

    Returns:
        bool: True se o CPF é válido, False caso contrário.
    """
    if not cpf:
        return False

    # Remove caracteres não numéricos
    cpf = ''.join(filter(str.isdigit, str(cpf)))

    # CPF deve ter 11 dígitos
    if len(cpf) != 11:
        return False

    # Verifica se todos os dígitos são iguais (caso inválido)
    if len(set(cpf)) == 1:
        return False

    # Validação básica - para validação completa seria necessário
    # implementar o algoritmo do dígito verificador
    return True


def is_valid_cnpj(cnpj):
    """
    Valida se um CNPJ é válido (implementação básica).

    Args:
        cnpj: String com o CNPJ a ser validado.

    Returns:
        bool: True se o CNPJ é válido, False caso contrário.
    """
    if not cnpj:
        return False

    # Remove caracteres não numéricos
    cnpj = ''.join(filter(str.isdigit, str(cnpj)))

    # CNPJ deve ter 14 dígitos
    if len(cnpj) != 14:
        return False

    # Verifica se todos os dígitos são iguais (caso inválido)
    if len(set(cnpj)) == 1:
        return False

    # Validação básica - para validação completa seria necessário
    # implementar o algoritmo do dígito verificador
    return True


def is_valid_date(date_str, format_str='%d/%m/%Y'):
    """
    Valida se uma string representa uma data válida no formato especificado.

    Args:
        date_str: String com a data a ser validada.
        format_str: Formato esperado da data.

    Returns:
        bool: True se a data é válida, False caso contrário.
    """
    if not date_str:
        return False

    try:
        datetime.strptime(date_str, format_str)
        return True
    except ValueError:
        return False


def is_strong_password(password):
    """
    Verifica se uma senha é forte, com pelo menos 8 caracteres,
    incluindo letras maiúsculas, minúsculas, números e caracteres especiais.

    Args:
        password: String com a senha a ser validada.

    Returns:
        bool: True se a senha é forte, False caso contrário.
    """
    if not password or len(password) < 8:
        return False

    # Verificar se contém pelo menos um caractere de cada tipo
    has_lowercase = bool(re.search(r'[a-z]', password))
    has_uppercase = bool(re.search(r'[A-Z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_special = bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password))

    return has_lowercase and has_uppercase and has_digit and has_special
