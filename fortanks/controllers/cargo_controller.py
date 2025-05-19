from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime

from models.database import db
from models.cargo import Cargo

cargo_bp = Blueprint('cargo', __name__)

# Middleware para verificar se o usuário tem permissão
@cargo_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_admin:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@cargo_bp.route('/')
@login_required
def index():
    """
    Lista todos os cargos
    """
    cargos = Cargo.query.all()
    return render_template('cargos/index.html', cargos=cargos)

@cargo_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cria um novo cargo
    """
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        status = request.form.get('status', 'Ativo')
        
        # Validação básica
        if not nome:
            flash('Por favor, informe o nome do cargo.', 'danger')
            return render_template('cargos/novo.html')
        
        # Verifica se já existe um cargo com o mesmo nome
        cargo_existente = Cargo.query.filter_by(nome=nome).first()
        if cargo_existente:
            flash('Já existe um cargo com este nome.', 'danger')
            return render_template('cargos/novo.html')
        
        # Cria o novo cargo
        novo_cargo = Cargo(
            nome=nome,
            descricao=descricao,
            status=status
        )
        
        novo_cargo.save()
        
        flash('Cargo criado com sucesso.', 'success')
        return redirect(url_for('cargo.index'))
    
    return render_template('cargos/novo.html')

@cargo_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um cargo existente
    """
    cargo = Cargo.query.get_or_404(id)
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        status = request.form.get('status')
        
        # Validação básica
        if not nome:
            flash('Por favor, informe o nome do cargo.', 'danger')
            return render_template('cargos/editar.html', cargo=cargo)
        
        # Verifica se já existe outro cargo com o mesmo nome
        cargo_existente = Cargo.query.filter_by(nome=nome).first()
        if cargo_existente and cargo_existente.id != id:
            flash('Já existe um cargo com este nome.', 'danger')
            return render_template('cargos/editar.html', cargo=cargo)
        
        # Atualiza o cargo
        cargo.nome = nome
        cargo.descricao = descricao
        cargo.status = status
        cargo.atualizado_em = datetime.now()
        
        cargo.save()
        
        flash('Cargo atualizado com sucesso.', 'success')
        return redirect(url_for('cargo.index'))
    
    return render_template('cargos/editar.html', cargo=cargo)

@cargo_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um cargo
    """
    cargo = Cargo.query.get_or_404(id)
    
    # Verificar se existem colaboradores vinculados ao cargo
    if cargo.colaboradores:
        flash('Não é possível excluir este cargo, pois existem colaboradores vinculados a ele.', 'danger')
        return redirect(url_for('cargo.index'))
    
    cargo.delete()
    
    flash('Cargo excluído com sucesso.', 'success')
    return redirect(url_for('cargo.index'))

@cargo_bp.route('/visualizar/<int:id>')
@login_required
def visualizar(id):
    """
    Visualiza os detalhes de um cargo
    """
    cargo = Cargo.query.get_or_404(id)
    return render_template('cargos/visualizar.html', cargo=cargo) 