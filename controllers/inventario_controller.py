from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from models.estoque import Estoque, MovimentacaoEstoque, InventarioEstoque, ItemInventario
from models.material import Material
from models.database import db
from forms.estoque_forms import InventarioEstoqueForm
from datetime import datetime, timedelta
from models.unidade import Unidade
from sqlalchemy import or_, func
from decimal import Decimal
import logging

# Configuração do logger
logger = logging.getLogger(__name__)

# Criar blueprint
inventario_bp = Blueprint('inventario', __name__, url_prefix='/inventario')

# Rotas de Inventário
@inventario_bp.route('/')
@login_required
def inventarios():
    """
    Listagem de inventários
    """
    page = request.args.get('page', 1, type=int)
    tipo = request.args.get('tipo', None)
    status = request.args.get('status', None)
    localizacao = request.args.get('localizacao', None)
    
    # Consulta base
    query = InventarioEstoque.query
    
    # Aplicar filtros
    if tipo:
        query = query.filter(InventarioEstoque.tipo_inventario == tipo)
    
    if status:
        query = query.filter(InventarioEstoque.status == status)
    
    # Filtro por localização - filtrar inventários que têm itens com a localização especificada
    if localizacao:
        # Encontrar IDs de inventários que têm itens com a localização especificada
        inventarios_ids = db.session.query(ItemInventario.inventario_id).join(
            Estoque, ItemInventario.estoque_id == Estoque.id
        ).filter(Estoque.localizacao == localizacao).distinct().all()
        
        if inventarios_ids:
            inventarios_ids_list = [row[0] for row in inventarios_ids]
            query = query.filter(InventarioEstoque.id.in_(inventarios_ids_list))
        else:
            # Se não há inventários com essa localização, retornar query vazia
            query = query.filter(InventarioEstoque.id == -1)
    
    # Obter resultados
    inventarios = query.order_by(InventarioEstoque.id.desc()).all()
    
    # Obter lista de localizações únicas para o filtro
    localizacoes = db.session.query(Estoque.localizacao).filter(
        Estoque.localizacao != None,
        Estoque.localizacao != ''
    ).distinct().order_by(Estoque.localizacao).all()
    localizacoes_list = [('', 'Todas')] + [(loc[0], loc[0]) for loc in localizacoes]
    
    # Paginação manual se necessário
    pagination = {
        'page': page,
        'pages': (len(inventarios) + 9) // 10,  # Arredonda para cima
        'total': len(inventarios)
    }
    
    return render_template('inventario/inventario_lista.html', 
                          inventarios=inventarios, 
                          pagination=pagination,
                          localizacoes=localizacoes_list,
                          localizacao=localizacao,
                          request=request)

@inventario_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo_inventario():
    """
    Criar novo inventário
    """
    # Verificar se é uma requisição AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    form = InventarioEstoqueForm()
    
    # Carregar categorias e localizações para filtros
    categorias = db.session.query(Material.categoria).filter(
        Material.categoria != None, 
        Material.categoria != ''
    ).distinct().all()
    categorias = [cat[0] for cat in categorias]
    
    localizacoes = db.session.query(Estoque.localizacao).filter(
        Estoque.localizacao != None, 
        Estoque.localizacao != ''
    ).distinct().all()
    localizacoes = [loc[0] for loc in localizacoes]
    
    # Debug: verificar se é AJAX e dados do formulário
    if is_ajax:
        logger.info(f"Requisição AJAX recebida - Dados: {request.form.to_dict()}")
    
    if form.validate_on_submit():
        try:
            logger.info(f"Criando inventário - Tipo: {form.tipo_inventario.data}")
            inventario = InventarioEstoque(
                tipo_inventario=form.tipo_inventario.data,
                observacoes=form.observacoes.data,
                criado_por_id=current_user.id
            )
            
            db.session.add(inventario)
            db.session.flush()  # Para obter o ID antes do commit
            
            # Selecionar itens para o inventário
            query = Estoque.query
            
            # Filtrar por tipo se for inventário parcial
            if form.tipo_inventario.data == 'Parcial':
                # Obter filtros do request
                filtro_parcial = request.form.get('filtro_parcial')
                logger.info(f"Filtro parcial selecionado: {filtro_parcial}")
                
                tipo_item = request.form.get('tipo_item')
                localizacao = request.form.get('localizacao')
                categoria = request.form.get('categoria')
                grupos_selecionados = request.form.getlist('grupos[]')
                itens_especificos = request.form.getlist('itens[]')
                
                logger.info(f"Filtros recebidos - Tipo: {tipo_item}, Localização: {localizacao}, Categoria: {categoria}, Grupos: {grupos_selecionados}")
                
                # Verificar se pelo menos um filtro foi selecionado
                if not any([tipo_item, localizacao, categoria, grupos_selecionados, itens_especificos]):
                    logger.warning("Inventário parcial sem filtros selecionados")
                    if is_ajax:
                        return jsonify({
                            'success': False,
                            'message': 'Para inventário parcial, selecione pelo menos um filtro.'
                        }), 400
                    else:
                        flash('Para inventário parcial, selecione pelo menos um filtro.', 'danger')
                        return render_template('inventario/inventario_form.html', 
                                              form=form, 
                                              categorias=categorias, 
                                              localizacoes=localizacoes)
                
                if tipo_item:
                    query = query.filter(Estoque.tipo_item == tipo_item)
                
                if localizacao:
                    query = query.filter(Estoque.localizacao == localizacao)
                
                if categoria:
                    # Filtrar por categoria do material
                    query = query.join(Estoque.material).filter(Material.categoria == categoria)
                
                if grupos_selecionados:
                    # Filtrar por grupos de materiais selecionados
                    logger.info(f"Filtrando por grupos: {grupos_selecionados}")
                    
                    # Construir placeholders para IN clause
                    placeholders = ','.join([f':grupo_{i}' for i in range(len(grupos_selecionados))])
                    sql = f"""
                        SELECT DISTINCT material_id FROM materiais_grupos 
                        WHERE grupo_id IN ({placeholders})
                    """
                    
                    # Criar dicionário de parâmetros
                    params = {f'grupo_{i}': int(grupo_id) for i, grupo_id in enumerate(grupos_selecionados)}
                    logger.info(f"SQL: {sql}")
                    logger.info(f"Parâmetros: {params}")
                    
                    materiais_grupo = db.session.execute(
                        db.text(sql), params
                    ).fetchall()
                    if materiais_grupo:
                        ids_materiais = [row[0] for row in materiais_grupo]
                        logger.info(f"Materiais encontrados nos grupos: {ids_materiais}")
                        
                        # Verificar se esses materiais existem no estoque
                        estoque_count = db.session.query(Estoque).filter(Estoque.material_id.in_(ids_materiais)).count()
                        logger.info(f"Quantidade de itens no estoque para esses materiais: {estoque_count}")
                        
                        if estoque_count > 0:
                            query = query.filter(Estoque.material_id.in_(ids_materiais))
                        else:
                            logger.warning("Nenhum item no estoque encontrado para os materiais dos grupos selecionados")
                            # Se não há itens no estoque para esses materiais, retornar query vazia
                            query = query.filter(Estoque.id == -1)
                    else:
                        logger.info("Nenhum material encontrado nos grupos selecionados")
                        # Se não há materiais nos grupos, retornar query vazia
                        query = query.filter(Estoque.id == -1)
                
                # Verificar se tem itens específicos selecionados
                itens_selecionados = request.form.getlist('itens[]')
                if itens_selecionados:
                    query = query.filter(Estoque.id.in_(itens_selecionados))
                    
            estoque_items = query.all()
            logger.info(f"Total de itens encontrados para o inventário: {len(estoque_items)}")
            
            # Criar itens de inventário
            for item in estoque_items:
                item_inventario = ItemInventario(
                    inventario_id=inventario.id,
                    estoque_id=item.id,
                    quantidade_sistema=item.quantidade
                )
                db.session.add(item_inventario)
            
            db.session.commit()
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Inventário criado com sucesso! Agora você pode iniciar a contagem.',
                    'redirect': url_for('inventario.inventario_detalhes', id=inventario.id)
                })
            else:
                flash('Inventário criado com sucesso! Agora você pode iniciar a contagem.', 'success')
                return redirect(url_for('inventario.inventario_detalhes', id=inventario.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar inventário: {str(e)}")
            
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': f'Erro ao criar inventário: {str(e)}'
                }), 500
            else:
                flash(f'Erro ao criar inventário: {str(e)}', 'danger')
    else:
        # Formulário não é válido
        if is_ajax:
            errors = {}
            for field, field_errors in form.errors.items():
                errors[field] = field_errors
            return jsonify({
                'success': False,
                'message': 'Dados do formulário inválidos',
                'errors': errors
            }), 400
    
    if is_ajax:
        # Se chegou até aqui e é AJAX, retornar erro genérico
        return jsonify({
            'success': False,
            'message': 'Erro inesperado ao processar requisição'
        }), 500
    
    return render_template('inventario/inventario_form.html', 
                          form=form, 
                          categorias=categorias, 
                          localizacoes=localizacoes)

@inventario_bp.route('/<int:id>')
@login_required
def inventario_detalhes(id):
    """
    Detalhes de um inventário
    """
    inventario = InventarioEstoque.query.get_or_404(id)
    itens = ItemInventario.query.filter_by(inventario_id=id).all()
    
    return render_template('inventario/inventario_detalhes.html', 
                          inventario=inventario, 
                          itens=itens)

@inventario_bp.route('/gerenciar')
@login_required
def gerenciar_inventario():
    """
    Página principal para gerenciar inventários
    """
    return render_template('inventario/gerenciar_inventario.html')

@inventario_bp.route('/api/estatisticas')
@login_required
def api_estatisticas_inventario():
    """
    API para obter estatísticas dos inventários
    """
    try:
        # Inventários ativos
        inventarios_ativos = InventarioEstoque.query.filter_by(status='Em Andamento').count()
        
        # Itens pendentes de contagem
        itens_pendentes = db.session.query(ItemInventario).join(InventarioEstoque).filter(
            InventarioEstoque.status == 'Em Andamento',
            ItemInventario.quantidade_contada.is_(None)
        ).count()
        
        # Diferenças encontradas
        diferencas = db.session.query(ItemInventario).join(InventarioEstoque).filter(
            InventarioEstoque.status == 'Finalizado',
            ItemInventario.quantidade_contada != ItemInventario.quantidade_sistema
        ).count()
        
        # Inventários finalizados nos últimos 30 dias
        data_limite = datetime.now() - timedelta(days=30)
        finalizados_30_dias = InventarioEstoque.query.filter(
            InventarioEstoque.status == 'Finalizado',
            InventarioEstoque.data_fim >= data_limite
        ).count()
        
        return jsonify({
            'success': True,
            'estatisticas': {
                'inventarios_ativos': inventarios_ativos,
                'itens_pendentes': itens_pendentes,
                'diferencas': diferencas,
                'finalizados_30_dias': finalizados_30_dias
            }
        })
    
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas de inventário: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao obter estatísticas: {str(e)}'
        }), 500

@inventario_bp.route('/api/ativos')
@login_required
def api_inventarios_ativos():
    """
    API para obter inventários ativos
    """
    try:
        inventarios = InventarioEstoque.query.filter_by(status='Em Andamento').order_by(
            InventarioEstoque.data_inicio.desc()
        ).all()
        
        inventarios_data = []
        for inv in inventarios:
            # Contar itens totais e contados
            total_itens = ItemInventario.query.filter_by(inventario_id=inv.id).count()
            itens_contados = ItemInventario.query.filter_by(
                inventario_id=inv.id
            ).filter(ItemInventario.quantidade_contada.isnot(None)).count()
            
            inventarios_data.append({
                'id': inv.id,
                'tipo_inventario': inv.tipo_inventario,
                'data_inicio': inv.data_inicio.isoformat(),
                'total_itens': total_itens,
                'itens_contados': itens_contados,
                'status': inv.status,
                'responsavel': inv.criado_por.nome if inv.criado_por else None
            })
        
        return jsonify({
            'success': True,
            'inventarios': inventarios_data
        })
    
    except Exception as e:
        logger.error(f"Erro ao obter inventários ativos: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao obter inventários ativos: {str(e)}'
        }), 500

@inventario_bp.route('/api/historico')
@login_required
def api_historico_inventarios():
    """
    API para obter histórico de inventários
    """
    try:
        # Parâmetros de filtro
        tipo = request.args.get('tipo', '')
        status = request.args.get('status', '')
        data = request.args.get('data', '')
        
        # Query base
        query = InventarioEstoque.query
        
        # Aplicar filtros
        if tipo:
            query = query.filter(InventarioEstoque.tipo_inventario == tipo)
        
        if status:
            query = query.filter(InventarioEstoque.status == status)
        
        if data:
            data_filtro = datetime.strptime(data, '%Y-%m-%d').date()
            query = query.filter(func.date(InventarioEstoque.data_inicio) == data_filtro)
        
        # Obter inventários
        inventarios = query.order_by(InventarioEstoque.data_inicio.desc()).limit(100).all()
        
        inventarios_data = []
        for inv in inventarios:
            # Contar itens e diferenças
            total_itens = ItemInventario.query.filter_by(inventario_id=inv.id).count()
            diferencas = db.session.query(ItemInventario).filter_by(
                inventario_id=inv.id
            ).filter(ItemInventario.quantidade_contada != ItemInventario.quantidade_sistema).count()
            
            inventarios_data.append({
                'id': inv.id,
                'tipo_inventario': inv.tipo_inventario,
                'data_inicio': inv.data_inicio.isoformat(),
                'data_fim': inv.data_fim.isoformat() if inv.data_fim else None,
                'status': inv.status,
                'total_itens': total_itens,
                'diferencas': diferencas,
                'responsavel': inv.criado_por.nome if inv.criado_por else None
            })
        
        return jsonify({
            'success': True,
            'inventarios': inventarios_data
        })
    
    except Exception as e:
        logger.error(f"Erro ao obter histórico de inventários: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao obter histórico: {str(e)}'
        }), 500

@inventario_bp.route('/api/salvar-configuracoes', methods=['POST'])
@login_required
def api_salvar_configuracoes():
    """
    API para salvar configurações de inventário
    """
    try:
        data = request.get_json()
        
        # Aqui você pode implementar a lógica para salvar as configurações
        # Por exemplo, em uma tabela de configurações ou em cache
        
        # Por enquanto, apenas retornar sucesso
        return jsonify({
            'success': True,
            'message': 'Configurações salvas com sucesso!'
        })
    
    except Exception as e:
        logger.error(f"Erro ao salvar configurações: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao salvar configurações: {str(e)}'
        }), 500

@inventario_bp.route('/<int:id>/contagem')
@login_required
def inventario_contagem(id):
    """
    Página de contagem de inventário
    """
    inventario = InventarioEstoque.query.get_or_404(id)
    
    # Buscar itens ordenados pelo nome do material
    # Fazer join com Estoque e Material para ordenar
    itens_ordenados = db.session.query(ItemInventario)\
        .join(Estoque, ItemInventario.estoque_id == Estoque.id)\
        .outerjoin(Material, Estoque.material_id == Material.id)\
        .filter(ItemInventario.inventario_id == id)\
        .order_by(func.coalesce(Material.nome, '').asc())\
        .all()
    
    # Atualizar quantidade_sistema para cada item
    for item in itens_ordenados:
        item.quantidade_sistema = item.estoque.get_saldo_ate_data()
        item.save()
    
    # Substituir a lista de itens do inventário pela lista ordenada
    # Isso mantém a compatibilidade com o template que usa inventario.itens
    inventario.itens = itens_ordenados
    
    # Verificar se o inventário está em andamento
    if inventario.status != 'Em andamento':
        flash('Este inventário já foi finalizado ou cancelado', 'warning')
        return redirect(url_for('inventario.inventario_detalhes', id=id))
    
    return render_template('inventario/inventario_contagem.html', 
                          inventario=inventario)

@inventario_bp.route('/<int:id>/finalizar', methods=['POST'])
@login_required
def finalizar_inventario(id):
    """
    Finalizar inventário com ajustes de estoque
    """
    # Verificar se é uma requisição AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    inventario = InventarioEstoque.query.get_or_404(id)
    
    # Verificar se todos os itens foram contados
    itens_nao_contados = ItemInventario.query.filter_by(inventario_id=id, quantidade_contada=None).count()
    if itens_nao_contados > 0:
        error_msg = f'Existem {itens_nao_contados} itens não contados. Finalize a contagem antes de encerrar o inventário.'
        if is_ajax:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400
        flash(error_msg, 'danger')
        return redirect(url_for('inventario.inventario_contagem', id=id))
    
    try:
        # Finalizar inventário e ajustar estoques
        inventario.finalizar(current_user.id)
        success_msg = 'Inventário finalizado com sucesso! Os estoques foram ajustados.'
        
        if is_ajax:
            return jsonify({
                'success': True,
                'message': success_msg,
                'redirect': url_for('inventario.inventario_detalhes', id=id)
            })
        
        flash(success_msg, 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao finalizar inventário: {str(e)}")
        error_msg = f'Erro ao finalizar inventário: {str(e)}'
        
        if is_ajax:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 500
        
        flash(error_msg, 'danger')
    
    return redirect(url_for('inventario.inventario_detalhes', id=id))

@inventario_bp.route('/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar_inventario(id):
    """
    Cancelar inventário (permite cancelar inventários em andamento e concluídos)
    Se o inventário estiver concluído, desfaz as movimentações de estoque
    """
    # Verificar se é uma requisição AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    inventario = InventarioEstoque.query.get_or_404(id)
    
    # Verificar se o inventário pode ser cancelado
    if inventario.status == 'Cancelado':
        error_msg = 'Este inventário já está cancelado.'
        if is_ajax:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400
        flash(error_msg, 'warning')
        return redirect(url_for('inventario.inventarios'))
    
    try:
        # Usar o método cancelar() do modelo que trata tanto inventários em andamento quanto concluídos
        inventario.cancelar(current_user.id)
        
        if inventario.status == 'Concluído':
            success_msg = 'Inventário cancelado com sucesso! As movimentações de estoque foram desfeitas.'
        else:
            success_msg = 'Inventário cancelado com sucesso!'
        
        if is_ajax:
            return jsonify({
                'success': True,
                'message': success_msg,
                'redirect': url_for('inventario.inventarios')
            })
        
        flash(success_msg, 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao cancelar inventário: {str(e)}")
        error_msg = f'Erro ao cancelar inventário: {str(e)}'
        
        if is_ajax:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 500
        
        flash(error_msg, 'danger')
    
    return redirect(url_for('inventario.inventarios'))


@inventario_bp.route('/<int:id>/reabrir', methods=['POST'])
@login_required
def reabrir_inventario(id):
    """
    Reabrir inventário concluído, desfazendo movimentações e voltando para contagem
    """
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    inventario = InventarioEstoque.query.get_or_404(id)

    if inventario.status not in ['Concluído', 'Cancelado']:
        error_msg = 'Apenas inventários concluídos ou cancelados podem ser reabertos.'
        if is_ajax:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400
        flash(error_msg, 'warning')
        return redirect(url_for('inventario.inventarios'))

    try:
        status_anterior = inventario.status
        inventario.reabrir(current_user.id)
        
        if status_anterior == 'Concluído':
            success_msg = 'Inventário reaberto com sucesso. As movimentações foram desfeitas.'
        else:
            success_msg = 'Inventário reaberto com sucesso. A contagem pode ser retomada.'

        if is_ajax:
            return jsonify({
                'success': True,
                'message': success_msg,
                'redirect': url_for('inventario.inventario_contagem', id=id)
            })

        flash(success_msg, 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao reabrir inventário: {str(e)}")
        error_msg = f'Erro ao reabrir inventário: {str(e)}'

        if is_ajax:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 500

        flash(error_msg, 'danger')

    return redirect(url_for('inventario.inventario_contagem', id=id))

@inventario_bp.route('/api/get-quantidade-sistema', methods=['GET'])
@login_required
def api_get_quantidade_sistema():
    """
    API para obter a quantidade do sistema baseada na data de contagem
    """
    estoque_id = request.args.get('estoque_id', type=int)
    data_contagem_str = request.args.get('data_contagem')
    
    if not estoque_id:
        return jsonify({'success': False, 'error': 'estoque_id é obrigatório'}), 400
    
    estoque = Estoque.query.get_or_404(estoque_id)
    
    # Processar data de contagem
    data_contagem = None
    if data_contagem_str:
        try:
            if len(data_contagem_str) == 10:
                data_contagem = datetime.strptime(data_contagem_str, '%Y-%m-%d')
            else:
                data_contagem = datetime.strptime(data_contagem_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    
    try:
        # Calcular quantidade do sistema usando get_saldo_ate_data
        quantidade_sistema = estoque.get_saldo_ate_data(data_contagem)
        
        return jsonify({
            'success': True,
            'quantidade_sistema': float(quantidade_sistema)
        })
    except Exception as e:
        logger.error(f"Erro ao calcular quantidade do sistema: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@inventario_bp.route('/<int:inventario_id>/item/<int:item_id>/contagem', methods=['POST'])
@login_required
def salvar_contagem_item(inventario_id, item_id):
    """
    Salvar contagem de um item
    """
    inventario = InventarioEstoque.query.get_or_404(inventario_id)
    
    # Verificar se o inventário está em andamento
    if inventario.status != 'Em andamento':
        return jsonify({'error': 'Este inventário não está em andamento'}), 400
    
    item = ItemInventario.query.filter_by(inventario_id=inventario_id, id=item_id).first_or_404()
    quantidade = request.form.get('quantidade_contada', type=float)
    data_contagem_str = request.form.get('data_contagem')
    
    # Processar data de contagem se fornecida
    data_contagem = None
    if data_contagem_str:
        try:
            # Aceitar formato YYYY-MM-DD ou YYYY-MM-DD HH:MM:SS
            if len(data_contagem_str) == 10:
                data_contagem = datetime.strptime(data_contagem_str, '%Y-%m-%d')
            else:
                data_contagem = datetime.strptime(data_contagem_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass  # Se a data não for válida, usar datetime.now() no método contar
    
    try:
        # Se não houver data de contagem, usar a data atual (será tratada como data padrão no frontend)
        if not data_contagem:
            data_contagem = datetime.now()
        
        # Recalcular quantidade_sistema baseado na data de contagem usando get_saldo_ate_data
        item.quantidade_sistema = item.estoque.get_saldo_ate_data(data_contagem)
        
        item.contar(Decimal(str(quantidade)) if quantidade is not None else None, current_user.id, data_contagem=data_contagem)
        
        # Calcular o progresso atual
        total_itens = len(inventario.itens)
        itens_contados = sum(1 for i in inventario.itens if i.quantidade_contada is not None)
        percentual = int((itens_contados / total_itens * 100)) if total_itens > 0 else 0
        
        return jsonify({
            'success': True, 
            'diferenca': float(item.diferenca) if item.diferenca is not None else None,
            'quantidade_sistema': float(item.quantidade_sistema),
            'progresso': {
                'contados': itens_contados,
                'total': total_itens,
                'percentual': percentual
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao salvar contagem: {str(e)}")
        return jsonify({'error': str(e)}), 500

@inventario_bp.route('/<int:inventario_id>/item/<int:item_id>/observacao', methods=['POST'])
@login_required
def salvar_observacao_item(inventario_id, item_id):
    """
    Salvar observação de um item
    """
    inventario = InventarioEstoque.query.get_or_404(inventario_id)
    
    # Verificar se o inventário está em andamento
    if inventario.status != 'Em andamento':
        return jsonify({'error': 'Este inventário não está em andamento'}), 400
    
    item = ItemInventario.query.filter_by(inventario_id=inventario_id, id=item_id).first_or_404()
    observacoes = request.form.get('observacoes', '')
    
    try:
        item.observacoes = observacoes
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao salvar observação: {str(e)}")
        return jsonify({'error': str(e)}), 500

@inventario_bp.route('/api/buscar-itens')
@login_required
def api_buscar_itens():
    """
    API para buscar itens para o inventário
    """
    termo = request.args.get('termo', '')
    
    if len(termo) < 3:
        return jsonify({'itens': []})
    
    try:
        termo = f"%{termo}%"
        
        # Consulta para itens de material
        query = db.session.query(
            Estoque.id,
            Material.codigo,
            Material.nome,
            Estoque.tipo_item,
            Estoque.localizacao,
            Estoque.quantidade,
            Unidade.nome
        ).join(Material, Estoque.material_id == Material.id).join(Unidade, Material.unidade_id == Unidade.id).filter(
            or_(
                Material.nome.ilike(termo),
                Material.codigo.ilike(termo),
                Estoque.localizacao.ilike(termo)
            )
        )
        
        # Similar para EPIs se necessário
        
        resultados = query.limit(20).all()
        
        itens = []
        for r in resultados:
            itens.append({
                'id': r[0],
                'codigo': r[1],
                'nome': r[2],
                'tipo': r[3],
                'localizacao': r[4],
                'quantidade': float(r[5]),
                'unidade': r[6]
            })
        
        return jsonify({'itens': itens})
    except Exception as e:
        logger.error(f"Erro na busca de itens: {str(e)}")
        return jsonify({'error': str(e)}), 500

@inventario_bp.route('/<int:id>/verificar-itens-nao-contados')
@login_required
def verificar_itens_nao_contados(id):
    """
    Verificar se existem itens não contados em um inventário
    """
    try:
        itens_nao_contados = ItemInventario.query.filter_by(inventario_id=id, quantidade_contada=None).count()
        return jsonify({'itens_nao_contados': itens_nao_contados})
    except Exception as e:
        logger.error(f"Erro ao verificar itens não contados: {str(e)}")
        return jsonify({'error': str(e)}), 500

@inventario_bp.route('/<int:inventario_id>/adicionar-item', methods=['POST'])
@login_required
def adicionar_item_inventario(inventario_id):
    """
    Adicionar um ou mais novos itens ao inventário durante a contagem
    Aceita estoque_id (único) ou estoque_ids (lista) para compatibilidade
    """
    inventario = InventarioEstoque.query.get_or_404(inventario_id)
    
    # Verificar se o inventário está em andamento
    if inventario.status != 'Em andamento':
        return jsonify({'error': 'Este inventário não está em andamento'}), 400
    
    # Suportar tanto estoque_id único quanto estoque_ids múltiplos
    estoque_ids = request.form.getlist('estoque_ids[]')
    # Também tentar sem os colchetes para compatibilidade
    if not estoque_ids:
        estoque_ids = request.form.getlist('estoque_ids')
    if not estoque_ids:
        # Fallback para compatibilidade com código antigo
        estoque_id = request.form.get('estoque_id', type=int)
        if estoque_id:
            estoque_ids = [estoque_id]
    
    if not estoque_ids:
        return jsonify({'error': 'ID(s) do estoque é(são) obrigatório(s)'}), 400
    
    # Converter para inteiros
    try:
        estoque_ids = [int(id) for id in estoque_ids]
    except (ValueError, TypeError):
        return jsonify({'error': 'IDs de estoque inválidos'}), 400
    
    itens_adicionados = []
    itens_nao_adicionados = []
    
    try:
        for estoque_id in estoque_ids:
            # Verificar se o item já está no inventário
            item_existente = ItemInventario.query.filter_by(
                inventario_id=inventario_id,
                estoque_id=estoque_id
            ).first()
            
            if item_existente:
                itens_nao_adicionados.append({
                    'estoque_id': estoque_id,
                    'motivo': 'Item já está no inventário'
                })
                continue
            
            # Verificar se o estoque existe
            estoque = Estoque.query.get(estoque_id)
            if not estoque:
                itens_nao_adicionados.append({
                    'estoque_id': estoque_id,
                    'motivo': 'Estoque não encontrado'
                })
                continue
            
            # Criar novo item de inventário
            item_inventario = ItemInventario(
                inventario_id=inventario_id,
                estoque_id=estoque_id,
                quantidade_sistema=estoque.quantidade
            )
            db.session.add(item_inventario)
            db.session.flush()  # Para obter o ID antes do commit
            
            # Preparar dados do item para resposta
            itens_adicionados.append({
                'id': item_inventario.id,
                'estoque_id': estoque_id,
                'quantidade_sistema': float(item_inventario.quantidade_sistema),
                'quantidade_contada': float(item_inventario.quantidade_contada) if item_inventario.quantidade_contada else None,
                'diferenca': float(item_inventario.diferenca) if item_inventario.diferenca else None,
                'observacoes': item_inventario.observacoes or '',
                'tipo_item': estoque.tipo_item,
                'codigo': estoque.material.codigo if estoque.material else (estoque.epi.material.codigo if estoque.epi and estoque.epi.material else 'N/A'),
                'nome': estoque.material.nome if estoque.material else (estoque.epi.material.nome if estoque.epi and estoque.epi.material else 'Item sem descrição'),
                'localizacao': estoque.localizacao or 'Não especificado',
                'unidade': estoque.material.unidade_obj.nome if estoque.material else ''
            })
        
        db.session.commit()
        
        # Retornar resposta
        response = {
            'success': True,
            'message': f'{len(itens_adicionados)} item(ns) adicionado(s) com sucesso!',
            'itens_adicionados': itens_adicionados
        }
        
        if itens_nao_adicionados:
            response['itens_nao_adicionados'] = itens_nao_adicionados
        
        # Para compatibilidade com código antigo, retornar também 'item' se for apenas um
        if len(itens_adicionados) == 1:
            response['item'] = itens_adicionados[0]
        
        return jsonify(response)
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao adicionar itens ao inventário: {str(e)}")
        return jsonify({'error': str(e)}), 500

@inventario_bp.route('/<int:inventario_id>/item/<int:item_id>/excluir', methods=['POST'])
@login_required
def excluir_item_inventario(inventario_id, item_id):
    """
    Excluir um item do inventário
    """
    # Verificar se é uma requisição AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    inventario = InventarioEstoque.query.get_or_404(inventario_id)
    
    # Verificar se o inventário está em andamento
    if inventario.status != 'Em andamento':
        error_msg = 'Apenas itens de inventários em andamento podem ser excluídos.'
        if is_ajax:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400
        flash(error_msg, 'warning')
        return redirect(url_for('inventario.inventario_contagem', id=inventario_id))
    
    item = ItemInventario.query.filter_by(
        inventario_id=inventario_id,
        id=item_id
    ).first_or_404()
    
    try:
        # Obter informações do item antes de excluir para feedback
        item_info = {
            'id': item.id,
            'codigo': item.estoque.material.codigo if item.estoque.material else (item.estoque.epi.material.codigo if item.estoque.epi and item.estoque.epi.material else 'N/A'),
            'nome': item.estoque.material.nome if item.estoque.material else (item.estoque.epi.material.nome if item.estoque.epi and item.estoque.epi.material else 'Item sem descrição')
        }
        
        # Excluir o item
        db.session.delete(item)
        db.session.commit()
        
        success_msg = f'Item "{item_info["nome"]}" removido do inventário com sucesso!'
        
        if is_ajax:
            return jsonify({
                'success': True,
                'message': success_msg,
                'item_id': item_id
            })
        
        flash(success_msg, 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir item do inventário: {str(e)}")
        error_msg = f'Erro ao excluir item: {str(e)}'
        
        if is_ajax:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 500
        
        flash(error_msg, 'danger')
    
    return redirect(url_for('inventario.inventario_contagem', id=inventario_id))
