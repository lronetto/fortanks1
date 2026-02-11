"""
Controlador para gerenciar unidades de medida
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models.database import db
from models.unidade import Unidades
from flask_login import login_required
from sqlalchemy import or_
import logging

logger = logging.getLogger(__name__)

unidade_bp = Blueprint('unidade', __name__, url_prefix='/admin/unidades')

@unidade_bp.route('/')
@login_required
def index():
    """Lista todas as unidades"""
    try:
        return render_template('unidades/index.html')
    except Exception as e:
        logger.error(f"Erro ao listar unidades: {str(e)}")
        flash(f"Erro ao listar unidades: {str(e)}", "danger")
        return redirect(url_for('admin.index'))

@unidade_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def criar():
    """Cria uma nova unidade (mantida para compatibilidade)"""
    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').upper().strip()
            descricao = request.form.get('descricao', '').strip()
            padrao = 'padrao' in request.form
            
            if not nome:
                flash("O nome da unidade é obrigatório", "warning")
                return render_template('unidades/form.html')
            
            # Verifica se já existe uma unidade com o mesmo nome
            unidade_existente = Unidades.query.filter(Unidades.nome.ilike(nome)).first()
            if unidade_existente:
                flash(f"Já existe uma unidade com o nome {nome}", "warning")
                return render_template('unidades/form.html')
            
            # Se for definida como padrão, remove o padrão das outras
            if padrao:
                unidades_padrao = Unidades.query.filter_by(padrao=True).all()
                for u in unidades_padrao:
                    u.padrao = False
            
            # Cria a nova unidade
            unidade = Unidades(
                nome=nome,
                descricao=descricao,
                padrao=padrao
            )
            
            db.session.add(unidade)
            db.session.commit()
            
            flash(f"Unidade {nome} criada com sucesso", "success")
            return redirect(url_for('unidade.index'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar unidade: {str(e)}")
            flash(f"Erro ao criar unidade: {str(e)}", "danger")
            return render_template('unidades/form.html')
    
    return render_template('unidades/form.html')

@unidade_bp.route('/api/criar', methods=['POST'])
@login_required
def api_criar():
    """API para criar unidade via AJAX"""
    try:
        nome = request.form.get('nome', '').upper().strip()
        descricao = request.form.get('descricao', '').strip()
        padrao = 'padrao' in request.form
        
        if not nome:
            return jsonify({
                'success': False,
                'message': 'O nome da unidade é obrigatório'
            }), 400
        
        # Verifica se já existe uma unidade com o mesmo nome
        unidade_existente = Unidades.query.filter(Unidades.nome.ilike(nome)).first()
        if unidade_existente:
            return jsonify({
                'success': False,
                'message': f'Já existe uma unidade com o nome {nome}'
            }), 400
        
        # Se for definida como padrão, remove o padrão das outras
        if padrao:
            unidades_padrao = Unidades.query.filter_by(padrao=True).all()
            for u in unidades_padrao:
                u.padrao = False
        
        # Cria a nova unidade
        unidade = Unidades(
            nome=nome,
            descricao=descricao,
            padrao=padrao
        )
        
        db.session.add(unidade)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Unidade {nome} criada com sucesso',
            'data': {
                'id': unidade.id,
                'nome': unidade.nome,
                'descricao': unidade.descricao,
                'padrao': unidade.padrao,
                'ativo': unidade.ativo
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao criar unidade via API: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Erro ao criar unidade: {str(e)}'
        }), 500

@unidade_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Edita uma unidade existente (mantida para compatibilidade)"""
    unidade = Unidades.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').upper().strip()
            descricao = request.form.get('descricao', '').strip()
            padrao = 'padrao' in request.form
            ativo = 'ativo' in request.form
            
            if not nome:
                flash("O nome da unidade é obrigatório", "warning")
                return render_template('unidades/form.html', unidade=unidade)
            
            # Verifica se já existe outra unidade com o mesmo nome
            unidade_existente = Unidades.query.filter(
                Unidades.nome.ilike(nome), 
                Unidades.id != id
            ).first()
            
            if unidade_existente:
                flash(f"Já existe outra unidade com o nome {nome}", "warning")
                return render_template('unidades/form.html', unidade=unidade)
            
            # Se for definida como padrão, remove o padrão das outras
            if padrao and not unidade.padrao:
                unidades_padrao = Unidades.query.filter_by(padrao=True).all()
                for u in unidades_padrao:
                    u.padrao = False
            
            # Atualiza a unidade
            unidade.nome = nome
            unidade.descricao = descricao
            unidade.padrao = padrao
            unidade.ativo = ativo
            
            db.session.commit()
            
            flash(f"Unidade {nome} atualizada com sucesso", "success")
            return redirect(url_for('unidade.index'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao atualizar unidade: {str(e)}")
            flash(f"Erro ao atualizar unidade: {str(e)}", "danger")
            return render_template('unidades/form.html', unidade=unidade)
    
    return render_template('unidades/form.html', unidade=unidade)

@unidade_bp.route('/api/editar/<int:id>', methods=['POST'])
@login_required
def api_editar(id):
    """API para editar unidade via AJAX"""
    try:
        unidade = Unidades.query.get_or_404(id)
        
        nome = request.form.get('nome', '').upper().strip()
        descricao = request.form.get('descricao', '').strip()
        padrao = 'padrao' in request.form
        ativo = 'ativo' in request.form
        
        if not nome:
            return jsonify({
                'success': False,
                'message': 'O nome da unidade é obrigatório'
            }), 400
        
        # Verifica se já existe outra unidade com o mesmo nome
        unidade_existente = Unidades.query.filter(
            Unidades.nome.ilike(nome), 
            Unidades.id != id
        ).first()
        
        if unidade_existente:
            return jsonify({
                'success': False,
                'message': f'Já existe outra unidade com o nome {nome}'
            }), 400
        
        # Se for definida como padrão, remove o padrão das outras
        if padrao and not unidade.padrao:
            unidades_padrao = Unidades.query.filter_by(padrao=True).all()
            for u in unidades_padrao:
                u.padrao = False
        
        # Atualiza a unidade
        unidade.nome = nome
        unidade.descricao = descricao
        unidade.padrao = padrao
        unidade.ativo = ativo
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Unidade {nome} atualizada com sucesso',
            'data': {
                'id': unidade.id,
                'nome': unidade.nome,
                'descricao': unidade.descricao,
                'padrao': unidade.padrao,
                'ativo': unidade.ativo
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao atualizar unidade via API: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Erro ao atualizar unidade: {str(e)}'
        }), 500

@unidade_bp.route('/api/buscar/<int:id>', methods=['GET'])
@login_required
def api_buscar(id):
    """API para buscar dados de uma unidade"""
    try:
        unidade = Unidades.query.get_or_404(id)
        
        return jsonify({
            'success': True,
            'data': {
                'id': unidade.id,
                'nome': unidade.nome,
                'descricao': unidade.descricao or '',
                'padrao': unidade.padrao,
                'ativo': unidade.ativo
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Erro ao buscar unidade via API: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Erro ao buscar unidade: {str(e)}'
        }), 500

@unidade_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """Exclui uma unidade"""
    try:
        unidade = Unidades.query.get_or_404(id)
        
        # Verifica se a unidade está sendo usada
        if hasattr(unidade, 'materiais') and unidade.materiais:
            flash("Esta unidade não pode ser excluída pois está sendo usada por materiais", "warning")
            return redirect(url_for('unidade.index'))
            
        # Verifica se é a unidade padrão
        if unidade.padrao:
            flash("A unidade padrão não pode ser excluída", "warning")
            return redirect(url_for('unidade.index'))
        
        nome = unidade.nome
        db.session.delete(unidade)
        db.session.commit()
        
        flash(f"Unidade {nome} excluída com sucesso", "success")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir unidade: {str(e)}")
        flash(f"Erro ao excluir unidade: {str(e)}", "danger")
        
    return redirect(url_for('unidade.index'))

@unidade_bp.route('/api/excluir/<int:id>', methods=['POST'])
@login_required
def api_excluir(id):
    """API para excluir unidade via AJAX"""
    try:
        unidade = Unidades.query.get_or_404(id)
        
        # Verifica se a unidade está sendo usada
        if hasattr(unidade, 'materiais') and unidade.materiais:
            return jsonify({
                'success': False,
                'message': 'Esta unidade não pode ser excluída pois está sendo usada por materiais'
            }), 400
            
        # Verifica se é a unidade padrão
        if unidade.padrao:
            return jsonify({
                'success': False,
                'message': 'A unidade padrão não pode ser excluída'
            }), 400
        
        nome = unidade.nome
        db.session.delete(unidade)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Unidade {nome} excluída com sucesso'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir unidade via API: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Erro ao excluir unidade: {str(e)}'
        }), 500

@unidade_bp.route('/api/datatables', methods=['GET'])
@login_required
def api_datatables():
    """API para DataTables - retorna unidades em formato JSON"""
    try:
        # Parâmetros do DataTables
        draw = int(request.args.get('draw', 1))
        start = int(request.args.get('start', 0))
        length = int(request.args.get('length', 25))
        search_value = request.args.get('search[value]', '').strip()
        
        # Parâmetros de ordenação
        order_column_index = int(request.args.get('order[0][column]', 0))
        order_dir = request.args.get('order[0][dir]', 'asc')
        
        # Mapeamento de colunas para ordenação
        column_map = {
            0: Unidades.id,
            1: Unidades.nome,
            2: Unidades.descricao,
            3: Unidades.padrao,
            4: Unidades.ativo
        }
        
        # Query base
        query = Unidades.query
        
        # Aplicar busca
        if search_value:
            query = query.filter(
                or_(
                    Unidades.nome.ilike(f'%{search_value}%'),
                    Unidades.descricao.ilike(f'%{search_value}%')
                )
            )
        
        # Contar total de registros antes da paginação
        total_records = Unidades.query.count()
        records_filtered = query.count()
        
        # Aplicar ordenação
        if order_column_index in column_map:
            order_column = column_map[order_column_index]
            if order_dir == 'desc':
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())
        else:
            # Ordenação padrão por nome
            query = query.order_by(Unidades.nome.asc())
        
        # Aplicar paginação
        unidades = query.offset(start).limit(length).all()
        
        # Preparar dados para resposta
        data = []
        for unidade in unidades:
            data.append({
                'id': unidade.id,
                'nome': unidade.nome,
                'descricao': unidade.descricao or '',
                'padrao': unidade.padrao,
                'ativo': unidade.ativo
            })
        
        return jsonify({
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': records_filtered,
            'data': data
        }), 200
        
    except Exception as e:
        logger.error(f'Erro ao buscar unidades: {str(e)}', exc_info=True)
        return jsonify({
            'draw': draw if 'draw' in locals() else 1,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e)
        }), 500

@unidade_bp.route('/api/todas', methods=['GET'])
def api_todas():
    """API para listar todas as unidades (mantida para compatibilidade)"""
    try:
        unidades = Unidades.query.filter_by(ativo=True).order_by(Unidades.nome).all()
        
        resultado = []
        for unidade in unidades:
            resultado.append({
                'id': unidade.id,
                'nome': unidade.nome,
                'descricao': unidade.descricao,
                'padrao': unidade.padrao
            })
            
        return jsonify(resultado)
        
    except Exception as e:
        logger.error(f"Erro ao listar unidades via API: {str(e)}")
        return jsonify({'error': str(e)}), 500 