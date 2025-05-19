from datetime import datetime
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, flash
from werkzeug.exceptions import abort
from models import db, ProdutoComposto, ProducaoPeca, ProducaoPecaMaterial, Material, Peca
from models.estoque import Estoque
from flask_login import login_required, current_user
import logging

logger = logging.getLogger(__name__)

producao_peca_bp = Blueprint('producao_peca', __name__)

@producao_peca_bp.route('/producao-peca')
@login_required
def listar():
    """
    Lista todas as produções de peças
    """
    producoes = ProducaoPeca.query.order_by(ProducaoPeca.data_producao.desc()).all()
    return render_template('producao_peca/listar.html', producoes=producoes)
def produzir(peca_id,produto_composto_id,quantidade,data_producao,observacoes,status):
    try:
        # Obter dados do formulário
        peca_id = request.form.get('peca_id', type=int)
        produto_composto_id = request.form.get('produto_composto_id', type=int)
        data_producao = datetime.strptime(request.form.get('data_producao'), '%Y-%m-%d')
        quantidade = request.form.get('quantidade', type=int, default=1)
        observacoes = request.form.get('observacoes')
        status = request.form.get('status', 'Concluída')
        
        # Criar nova produção
        producao = ProducaoPeca(
            peca_id=peca_id,
            produto_composto_id=produto_composto_id,
            data_producao=data_producao,
            quantidade=quantidade,
            observacoes=observacoes,
            status=status
        )
        
        # Buscar produto composto e adicionar materiais
        produto = ProdutoComposto.query.get(produto_composto_id)
        if produto:
            materiais_necessarios = produto.calcular_materiais_necessarios(quantidade)
            
            for material_id, info in materiais_necessarios.items():
                material = info['material']
                quantidade_necessaria = info['quantidade']
                unidade = info['unidade']
                
                producao.adicionar_material(material, quantidade_necessaria, unidade)
        
        # Salvar produção
        producao.save()
        
        # Se status for Concluída, fazer baixa de estoque
        if status == 'Concluída':
            resultado_baixa = producao.baixar_materiais_estoque(current_user.id)
            for resultado in resultado_baixa:
                if 'erro' in resultado:
                    flash(f"Erro ao baixar {resultado['material']}: {resultado['erro']}", 'warning')
                else:
                    flash(f"Baixado {resultado['baixado']} {resultado['unidade']} de {resultado['material']}", 'info')
        
        flash('Produção de peça registrada com sucesso!', 'success')
        return redirect(url_for('producao_peca.listar'))
        
    except Exception as e:
        logger.error(f"Erro ao registrar produção de peça: {str(e)}", exc_info=True)
        db.session.rollback()
        flash(f'Erro ao registrar produção de peça: {str(e)}', 'danger')
@producao_peca_bp.route('/producao-peca/nova', methods=['GET', 'POST'])
@login_required
def nova():
    """
    Registra uma nova produção de peça
    """
    if request.method == 'POST':
        producao = ProducaoPeca(
            peca_id=request.form.get('peca_id', type=int),
            produto_composto_id=request.form.get('produto_composto_id', type=int),
            data_producao=datetime.strptime(request.form.get('data_producao'), '%Y-%m-%d'),
            quantidade=request.form.get('quantidade', type=int, default=1),
            observacoes=request.form.get('observacoes'),
            status=request.form.get('status', 'Concluída')
        )
        producao.produzir(current_user.id)
        if producao.status == 'Concluída':
            resultado_baixa = producao.baixar_materiais_estoque(current_user.id)
            for resultado in resultado_baixa:
                if 'erro' in resultado:
                    flash(f"Erro ao baixar {resultado['material']}: {resultado['erro']}", 'warning')
                else:
                    flash(f"Baixado {resultado['baixado']} {resultado['unidade']} de {resultado['material']}", 'info')
        
        flash('Produção de peça registrada com sucesso!', 'success')
        return redirect(url_for('producao_peca.listar'))
    
    # Buscar peças disponíveis
    pecas = Peca.query.all()
    
    # Buscar produtos compostos
    produtos = ProdutoComposto.query.filter_by(status='Ativo').all()
    
    return render_template('producao_peca/form.html', 
                           producao=None, 
                           pecas=pecas,
                           produtos=produtos,
                           data_atual=datetime.now().strftime('%Y-%m-%d'))

@producao_peca_bp.route('/producao-peca/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita uma produção de peça existente
    """
    producao = ProducaoPeca.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            if producao.status != 'Concluída':
                producao.peca_id = request.form.get('peca_id', type=int)
                producao.produto_composto_id = request.form.get('produto_composto_id', type=int)
                producao.data_producao = datetime.strptime(request.form.get('data_producao'), '%Y-%m-%d')
                producao.quantidade = request.form.get('quantidade', type=int, default=1)
                producao.status = request.form.get('status', 'Concluída')
            
            producao.observacoes = request.form.get('observacoes')
            
            # Se status mudou para Concluída, fazer baixa de estoque
            status_anterior = db.session.query(ProducaoPeca.status).filter(ProducaoPeca.id == id).scalar()
            if status_anterior != 'Concluída' and producao.status == 'Concluída':
                producao.save()  # Salvar primeiro para garantir que temos ID válido
                resultado_baixa = producao.baixar_materiais_estoque(current_user.id)
                for resultado in resultado_baixa:
                    if 'erro' in resultado:
                        flash(f"Erro ao baixar {resultado['material']}: {resultado['erro']}", 'warning')
                    else:
                        flash(f"Baixado {resultado['baixado']} {resultado['unidade']} de {resultado['material']}", 'info')
            else:
                producao.save()
                
            flash('Produção de peça atualizada com sucesso!', 'success')
            
        except Exception as e:
            logger.error(f"Erro ao atualizar produção de peça: {str(e)}", exc_info=True)
            db.session.rollback()
            flash(f'Erro ao atualizar produção de peça: {str(e)}', 'danger')
    
    # Buscar peças disponíveis
    pecas = Peca.query.all()
    
    # Buscar produtos compostos
    produtos = ProdutoComposto.query.filter_by(status='Ativo').all()
    
    return render_template('producao_peca/form.html', 
                           producao=producao, 
                           pecas=pecas,
                           produtos=produtos)

@producao_peca_bp.route('/producao-peca/<int:id>/deletar', methods=['POST'])
@login_required
def deletar(id):
    """
    Remove uma produção de peça do sistema
    """
    producao = ProducaoPeca.query.get_or_404(id)
    
    try:
        # Não permitir excluir produções já concluídas
        if producao.status == 'Concluída':
            flash('Não é possível excluir uma produção já concluída!', 'danger')
            return redirect(url_for('producao_peca.editar', id=id))
            
        producao.delete()
        flash('Produção de peça removida com sucesso!', 'success')
        return redirect(url_for('producao_peca.listar'))
        
    except Exception as e:
        logger.error(f"Erro ao deletar produção de peça: {str(e)}", exc_info=True)
        db.session.rollback()
        flash(f'Erro ao deletar produção de peça: {str(e)}', 'danger')
        return redirect(url_for('producao_peca.editar', id=id))

@producao_peca_bp.route('/api/producao-peca/verificar-estoque')
@login_required
def api_verificar_estoque():
    """
    API que verifica a disponibilidade de estoque para uma produção de peças
    """
    produto_id = request.args.get('produto_id', type=int)
    quantidade = request.args.get('quantidade', 1, type=int)
    
    if not produto_id:
        return jsonify({'error': 'Produto não especificado'}), 400
        
    produto = ProdutoComposto.query.get_or_404(produto_id)
    
    disponibilidade = produto.verificar_disponibilidade_estoque(quantidade)
    
    # Preparar resposta
    resultado = []
    for item in disponibilidade:
        resultado.append({
            'material': item['material'].nome,
            'quantidade_necessaria': float(item['quantidade_necessaria']),
            'quantidade_estoque': float(item['quantidade_estoque']),
            'unidade': item['unidade'],
            'disponivel': item['disponivel']
        })
        
    return jsonify({
        'produto': produto.nome,
        'quantidade': quantidade,
        'disponibilidade': resultado,
        'disponivel_total': all(item['disponivel'] for item in disponibilidade)
    })

@producao_peca_bp.route('/api/producao-peca/materiais-por-tipo')
@login_required
def api_materiais_por_tipo():
    """
    API que retorna os materiais necessários para um tipo de peça
    """
    tipo_peca = request.args.get('tipo_peca')
    quantidade = request.args.get('quantidade', 1, type=int)
    
    if not tipo_peca:
        return jsonify({'error': 'Tipo de peça não especificado'}), 400
        
    produto = ProdutoComposto.get_by_tipo_peca(tipo_peca)
    
    if not produto:
        return jsonify({'error': 'Não existe produto composto para este tipo de peça'}), 404
        
    materiais_necessarios = produto.calcular_materiais_necessarios(quantidade)
    
    # Preparar resposta
    resultado = []
    for material_id, info in materiais_necessarios.items():
        resultado.append({
            'material_id': material_id,
            'material_nome': info['material'].nome,
            'quantidade': float(info['quantidade']),
            'unidade': info['unidade']
        })
        
    return jsonify({
        'produto_id': produto.id,
        'produto_nome': produto.nome,
        'tipo_peca': tipo_peca,
        'quantidade': quantidade,
        'materiais': resultado
    }) 