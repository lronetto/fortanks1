from functools import wraps
from flask import flash, redirect, url_for, abort, request, jsonify, current_app, g
from flask_login import current_user
import jwt as pyjwt

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


def jwt_required(f):
    """
    Decorador para proteger rotas da API mobile com JWT.
    Popula g.usuario_atual com a instância do Usuario autenticado.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        import logging
        _logger = logging.getLogger('jwt_required')

        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            _logger.warning("Token não fornecido. Authorization header: %r", auth_header[:50] if auth_header else '(vazio)')
            return jsonify({'error': 'Token não fornecido.'}), 401

        token = auth_header.split(' ', 1)[1]
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                payload = pyjwt.decode(
                    token,
                    current_app.config['JWT_SECRET_KEY'],
                    algorithms=['HS256'],
                )
        except pyjwt.ExpiredSignatureError:
            _logger.warning("Token expirado.")
            return jsonify({'error': 'Token expirado.'}), 401
        except pyjwt.InvalidTokenError as e:
            _logger.warning("Token inválido: %s", e)
            return jsonify({'error': 'Token inválido.'}), 401

        if payload.get('type') != 'access':
            _logger.warning("Tipo de token inválido: %s", payload.get('type'))
            return jsonify({'error': 'Tipo de token inválido.'}), 401

        from models.usuario import Usuario
        usuario = Usuario.query.get(int(payload.get('sub')))
        if not usuario:
            _logger.warning("Usuário não encontrado: sub=%s", payload.get('sub'))
            return jsonify({'error': 'Usuário não encontrado.'}), 401

        g.usuario_atual = usuario
        return f(*args, **kwargs)

    return wrapper