from functools import wraps
from flask import flash, redirect, url_for, abort, request, jsonify, current_app, g
from flask_login import current_user, login_required
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


def require_departamento(dept_ids):
    """
    Decorator para rotas que exigem que o usuário pertença a um departamento específico.

    Uso:
        @bp.route('/api/dados')
        @login_required
        @require_departamento([4])
        def dados():
            ...

    Args:
        dept_ids: Lista de IDs de departamento permitidos.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not (
                current_user.colaborador
                and current_user.colaborador.departamento_id in dept_ids
            ):
                return jsonify({'success': False, 'error': 'Acesso não autorizado para este recurso.'}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


def criar_verificacao_permissao(nivel: str = 'gerente'):
    """
    Fábrica que retorna a função verificar_permissao pronta para uso em before_request.

    Elimina o bloco repetido de 6 linhas nos blueprints.

    Uso no blueprint:
        from utils.decorators import criar_verificacao_permissao
        bp.before_request(login_required(criar_verificacao_permissao('gerente')))

    Args:
        nivel: 'gerente' → is_gerente_ou_superior | 'admin' → is_admin

    Retorna:
        Função verificar_permissao configurada para o nível especificado.
    """
    MENSAGEM = 'Acesso restrito. Você não tem permissão para acessar esta área.'

    def verificar_permissao():
        if nivel == 'admin':
            if not current_user.is_admin:
                flash(MENSAGEM, 'danger')
                return redirect(url_for('dashboard.index'))
        else:  # 'gerente' (padrão)
            if not current_user.is_gerente_ou_superior:
                flash(MENSAGEM, 'danger')
                return redirect(url_for('dashboard.index'))

    return verificar_permissao


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