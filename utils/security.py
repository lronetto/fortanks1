"""
Utilitários de segurança centralizados.
Validação de URLs, sanitização de uploads e helpers de proteção.
"""
import re
from urllib.parse import urlparse, urljoin
from flask import request, current_app
from werkzeug.utils import secure_filename


def is_safe_redirect_url(target: str) -> bool:
    """
    Valida que uma URL de redirecionamento é segura (pertence ao mesmo host).
    Previne ataques de Open Redirect.
    """
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def is_allowed_file(filename: str) -> bool:
    """Verifica se o arquivo tem extensão permitida (whitelist)."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    return ext in allowed


def sanitize_filename(filename: str) -> str:
    """Retorna nome de arquivo seguro usando Werkzeug."""
    return secure_filename(filename) or 'arquivo'


def validate_password_strength(senha: str) -> tuple[bool, str]:
    """
    Valida complexidade da senha.
    Retorna (valida, mensagem_erro).
    """
    min_length = current_app.config.get('PASSWORD_MIN_LENGTH', 10)

    if len(senha) < min_length:
        return False, f'A senha deve ter pelo menos {min_length} caracteres.'
    if not re.search(r'[A-Z]', senha):
        return False, 'A senha deve conter pelo menos uma letra maiúscula.'
    if not re.search(r'[a-z]', senha):
        return False, 'A senha deve conter pelo menos uma letra minúscula.'
    if not re.search(r'\d', senha):
        return False, 'A senha deve conter pelo menos um número.'
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;\'`~]', senha):
        return False, 'A senha deve conter pelo menos um caractere especial.'

    return True, ''
