from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from models import Peca, Tanque, Contrato, TanqueProdutoComposto, ProdutoComposto
from models import db
from models.estoque import Estoque, MovimentacaoEstoque
from models.produto_composto import ProdutoCompostoItem
from flask_wtf.csrf import generate_csrf
from flask_login import login_required, current_user
from datetime import datetime
from decimal import Decimal
import json

# Criação do blueprint
peca = Blueprint('peca', __name__, url_prefix='/pecas')

@peca.route('/')
def index():
    """Lista todas as peças do sistema em uma única tabela com filtros"""
    # Obter filtros da query string
    tanque_id = request.args.get('tanque_id', type=int)
    projeto_id = request.args.get('projeto_id', type=int)  # projeto_id = contrato_id
    
    # Query base com join para incluir tanque e contrato
    query = db.session.query(Peca)\
        .join(Tanque, Peca.tanque_id == Tanque.id)\
        .outerjoin(Contrato, Tanque.contrato_id == Contrato.id)
    
    # Aplicar filtros
    if tanque_id:
        query = query.filter(Peca.tanque_id == tanque_id)
    
    if projeto_id:
        query = query.filter(Tanque.contrato_id == projeto_id)
    
    # Ordenar por tanque e número sequencial
    pecas = query.order_by(Tanque.nome, Peca.numero_sequencial).all()
    
    # Buscar todos os tanques e contratos para os filtros
    tanques = Tanque.query.order_by(Tanque.nome).all()
    contratos = Contrato.query.order_by(Contrato.nome).all()
    
    # Buscar tipos de peças únicos das peças cadastradas para o modal
    tipos_peca = db.session.query(Peca.tipo).distinct().order_by(Peca.tipo).all()
    tipos_peca = [t[0] for t in tipos_peca if t[0]]
    
    return render_template('pecas/index.html', 
                         pecas=pecas, 
                         tanques=tanques, 
                         contratos=contratos,
                         tipos_peca=tipos_peca,
                         tanque_id_filtro=tanque_id,
                         projeto_id_filtro=projeto_id)

@peca.route('/tanque/<int:tanque_id>')
def listar_por_tanque(tanque_id):
    """Lista todas as peças de um tanque específico"""
    tanque = Tanque.query.get_or_404(tanque_id)
    pecas = Peca.query.filter_by(tanque_id=tanque_id).order_by(Peca.numero_sequencial).all()
    
    return render_template('pecas/listar.html', pecas=pecas, tanque=tanque)

@peca.route('/novo/<int:tanque_id>', methods=['GET', 'POST'])
def novo(tanque_id):
    """Adiciona uma nova peça a um tanque"""
    tanque = Tanque.query.get_or_404(tanque_id)
    
    # Obtém o próximo número sequencial
    proximo_sequencial = db.session.query(db.func.max(Peca.numero_sequencial))\
        .filter(Peca.tanque_id == tanque_id).scalar() or 0
    proximo_sequencial += 1
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            tipo = request.form.get('tipo')
            nome = request.form.get('nome')
            numero_tanque = request.form.get('numero_tanque')
            
            # Converter numero_tanque para inteiro se não estiver vazio
            if numero_tanque and numero_tanque.strip():
                try:
                    numero_tanque = int(numero_tanque)
                except ValueError:
                    numero_tanque = None
            else:
                numero_tanque = None
            
            # Criar nova peça
            nova_peca = Peca(
                tipo=tipo,
                nome=nome,
                numero_tanque=numero_tanque,
                tanque_id=tanque_id,
                numero_sequencial=proximo_sequencial
            )
            
            # Salvar no banco de dados
            nova_peca.save()
            
            flash('Peça adicionada com sucesso!', 'success')
            return redirect(url_for('peca.listar_por_tanque', tanque_id=tanque_id))
            
        except Exception as e:
            flash(f'Erro ao adicionar peça: {str(e)}', 'danger')
    
    return render_template('pecas/novo.html', tanque=tanque, proximo_sequencial=proximo_sequencial)

@peca.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """Edita uma peça existente"""
    peca = Peca.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            peca.tipo = request.form.get('tipo')
            peca.nome = request.form.get('nome')
            
            numero_tanque = request.form.get('numero_tanque')
            # Converter numero_tanque para inteiro se não estiver vazio
            if numero_tanque and numero_tanque.strip():
                try:
                    peca.numero_tanque = int(numero_tanque)
                except ValueError:
                    peca.numero_tanque = None
            else:
                peca.numero_tanque = None
            
            # Salvar alterações
            peca.save()
            
            flash('Peça atualizada com sucesso!', 'success')
            return redirect(url_for('peca.visualizar', id=peca.id))
            
        except Exception as e:
            flash(f'Erro ao atualizar peça: {str(e)}', 'danger')
    
    return render_template('pecas/editar.html', peca=peca)

@peca.route('/visualizar/<int:id>')
def visualizar(id):
    """Visualiza detalhes de uma peça"""
    peca = Peca.query.get_or_404(id)
    return render_template('pecas/visualizar.html', peca=peca)

@peca.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """Exclui uma peça"""
    peca = Peca.query.get_or_404(id)
    tanque_id = peca.tanque_id
    numero_sequencial = peca.numero_sequencial
    
    try:
        # Excluir a peça
        peca.delete()
        
        # Reordenar as peças restantes
        pecas_posteriores = Peca.query.filter(
            Peca.tanque_id == tanque_id,
            Peca.numero_sequencial > numero_sequencial
        ).order_by(Peca.numero_sequencial).all()
        
        # Atualizar os números sequenciais
        for p in pecas_posteriores:
            p.numero_sequencial -= 1
            p.save()
            
        flash('Peça excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir peça: {str(e)}', 'danger')
    
    return redirect(url_for('peca.listar_por_tanque', tanque_id=tanque_id))

@peca.route('/acabamento', methods=['GET', 'POST'])
def acabamento():
    """Registra acabamento de uma peça"""
    if request.method == 'POST':
        tanque_id = request.form.get('tanque_id')
        peca_nome = request.form.get('peca_nome')
        placa = request.form.get('placa')
        data_acabamento = request.form.get('data_acabamento')
        if not data_acabamento:
            data_acabamento = datetime.now().strftime('%Y-%m-%d')
        try:
            peca = Peca.query.filter_by(tanque_id=tanque_id, nome=peca_nome).first()
            if not peca:
                return jsonify({'success': False, 'message': 'Peça não encontrada'}), 404
            qualidade = peca.qualidade or '{}'
            qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
            qualidade_dict['acabamento'] = {
                'placa': placa,
                'data': data_acabamento
            }
            peca.qualidade = json.dumps(qualidade_dict)
            peca.save()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    # GET: retorna o modal
    tanques = Tanque.query.order_by(Tanque.nome).all()
    csrf_token = generate_csrf()
    return render_template('pecas/modais/acabamento.html', tanques=tanques, csrf_token=csrf_token)

@peca.route('/transporte', methods=['GET', 'POST'])
def transporte():
    """Registra transporte de peças"""
    if request.method == 'POST':
        tanque_ids = request.form.getlist('tanque_ids')
        peca_nomes = request.form.getlist('peca_nomes')
        placas = request.form.getlist('placas')
        nota_fiscal = request.form.get('nota_fiscal')
        placa_carreta = request.form.get('placa_carreta')
        data_transporte = request.form.get('data_transporte')
        transportadora = request.form.get('transportadora')
        if not data_transporte:
            data_transporte = datetime.now().strftime('%Y-%m-%d')
        try:
            pecas = Peca.query.filter(Peca.tanque_id.in_(tanque_ids), Peca.nome.in_(peca_nomes)).all()
            for peca in pecas:
                qualidade = peca.qualidade or '{}'
                qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
                qualidade_dict['transporte'] = {
                    'data_transporte': data_transporte,
                    'placas': placas,
                    'nota': nota_fiscal,
                    'placa_carreta': placa_carreta,
                    'transportadora': transportadora
                }
                peca.qualidade = json.dumps(qualidade_dict)
                peca.data_entrega = data_transporte
                peca.save()
            return jsonify({'success': True, 'pecas_afetadas': [p.id for p in pecas]})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    # GET: retorna o modal
    tanques = Tanque.query.order_by(Tanque.nome).all()
    csrf_token = generate_csrf()
    return render_template('pecas/modais/transporte.html', tanques=tanques, csrf_token=csrf_token)

@peca.route('/api/tanques-por-projeto')
def api_tanques_por_projeto():
    """API para buscar tanques filtrados por projeto (contrato)"""
    projeto_id = request.args.get('projeto_id', type=int)
    
    if projeto_id:
        tanques = Tanque.query.filter_by(contrato_id=projeto_id).order_by(Tanque.nome).all()
    else:
        tanques = Tanque.query.order_by(Tanque.nome).all()
    
    tanques_json = []
    for tanque in tanques:
        tanques_json.append({
            'id': tanque.id,
            'nome': tanque.nome,
            'sistema': tanque.sistema
        })
    
    return jsonify({'tanques': tanques_json})

@peca.route('/vinculacao-produto-composto', methods=['GET', 'POST'])
def vinculacao_produto_composto():
    """Modal e processamento de vinculação de tanque a produto composto"""
    if request.method == 'POST':
        try:
            # O Flask-WTF valida CSRF automaticamente via CSRFProtect
            # O token deve estar em request.form['csrf_token'] ou no header X-CSRFToken
            
            tanque_id = request.form.get('tanque_id', type=int)
            tipo_peca = request.form.get('tipo_peca')
            produto_composto_id = request.form.get('produto_composto_id', type=int)
            
            if not tanque_id or not tipo_peca or not produto_composto_id:
                return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios'}), 400
            
            # Verificar se já existe vinculação
            vinculacao_existente = TanqueProdutoComposto.query.filter_by(
                tanque_id=tanque_id,
                tipo_peca=tipo_peca,
                produto_composto_id=produto_composto_id
            ).first()
            
            if vinculacao_existente:
                return jsonify({'success': False, 'message': 'Vinculação já existe para este tanque e tipo de peça'}), 400
            
            # Criar nova vinculação
            nova_vinculacao = TanqueProdutoComposto(
                tanque_id=tanque_id,
                tipo_peca=tipo_peca,
                produto_composto_id=produto_composto_id
            )
            nova_vinculacao.save()
            
            return jsonify({'success': True, 'message': 'Vinculação criada com sucesso!'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Erro ao criar vinculação: {str(e)}'}), 500
    
    # GET: retorna o modal
    contratos = Contrato.query.order_by(Contrato.nome).all()
    csrf_token = generate_csrf()
    
    return render_template('pecas/modais/vinculacao_produto_composto.html', 
                         contratos=contratos, 
                         csrf_token=csrf_token)

@peca.route('/api/tipos-peca-por-tanque')
def api_tipos_peca_por_tanque():
    """API para buscar tipos de peças filtrados por tanque"""
    tanque_id = request.args.get('tanque_id', type=int)
    
    if not tanque_id:
        return jsonify({'tipos': []})
    
    # Buscar tipos de peças únicos do tanque
    tipos_peca = db.session.query(Peca.tipo)\
        .filter(Peca.tanque_id == tanque_id)\
        .distinct()\
        .order_by(Peca.tipo)\
        .all()
    
    tipos_json = [t[0] for t in tipos_peca if t[0]]
    
    return jsonify({'tipos': tipos_json})

@peca.route('/api/produtos-compostos')
def api_produtos_compostos():
    """API para buscar produtos compostos com busca por nome"""
    termo = request.args.get('termo', '').strip()
    
    query = ProdutoComposto.query.filter(ProdutoComposto.status == 'Ativo')
    
    if termo:
        query = query.filter(ProdutoComposto.nome.like(f'%{termo}%'))
    
    produtos = query.order_by(ProdutoComposto.nome).limit(50).all()
    
    produtos_json = []
    for produto in produtos:
        produtos_json.append({
            'id': produto.id,
            'nome': produto.nome,
            'descricao': produto.descricao,
            'tempo_producao': float(produto.tempo_producao) if produto.tempo_producao else None,
            'componentes': len(produto.componentes)
        })
    
    return jsonify({'produtos': produtos_json})

@peca.route('/api/vinculacoes/<int:tanque_id>')
def api_vinculacoes_tanque(tanque_id):
    """API para buscar vinculações de um tanque"""
    vinculacoes = TanqueProdutoComposto.query.filter_by(tanque_id=tanque_id).all()
    
    vinculacoes_json = []
    for v in vinculacoes:
        vinculacoes_json.append({
            'id': v.id,
            'tipo_peca': v.tipo_peca,
            'produto_composto_id': v.produto_composto_id,
            'produto_composto_nome': v.produto_composto.nome if v.produto_composto else None
        })
    
    return jsonify({'vinculacoes': vinculacoes_json})

@peca.route('/api/vinculacoes')
def api_vinculacoes_todas():
    """API para buscar todas as vinculações com informações completas"""
    vinculacoes = TanqueProdutoComposto.query\
        .join(Tanque, TanqueProdutoComposto.tanque_id == Tanque.id)\
        .outerjoin(Contrato, Tanque.contrato_id == Contrato.id)\
        .join(ProdutoComposto, TanqueProdutoComposto.produto_composto_id == ProdutoComposto.id)\
        .order_by(Tanque.nome, TanqueProdutoComposto.tipo_peca)\
        .all()
    
    vinculacoes_json = []
    for v in vinculacoes:
        # Acessar relacionamentos que já foram carregados pelo join
        tanque = v.tanque
        produto = v.produto_composto
        contrato = tanque.contrato if tanque else None
        
        vinculacoes_json.append({
            'id': v.id,
            'tanque_id': v.tanque_id,
            'tanque_nome': tanque.nome if tanque else None,
            'tanque_sistema': tanque.sistema if tanque else None,
            'projeto_nome': contrato.nome if contrato else None,
            'tipo_peca': v.tipo_peca,
            'produto_composto_id': v.produto_composto_id,
            'produto_composto_nome': produto.nome if produto else None,
            'criado_em': v.criado_em.strftime('%d/%m/%Y %H:%M') if v.criado_em else None
        })
    
    return jsonify({'vinculacoes': vinculacoes_json})

@peca.route('/vinculacao-produto-composto/<int:id>/excluir', methods=['POST'])
def excluir_vinculacao(id):
    """Exclui uma vinculação"""
    try:
        vinculacao = TanqueProdutoComposto.query.get_or_404(id)
        vinculacao.delete()
        return jsonify({'success': True, 'message': 'Vinculação excluída com sucesso!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao excluir vinculação: {str(e)}'}), 500

def _processar_componentes_recursivo(produto_composto, quantidade_pecas, data_movimento, produto_composto_id, 
                                     data_dia, usuario_id, pecas_grupo, pecas_sem_estoque, produtos_processados, 
                                     nivel_recursao=0, prefixo_observacao=''):
    """
    Processa componentes de um produto composto recursivamente.
    Se um componente for outro produto composto, processa seus componentes também.
    """
    from sqlalchemy import func
    from datetime import date as date_type
    
    movimentacoes_criadas = 0
    
    # Evitar loops infinitos
    if produto_composto.id in produtos_processados:
        return movimentacoes_criadas
    
    produtos_processados.add(produto_composto.id)
    
    # Processar cada componente do produto composto
    for componente in produto_composto.componentes:
        estoque_id = componente.estoque_id
        quantidade_por_peca = Decimal(str(componente.quantidade))
        quantidade_total = quantidade_por_peca * Decimal(str(quantidade_pecas))
        
        # Buscar o estoque
        estoque = Estoque.query.get(estoque_id)
        if not estoque:
            pecas_sem_estoque.append({
                'produto_composto': produto_composto.nome,
                'data': data_dia.strftime('%d/%m/%Y') if isinstance(data_dia, date_type) else str(data_dia),
                'quantidade_pecas': quantidade_pecas,
                'estoque_id': estoque_id,
                'material': f'Estoque ID {estoque_id}',
                'nivel': nivel_recursao
            })
            continue
        
        # Verificar se o estoque é um produto composto aninhado
        if estoque.ProdComp_id:
            # É um produto composto aninhado - processar recursivamente
            produto_composto_aninhado = ProdutoComposto.query.get(estoque.ProdComp_id)
            if produto_composto_aninhado:
                # Processar os componentes do produto composto aninhado
                # quantidade_total = quantidade_por_peca * quantidade_pecas
                # Exemplo: se cada peça precisa de 2 unidades do produto composto aninhado,
                # e temos 10 peças, quantidade_total = 2 * 10 = 20 unidades
                # Então processamos o produto composto aninhado como se fossem 20 "peças" dele
                
                novo_prefixo = f"{prefixo_observacao} > {produto_composto_aninhado.nome}" if prefixo_observacao else produto_composto_aninhado.nome
                
                movimentacoes_aninhadas = _processar_componentes_recursivo(
                    produto_composto=produto_composto_aninhado,
                    quantidade_pecas=quantidade_total,  # Quantidade total de unidades necessárias
                    data_movimento=data_movimento,
                    produto_composto_id=produto_composto_aninhado.id,
                    data_dia=data_dia,
                    usuario_id=usuario_id,
                    pecas_grupo=pecas_grupo,
                    pecas_sem_estoque=pecas_sem_estoque,
                    produtos_processados=produtos_processados,
                    nivel_recursao=nivel_recursao + 1,
                    prefixo_observacao=novo_prefixo
                )
                movimentacoes_criadas += movimentacoes_aninhadas
                continue
        
        # Verificar se já existe movimentação para este grupo
        pecas_ids = [p.id for p in pecas_grupo]
        movimentacao_existente = MovimentacaoEstoque.query.filter(
            MovimentacaoEstoque.estoque_id == estoque_id,
            MovimentacaoEstoque.origem_id.in_(pecas_ids),
            MovimentacaoEstoque.origem_tipo == 'producao_peca'
        ).first()
        
        # Se não encontrou por peça individual, verificar por grupo (método otimizado)
        if not movimentacao_existente:
            data_para_comparacao = data_dia if isinstance(data_dia, date_type) else data_dia.date() if isinstance(data_dia, datetime) else data_dia
            movimentacao_existente = MovimentacaoEstoque.query.filter(
                MovimentacaoEstoque.estoque_id == estoque_id,
                MovimentacaoEstoque.origem_id == produto_composto_id,
                MovimentacaoEstoque.origem_tipo == 'producao_peca',
                func.date(MovimentacaoEstoque.data_movimento) == data_para_comparacao
            ).first()
        
        if movimentacao_existente:
            # Já foi processado, pular
            continue
        
        # Verificar disponibilidade de estoque
        if estoque.quantidade < quantidade_total:
            material_nome = estoque.material.nome if estoque.material else f'Estoque ID {estoque_id}'
            pecas_sem_estoque.append({
                'produto_composto': produto_composto.nome,
                'data': data_dia.strftime('%d/%m/%Y') if isinstance(data_dia, date_type) else str(data_dia),
                'quantidade_pecas': quantidade_pecas,
                'material': material_nome,
                'necessario': float(quantidade_total),
                'disponivel': float(estoque.quantidade),
                'nivel': nivel_recursao
            })
            continue
        
        # Criar uma única movimentação para todo o grupo
        movimentacao = MovimentacaoEstoque()
        
        # Criar lista de peças para observação
        nomes_pecas = [f"{p.nome} (Tanque: {p.tanque.nome})" for p in pecas_grupo[:5]]
        if len(pecas_grupo) > 5:
            nomes_pecas.append(f"... e mais {len(pecas_grupo) - 5} peça(s)")
        
        observacao_base = (
            f'Produção de {quantidade_pecas} peça(s) - Produto: {produto_composto.nome} - '
            f'Data: {data_dia.strftime("%d/%m/%Y") if isinstance(data_dia, date_type) else str(data_dia)}'
        )
        
        if prefixo_observacao:
            observacao = f'{observacao_base} - Componente: {prefixo_observacao} - Peças: {", ".join(nomes_pecas)}'
        else:
            observacao = f'{observacao_base} - Peças: {", ".join(nomes_pecas)}'
        
        movimentacao.remover(
            quantidade=quantidade_total,
            estoque_id=estoque_id,
            origem_id=produto_composto_id,
            origem_tipo='producao_peca_grupo',
            usuario_id=usuario_id,
            motivo=observacao
        )
        movimentacao.data_movimento = data_movimento
        
        # Salvar movimentação (o método save() atualiza o estoque automaticamente)
        movimentacao.save()
        movimentacoes_criadas += 1
    
    return movimentacoes_criadas

@peca.route('/processar-producao', methods=['POST'])
@login_required
def processar_producao():
    """Processa a produção de peças concretadas, consumindo estoque baseado no produto composto vinculado
    Otimizado para agrupar por vinculação (produto composto) e por dia"""
    try:
        from collections import defaultdict
        from datetime import date as date_type
        
        MovimentacaoEstoque.query.filter(MovimentacaoEstoque.origem_tipo.like('%producao_peca%')).delete()
        # Buscar todas as peças com data_concretagem preenchida
        pecas_concretadas = Peca.query.filter(Peca.data_concretagem.isnot(None)).all()
        
        if not pecas_concretadas:
            return jsonify({
                'success': False, 
                'message': 'Nenhuma peça com data de concretagem encontrada.'
            }), 400
        
        usuario_id = current_user.id if current_user else 1
        
        # Estrutura para agrupar: {(produto_composto_id, data_dia): [lista_de_pecas]}
        grupos_producao = defaultdict(list)
        pecas_sem_vinculacao = []
        
        # Primeira passada: agrupar peças por produto composto e data
        for peca in pecas_concretadas:
            try:
                # Buscar produto composto vinculado ao tanque e tipo de peça
                vinculacao = TanqueProdutoComposto.query.filter_by(
                    tanque_id=peca.tanque_id,
                    tipo_peca=peca.tipo
                ).first()
                
                if not vinculacao or not vinculacao.produto_composto:
                    pecas_sem_vinculacao.append({
                        'peca_id': peca.id,
                        'peca_nome': peca.nome,
                        'tanque': peca.tanque.nome,
                        'tipo': peca.tipo
                    })
                    continue
                
                # Normalizar data para agrupar por dia (sem hora)
                data_concretagem = peca.data_concretagem
                if isinstance(data_concretagem, datetime):
                    data_dia = data_concretagem.date()
                else:
                    data_dia = data_concretagem if isinstance(data_concretagem, date_type) else data_concretagem
                
                # Criar chave de agrupamento: (produto_composto_id, data_dia)
                chave_grupo = (vinculacao.produto_composto_id, data_dia)
                grupos_producao[chave_grupo].append(peca)
                
            except Exception as e:
                continue
        
        # Segunda passada: processar cada grupo otimizado
        movimentacoes_criadas = 0
        pecas_processadas = 0
        pecas_sem_estoque = []
        erros = []
        
        for (produto_composto_id, data_dia), pecas_grupo in grupos_producao.items():
            try:
                # Buscar produto composto
                produto_composto = ProdutoComposto.query.get(produto_composto_id)
                if not produto_composto:
                    continue
                
                # Quantidade de peças neste grupo
                quantidade_pecas = len(pecas_grupo)
                
                # Converter data_dia para datetime (início do dia)
                if isinstance(data_dia, date_type):
                    data_movimento = datetime.combine(data_dia, datetime.min.time())
                else:
                    data_movimento = datetime.combine(data_dia, datetime.min.time())
                
                # Processar componentes do produto composto (recursivamente se necessário)
                movimentacoes_grupo = _processar_componentes_recursivo(
                    produto_composto=produto_composto,
                    quantidade_pecas=quantidade_pecas,
                    data_movimento=data_movimento,
                    produto_composto_id=produto_composto_id,
                    data_dia=data_dia,
                    usuario_id=usuario_id,
                    pecas_grupo=pecas_grupo,
                    pecas_sem_estoque=pecas_sem_estoque,
                    produtos_processados=set()  # Para evitar loops infinitos
                )
                movimentacoes_criadas += movimentacoes_grupo
                
                pecas_processadas += quantidade_pecas
                
            except Exception as e:
                erros.append({
                    'produto_composto_id': produto_composto_id,
                    'data': data_dia.strftime('%d/%m/%Y') if isinstance(data_dia, date_type) else str(data_dia),
                    'quantidade_pecas': len(pecas_grupo),
                    'erro': str(e)
                })
                continue
        
        # Commit de todas as alterações
        db.session.commit()
        
        mensagem = (
            f'Processamento concluído!\n'
            f'- {pecas_processadas} peça(s) processada(s)\n'
            f'- {movimentacoes_criadas} movimentação(ões) de estoque criada(s)\n'
            f'- {len(grupos_producao)} grupo(s) processado(s)'
        )
        
        if pecas_sem_vinculacao:
            mensagem += f'\n\n{len(pecas_sem_vinculacao)} peça(s) sem vinculação de produto composto.'
        
        if pecas_sem_estoque:
            mensagem += f'\n\n{len(pecas_sem_estoque)} grupo(s) com estoque insuficiente.'
        
        if erros:
            mensagem += f'\n\n{len(erros)} erro(s) durante o processamento.'
        
        return jsonify({
            'success': True,
            'message': mensagem,
            'pecas_processadas': pecas_processadas,
            'movimentacoes_criadas': movimentacoes_criadas,
            'grupos_processados': len(grupos_producao),
            'pecas_sem_vinculacao': pecas_sem_vinculacao,
            'pecas_sem_estoque': pecas_sem_estoque,
            'erros': erros
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        return jsonify({
            'success': False,
            'message': f'Erro ao processar produção: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500