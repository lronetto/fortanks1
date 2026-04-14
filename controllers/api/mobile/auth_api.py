"""
API REST de autenticação para o app mobile (Flutter).
Utiliza JWT (access + refresh tokens) em vez de sessão/cookie.
"""
import logging
from datetime import datetime, timezone

import jwt as pyjwt
from flask import request, jsonify, current_app, g
from sqlalchemy.orm import joinedload

from models.database import db
from models.usuario import Usuario
from models.colaborador import Colaborador
from utils.decorators import jwt_required

logger = logging.getLogger(__name__)

_tentativas_login: dict = {}
MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 15


def _verificar_bloqueio(email: str) -> bool:
    info = _tentativas_login.get(email)
    if not info:
        return False
    if info['tentativas'] >= MAX_TENTATIVAS:
        tempo_restante = info['bloqueado_ate'] - datetime.now(timezone.utc)
        if tempo_restante.total_seconds() > 0:
            return True
        del _tentativas_login[email]
    return False


def _registrar_tentativa_falha(email: str):
    from datetime import timedelta
    info = _tentativas_login.get(email, {'tentativas': 0, 'bloqueado_ate': None})
    info['tentativas'] += 1
    if info['tentativas'] >= MAX_TENTATIVAS:
        info['bloqueado_ate'] = datetime.now(timezone.utc) + timedelta(minutes=BLOQUEIO_MINUTOS)
    _tentativas_login[email] = info


def _limpar_tentativas(email: str):
    _tentativas_login.pop(email, None)


def _gerar_tokens(usuario: Usuario) -> dict:
    """Gera par access + refresh token para o usuário."""
    now = datetime.now(timezone.utc)

    access_payload = {
        'sub': str(usuario.id),
        'type': 'access',
        'iat': now,
        'exp': now + current_app.config['JWT_ACCESS_TOKEN_EXPIRES'],
    }
    refresh_payload = {
        'sub': str(usuario.id),
        'type': 'refresh',
        'iat': now,
        'exp': now + current_app.config['JWT_REFRESH_TOKEN_EXPIRES'],
    }

    import warnings
    secret = current_app.config['JWT_SECRET_KEY']
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        access_token = pyjwt.encode(access_payload, secret, algorithm='HS256')
        refresh_token = pyjwt.encode(refresh_payload, secret, algorithm='HS256')

    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'Bearer',
        'expires_in': int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds()),
    }


def _serializar_usuario(usuario: Usuario) -> dict:
    """Retorna dict com dados do usuário para resposta JSON."""
    return {
        'id': usuario.id,
        'nome': usuario.nome,
        'email': usuario.email,
        'departamento': usuario.departamento,
        'cargo': usuario.cargo,
        'departamento_id': usuario.departamento_id,
        'cargo_id': usuario.cargo_id,
        'colaborador_id': usuario.colaborador_id,
        'is_admin': usuario.is_admin,
        'criado_em': usuario.criado_em.isoformat() if usuario.criado_em else None,
        'ultimo_login': usuario.ultimo_login.isoformat() if usuario.ultimo_login else None,
    }


def register(bp):
    """Registra as rotas de autenticação mobile no blueprint fornecido."""

    @bp.route('/mobile/auth/login', methods=['POST'])
    def mobile_login():
        dados = request.get_json(silent=True)
        if not dados:
            return jsonify({'error': 'Corpo JSON obrigatório.'}), 400

        email = (dados.get('email') or '').strip().lower()
        senha = dados.get('senha') or ''

        if not email or not senha:
            return jsonify({'error': 'Email e senha são obrigatórios.'}), 400

        if _verificar_bloqueio(email):
            return jsonify({
                'error': f'Conta temporariamente bloqueada. Tente novamente em {BLOQUEIO_MINUTOS} minutos.',
            }), 429

        usuario = (
            Usuario.query
            .join(Colaborador, Usuario.colaborador_id == Colaborador.id)
            .options(joinedload(Usuario.colaborador))
            .filter(Usuario.email == email)
            .first()
        )

        if not usuario or not usuario.verificar_senha(senha):
            _registrar_tentativa_falha(email)
            return jsonify({'error': 'Email ou senha incorretos.'}), 401

        if usuario.colaborador and usuario.colaborador.status != 'Ativo':
            return jsonify({'error': 'Colaborador inativo. Contate o administrador.'}), 403

        if not Usuario.is_argon2_hash(usuario.senha):
            usuario.set_senha(senha)

        _limpar_tentativas(email)
        usuario.ultimo_login = datetime.now(timezone.utc)
        db.session.commit()

        tokens = _gerar_tokens(usuario)
        return jsonify({
            'usuario': _serializar_usuario(usuario),
            **tokens,
        })

    @bp.route('/mobile/auth/refresh', methods=['POST'])
    def mobile_refresh():
        dados = request.get_json(silent=True)
        refresh_token = (dados or {}).get('refresh_token', '')
        if not refresh_token:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                refresh_token = auth_header.split(' ', 1)[1]

        if not refresh_token:
            return jsonify({'error': 'Refresh token obrigatório.'}), 400

        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                payload = pyjwt.decode(
                    refresh_token,
                    current_app.config['JWT_SECRET_KEY'],
                    algorithms=['HS256'],
                )
        except pyjwt.ExpiredSignatureError:
            logger.warning("Refresh token expirado.")
            return jsonify({'error': 'Refresh token expirado. Faça login novamente.'}), 401
        except pyjwt.InvalidTokenError as e:
            logger.warning("Refresh token inválido: %s", e)
            return jsonify({'error': 'Refresh token inválido.'}), 401

        if payload.get('type') != 'refresh':
            return jsonify({'error': 'Tipo de token inválido.'}), 401

        usuario = Usuario.query.get(int(payload.get('sub')))
        if not usuario:
            return jsonify({'error': 'Usuário não encontrado.'}), 401

        tokens = _gerar_tokens(usuario)
        return jsonify(tokens)

    @bp.route('/mobile/auth/me', methods=['GET'])
    @jwt_required
    def mobile_me():
        usuario = g.usuario_atual
        return jsonify({'usuario': _serializar_usuario(usuario)})

    @bp.route('/mobile/auth/alterar-senha', methods=['POST'])
    @jwt_required
    def mobile_alterar_senha():
        usuario = g.usuario_atual
        dados = request.get_json(silent=True)
        if not dados:
            return jsonify({'error': 'Corpo JSON obrigatório.'}), 400

        senha_atual = dados.get('senha_atual', '')
        nova_senha = dados.get('nova_senha', '')
        confirmar_senha = dados.get('confirmar_senha', '')

        if not senha_atual or not nova_senha or not confirmar_senha:
            return jsonify({'error': 'Todos os campos são obrigatórios.'}), 400

        if not usuario.verificar_senha(senha_atual):
            return jsonify({'error': 'Senha atual incorreta.'}), 401

        if nova_senha != confirmar_senha:
            return jsonify({'error': 'As novas senhas não coincidem.'}), 400

        from utils.security import validate_password_strength
        valida, msg_erro = validate_password_strength(nova_senha)
        if not valida:
            return jsonify({'error': msg_erro}), 400

        usuario.set_senha(nova_senha)
        db.session.commit()

        tokens = _gerar_tokens(usuario)
        return jsonify({
            'message': 'Senha alterada com sucesso.',
            **tokens,
        })
