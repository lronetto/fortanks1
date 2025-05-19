from datetime import datetime
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, flash
from werkzeug.exceptions import abort
from models import db, ProdutoComposto, ComponenteProduto, Material,Peca
from models.unidade import Unidade
from models.conversao_unidade import ConversaoUnidade
from flask_login import login_required, current_user
import logging

logger = logging.getLogger(__name__)

produto_composto_bp = Blueprint('produto_composto', __name__)

@produto_composto_bp.route('/produto-composto')
@login_required
def listar():
    """
    Lista todos os produtos compostos cadastrados
    """
    produtos = ProdutoComposto.query.order_by(ProdutoComposto.nome).all()
    return render_template('produto_composto/listar.html', produtos=produtos)

@produto_composto_bp.route('/produto-composto/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Adiciona um novo produto composto
    """
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            nome = request.form.get('nome')
            codigo = request.form.get('codigo')
            descricao = request.form.get('descricao')
            tipo_peca = request.form.get('tipo_peca')
            tempo_producao = request.form.get('tempo_producao')
            
            # Criar novo produto composto
            produto = ProdutoComposto(
                nome=nome,
                codigo=codigo,
                descricao=descricao,
                tipo_peca=tipo_peca,
                tempo_producao=tempo_producao if tempo_producao else None,
                status='Ativo'
            )
            
            produto.save()
            flash('Produto composto criado com sucesso!', 'success')
            return redirect(url_for('produto_composto.editar', id=produto.id))
            
        except Exception as e:
            logger.error(f"Erro ao criar produto composto: {str(e)}", exc_info=True)
            db.session.rollback()
            flash(f'Erro ao criar produto composto: {str(e)}', 'danger')
    
    # Buscar tipos de peças existentes
    tipos_peca = db.session.query(Peca.tipo).distinct().all()
    tipos_peca = [tipo[0] for tipo in tipos_peca]
    
    return render_template('produto_composto/form.html', produto=None, tipos_peca=tipos_peca)

@produto_composto_bp.route('/produto-composto/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um produto composto existente
    """
    produto = ProdutoComposto.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            produto.nome = request.form.get('nome')
            produto.codigo = request.form.get('codigo')
            produto.descricao = request.form.get('descricao')
            produto.tipo_peca = request.form.get('tipo_peca')
            produto.tempo_producao = request.form.get('tempo_producao')
            produto.status = request.form.get('status', 'Ativo')
            
            produto.save()
            flash('Produto composto atualizado com sucesso!', 'success')
            
        except Exception as e:
            logger.error(f"Erro ao atualizar produto composto: {str(e)}", exc_info=True)
            db.session.rollback()
            flash(f'Erro ao atualizar produto composto: {str(e)}', 'danger')
    
    # Buscar tipos de peças existentes
    tipos_peca = db.session.query(Peca.tipo).distinct().all()
    tipos_peca = [tipo[0] for tipo in tipos_peca]
    
    # Buscar materiais para adicionar ao produto
    materiais = Material.query.filter_by(ativo=True).order_by(Material.nome).all()
    
    return render_template('produto_composto/form.html', 
                           produto=produto, 
                           tipos_peca=tipos_peca,
                           materiais=materiais)

@produto_composto_bp.route('/produto-composto/<int:id>/deletar', methods=['POST'])
@login_required
def deletar(id):
    """
    Remove um produto composto do sistema
    """
    produto = ProdutoComposto.query.get_or_404(id)
    
    try:
        produto.delete()
        flash('Produto composto removido com sucesso!', 'success')
        return redirect(url_for('produto_composto.listar'))
        
    except Exception as e:
        logger.error(f"Erro ao deletar produto composto: {str(e)}", exc_info=True)
        db.session.rollback()
        flash(f'Erro ao deletar produto composto: {str(e)}', 'danger')
        return redirect(url_for('produto_composto.editar', id=id))

@produto_composto_bp.route('/produto-composto/<int:id>/adicionar-material', methods=['POST'])
@login_required
def adicionar_material(id):
    """
    Adiciona um material ao produto composto
    """
    produto = ProdutoComposto.query.get_or_404(id)
    
    try:
        # Obter dados do formulário
        material_id = request.form.get('material_id')
        quantidade = request.form.get('quantidade')
        unidade = request.form.get('unidade')
        observacao = request.form.get('observacao')
        
        # Buscar o material
        material = Material.query.get_or_404(material_id)
        
        # Verificar se a unidade selecionada é diferente da unidade padrão do material
        unidade_padrao = material.get_unidade_nome()
        if unidade != unidade_padrao:
            # Buscar a conversão
            conversao = ConversaoUnidade.obter_por_unidades(unidade, unidade_padrao, material_id)
            if not conversao:
                # Tentar a conversão inversa
                conversao = ConversaoUnidade.obter_por_unidades(unidade_padrao, unidade, material_id)
                if conversao:
                    # Converter a quantidade
                    quantidade = float(quantidade) / conversao.fator
                else:
                    # Não foi encontrada conversão
                    flash(f'Não foi possível converter de {unidade} para {unidade_padrao}', 'warning')
            else:
                # Converter a quantidade
                quantidade = float(quantidade) * conversao.fator
        print(f'quantidade: {quantidade}')
        # Adicionar o material ao produto
        componente = produto.adicionar_material(material, quantidade, unidade)
        
        # Adicionar observação se fornecida
        if observacao:
            componente.observacao = observacao
            db.session.add(componente)
        db.session.commit()
            
        flash('Material adicionado com sucesso!', 'success')
        
    except Exception as e:
        logger.error(f"Erro ao adicionar material ao produto: {str(e)}", exc_info=True)
        db.session.rollback()
        flash(f'Erro ao adicionar material: {str(e)}', 'danger')
        
    return redirect(url_for('produto_composto.editar', id=id))

@produto_composto_bp.route('/produto-composto/<int:id>/remover-material/<int:material_id>', methods=['POST'])
@login_required
def remover_material(id, material_id):
    """
    Remove um material do produto composto
    """
    produto = ProdutoComposto.query.get_or_404(id)
    
    try:
        if produto.remover_material(material_id):
            db.session.commit()
            flash('Material removido com sucesso!', 'success')
        else:
            flash('Material não encontrado no produto!', 'warning')
            
    except Exception as e:
        logger.error(f"Erro ao remover material do produto: {str(e)}", exc_info=True)
        db.session.rollback()
        flash(f'Erro ao remover material: {str(e)}', 'danger')
        
    return redirect(url_for('produto_composto.editar', id=id))

@produto_composto_bp.route('/api/produto-composto/por-tipo/<tipo_peca>')
@login_required
def api_produto_por_tipo(tipo_peca):
    """
    API que retorna um produto composto por tipo de peça
    """
    produto = ProdutoComposto.get_by_tipo_peca(tipo_peca)
    
    if not produto:
        return jsonify({'error': 'Produto não encontrado para este tipo de peça'}), 404
        
    # Montar resposta com componentes
    componentes = []
    for componente in produto.componentes:
        componentes.append({
            'id': componente.id,
            'material_id': componente.material_id,
            'material_nome': componente.material.nome,
            'quantidade': float(componente.quantidade),
            'unidade': componente.unidade,
            'observacao': componente.observacao
        })
        
    return jsonify({
        'id': produto.id,
        'nome': produto.nome,
        'codigo': produto.codigo,
        'tipo_peca': produto.tipo_peca,
        'tempo_producao': float(produto.tempo_producao) if produto.tempo_producao else None,
        'componentes': componentes
    })

@produto_composto_bp.route('/api/produto-composto/<int:id>/verificar-estoque')
@login_required
def api_verificar_estoque(id):
    """
    API que verifica a disponibilidade de estoque para um produto composto
    """
    produto = ProdutoComposto.query.get_or_404(id)
    quantidade = request.args.get('quantidade', 1, type=int)
    
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

@produto_composto_bp.route('/api/produto-composto/material/<int:material_id>/unidades')
@login_required
def api_material_unidades(material_id):
    """
    API que retorna as unidades disponíveis para um material específico,
    incluindo as conversões de unidade
    """
    material = Material.query.get_or_404(material_id)
    
    # Obter a unidade padrão do material
    unidade_padrao = None
    if material.unidade_id:
        unidade_padrao = Unidade.query.get(material.unidade_id)
    
    # Se não tiver unidade_id, tenta usar o campo unidade (string)
    unidade_padrao_str = material.unidade
    if not unidade_padrao and unidade_padrao_str:
        unidade_padrao = Unidade.query.filter(Unidade.nome.ilike(unidade_padrao_str)).first()
    
    # Obter todas as unidades para o dropdown
    unidades = Unidade.query.filter_by(ativo=True).order_by(Unidade.nome).all()
    
    # Obter conversões de unidade para este material
    conversoes = ConversaoUnidade.listar_para_material(material.id)
    
    # Preparar lista de unidades disponíveis
    unidades_disponiveis = []
    
    # Adicionar unidade padrão (se existir)
    if unidade_padrao:
        unidades_disponiveis.append({
            'id': unidade_padrao.id,
            'nome': unidade_padrao.nome,
            'descricao': unidade_padrao.descricao,
            'padrao': True
        })
    elif unidade_padrao_str:
        # Se não encontrou a unidade no banco mas tem a string
        unidades_disponiveis.append({
            'id': 0,
            'nome': unidade_padrao_str,
            'descricao': unidade_padrao_str,
            'padrao': True
        })
    
    # Adicionar as conversões
    for conv in conversoes:
        # Verificar se a unidade de entrada é a padrão do material
        is_entrada_padrao = False
        if unidade_padrao and conv.unidade_entrada == unidade_padrao.nome:
            is_entrada_padrao = True
        elif not unidade_padrao and conv.unidade_entrada == unidade_padrao_str:
            is_entrada_padrao = True
        
        # Verificar se a unidade de saída é a padrão do material
        is_saida_padrao = False
        if unidade_padrao and conv.unidade_saida == unidade_padrao.nome:
            is_saida_padrao = True
        elif not unidade_padrao and conv.unidade_saida == unidade_padrao_str:
            is_saida_padrao = True
        
        # Adicionar a unidade de entrada se não for a padrão
        if not is_entrada_padrao:
            # Buscar a unidade no banco se possível
            unidade = Unidade.query.filter(Unidade.nome.ilike(conv.unidade_entrada)).first()
            if unidade:
                unidades_disponiveis.append({
                    'id': unidade.id,
                    'nome': unidade.nome,
                    'descricao': unidade.descricao,
                    'padrao': False,
                    'fator_conversao': 1 / conv.fator if is_saida_padrao else None
                })
            else:
                unidades_disponiveis.append({
                    'id': 0,
                    'nome': conv.unidade_entrada,
                    'descricao': conv.unidade_entrada,
                    'padrao': False,
                    'fator_conversao': 1 / conv.fator if is_saida_padrao else None
                })
        
        # Adicionar a unidade de saída se não for a padrão
        if not is_saida_padrao:
            # Buscar a unidade no banco se possível
            unidade = Unidade.query.filter(Unidade.nome.ilike(conv.unidade_saida)).first()
            if unidade:
                unidades_disponiveis.append({
                    'id': unidade.id,
                    'nome': unidade.nome,
                    'descricao': unidade.descricao,
                    'padrao': False,
                    'fator_conversao': conv.fator if is_entrada_padrao else None
                })
            else:
                unidades_disponiveis.append({
                    'id': 0,
                    'nome': conv.unidade_saida,
                    'descricao': conv.unidade_saida,
                    'padrao': False,
                    'fator_conversao': conv.fator if is_entrada_padrao else None
                })
    
    # Adicionar todas as outras unidades do sistema
    for unidade in unidades:
        # Verificar se já foi adicionada
        if not any(u['nome'].lower() == unidade.nome.lower() for u in unidades_disponiveis):
            unidades_disponiveis.append({
                'id': unidade.id,
                'nome': unidade.nome,
                'descricao': unidade.descricao,
                'padrao': False
            })
    
    # Ordenar: primeiro a unidade padrão, depois por nome
    unidades_disponiveis.sort(key=lambda x: (not x['padrao'], x['nome']))
    
    return jsonify({
        'material': {
            'id': material.id,
            'nome': material.nome,
            'unidade_padrao': unidade_padrao.nome if unidade_padrao else unidade_padrao_str
        },
        'unidades': unidades_disponiveis
    }) 