from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
import logging
from models.database import db
from models.usuario import Usuario
from utils.password import is_argon2_hash
from models.colaborador import Colaborador
from extensions import limiter


auth_bp = Blueprint('auth', __name__)

logger = logging.getLogger(__name__)

_tentativas_login = {}
MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 15


def _is_safe_url(target):
    """Valida que a URL de redirecionamento é segura (interna)."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def _verificar_bloqueio(email):
    """Retorna True se o email está bloqueado por excesso de tentativas."""
    info = _tentativas_login.get(email)
    if not info:
        return False
    if info['tentativas'] >= MAX_TENTATIVAS:
        tempo_restante = info['bloqueado_ate'] - datetime.utcnow()
        if tempo_restante.total_seconds() > 0:
            return True
        del _tentativas_login[email]
    return False


def _registrar_tentativa_falha(email):
    info = _tentativas_login.get(email, {'tentativas': 0, 'bloqueado_ate': None})
    info['tentativas'] += 1
    if info['tentativas'] >= MAX_TENTATIVAS:
        info['bloqueado_ate'] = datetime.utcnow() + timedelta(minutes=BLOQUEIO_MINUTOS)
    _tentativas_login[email] = info


def _limpar_tentativas(email):
    _tentativas_login.pop(email, None)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        if not email or not senha:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('auth/login.html')
        
        if _verificar_bloqueio(email):
            flash(f'Conta temporariamente bloqueada. Tente novamente em {BLOQUEIO_MINUTOS} minutos.', 'danger')
            return render_template('auth/login.html'), 429
        
        usuario = Usuario.query.join(
            Colaborador, Usuario.colaborador_id == Colaborador.id
        ).filter(Usuario.email == email).first()
        
        if usuario and usuario.verificar_senha(senha):
            if usuario.colaborador.status != 'Ativo':
                flash('Colaborador inativo. Por favor, contate o administrador.', 'danger')
                return redirect(url_for('auth.login'))

            if not is_argon2_hash(usuario.senha):
                usuario.set_senha(senha)

            _limpar_tentativas(email)
            login_user(usuario)
            usuario.ultimo_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if next_page and _is_safe_url(next_page):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        else:
            _registrar_tentativa_falha(email or '')
            flash('Email ou senha incorretos.', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """
    Rota para logout de usuários
    """
    logout_user()
    flash('Você foi desconectado com sucesso.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/alterar-senha', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
@login_required
def alterar_senha():
    """
    Rota para alteração de senha
    """
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')
        
        # Validação básica
        if not senha_atual or not nova_senha or not confirmar_senha:
            flash('Por favor, preencha todos os campos.', 'danger')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Por favor, preencha todos os campos.'})
            return render_template('auth/alterar_senha.html')
        
        # Verifica se a senha atual está correta
        if not current_user.verificar_senha(senha_atual):
            flash('Senha atual incorreta.', 'danger')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Senha atual incorreta.'})
            return render_template('auth/alterar_senha.html')
        
        # Verifica se as novas senhas coincidem
        if nova_senha != confirmar_senha:
            flash('As novas senhas não coincidem.', 'danger')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'As novas senhas não coincidem.'})
            return render_template('auth/alterar_senha.html')
        
        from utils.security import validate_password_strength
        valida, msg_erro = validate_password_strength(nova_senha)
        if not valida:
            flash(msg_erro, 'danger')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': msg_erro})
            return render_template('auth/alterar_senha.html')
        
        current_user.set_senha(nova_senha)
        db.session.commit()
        
        flash('Senha alterada com sucesso.', 'success')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Senha alterada com sucesso.'})
        return redirect(url_for('dashboard.index'))
    
    return render_template('auth/alterar_senha.html') 