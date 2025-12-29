"""
Controlador para gerenciar unidades de medida
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models.database import db
from models.unidade import Unidades
from flask_login import login_required
import logging

logger = logging.getLogger(__name__)

unidade_bp = Blueprint('unidade', __name__, url_prefix='/admin/unidades')

@unidade_bp.route('/')
@login_required
def listar():
    """Lista todas as unidades"""
    try:
        unidades = Unidades.query.order_by(Unidades.nome).all()
        return render_template('unidades/index.html', unidades=unidades)
    except Exception as e:
        logger.error(f"Erro ao listar unidades: {str(e)}")
        flash(f"Erro ao listar unidades: {str(e)}", "danger")
        return redirect(url_for('admin.index'))

@unidade_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def criar():
    """Cria uma nova unidade"""
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
            return redirect(url_for('unidade.listar'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar unidade: {str(e)}")
            flash(f"Erro ao criar unidade: {str(e)}", "danger")
            return render_template('unidades/form.html')
    
    return render_template('unidades/form.html')

@unidade_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Edita uma unidade existente"""
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
            return redirect(url_for('unidade.listar'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao atualizar unidade: {str(e)}")
            flash(f"Erro ao atualizar unidade: {str(e)}", "danger")
            return render_template('unidades/form.html', unidade=unidade)
    
    return render_template('unidades/form.html', unidade=unidade)

@unidade_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """Exclui uma unidade"""
    try:
        unidade = Unidades.query.get_or_404(id)
        
        # Verifica se a unidade está sendo usada
        if hasattr(unidade, 'materiais') and unidade.materiais:
            flash("Esta unidade não pode ser excluída pois está sendo usada por materiais", "warning")
            return redirect(url_for('unidade.listar'))
            
        # Verifica se é a unidade padrão
        if unidade.padrao:
            flash("A unidade padrão não pode ser excluída", "warning")
            return redirect(url_for('unidade.listar'))
        
        nome = unidade.nome
        db.session.delete(unidade)
        db.session.commit()
        
        flash(f"Unidade {nome} excluída com sucesso", "success")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir unidade: {str(e)}")
        flash(f"Erro ao excluir unidade: {str(e)}", "danger")
        
    return redirect(url_for('unidade.listar'))

@unidade_bp.route('/api/todas', methods=['GET'])
def api_todas():
    """API para listar todas as unidades"""
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