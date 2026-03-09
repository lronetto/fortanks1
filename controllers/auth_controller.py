from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
import logging
from models.database import db
from models.usuario import Usuario
from utils.password import is_argon2_hash
from models.colaborador import Colaborador


auth_bp = Blueprint('auth', __name__)

logger = logging.getLogger(__name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Rota para login de usuários
    """
    logger.info('Login de usuário')
    # Se o usuário já estiver logado, redireciona para o dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        # Validação básica
        if not email or not senha:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('auth/login.html')
        
        # Busca o usuário pelo email
        usuario = Usuario.query.join(Colaborador, Usuario.colaborador_id == Colaborador.id).filter(Usuario.email==email).first()
        print(f'usuario: {usuario} email: {email} senha: {senha}')
        
        # Verifica se o usuário existe e se a senha está correta
        if usuario and usuario.verificar_senha(senha):
            if usuario.colaborador.status != 'Ativo':
                flash('Colaborador inativo. Por favor, contate o administrador.', 'danger')
                return redirect(url_for('auth.login'))
            # Migra hash legado (scrypt/pbkdf2) para Argon2id no próximo login
            if not is_argon2_hash(usuario.senha):
                usuario.set_senha(senha)
            # Realiza o login
            login_user(usuario)
            # Atualiza a data do último login
            usuario.ultimo_login = datetime.utcnow()
            db.session.commit()
            
            # Redireciona para a página solicitada ou para o dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        else:
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
        
        # Atualiza a senha
        current_user.set_senha(nova_senha)
        db.session.commit()
        
        flash('Senha alterada com sucesso.', 'success')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Senha alterada com sucesso.'})
        return redirect(url_for('dashboard.index'))
    
    return render_template('auth/alterar_senha.html') 