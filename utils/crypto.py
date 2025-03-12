"""
Utilitário para criptografia segura de dados sensíveis como senhas de ERP.

Este módulo implementa criptografia simétrica usando Fernet (AES-128 em modo CBC)
que permite criptografar e descriptografar dados de forma segura.
"""

import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv

# Configurar logging
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

# Chave secreta para criptografia - obtida do ambiente ou gerada


def get_encryption_key():
    """
    Obtém a chave de criptografia do ambiente ou gera uma nova se não existir.

    Esta função verifica se existe uma chave no arquivo .env, caso contrário
    gera uma nova chave e orienta o usuário a salvá-la.

    Retorna:
        bytes: Chave de criptografia em formato bytes
    """
    key = os.environ.get('ENCRYPTION_KEY')

    if not key:
        # Gerar uma nova chave se não existir
        logger.warning(
            "Chave de criptografia não encontrada no ambiente. Gerando nova chave.")
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(os.urandom(32)))
        logger.warning(
            "IMPORTANTE: Adicione a seguinte linha ao seu arquivo .env:\n"
            f"ENCRYPTION_KEY={key.decode()}\n"
            "Esta chave é necessária para descriptografar senhas existentes."
        )
    else:
        try:
            # Converter a chave de string para bytes
            key = key.encode() if isinstance(key, str) else key
        except Exception as e:
            logger.error(f"Erro ao processar a chave de criptografia: {e}")
            # Fallback para uma chave temporária (não recomendado para produção)
            key = Fernet.generate_key()

    return key

# Inicializar Fernet com a chave


def get_cipher():
    """
    Inicializa e retorna o objeto Fernet para criptografia/descriptografia.

    Retorna:
        Fernet: Objeto Fernet para operações de criptografia
    """
    try:
        key = get_encryption_key()
        return Fernet(key)
    except Exception as e:
        logger.error(f"Erro ao inicializar Fernet: {e}")
        raise


def encrypt_password(senha):
    """
    Criptografa uma senha usando Fernet (AES).

    Args:
        senha (str): Senha em texto plano

    Returns:
        str: Senha criptografada em formato base64
    """
    if not senha:
        return ""

    try:
        cipher = get_cipher()
        senha_bytes = senha.encode('utf-8')
        senha_criptografada = cipher.encrypt(senha_bytes)
        return senha_criptografada.decode('utf-8')
    except Exception as e:
        logger.error(f"Erro ao criptografar senha: {e}")
        # Fallback para o método antigo em caso de erro (temporário)
        return base64.b64encode(senha.encode('utf-8')).decode('utf-8')


def decrypt_password(senha_criptografada):
    """
    Descriptografa uma senha criptografada usando Fernet (AES).

    Args:
        senha_criptografada (str): Senha criptografada em formato base64

    Returns:
        str: Senha em texto plano
    """
    if not senha_criptografada:
        return ""

    try:
        # Tentar descriptografar com Fernet
        cipher = get_cipher()
        senha_bytes = senha_criptografada.encode('utf-8')
        senha_descriptografada = cipher.decrypt(senha_bytes)
        return senha_descriptografada.decode('utf-8')
    except Exception as e:
        logger.error(f"Erro ao descriptografar com Fernet: {e}")

        # Tentar descriptografar com o método antigo (base64)
        try:
            return base64.b64decode(senha_criptografada).decode('utf-8')
        except Exception as e2:
            logger.error(f"Erro ao descriptografar com base64: {e2}")
            return ""


def recrypt_password(senha_criptografada_antiga):
    """
    Converte uma senha do formato antigo (base64) para o novo formato (Fernet).

    Esta função é útil para migrar senhas existentes para o novo sistema
    mais seguro.

    Args:
        senha_criptografada_antiga (str): Senha no formato antigo

    Returns:
        str: Senha recriptografada no novo formato
    """
    if not senha_criptografada_antiga:
        return ""

    try:
        # Descriptografar com método antigo
        senha_plana = ""
        try:
            senha_plana = base64.b64decode(
                senha_criptografada_antiga).decode('utf-8')
        except:
            # Se não conseguir descriptografar com base64, tenta com Fernet
            try:
                senha_plana = decrypt_password(senha_criptografada_antiga)
            except:
                logger.error(
                    "Não foi possível descriptografar a senha para recriptografar.")
                return senha_criptografada_antiga

        # Criptografar com método novo
        if senha_plana:
            return encrypt_password(senha_plana)
        return senha_criptografada_antiga
    except Exception as e:
        logger.error(f"Erro ao recriptografar senha: {e}")
        return senha_criptografada_antiga
