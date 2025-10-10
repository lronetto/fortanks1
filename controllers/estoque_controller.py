from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, abort
from flask_login import login_required, current_user
from models.estoque import Estoque, MovimentacaoEstoque, InventarioEstoque, ItemInventario
from models.material import Material
from models.epi import EPI
from models.centro_custo import CentroCusto
from models.database import db
from forms.estoque_forms import EstoqueForm, MovimentacaoEstoqueForm, InventarioEstoqueForm, ItemInventarioForm, FiltroEstoqueForm
from datetime import datetime, date
from sqlalchemy import or_, func

from decimal import Decimal
import logging

from models.produto_composto import ProdutoComposto

# Configuração do logger
logger = logging.getLogger(__name__)

# Criar blueprint
estoque_bp = Blueprint('estoque', __name__)

# Rotas principais de estoque
@estoque_bp.route('/')
@login_required
def index():
    """
    Listagem de itens no estoque com filtros
    """
    page = request.args.get('page', 1, type=int)
    form_filtro = FiltroEstoqueForm()
    
    # Aplicar filtros da URL aos campos do formulário
    if request.args.get('tipo_item'):
        form_filtro.tipo_item.data = request.args.get('tipo_item')
    if request.args.get('status_estoque'):
        form_filtro.status_estoque.data = request.args.get('status_estoque')
    if request.args.get('termo_busca'):
        form_filtro.termo_busca.data = request.args.get('termo_busca')
    
    # Consulta base
    query = Estoque.query
    
    # Aplicar filtros
    if form_filtro.tipo_item.data and form_filtro.tipo_item.data != 'todos':
        query = query.filter(Estoque.tipo_item == form_filtro.tipo_item.data)
    
    if form_filtro.termo_busca.data:
        termo = f"%{form_filtro.termo_busca.data}%"
        query = query.join(Estoque.material, isouter=True).join(
            ProdutoComposto, Estoque.ProdComp_id == ProdutoComposto.id, isouter=True).filter(
            or_(
                Material.nome.ilike(termo),
                Material.codigo.ilike(termo),
                Estoque.localizacao.ilike(termo),
                ProdutoComposto.nome.ilike(termo)
            )
        )
    
    # Filtrar por status
    if form_filtro.status_estoque.data and form_filtro.status_estoque.data != 'todos':
        # Implementar filtros mais complexos baseados no status
        if form_filtro.status_estoque.data == 'critico':
            query = query.filter(Estoque.quantidade <= Estoque.quantidade_minima)
        elif form_filtro.status_estoque.data == 'esgotado':
            query = query.filter(Estoque.quantidade <= 0)
        elif form_filtro.status_estoque.data == 'excesso':
            query = query.filter(Estoque.quantidade >= Estoque.quantidade_maxima)
    
    # Obter resultados paginados
    items = query.order_by(Estoque.id.desc()).paginate(page=page, per_page=20, error_out=False)
    
    return render_template('estoque/index.html', items=items, form_filtro=form_filtro)

@estoque_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Adicionar novo item ao estoque
    """
    # Verificar se é uma requisição AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    form = EstoqueForm()
    # Preencher as opções de select
    form.material_id.choices = [(m.id, f"{m.codigo} - {m.nome}") for m in Material.query.filter_by(ativo=True).all()]
    form.material_id.choices.insert(0, (0, 'Selecione um material'))
    
    if form.validate_on_submit():
        try:
            item = Estoque()
            item.tipo_item = 'material'  # Sempre será material
            item.material_id = form.material_id.data
            item.quantidade = form.quantidade.data or 0
            item.quantidade_minima = form.quantidade_minima.data
            item.quantidade_maxima = form.quantidade_maxima.data or 0
            item.lote = form.lote.data
            item.data_validade = form.data_validade.data
            item.usuario_id = current_user.id
            item.save()
            
            # Se tiver quantidade inicial, criar movimentação de entrada
            if form.quantidade.data and float(form.quantidade.data) > 0:
                mov = MovimentacaoEstoque(
                    estoque_id=item.id,
                    tipo_movimento='entrada',
                    quantidade=form.quantidade.data,
                    observacao='Cadastro inicial',
                    usuario_id=current_user.id
                )
                mov.save()
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Item adicionado ao estoque com sucesso!',
                    'redirect': url_for('estoque.index')
                })
            
            flash('Item adicionado ao estoque com sucesso!', 'success')
            return redirect(url_for('estoque.index'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao adicionar item ao estoque: {str(e)}")
            
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': f'Erro ao adicionar item: {str(e)}'
                })
            
            flash(f'Erro ao adicionar item: {str(e)}', 'danger')
    elif request.method == 'POST' and is_ajax:
        # Retornar erros de validação para o modal
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = field_errors
        
        print(errors)
        return jsonify({
            'success': False,
            'message': 'Erro de validação',
            'errors': errors
        })
    
    return render_template('estoque/form.html', form=form, title='Novo Item de Estoque')

@estoque_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required

def editar(id):
    """
    Editar item do estoque
    """
    item = Estoque.query.get_or_404(id)
    form = EstoqueForm(obj=item)
    
    # Preencher as opções de select
    form.material_id.choices = [(m.id, f"{m.codigo} - {m.nome}") for m in Material.query.filter_by(ativo=True).all()]
    form.material_id.choices.insert(0, (0, 'Selecione um material'))
    
    form.epi_id.choices = [(e.id, f"{e.material.nome} - CA: {e.ca_numero or 'N/A'}") for e in EPI.query.all()]
    form.epi_id.choices.insert(0, (0, 'Selecione um EPI'))
    
    form.centro_custo_id.choices = [(c.id, c.descricao) for c in CentroCusto.query.all()]
    form.centro_custo_id.choices.insert(0, (0, 'Selecione um centro de custo'))
    
    if form.validate_on_submit():
        try:
            # Verificar se a quantidade foi alterada
            quantidade_anterior = item.quantidade
            
            # Atualizar campos
            item.tipo_item = form.tipo_item.data
            
            if form.tipo_item.data == 'material' and form.material_id.data:
                item.material_id = form.material_id.data
                item.epi_id = None
            elif form.tipo_item.data == 'epi' and form.epi_id.data:
                item.epi_id = form.epi_id.data
                item.material_id = None
            
            # Não atualizar quantidade diretamente aqui, usar movimentação de ajuste
            item.quantidade_minima = form.quantidade_minima.data
            item.quantidade_maxima = form.quantidade_maxima.data
            item.localizacao = form.localizacao.data
            item.lote = form.lote.data
            item.data_validade = form.data_validade.data
            
            if form.centro_custo_id.data:
                item.centro_custo_id = form.centro_custo_id.data
            else:
                item.centro_custo_id = None
            
            item.usuario_id = current_user.id
            item.save()
            
            # Se a quantidade foi alterada, criar movimentação de ajuste
            nova_quantidade = form.quantidade.data
            if nova_quantidade != quantidade_anterior:
                mov = MovimentacaoEstoque(
                    estoque_id=item.id,
                    tipo_movimento='ajuste',
                    quantidade=nova_quantidade,  # Quantidade total após ajuste
                    observacao='Ajuste manual via edição',
                    usuario_id=current_user.id
                )
                mov.save()
                
                # Ajustar quantidade do item diretamente
                item.quantidade = nova_quantidade
                item.save()
            
            flash('Item atualizado com sucesso!', 'success')
            return redirect(url_for('estoque.detalhes', id=item.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao editar item do estoque: {str(e)}")
            flash(f'Erro ao atualizar item: {str(e)}', 'danger')
    
    return render_template('estoque/form.html', form=form, title='Editar Item de Estoque')

@estoque_bp.route('/api/listar', methods=['GET'])
@login_required
def api_listar():
    """
    API que retorna uma lista de itens de estoque (Materiais e Produtos Compostos) para uso em selects.
    """
    search_term = request.args.get('q', '')

    # Query base no Estoque, carregando relacionamentos para evitar N+1 queries
    query = Estoque.query.options(
        db.joinedload(Estoque.material).joinedload(Material.unidade_obj),
        db.joinedload(Estoque.produto_composto)
    ).filter(
        db.or_(Estoque.material_id.isnot(None), Estoque.ProdComp_id.isnot(None))
    )

    # Aplicar filtro de busca se houver
    if search_term:
        query = query.outerjoin(Material, Estoque.material_id == Material.id)\
                     .outerjoin(ProdutoComposto, Estoque.ProdComp_id == ProdutoComposto.id)\
                     .filter(
                        db.or_(
                            Material.nome.ilike(f'%{search_term}%'),
                            ProdutoComposto.nome.ilike(f'%{search_term}%')
                        )
                     )

    itens_estoque = query.all()

    resultado = []
    for item in itens_estoque:
        text = ""
        # Verifica se o item de estoque é um material
        if item.material:
            unidade = f" ({item.material.unidade_obj.nome})" if item.material.unidade_obj else " (s/unid.)"
            text = f"[M] {item.material.nome}{unidade}"
            resultado.append({'id': item.id, 'text': text})
        # Verifica se o item de estoque é um produto composto
        elif item.produto_composto:
            text = f"[P] {item.produto_composto.nome}"
            resultado.append({'id': item.id, 'text': text})
            
    # Ordena a lista final pelo texto
    resultado.sort(key=lambda x: x['text'])
            
    return jsonify({'results': resultado})


@estoque_bp.route('/detalhes/<int:id>')
@login_required
def detalhes(id):
    """
    Exibir detalhes de um item do estoque
    """
    estoque = Estoque.query.get_or_404(id)
    movimentacoes = MovimentacaoEstoque.query.filter_by(estoque_id=id).order_by(MovimentacaoEstoque.data_movimento.desc()).limit(10).all()
    return render_template('estoque/detalhes.html', estoque=estoque, movimentacoes=movimentacoes)

@estoque_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required

def excluir(id):
    """
    Excluir item do estoque
    """
    item = Estoque.query.get_or_404(id)
    try:
        # Excluir movimentações
        MovimentacaoEstoque.query.filter_by(estoque_id=id).delete()
        # Excluir item
        item.delete()
        flash('Item excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir item do estoque: {str(e)}")
        flash(f'Erro ao excluir item: {str(e)}', 'danger')
    
    return redirect(url_for('estoque.index'))

# Rotas de Movimentação de Estoque
@estoque_bp.route('/movimentacoes')
@login_required
def movimentacoes():
    """
    Listagem de movimentações de estoque
    """
    page = request.args.get('page', 1, type=int)
    estoque_id = request.args.get('estoque_id', None, type=int)
    tipo = request.args.get('tipo', None)
    data_inicio = request.args.get('data_inicio', None)
    data_fim = request.args.get('data_fim', None)
    material_id = request.args.get('material_id', None, type=int)
    observacao = request.args.get('observacao', None)
    
    # Consulta base
    query = MovimentacaoEstoque.query
    
    # Aplicar filtros
    if estoque_id:
        query = query.filter(MovimentacaoEstoque.estoque_id == estoque_id)
    
    # Filtro por material
    if material_id:
        query = query.join(Estoque).filter(Estoque.material_id == material_id)
    
    if tipo:
        query = query.filter(MovimentacaoEstoque.tipo_movimento == tipo)
    
    # Filtro por observação
    if observacao:
        query = query.filter(MovimentacaoEstoque.observacao.ilike(f'%{observacao}%'))
    
    if data_inicio:
        try:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            query = query.filter(func.date(MovimentacaoEstoque.data_movimento) >= data_inicio)
        except ValueError:
            flash('Formato de data inválido para Data Início', 'warning')
    
    if data_fim:
        try:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            query = query.filter(func.date(MovimentacaoEstoque.data_movimento) <= data_fim)
        except ValueError:
            flash('Formato de data inválido para Data Fim', 'warning')
    
    # Obter resultados paginados
    movimentacoes = query.order_by(MovimentacaoEstoque.data_movimento.desc()).paginate(page=page, per_page=20, error_out=False)
    
    # Obter todos os itens de estoque para o filtro
    itens_estoque = Estoque.query.all()
    
    # Obter todos os materiais para o filtro
    materiais = Material.query.filter_by(ativo=True).order_by(Material.nome).all()
    
    return render_template('estoque/movimentacoes.html', 
                          movimentacoes=movimentacoes, 
                          itens_estoque=itens_estoque,
                          materiais=materiais,
                          estoque_id=estoque_id, 
                          tipo=tipo, 
                          data_inicio=data_inicio, 
                          data_fim=data_fim,
                          material_id=material_id,
                          observacao=observacao)

@estoque_bp.route('/nova-movimentacao', methods=['GET', 'POST'])
@login_required

def nova_movimentacao():
    """
    Adicionar nova movimentação ao estoque
    """
    form = MovimentacaoEstoqueForm()
    
    # Preencher opções de estoque
    estoques = Estoque.query.all()
    opcoes_estoque = []
    for e in estoques:
        nome_item = ''
        if e.material:
            nome_item = f"{e.material.codigo} - {e.material.nome}"
        elif e.epi and e.epi.material:
            nome_item = f"{e.epi.material.codigo or 'S/C'} - {e.epi.material.nome}"
        else:
            nome_item = "Item sem descrição"
            
        # Determinar a unidade a ser exibida
        unidade = ""
        if e.material and e.material.unidade:
            unidade = e.material.unidade
        elif e.epi and e.epi.material and e.epi.material.unidade:
            unidade = e.epi.material.unidade
            
        opcoes_estoque.append((e.id, f"{nome_item} ({float(e.quantidade)} {unidade})"))
    
    form.estoque_id.choices = opcoes_estoque
    
    if form.validate_on_submit():
        try:
            estoque = Estoque.query.get(form.estoque_id.data)
            if not estoque:
                flash('Item de estoque não encontrado', 'danger')
                return redirect(url_for('estoque.movimentacoes'))
            
            tipo_movimento = form.tipo_movimento.data
            quantidade = form.quantidade.data
            
            if tipo_movimento == 'saida' and quantidade > estoque.quantidade:
                flash('Quantidade insuficiente em estoque para esta saída', 'danger')
                return render_template('estoque/movimentacao_form.html', form=form)
            
            mov = MovimentacaoEstoque(
                estoque_id=form.estoque_id.data,
                tipo_movimento=tipo_movimento,
                quantidade=quantidade,
                observacao=form.observacao.data,
                usuario_id=current_user.id
            )
            
            mov.save()
            flash('Movimentação registrada com sucesso!', 'success')
            return redirect(url_for('estoque.movimentacoes'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao registrar movimentação: {str(e)}")
            flash(f'Erro ao registrar movimentação: {str(e)}', 'danger')
    
    return render_template('estoque/movimentacao_form.html', form=form)

@estoque_bp.route('/movimentacoes/excluir/<int:id_movimentacao>', methods=['POST'])
@login_required
def excluir_movimentacao(id_movimentacao):
    """
    Exclui uma movimentação de estoque específica.
    Apenas administradores podem realizar esta ação.
    """
    if not current_user.is_admin:
        flash('Acesso negado. Você não tem permissão para excluir movimentações.', 'danger')
        return redirect(url_for('estoque.movimentacoes'))

    movimentacao = MovimentacaoEstoque.query.get_or_404(id_movimentacao)
    
    try:
        # O método delete no modelo MovimentacaoEstoque deve cuidar da reversão do estoque
        movimentacao.delete() 
        flash(f'Movimentação ID {id_movimentacao} excluída com sucesso e estoque revertido.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir movimentação de estoque ID {id_movimentacao}: {str(e)}")
        flash(f'Erro ao excluir movimentação: {str(e)}', 'danger')
    
    return redirect(url_for('estoque.movimentacoes'))

# Rotas de API para estoque
@estoque_bp.route('/api/estoque/<int:id>')
@login_required
def api_estoque_info(id):
    """
    API para buscar informações de um item de estoque
    """
    try:
        estoque = Estoque.query.get_or_404(id)
        
        return jsonify({
            'success': True,
            'data': {
                'id': estoque.id,
                'material_id': estoque.material_id,
                'material_nome': estoque.material.nome if estoque.material else None,
                'material_unidade': estoque.material.unidade if estoque.material else None,
                'tipo_item': estoque.tipo_item,
                'quantidade': float(estoque.quantidade),
                'quantidade_minima': float(estoque.quantidade_minima),
                'quantidade_maxima': float(estoque.quantidade_maxima),
                'status': estoque.status_estoque
            }
        })
    except Exception as e:
        logger.error(f"Erro ao buscar informações do estoque: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao buscar informações: {str(e)}'
        }), 500

@estoque_bp.route('/api/estoque-por-material/<int:material_id>')
@login_required
def api_estoque_por_material(material_id):
    """
    API para buscar informações de estoque por material
    """
    try:
        estoque = Estoque.query.filter_by(material_id=material_id, tipo_item='material').first()
        
        if not estoque:
            return jsonify({
                'success': True,
                'data': None
            })
        
        material = Material.query.get(material_id)
        
        return jsonify({
            'success': True,
            'data': {
                'id': estoque.id,
                'material_id': estoque.material_id,
                'material_nome': material.nome if material else None,
                'material_unidade': material.unidade if material else None,
                'quantidade': float(estoque.quantidade),
                'quantidade_minima': float(estoque.quantidade_minima),
                'quantidade_maxima': float(estoque.quantidade_maxima),
                'status': estoque.status_estoque
            }
        })
    except Exception as e:
        logger.error(f"Erro ao buscar informações do estoque por material: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao buscar informações: {str(e)}'
        }), 500

# Rotas de Inventário
@estoque_bp.route('/inventarios')
@login_required
def inventarios():
    """
    Listagem de inventários
    """
    page = request.args.get('page', 1, type=int)
    tipo = request.args.get('tipo', None)
    status = request.args.get('status', None)
    
    # Consulta base
    query = InventarioEstoque.query
    
    # Aplicar filtros
    if tipo:
        query = query.filter(InventarioEstoque.tipo_inventario == tipo)
    
    if status:
        query = query.filter(InventarioEstoque.status == status)
    
    # Obter resultados
    inventarios = query.order_by(InventarioEstoque.id.desc()).all()
    
    # Paginação manual se necessário
    pagination = {
        'page': page,
        'pages': (len(inventarios) + 9) // 10,  # Arredonda para cima
        'total': len(inventarios)
    }
    
    return render_template('estoque/inventario_lista.html', 
                          inventarios=inventarios, 
                          pagination=pagination,
                          request=request)

@estoque_bp.route('/novo-inventario', methods=['GET', 'POST'])
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
                
                logger.info(f"Filtros recebidos - Tipo: {tipo_item}, Localização: {localizacao}, Categoria: {categoria}, Grupos: {grupos_selecionados}")
                
                # Verificar se pelo menos um filtro foi selecionado
                if not any([tipo_item, localizacao, categoria, grupos_selecionados]):
                    logger.warning("Inventário parcial sem filtros selecionados")
                    if is_ajax:
                        return jsonify({
                            'success': False,
                            'message': 'Para inventário parcial, selecione pelo menos um filtro.'
                        }), 400
                    else:
                        flash('Para inventário parcial, selecione pelo menos um filtro.', 'danger')
                        return render_template('estoque/inventario_form.html', 
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
                    'redirect': url_for('estoque.inventario_detalhes', id=inventario.id)
                })
            else:
                flash('Inventário criado com sucesso! Agora você pode iniciar a contagem.', 'success')
                return redirect(url_for('estoque.inventario_detalhes', id=inventario.id))
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
    
    return render_template('estoque/inventario_form.html', 
                          form=form, 
                          categorias=categorias, 
                          localizacoes=localizacoes)

@estoque_bp.route('/inventario/<int:id>')
@login_required
def inventario_detalhes(id):
    """
    Detalhes de um inventário
    """
    inventario = InventarioEstoque.query.get_or_404(id)
    itens = ItemInventario.query.filter_by(inventario_id=id).all()
    
    return render_template('estoque/inventario_detalhes.html', 
                          inventario=inventario, 
                          itens=itens)

@estoque_bp.route('/gerenciar-inventario')
@login_required
def gerenciar_inventario():
    """
    Página principal para gerenciar inventários
    """
    return render_template('estoque/gerenciar_inventario.html')

@estoque_bp.route('/api/estatisticas-inventario')
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
        from datetime import datetime, timedelta
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

@estoque_bp.route('/api/inventarios-ativos')
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

@estoque_bp.route('/api/historico-inventarios')
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
            from datetime import datetime
            data_filtro = datetime.strptime(data, '%Y-%m-%d').date()
            query = query.filter(db.func.date(InventarioEstoque.data_inicio) == data_filtro)
        
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

@estoque_bp.route('/api/salvar-configuracoes', methods=['POST'])
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

@estoque_bp.route('/inventario/<int:id>/contagem')
@login_required
def inventario_contagem(id):
    """
    Página de contagem de inventário
    """
    inventario = InventarioEstoque.query.get_or_404(id)
    
    # Verificar se o inventário está em andamento
    if inventario.status != 'Em andamento':
        flash('Este inventário já foi finalizado ou cancelado', 'warning')
        return redirect(url_for('estoque.inventario_detalhes', id=id))
    
    return render_template('estoque/inventario_contagem.html', 
                          inventario=inventario)

@estoque_bp.route('/inventario/<int:id>/finalizar', methods=['POST'])
@login_required

def finalizar_inventario(id):
    """
    Finalizar inventário com ajustes de estoque
    """
    inventario = InventarioEstoque.query.get_or_404(id)
    
    # Verificar se todos os itens foram contados
    itens_nao_contados = ItemInventario.query.filter_by(inventario_id=id, quantidade_contada=None).count()
    if itens_nao_contados > 0:
        flash(f'Existem {itens_nao_contados} itens não contados. Finalize a contagem antes de encerrar o inventário.', 'danger')
        return redirect(url_for('estoque.inventario_contagem', id=id))
    
    try:
        # Finalizar inventário e ajustar estoques
        inventario.finalizar(current_user.id)
        flash('Inventário finalizado com sucesso! Os estoques foram ajustados.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao finalizar inventário: {str(e)}")
        flash(f'Erro ao finalizar inventário: {str(e)}', 'danger')
    
    return redirect(url_for('estoque.inventario_detalhes', id=id))

@estoque_bp.route('/inventario/<int:id>/cancelar', methods=['POST'])
@login_required

def cancelar_inventario(id):
    """
    Cancelar inventário
    """
    inventario = InventarioEstoque.query.get_or_404(id)
    
    try:
        inventario.status = 'Cancelado'
        inventario.data_fim = datetime.now()
        inventario.finalizado_por_id = current_user.id
        db.session.commit()
        flash('Inventário cancelado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao cancelar inventário: {str(e)}")
        flash(f'Erro ao cancelar inventário: {str(e)}', 'danger')
    
    return redirect(url_for('estoque.inventario_detalhes', id=id))

@estoque_bp.route('/inventario/<int:inventario_id>/item/<int:item_id>/contagem', methods=['POST'])
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
    
    try:
        item.contar(Decimal(str(quantidade)) if quantidade is not None else None, current_user.id)
        
        # Calcular o progresso atual
        total_itens = len(inventario.itens)
        itens_contados = sum(1 for i in inventario.itens if i.quantidade_contada is not None)
        percentual = int((itens_contados / total_itens * 100)) if total_itens > 0 else 0
        
        return jsonify({
            'success': True, 
            'diferenca': float(item.diferenca) if item.diferenca is not None else None,
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

@estoque_bp.route('/inventario/<int:inventario_id>/item/<int:item_id>/observacao', methods=['POST'])
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

@estoque_bp.route('/api/buscar-itens')
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
            Material.unidade
        ).join(Material, Estoque.material_id == Material.id).filter(
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

@estoque_bp.route('/inventario/<int:id>/verificar-itens-nao-contados')
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

# Rotas de API para o gráfico
@estoque_bp.route('/api/estoque/<int:estoque_id>/historico-saldo')
@login_required
def api_historico_saldo_estoque(estoque_id):
    """
    Retorna dados formatados para o gráfico de histórico de saldo.
    Aceita 'data_inicio' e 'data_fim' como query parameters.
    Ex: /api/estoque/1/historico-saldo?data_inicio=2023-01-01&data_fim=2023-12-31
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')

    data_inicio = None
    if data_inicio_str:
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Formato de data_inicio inválido. Use YYYY-MM-DD'}), 400

    data_fim = None
    if data_fim_str:
        try:
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Formato de data_fim inválido. Use YYYY-MM-DD'}), 400

    # Verificar se o item de estoque existe
    item_estoque = Estoque.query.get_or_404(estoque_id)

    historico_data = MovimentacaoEstoque.get_historico_saldo_para_grafico(
        estoque_id=item_estoque.id,
        data_inicio=data_inicio,
        data_fim=data_fim
    )

    datas = [item['data'] for item in historico_data]
    saldos = [item['saldo'] for item in historico_data]

    return jsonify({
        'datas': datas,
        'saldos': saldos
    }) 