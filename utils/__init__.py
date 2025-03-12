# utils/__init__.py

# Centralização das importações
from .db import get_db_connection, execute_query, get_single_result, insert_data, update_data, db_cursor
from .auth import verificar_permissao, login_obrigatorio, admin_obrigatorio, get_user_id, verificar_login_api
from .validators import is_valid_email, is_valid_cpf, is_valid_cnpj, is_valid_date, is_strong_password
from .formatters import format_currency, format_date, format_cpf, format_cnpj, truncate_text
from .file_handlers import save_uploaded_file, get_file_info, delete_file
from .crypto import encrypt_password, decrypt_password, recrypt_password

# Lista de todas as funções exportadas
__all__ = [
    # Database
    'get_db_connection',
    'execute_query',
    'get_single_result',
    'insert_data',
    'update_data',
    'db_cursor',

    # Auth
    'verificar_permissao',
    'login_obrigatorio',
    'admin_obrigatorio',
    'get_user_id',
    'verificar_login_api',

    # Validators
    'is_valid_email',
    'is_valid_cpf',
    'is_valid_cnpj',
    'is_valid_date',
    'is_strong_password',

    # Formatters
    'format_currency',
    'format_date',
    'format_cpf',
    'format_cnpj',
    'truncate_text',

    # File Handlers
    'save_uploaded_file',
    'get_file_info',
    'delete_file',

    # Crypto
    'encrypt_password',
    'decrypt_password',
    'recrypt_password'
]
