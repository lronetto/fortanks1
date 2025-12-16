from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, abort
from flask_login import login_required, current_user
from models.estoque import Estoque, MovimentacaoEstoque
from models.material import Material
from models.epi import EPI
from models.centro_custo import CentroCusto
from models.database import db
from forms.estoque_forms import EstoqueForm, MovimentacaoEstoqueForm, FiltroEstoqueForm
from datetime import datetime, date
from models.unidade import Unidade
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
    
    # Obter lista de localizações únicas para o filtro ANTES de aplicar o valor
    localizacoes = db.session.query(Estoque.localizacao).filter(
        Estoque.localizacao != None,
        Estoque.localizacao != ''
    ).distinct().order_by(Estoque.localizacao).all()
    form_filtro.localizacao.choices = [('', 'Todas')] + [(loc[0], loc[0]) for loc in localizacoes]
    
    # Aplicar valor de localização após popular as choices
    localizacao_param = request.args.get('localizacao', '').strip()
    if localizacao_param:
        form_filtro.localizacao.data = localizacao_param
    
    if request.args.get('termo_busca'):
        form_filtro.termo_busca.data = request.args.get('termo_busca')
    
    # Verificar o checkbox de ignorar localizações
    # Verificar tanto em args (GET) quanto em form (POST)
    ignorar_localizacoes_param = request.args.get('ignorar_localizacoes') or request.form.get('ignorar_localizacoes', '')
    form_filtro.ignorar_localizacoes.data = (ignorar_localizacoes_param == 'on' or 
                                              ignorar_localizacoes_param == 'True' or 
                                              ignorar_localizacoes_param == 'true' or
                                              ignorar_localizacoes_param == '1' or
                                              bool(ignorar_localizacoes_param))
    
    # Log para debug
    logger.info(f"Filtro ignorar_localizacoes: args={request.args.get('ignorar_localizacoes')}, form={request.form.get('ignorar_localizacoes')}, param={ignorar_localizacoes_param}, data={form_filtro.ignorar_localizacoes.data}")
    
    # Consulta base
    query = Estoque.query
    
    # Aplicar filtros
    if form_filtro.tipo_item.data and form_filtro.tipo_item.data != 'todos':
        query = query.filter(Estoque.tipo_item == form_filtro.tipo_item.data)
    
    # Aplicar filtro de localização (não aplicar se estiver agrupando por item)
    # Verificar tanto no form quanto diretamente nos parâmetros da requisição
    localizacao_filtro = None
    if form_filtro.localizacao.data:
        localizacao_filtro = str(form_filtro.localizacao.data).strip()
    elif request.args.get('localizacao'):
        localizacao_filtro = request.args.get('localizacao', '').strip()
    
    # Aplicar filtro se houver valor e não estiver agrupando
    if localizacao_filtro and localizacao_filtro != '' and localizacao_filtro != 'None' and not form_filtro.ignorar_localizacoes.data:
        query = query.filter(Estoque.localizacao == localizacao_filtro)
    
    if form_filtro.termo_busca.data:
        termo = f"%{form_filtro.termo_busca.data}%"
        query = query.outerjoin(Material, Estoque.material_id == Material.id).outerjoin(
            ProdutoComposto, Estoque.ProdComp_id == ProdutoComposto.id).filter(
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
    
    # Garantir joins com Material e ProdutoComposto para ordenação
    # Verificar se os joins já foram feitos (quando há termo de busca)
    if not form_filtro.termo_busca.data:
        query = query.outerjoin(Material, Estoque.material_id == Material.id)\
                     .outerjoin(ProdutoComposto, Estoque.ProdComp_id == ProdutoComposto.id)
    
    # Se o filtro de ignorar localizações estiver ativo, agrupar por material/produto
    # Verificar também diretamente nos parâmetros como fallback
    ignorar_ativo = form_filtro.ignorar_localizacoes.data
    if not ignorar_ativo:
        ignorar_param = request.args.get('ignorar_localizacoes') or request.form.get('ignorar_localizacoes', '')
        ignorar_ativo = (ignorar_param == 'on' or ignorar_param == 'True' or ignorar_param == 'true' or ignorar_param == '1' or bool(ignorar_param))
    
    logger.info(f"Verificando agrupamento: form.data={form_filtro.ignorar_localizacoes.data}, ignorar_ativo={ignorar_ativo}")
    
    if ignorar_ativo:
        logger.info("Agrupamento ATIVO - iniciando processo de agrupamento")
        # Garantir que os relacionamentos são carregados para evitar N+1 queries
        # Usar options para fazer eager loading dos relacionamentos
        from sqlalchemy.orm import joinedload
        # Aplicar eager loading apenas se os joins não foram feitos no termo de busca
        # Se os joins já foram feitos, os relacionamentos já estão disponíveis
        if not form_filtro.termo_busca.data:
            query = query.options(
                joinedload(Estoque.material),
                joinedload(Estoque.produto_composto),
                joinedload(Estoque.epi)
            )
        # Buscar todos os itens e agrupar em Python
        all_items = query.order_by(func.coalesce(Material.nome, ProdutoComposto.nome).asc()).all()
        logger.info(f"Total de itens encontrados antes do agrupamento: {len(all_items)}")
        
        # Agrupar por material_id ou ProdComp_id
        grouped = {}
        for item in all_items:
            # Chave única para agrupamento - usar material_id ou ProdComp_id como chave principal
            # Se ambos forem None, usar o ID do estoque como fallback
            if item.material_id:
                key = f"material_{item.material_id}"
                logger.info(f"Item ID {item.id}: material_id={item.material_id}, quantidade={item.quantidade}, localizacao={item.localizacao}, key={key}")
            elif item.ProdComp_id:
                key = f"produto_{item.ProdComp_id}"
                logger.info(f"Item ID {item.id}: ProdComp_id={item.ProdComp_id}, quantidade={item.quantidade}, localizacao={item.localizacao}, key={key}")
            else:
                # Se não tem material nem produto composto, não agrupar (manter separado)
                key = f"item_{item.id}"
                logger.info(f"Item ID {item.id}: sem material/produto, quantidade={item.quantidade}, key={key}")
            
            if key not in grouped:
                # Criar um novo objeto Estoque agrupado
                grouped_item = Estoque()
                grouped_item.id = item.id
                grouped_item.material_id = item.material_id
                grouped_item.ProdComp_id = item.ProdComp_id
                grouped_item.tipo_item = item.tipo_item
                grouped_item.quantidade = Decimal(0)
                grouped_item.quantidade_minima = item.quantidade_minima or Decimal(0)
                grouped_item.quantidade_maxima = item.quantidade_maxima or Decimal(0)
                grouped_item.localizacao = item.localizacao or "Não especificado"
                grouped_item.material = item.material
                grouped_item.produto_composto = item.produto_composto
                grouped_item.epi = item.epi
                grouped_item.lote = item.lote
                grouped_item.data_validade = item.data_validade
                grouped_item.centro_custo_id = item.centro_custo_id
                grouped_item.criado_em = item.criado_em
                grouped_item.atualizado_em = item.atualizado_em
                grouped_item.usuario_id = item.usuario_id
                grouped[key] = grouped_item
            
            # Somar quantidades
            grouped[key].quantidade += item.quantidade or Decimal(0)
            
            # Coletar localizações únicas
            if item.localizacao:
                current_loc = grouped[key].localizacao or "Não especificado"
                if current_loc == "Não especificado":
                    grouped[key].localizacao = item.localizacao
                elif "," in current_loc:
                    # Se já tem múltiplas, verificar se a nova localização já está na lista
                    localizacoes_list = current_loc.split(", ")
                    if item.localizacao not in localizacoes_list:
                        grouped[key].localizacao += f", {item.localizacao}"
                elif current_loc != item.localizacao:
                    # Se é diferente da primeira, marcar como múltiplas
                    grouped[key].localizacao = f"{current_loc}, {item.localizacao}"
        
        # Converter para lista e ordenar
        grouped_items = list(grouped.values())
        grouped_items.sort(key=lambda x: (x.material.nome if x.material else x.produto_composto.nome if x.produto_composto else ""))
        
        # Log para debug
        logger.info(f"Agrupamento: {len(all_items)} itens originais agrupados em {len(grouped_items)} grupos")
        for grouped_item in grouped_items:
            logger.info(f"  Grupo: material_id={grouped_item.material_id}, quantidade={grouped_item.quantidade}, localizacao={grouped_item.localizacao}")
        
        # Paginação manual
        total = len(grouped_items)
        per_page = 20
        start = (page - 1) * per_page
        end = start + per_page
        paginated_items = grouped_items[start:end]
        
        # Criar um objeto paginado manual
        class PaginatedList:
            def __init__(self, items, page, per_page, total):
                self.items = items
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = (total + per_page - 1) // per_page if per_page > 0 else 1
                
            def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=5):
                last = self.pages
                for num in range(1, last + 1):
                    if num <= left_edge or \
                       (num > self.page - left_current - 1 and num < self.page + right_current) or \
                       num > last - right_edge:
                        yield num
        
        items = PaginatedList(paginated_items, page, per_page, total)
    else:
        # Ordenar pelo nome do material ou pelo nome do produto composto
        items = query.order_by(func.coalesce(Material.nome, ProdutoComposto.nome).asc()).paginate(page=page, per_page=20, error_out=False)
    
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
    localizacao = request.args.get('localizacao', None)
    observacao = request.args.get('observacao', None)
    
    # Consulta base
    query = MovimentacaoEstoque.query.join(Estoque)
    
    # Aplicar filtros
    if estoque_id:
        query = query.filter(MovimentacaoEstoque.estoque_id == estoque_id)
    
    # Filtro por material
    if material_id:
        query = query.filter(Estoque.material_id == material_id)
    
    # Filtro por localização
    if localizacao:
        query = query.filter(Estoque.localizacao == localizacao)
    
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
    
    # Obter lista de localizações únicas para o filtro
    localizacoes = db.session.query(Estoque.localizacao).filter(
        Estoque.localizacao != None,
        Estoque.localizacao != ''
    ).distinct().order_by(Estoque.localizacao).all()
    localizacoes_list = [('', 'Todas')] + [(loc[0], loc[0]) for loc in localizacoes]
    
    return render_template('estoque/movimentacoes.html', 
                          movimentacoes=movimentacoes, 
                          itens_estoque=itens_estoque,
                          materiais=materiais,
                          localizacoes=localizacoes_list,
                          estoque_id=estoque_id, 
                          tipo=tipo, 
                          data_inicio=data_inicio, 
                          data_fim=data_fim,
                          material_id=material_id,
                          localizacao=localizacao,
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


# Rotas de API para o gráfico
@estoque_bp.route('/api/estoque/<int:estoque_id>/historico-saldo')
@login_required
def api_historico_saldo_estoque(estoque_id):
    """
    Retorna dados formatados para o gráfico de histórico de saldo.
    Aceita 'data_inicio', 'data_fim', 'agrupar_semana' e 'agrupar_por_material' como query parameters.
    Se 'agrupar_por_material' for true, agrega o histórico de todos os estoques do mesmo material.
    Ex: /api/estoque/1/historico-saldo?data_inicio=2023-01-01&data_fim=2023-12-31&agrupar_semana=true&agrupar_por_material=true
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    agrupar_semana = request.args.get('agrupar_semana', 'false').lower() == 'true'
    agrupar_por_material = request.args.get('agrupar_por_material', 'false').lower() == 'true'

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
    
    # Se deve agrupar por material, buscar todos os estoques do mesmo material
    if agrupar_por_material and item_estoque.material_id:
        # Buscar todos os estoques com o mesmo material_id
        estoques_material = Estoque.query.filter_by(material_id=item_estoque.material_id).all()
        estoque_ids = [e.id for e in estoques_material]
        
        # Calcular quantidade total atual
        quantidade_total = sum(float(e.quantidade) for e in estoques_material)
        
        # Buscar todas as movimentações de todos os estoques do material
        query = MovimentacaoEstoque.query.filter(MovimentacaoEstoque.estoque_id.in_(estoque_ids))
        
        if data_inicio:
            query = query.filter(MovimentacaoEstoque.data_movimento >= data_inicio)
        if data_fim:
            from datetime import timedelta
            query = query.filter(MovimentacaoEstoque.data_movimento < data_fim + timedelta(days=1))
        
        movimentacoes = query.order_by(MovimentacaoEstoque.data_movimento.asc()).all()
        
        # Calcular saldo inicial (antes da data_inicio, se houver)
        saldo_inicial = Decimal('0.0')
        if data_inicio:
            movimentacoes_anteriores = MovimentacaoEstoque.query.filter(
                MovimentacaoEstoque.estoque_id.in_(estoque_ids),
                MovimentacaoEstoque.data_movimento < data_inicio
            ).order_by(MovimentacaoEstoque.data_movimento.asc()).all()
            
            for mov in movimentacoes_anteriores:
                if mov.tipo_movimento == 'entrada':
                    saldo_inicial += mov.quantidade
                elif mov.tipo_movimento == 'saida':
                    saldo_inicial -= mov.quantidade
                elif mov.tipo_movimento == 'ajuste':
                    saldo_inicial = mov.quantidade
        
        # Agregar movimentações por data e hora (para manter ordem cronológica)
        from collections import defaultdict
        from datetime import datetime, timedelta
        
        # Rastrear saldo individual de cada estoque para calcular ajustes corretamente
        saldos_estoques = {eid: Decimal('0.0') for eid in estoque_ids}
        
        # Calcular saldo inicial de cada estoque
        if data_inicio:
            for eid in estoque_ids:
                movs_ant = MovimentacaoEstoque.query.filter(
                    MovimentacaoEstoque.estoque_id == eid,
                    MovimentacaoEstoque.data_movimento < data_inicio
                ).order_by(MovimentacaoEstoque.data_movimento.asc()).all()
                for mov in movs_ant:
                    if mov.tipo_movimento == 'entrada':
                        saldos_estoques[eid] += mov.quantidade
                    elif mov.tipo_movimento == 'saida':
                        saldos_estoques[eid] -= mov.quantidade
                    elif mov.tipo_movimento == 'ajuste':
                        saldos_estoques[eid] = mov.quantidade
        
        # Ordenar movimentações por data para processar em ordem cronológica
        movimentacoes_ordenadas = sorted(movimentacoes, key=lambda x: x.data_movimento)
        
        # Construir histórico agregado processando cada movimentação em ordem
        historico_data = []
        saldo_acumulado = saldo_inicial
        
        for mov in movimentacoes_ordenadas:
            estoque_id_mov = mov.estoque_id
            saldo_anterior_estoque = saldos_estoques.get(estoque_id_mov, Decimal('0.0'))
            
            if mov.tipo_movimento == 'entrada':
                saldo_acumulado += mov.quantidade
                saldos_estoques[estoque_id_mov] += mov.quantidade
            elif mov.tipo_movimento == 'saida':
                saldo_acumulado -= mov.quantidade
                saldos_estoques[estoque_id_mov] -= mov.quantidade
            elif mov.tipo_movimento == 'ajuste':
                # Calcular diferença do ajuste e aplicar ao saldo agregado
                diferenca = mov.quantidade - saldo_anterior_estoque
                saldo_acumulado += diferenca
                saldos_estoques[estoque_id_mov] = mov.quantidade
            
            historico_data.append({
                "data": mov.data_movimento.strftime('%Y-%m-%d %H:%M:%S'),
                "saldo": float(saldo_acumulado)
            })
        
        # Garantir que o último ponto corresponde à quantidade total atual
        if not data_fim:
            agora = datetime.now()
            if not historico_data or abs(quantidade_total - historico_data[-1]['saldo']) > 0.01:
                if historico_data:
                    historico_data.append({
                        "data": agora.strftime('%Y-%m-%d %H:%M:%S'),
                        "saldo": quantidade_total
                    })
                else:
                    historico_data.append({
                        "data": agora.strftime('%Y-%m-%d %H:%M:%S'),
                        "saldo": quantidade_total
                    })
        
        # Agrupar por semana se solicitado
        if agrupar_semana and historico_data:
            historico_data = MovimentacaoEstoque._agrupar_por_semana(historico_data)
            if not data_fim and historico_data:
                if abs(quantidade_total - historico_data[-1]['saldo']) > 0.01:
                    agora = datetime.now()
                    dias_para_segunda = agora.weekday()
                    inicio_semana = agora - timedelta(days=dias_para_segunda)
                    historico_data.append({
                        "data": agora.strftime('%Y-%m-%d %H:%M:%S'),
                        "saldo": quantidade_total,
                        "semana": f"Semana de {inicio_semana.strftime('%d/%m/%Y')}"
                    })
    else:
        # Comportamento normal: histórico de um único estoque
        historico_data = MovimentacaoEstoque.get_historico_saldo_para_grafico(
            estoque_id=item_estoque.id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            agrupar_por_semana=agrupar_semana
        )
        quantidade_total = float(item_estoque.quantidade)

    datas = [item['data'] for item in historico_data]
    saldos = [item['saldo'] for item in historico_data]
    semanas = [item.get('semana', '') for item in historico_data] if agrupar_semana else []

    return jsonify({
        'datas': datas,
        'saldos': saldos,
        'semanas': semanas,
        'agrupar_semana': agrupar_semana,
        'quantidade_atual': quantidade_total
    }) 