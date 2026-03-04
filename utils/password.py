"""
Utilitários de hash de senha.
Novas senhas usam Argon2id (argon2-cffi). Hashes antigos (scrypt/pbkdf2 do Werkzeug) continuam válidos.
"""
import logging
from werkzeug.security import check_password_hash as _werkzeug_check

logger = logging.getLogger(__name__)

# Hasher Argon2id (usado para novas senhas)
_argon2_hasher = None


def _get_argon2_hasher():
    global _argon2_hasher
    if _argon2_hasher is None:
        from argon2 import PasswordHasher
        _argon2_hasher = PasswordHasher()
    return _argon2_hasher


def hash_password(password: str) -> str:
    """Gera hash da senha com Argon2id. Use esta função para novas senhas."""
    return _get_argon2_hasher().hash(password)


def is_argon2_hash(pwhash: str) -> bool:
    """Retorna True se o hash armazenado é Argon2 (argon2id/argon2i/argon2d)."""
    return bool(pwhash and pwhash.strip().startswith("$argon2"))


def check_password(pwhash: str, password: str) -> bool:
    """
    Verifica se a senha confere com o hash armazenado.
    Aceita hashes Argon2id (novos) e scrypt/pbkdf2 do Werkzeug (legado).
    """
    if not pwhash or not password:
        return False
    pwhash = pwhash.strip()
    # Hash Argon2 (argon2id ou argon2i/d) começa com $argon2
    if pwhash.startswith("$argon2"):
        try:
            from argon2.exceptions import VerifyMismatchError, InvalidHashError
            _get_argon2_hasher().verify(pwhash, password)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False
        except Exception as e:
            logger.warning("Erro ao verificar hash Argon2: %s", e)
            return False
    # Legado: Werkzeug (scrypt, pbkdf2)
    return _werkzeug_check(pwhash, password)
