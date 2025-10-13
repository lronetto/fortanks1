from functools import wraps
from flask import abort, request, redirect, url_for, flash
from flask_login import current_user
from models.permissoes import Permissao
import logging

logger = logging.getLogger(__name__)

def verificar_permissao(modulo, acao='visualizar'):
    """
    Decorator para verificar permissões de acesso a módulos
    
    Args:
        modulo (str): Nome do módulo
        acao (str): Ação a ser verificada (visualizar, criar, editar, excluir, exportar)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Se o usuário não está autenticado, redireciona para login
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Administradores têm acesso total
            if current_user.is_admin:
                return f(*args, **kwargs)
            
            # Verifica se o usuário tem permissão para o módulo e ação
            try:
                tem_permissao = Permissao.verificar_permissao_completa(current_user, modulo, acao)
                
                if not tem_permissao:
                    logger.warning(f"Usuário {current_user.email} tentou acessar {modulo} sem permissão")
                    flash(f'Você não tem permissão para {acao} o módulo {modulo}', 'error')
                    return abort(403)
                
                return f(*args, **kwargs)
                
            except Exception as e:
                logger.error(f"Erro ao verificar permissão: {str(e)}")
                flash('Erro ao verificar permissões', 'error')
                return abort(500)
        
        return decorated_function
    return decorator

def verificar_permissao_ajax(modulo, acao='visualizar'):
    """
    Decorator para verificar permissões em requisições AJAX
    
    Args:
        modulo (str): Nome do módulo
        acao (str): Ação a ser verificada
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Se o usuário não está autenticado
            if not current_user.is_authenticated:
                return {'error': 'Usuário não autenticado'}, 401
            
            # Administradores têm acesso total
            if current_user.is_admin:
                return f(*args, **kwargs)
            
            # Verifica se o usuário tem permissão para o módulo e ação
            try:
                tem_permissao = Permissao.verificar_permissao_completa(current_user, modulo, acao)
                
                if not tem_permissao:
                    logger.warning(f"Usuário {current_user.email} tentou acessar {modulo} via AJAX sem permissão")
                    return {'error': f'Sem permissão para {acao} o módulo {modulo}'}, 403
                
                return f(*args, **kwargs)
                
            except Exception as e:
                logger.error(f"Erro ao verificar permissão AJAX: {str(e)}")
                return {'error': 'Erro ao verificar permissões'}, 500
        
        return decorated_function
    return decorator

def verificar_permissao_template(modulo, acao='visualizar'):
    """
    Função para verificar permissões em templates
    
    Args:
        modulo (str): Nome do módulo
        acao (str): Ação a ser verificada
    
    Returns:
        bool: True se tem permissão, False caso contrário
    """
    if not current_user.is_authenticated:
        return False
    
    # Administradores têm acesso total
    if current_user.is_admin:
        return True
    
    try:
        return Permissao.verificar_permissao_completa(current_user, modulo, acao)
    except Exception as e:
        logger.error(f"Erro ao verificar permissão no template: {str(e)}")
        return False

def obter_modulos_permitidos():
    """
    Retorna lista de módulos que o usuário tem permissão de visualizar
    
    Returns:
        list: Lista de módulos permitidos
    """
    if not current_user.is_authenticated:
        return []
    
    # Administradores têm acesso a todos os módulos
    if current_user.is_admin:
        from models.permissoes import Modulo
        return Modulo.query.filter_by(status='Ativo').order_by(Modulo.ordem, Modulo.nome).all()
    
    try:
        from models.permissoes import Modulo
        modulos_permitidos = []
        modulos = Modulo.query.filter_by(status='Ativo').order_by(Modulo.ordem, Modulo.nome).all()
        
        for modulo in modulos:
            if Permissao.verificar_permissao_completa(current_user, modulo.nome, 'visualizar'):
                modulos_permitidos.append(modulo)
        
        return modulos_permitidos
    except Exception as e:
        logger.error(f"Erro ao obter módulos permitidos: {str(e)}")
        return []

def verificar_permissao_menu(modulo):
    """
    Função específica para verificar se um item de menu deve ser exibido
    
    Args:
        modulo (str): Nome do módulo
    
    Returns:
        bool: True se deve exibir o menu, False caso contrário
    """
    return verificar_permissao_template(modulo, 'visualizar')

