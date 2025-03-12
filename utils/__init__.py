# utils/__init__.py

# Importações de db.py
from .db import get_db_connection

# Importações de auth.py
from .auth import verificar_permissao

# Importações de formatters.py
from .formatters import (
    format_currency,
    format_date,
    format_cnpj,
    format_cpf,
    truncate_text
)

# Importações de validators.py
from .validators import (
    is_valid_email,
    is_valid_cpf,
    is_valid_cnpj,
    is_valid_date,
    is_strong_password
)

# Importações de file_handlers.py
from .file_handlers import (
    save_uploaded_file,
    get_file_info,
    delete_file
)

# Exportar todas as funções
__all__ = [
    # db
    'get_db_connection',

    # auth
    'verificar_permissao',

    # formatters
    'format_currency',
    'format_date',
    'format_cnpj',
    'format_cpf',
    'truncate_text',

    # validators
    'is_valid_email',
    'is_valid_cpf',
    'is_valid_cnpj',
    'is_valid_date',
    'is_strong_password',

    # file_handlers
    'save_uploaded_file',
    'get_file_info',
    'delete_file'
]
