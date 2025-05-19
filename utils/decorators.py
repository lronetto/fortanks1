from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user

def role_required(roles):
    """
    Decorador para verificar se o usuário atual possui pelo menos uma das funções necessárias.
    
    Args:
        roles (list): Lista de funções permitidas para acessar a rota.
    
    Returns:
        function: Função decoradora que verifica as permissões.
    """
    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):
            # Verifica se o usuário está autenticado
            if not current_user.is_authenticated:
                flash('Por favor, faça login para acessar esta página.', 'warning')
                return redirect(url_for('auth.login'))
            
            # Verificação de permissões
            tem_permissao = False
            
            # Verifica se o usuário é admin (que tem acesso a tudo)
            if current_user.is_admin:
                tem_permissao = True
            
            # Verifica se o usuário é gerente ou superior e se 'gerente' está nas roles permitidas
            elif 'gerente' in roles and current_user.is_gerente_ou_superior:
                tem_permissao = True
            
            # Verifica se o cargo do usuário está na lista de cargos permitidos
            elif current_user.cargo in roles:
                tem_permissao = True
            
            # Se não tiver permissão, redireciona para página de acesso negado
            if not tem_permissao:
                flash('Você não tem permissão para acessar esta página.', 'danger')
                return redirect(url_for('index'))
            
            # Se tiver permissão, executa a função
            return view_function(*args, **kwargs)
        
        return wrapper
    
    return decorator 