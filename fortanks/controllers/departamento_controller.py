from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime

from models.database import db
from models.departamento import Departamento

departamento_bp = Blueprint('departamento', __name__)

# Middleware para verificar se o usuário tem permissão
@departamento_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_admin:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@departamento_bp.route('/')
@login_required
def index():
    """
    Lista todos os departamentos
    """
    departamentos = Departamento.query.all()
    return render_template('departamentos/index.html', departamentos=departamentos)

@departamento_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cria um novo departamento
    """
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        status = request.form.get('status', 'Ativo')
        
        # Validação básica
        if not nome:
            flash('Por favor, informe o nome do departamento.', 'danger')
            return render_template('departamentos/novo.html')
        
        # Verifica se já existe um departamento com o mesmo nome
        departamento_existente = Departamento.query.filter_by(nome=nome).first()
        if departamento_existente:
            flash('Já existe um departamento com este nome.', 'danger')
            return render_template('departamentos/novo.html')
        
        # Cria o novo departamento
        novo_departamento = Departamento(
            nome=nome,
            descricao=descricao,
            status=status
        )
        
        novo_departamento.save()
        
        flash('Departamento criado com sucesso.', 'success')
        return redirect(url_for('departamento.index'))
    
    return render_template('departamentos/novo.html')

@departamento_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um departamento existente
    """
    departamento = Departamento.query.get_or_404(id)
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        status = request.form.get('status')
        
        # Validação básica
        if not nome:
            flash('Por favor, informe o nome do departamento.', 'danger')
            return render_template('departamentos/editar.html', departamento=departamento)
        
        # Verifica se já existe outro departamento com o mesmo nome
        departamento_existente = Departamento.query.filter_by(nome=nome).first()
        if departamento_existente and departamento_existente.id != id:
            flash('Já existe um departamento com este nome.', 'danger')
            return render_template('departamentos/editar.html', departamento=departamento)
        
        # Atualiza o departamento
        departamento.nome = nome
        departamento.descricao = descricao
        departamento.status = status
        departamento.atualizado_em = datetime.now()
        
        departamento.save()
        
        flash('Departamento atualizado com sucesso.', 'success')
        return redirect(url_for('departamento.index'))
    
    return render_template('departamentos/editar.html', departamento=departamento)

@departamento_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um departamento
    """
    departamento = Departamento.query.get_or_404(id)
    
    # Verificar se existem colaboradores vinculados ao departamento
    if departamento.colaboradores:
        flash('Não é possível excluir este departamento, pois existem colaboradores vinculados a ele.', 'danger')
        return redirect(url_for('departamento.index'))
    
    departamento.delete()
    
    flash('Departamento excluído com sucesso.', 'success')
    return redirect(url_for('departamento.index'))

@departamento_bp.route('/visualizar/<int:id>')
@login_required
def visualizar(id):
    """
    Visualiza os detalhes de um departamento
    """
    departamento = Departamento.query.get_or_404(id)
    return render_template('departamentos/visualizar.html', departamento=departamento) 