from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import or_

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
    return render_template('admin/cadastros/departamentos/index.html')

@departamento_bp.route('/api/datatables', methods=['GET'])
@login_required
def api_datatables():
    """
    Endpoint AJAX para DataTables - retorna departamentos em formato JSON
    """
    try:
        draw = request.args.get('draw', 1, type=int)
        start = request.args.get('start', 0, type=int)
        length = request.args.get('length', 25, type=int)
        search_value = request.args.get('search[value]', '', type=str).strip()

        order_column_index = request.args.get('order[0][column]', '0', type=int)
        order_dir = request.args.get('order[0][dir]', 'desc')

        column_mapping = {
            0: Departamento.id,
            1: Departamento.nome,
            2: Departamento.descricao,
            3: Departamento.status,
            4: Departamento.criado_em,
        }

        query = Departamento.query

        if search_value:
            query = query.filter(
                or_(
                    Departamento.nome.ilike(f'%{search_value}%'),
                    Departamento.descricao.ilike(f'%{search_value}%'),
                    Departamento.status.ilike(f'%{search_value}%'),
                )
            )

        total_records = Departamento.query.count()
        records_filtered = query.count()

        order_column = column_mapping.get(order_column_index, Departamento.id)
        if order_dir == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        departamentos = query.offset(start).limit(length).all()

        data = []
        for dep in departamentos:
            badge = (
                '<span class="badge bg-success">Ativo</span>'
                if dep.status == 'Ativo'
                else '<span class="badge bg-danger">Inativo</span>'
            )

            criado_em = dep.criado_em.strftime('%d/%m/%Y %H:%M') if dep.criado_em else ''
            atualizado_em = dep.atualizado_em.strftime('%d/%m/%Y %H:%M') if dep.atualizado_em else ''

            acoes = (
                f'<div class="ft-acoes-dropdown dropdown">'
                f'<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false" title="Ações"><i class="fas fa-ellipsis-v"></i></button>'
                f'<ul class="dropdown-menu dropdown-menu-end">'
                f'<li><button type="button" class="dropdown-item btn-visualizar"'
                f' data-id="{dep.id}" data-nome="{dep.nome}"'
                f' data-descricao="{dep.descricao or "N/A"}" data-status="{dep.status}"'
                f' data-status-badge=\'{badge}\' data-criado="{criado_em}" data-atualizado="{atualizado_em}">'
                f'<i class="fas fa-eye text-info"></i> Visualizar</button></li>'
                f'<li><button type="button" class="dropdown-item btn-editar"'
                f' data-id="{dep.id}" data-nome="{dep.nome}"'
                f' data-descricao="{dep.descricao or ""}" data-status="{dep.status}">'
                f'<i class="fas fa-edit text-primary"></i> Editar</button></li>'
                f'<li><hr class="dropdown-divider"></li>'
                f'<li><button type="button" class="dropdown-item text-danger btn-excluir"'
                f' data-id="{dep.id}" data-nome="{dep.nome}">'
                f'<i class="fas fa-trash text-danger"></i> Excluir</button></li>'
                f'</ul></div>'
            )

            data.append({
                'id': dep.id,
                'nome': dep.nome,
                'descricao': dep.descricao or 'N/A',
                'status': badge,
                'criado_em': criado_em,
                'acoes': acoes,
            })

        return jsonify({
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': records_filtered,
            'data': data,
        })
    except Exception as e:
        return jsonify({
            'draw': 1,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e),
        }), 500

@departamento_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_detalhe(id):
    """Retorna detalhes de um departamento em JSON"""
    dep = Departamento.query.get_or_404(id)
    return jsonify({
        'id': dep.id,
        'nome': dep.nome,
        'descricao': dep.descricao or '',
        'status': dep.status,
        'criado_em': dep.criado_em.strftime('%d/%m/%Y %H:%M') if dep.criado_em else '',
        'atualizado_em': dep.atualizado_em.strftime('%d/%m/%Y %H:%M') if dep.atualizado_em else '',
    })

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
            return render_template('admin/cadastros/departamentos/novo.html')
        
        # Verifica se já existe um departamento com o mesmo nome
        departamento_existente = Departamento.query.filter_by(nome=nome).first()
        if departamento_existente:
            flash('Já existe um departamento com este nome.', 'danger')
            return render_template('admin/cadastros/departamentos/novo.html')
        
        # Cria o novo departamento
        novo_departamento = Departamento(
            nome=nome,
            descricao=descricao,
            status=status
        )
        
        novo_departamento.save()
        
        flash('Departamento criado com sucesso.', 'success')
        return redirect(url_for('departamento.index'))
    
    return render_template('admin/cadastros/departamentos/novo.html')

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
            return render_template('admin/cadastros/departamentos/editar.html', departamento=departamento)
        
        # Verifica se já existe outro departamento com o mesmo nome
        departamento_existente = Departamento.query.filter_by(nome=nome).first()
        if departamento_existente and departamento_existente.id != id:
            flash('Já existe um departamento com este nome.', 'danger')
            return render_template('admin/cadastros/departamentos/editar.html', departamento=departamento)
        
        # Atualiza o departamento
        departamento.nome = nome
        departamento.descricao = descricao
        departamento.status = status
        departamento.atualizado_em = datetime.now()
        
        departamento.save()
        
        flash('Departamento atualizado com sucesso.', 'success')
        return redirect(url_for('departamento.index'))
    
    return render_template('admin/cadastros/departamentos/editar.html', departamento=departamento)

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
    return render_template('admin/cadastros/departamentos/visualizar.html', departamento=departamento) 