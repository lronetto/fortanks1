from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime

from models.database import db
from models.usuario import Usuario

usuario_bp = Blueprint('usuario', __name__)

# Middleware para verificar se o usuário tem permissão
@usuario_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_admin:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@usuario_bp.route('/')
@login_required
def index():
    """
    Lista todos os usuários
    """
    usuarios = Usuario.query.all()
    return render_template('usuarios/index.html', usuarios=usuarios)

@usuario_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cria um novo usuário
    """
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        departamento = request.form.get('departamento')
        cargo = request.form.get('cargo')
        
        # Validação básica
        if not nome or not email or not senha or not departamento or not cargo:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('usuarios/novo.html')
        
        # Verifica se o email já está em uso
        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente:
            flash('Este email já está em uso.', 'danger')
            return render_template('usuarios/novo.html')
        
        # Cria o novo usuário
        novo_usuario = Usuario(
            nome=nome,
            email=email,
            senha=generate_password_hash(senha),
            departamento=departamento,
            cargo=cargo
        )
        
        db.session.add(novo_usuario)
        db.session.commit()
        
        flash('Usuário criado com sucesso.', 'success')
        return redirect(url_for('usuario.index'))
    
    return render_template('usuarios/novo.html')

@usuario_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um usuário existente
    """
    usuario = Usuario.query.get_or_404(id)
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        departamento = request.form.get('departamento')
        cargo = request.form.get('cargo')
        
        # Validação básica
        if not nome or not email or not departamento or not cargo:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('usuarios/editar.html', usuario=usuario)
        
        # Verifica se o email já está em uso por outro usuário
        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente and usuario_existente.id != id:
            flash('Este email já está em uso.', 'danger')
            return render_template('usuarios/editar.html', usuario=usuario)
        
        # Atualiza o usuário
        usuario.nome = nome
        usuario.email = email
        usuario.departamento = departamento
        usuario.cargo = cargo
        
        db.session.commit()
        
        flash('Usuário atualizado com sucesso.', 'success')
        return redirect(url_for('usuario.index'))
    
    return render_template('usuarios/editar.html', usuario=usuario)

@usuario_bp.route('/resetar-senha/<int:id>', methods=['GET', 'POST'])
def resetar_senha(id):
    """
    Reseta a senha de um usuário
    """
    usuario = Usuario.query.get_or_404(id)
    
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')
        
        # Validação básica
        if not nova_senha or not confirmar_senha:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('usuarios/resetar_senha.html', usuario=usuario)
        
        # Verifica se as senhas coincidem
        if nova_senha != confirmar_senha:
            flash('As senhas não coincidem.', 'danger')
            return render_template('usuarios/resetar_senha.html', usuario=usuario)
        
        # Atualiza a senha
        usuario.senha = generate_password_hash(nova_senha)
        db.session.commit()
        
        flash('Senha resetada com sucesso.', 'success')
        return redirect(url_for('usuario.index'))
    
    return render_template('usuarios/resetar_senha.html', usuario=usuario)

@usuario_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um usuário
    """
    usuario = Usuario.query.get_or_404(id)
    
    # Não permite excluir o próprio usuário
    if usuario.id == current_user.id:
        flash('Você não pode excluir seu próprio usuário.', 'danger')
        return redirect(url_for('usuario.index'))
    
    db.session.delete(usuario)
    db.session.commit()
    
    flash('Usuário excluído com sucesso.', 'success')
    return redirect(url_for('usuario.index')) 