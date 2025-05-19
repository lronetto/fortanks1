from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime

from models.database import db
from models.centro_custo import CentroCusto

centro_custo_bp = Blueprint('centro_custo', __name__)

# Middleware para verificar se o usuário tem permissão
@centro_custo_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_gerente_ou_superior:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@centro_custo_bp.route('/')
def index():
    """
    Lista todos os centros de custo
    """
    centros_custo = CentroCusto.query.all()
    return render_template('centro_custo/index.html', centros_custo=centros_custo)

@centro_custo_bp.route('/novo', methods=['GET', 'POST'])
def novo():
    """
    Cria um novo centro de custo
    """
    if request.method == 'POST':
        codigo = request.form.get('codigo')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        ativo = 'ativo' in request.form
        
        # Validação básica
        if not codigo or not nome:
            flash('Por favor, preencha todos os campos obrigatórios.', 'danger')
            return render_template('centro_custo/novo.html')
        
        # Verifica se o código já está em uso
        centro_existente = CentroCusto.query.filter_by(codigo=codigo).first()
        if centro_existente:
            flash('Este código já está em uso.', 'danger')
            return render_template('centro_custo/novo.html')
        
        # Cria o novo centro de custo
        novo_centro = CentroCusto(
            codigo=codigo,
            nome=nome,
            descricao=descricao,
            ativo=ativo
        )
        
        db.session.add(novo_centro)
        db.session.commit()
        
        flash('Centro de custo criado com sucesso.', 'success')
        return redirect(url_for('centro_custo.index'))
    
    return render_template('centro_custo/novo.html')

@centro_custo_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """
    Edita um centro de custo existente
    """
    centro_custo = CentroCusto.query.get_or_404(id)
    
    if request.method == 'POST':
        codigo = request.form.get('codigo')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        ativo = 'ativo' in request.form
        
        # Validação básica
        if not codigo or not nome:
            flash('Por favor, preencha todos os campos obrigatórios.', 'danger')
            return render_template('centro_custo/editar.html', centro_custo=centro_custo)
        
        # Verifica se o código já está em uso por outro centro de custo
        centro_existente = CentroCusto.query.filter_by(codigo=codigo).first()
        if centro_existente and centro_existente.id != id:
            flash('Este código já está em uso.', 'danger')
            return render_template('centro_custo/editar.html', centro_custo=centro_custo)
        
        # Atualiza o centro de custo
        centro_custo.codigo = codigo
        centro_custo.nome = nome
        centro_custo.descricao = descricao
        centro_custo.ativo = ativo
        
        db.session.commit()
        
        flash('Centro de custo atualizado com sucesso.', 'success')
        return redirect(url_for('centro_custo.index'))
    
    return render_template('centro_custo/editar.html', centro_custo=centro_custo)

@centro_custo_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """
    Exclui um centro de custo
    """
    centro_custo = CentroCusto.query.get_or_404(id)
    
    # Verifica se o centro de custo está sendo usado em contratos ou solicitações
    if centro_custo.contratos or centro_custo.solicitacoes:
        flash('Este centro de custo não pode ser excluído pois está sendo usado em contratos ou solicitações.', 'danger')
        return redirect(url_for('centro_custo.index'))
    
    db.session.delete(centro_custo)
    db.session.commit()
    
    flash('Centro de custo excluído com sucesso.', 'success')
    return redirect(url_for('centro_custo.index'))

@centro_custo_bp.route('/listar-json')
@login_required
def listar_json():
    """
    Retorna uma lista de centros de custo em formato JSON para uso em selects
    """
    centros = CentroCusto.query.filter_by(ativo=True).all()
    resultado = []
    
    for centro in centros:
        resultado.append({
            'id': centro.id,
            'codigo': centro.codigo or '',
            'nome': centro.nome or '',
            'descricao': centro.descricao or ''
        })
    
    return jsonify(resultado)