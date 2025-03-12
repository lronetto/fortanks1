from flask import session, redirect, url_for, flash, request, jsonify
from functools import wraps
import logging

# Configurar logger
logger = logging.getLogger(__name__)


def verificar_permissao(nivel_permissao):
    """
    Verifica se o usuário logado tem a permissão necessária

    Args:
        nivel_permissao (str): Nível de permissão requerido

    Returns:
        bool: True se o usuário tem permissão, False caso contrário
    """
    # Se não está logado, não tem permissão
    if 'usuario_id' not in session:
        return False

    # Verifica o cargo do usuário (simplificado)
    cargo = session.get('cargo', '')

    # Lógica simplificada de permissões
    if cargo == 'admin':
        # Administradores têm todas as permissões
        return True
    elif cargo == 'gerente':
        # Gerentes têm permissões específicas
        if nivel_permissao in ['visualizar', 'editar', 'relatorio']:
            return True
    elif cargo == 'supervisor':
        # Supervisores só podem visualizar e gerar relatórios
        if nivel_permissao in ['visualizar', 'relatorio']:
            return True
    elif cargo == 'usuario':
        # Usuários comuns só podem visualizar
        if nivel_permissao == 'visualizar':
            return True

    return False


def login_obrigatorio(view_func):
    """
    Decorador que requer que o usuário esteja logado

    Args:
        view_func (function): A função de visualização a ser decorada

    Returns:
        function: A função decorada que verifica login
    """
    @wraps(view_func)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Por favor, faça login para acessar esta página', 'warning')
            return redirect(url_for('login', next=request.url))
        return view_func(*args, **kwargs)
    return decorated_function


def admin_obrigatorio(view_func):
    """
    Decorador que requer que o usuário seja administrador

    Args:
        view_func (function): A função de visualização a ser decorada

    Returns:
        function: A função decorada que verifica se o usuário é admin
    """
    @wraps(view_func)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Por favor, faça login para acessar esta página', 'warning')
            return redirect(url_for('login', next=request.url))

        if session.get('cargo') != 'admin':
            flash('Você não tem permissão para acessar esta página', 'danger')
            return redirect(url_for('dashboard'))

        return view_func(*args, **kwargs)
    return decorated_function


def verificar_login_api():
    """
    Verifica se o usuário está logado para uso em REST API

    Returns:
        tuple: (logado, response) onde:
            - logado (bool): True se o usuário está logado, False caso contrário
            - response (Response): Objeto de resposta em caso de erro, None se estiver logado
    """
    if 'usuario_id' not in session:
        return False, jsonify({
            'status': 'error',
            'message': 'Não autorizado. Faça login para continuar.',
            'code': 401
        })
    return True, None


def get_user_id():
    """
    Retorna o ID do usuário logado

    Returns:
        int: ID do usuário logado ou None se não estiver logado
    """
    return session.get('usuario_id')
