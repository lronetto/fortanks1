from itertools import groupby
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app
from models import db
from models.contrato import Contrato
from models.tanque import TanquesGrupos, Tanques, TanquesPecas, TanquesProdutoComposto
from models.estoque import Estoque, EstoqueMovimentacoes
from models.produto_composto import ProdutoComposto, ProdutoCompostoItem
from flask_wtf.csrf import generate_csrf
from flask_login import login_required, current_user
from datetime import datetime
from decimal import Decimal
import json
import os
import tempfile
from models.logs import Logs

# Função auxiliar para converter Decimal para float recursivamente
def converter_decimal_para_float(obj):
    """Converte valores Decimal para float recursivamente em estruturas de dados"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: converter_decimal_para_float(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [converter_decimal_para_float(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(converter_decimal_para_float(item) for item in obj)
    else:
        return obj

# Criação do blueprint
peca = Blueprint('peca', __name__, url_prefix='/pecas')

@peca.route('/')
@login_required
def index():
    """Lista todas as peças do sistema em uma única tabela com filtros"""
    # Obter filtros da query string
    tanque_id = request.args.get('tanque_id', type=int)
    projeto_id = request.args.get('projeto_id', type=int)  # projeto_id = contrato_id
    
    # Query base com join para incluir tanque e contrato
    query = db.session.query(TanquesPecas)\
        .join(Tanques, TanquesPecas.tanque_id == Tanques.id)\
        .outerjoin(Contrato, Tanques.contrato_id == Contrato.id)
    
    # Aplicar filtros
    if tanque_id:
        query = query.filter(TanquesPecas.tanque_id == tanque_id)
    
    if projeto_id:
        query = query.filter(Tanques.contrato_id == projeto_id)
    
    # Ordenar por tanque e número sequencial
    pecas = query.order_by(Tanques.nome, TanquesPecas.numero_sequencial).all()
    
    # Buscar todos os tanques e contratos para os filtros
    tanques = Tanques.query.order_by(Tanques.nome).all()
    contratos = Contrato.query.order_by(Contrato.nome).all()
    
    # Buscar tipos de peças únicos das peças cadastradas para o modal
    tipos_peca = db.session.query(TanquesPecas.tipo).distinct().order_by(TanquesPecas.tipo).all()
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
    tanque = Tanques.query.get_or_404(tanque_id)
    pecas = TanquesPecas.query.filter_by(tanque_id=tanque_id).order_by(TanquesPecas.numero_sequencial).all()
    
    return render_template('pecas/listar.html', pecas=pecas, tanque=tanque)

@peca.route('/novo/<int:tanque_id>', methods=['GET', 'POST'])
def novo(tanque_id):
    """Adiciona uma nova peça a um tanque"""
    tanque = Tanques.query.get_or_404(tanque_id)
    
    # Obtém o próximo número sequencial
    proximo_sequencial = db.session.query(db.func.max(TanquesPecas.numero_sequencial))\
        .filter(TanquesPecas.tanque_id == tanque_id).scalar() or 0
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
            nova_peca = TanquesPecas(
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
    peca = TanquesPecas.query.get_or_404(id)
    
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
    peca = TanquesPecas.query.get_or_404(id)
    return render_template('pecas/visualizar.html', peca=peca)

@peca.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """Exclui uma peça"""
    peca = TanquesPecas.query.get_or_404(id)
    tanque_id = peca.tanque_id
    numero_sequencial = peca.numero_sequencial
    
    try:
        # Excluir a peça
        peca.delete()
        
        # Reordenar as peças restantes
        pecas_posteriores = TanquesPecas.query.filter(
            TanquesPecas.tanque_id == tanque_id,
            TanquesPecas.numero_sequencial > numero_sequencial
        ).order_by(TanquesPecas.numero_sequencial).all()
        
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
            peca = TanquesPecas.query.filter_by(tanque_id=tanque_id, nome=peca_nome).first()
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
    tanques = Tanques.query.order_by(Tanques.nome).all()
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
            pecas = TanquesPecas.query.filter(TanquesPecas.tanque_id.in_(tanque_ids), TanquesPecas.nome.in_(peca_nomes)).all()
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
    tanques = Tanques.query.order_by(Tanques.nome).all()
    csrf_token = generate_csrf()
    return render_template('pecas/modais/transporte.html', tanques=tanques, csrf_token=csrf_token)

@peca.route('/api/tanques-por-projeto')
def api_tanques_por_projeto():
    """API para buscar tanques filtrados por projeto (contrato)"""
    projeto_id = request.args.get('projeto_id', type=int)
    
    if projeto_id:
        tanques = Tanques.query.filter_by(contrato_id=projeto_id).order_by(Tanques.nome).all()
    else:
        tanques = Tanques.query.order_by(Tanques.nome).all()
    
    tanques_json = []
    for tanque in tanques:
        tanques_json.append({
            'id': tanque.id,
            'nome': tanque.nome,
            'sistema': tanque.sistema
        })
    
    return jsonify({'tanques': tanques_json})

@peca.route('/api/grupos-tanques')
def api_grupos_tanques():
    """API para buscar todos os grupos de tanques"""
    grupos = TanquesGrupos.get_all()
    
    grupos_json = []
    for grupo in grupos:
        grupos_json.append({
            'id': grupo.id,
            'nome': grupo.nome,
            'descricao': grupo.descricao,
            'cor': grupo.cor or '#6c757d',
            'icone': grupo.icone or 'fas fa-layer-group',
            'total_tanques': grupo.total_tanques
        })
    
    return jsonify({'grupos': grupos_json})

@peca.route('/vinculacao-produto-composto', methods=['GET', 'POST'])
def vinculacao_produto_composto():
    """Modal e processamento de vinculação de tanque(s) a produto composto"""
    if request.method == 'POST':
        try:
            # O Flask-WTF valida CSRF automaticamente via CSRFProtect
            # O token deve estar em request.form['csrf_token'] ou no header X-CSRFToken
            
            # Verificar se é edição (tem vinculacao_id)
            vinculacao_id = request.form.get('vinculacao_id', type=int)
            
            if vinculacao_id:
                # Modo edição - atualizar vinculação existente
                vinculacao = TanquesProdutoComposto.query.get_or_404(vinculacao_id)
                
                # Aceitar tanto tanque_id único quanto lista de tanque_ids
                tanque_ids = request.form.getlist('tanque_ids[]')
                if not tanque_ids:
                    tanque_id = request.form.get('tanque_id', type=int)
                    if tanque_id:
                        tanque_ids = [tanque_id]
                
                tipo_peca = request.form.get('tipo_peca')
                produto_composto_id = request.form.get('produto_composto_id', type=int)
                
                if not tanque_ids or not tipo_peca or not produto_composto_id:
                    return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios'}), 400
                
                # Converter para inteiros
                try:
                    tanque_ids = [int(tid) for tid in tanque_ids if tid]
                except (ValueError, TypeError):
                    return jsonify({'success': False, 'message': 'IDs de tanques inválidos'}), 400
                
                if not tanque_ids:
                    return jsonify({'success': False, 'message': 'Selecione pelo menos um tanque'}), 400
                
                # Para edição, vamos atualizar apenas o primeiro tanque (comportamento simplificado)
                # Se houver múltiplos tanques, criar novas vinculações para os adicionais
                tanque_id_principal = tanque_ids[0]
                tanques_adicionais = tanque_ids[1:] if len(tanque_ids) > 1 else []
                
                # Atualizar vinculação existente
                vinculacao.tanque_id = tanque_id_principal
                vinculacao.tipo_peca = tipo_peca
                vinculacao.produto_composto_id = produto_composto_id
                vinculacao.save()
                
                # Criar vinculações para tanques adicionais se houver
                vinculacoes_criadas = 0
                for tanque_id in tanques_adicionais:
                    # Verificar se já existe
                    vinculacao_existente = TanquesProdutoComposto.query.filter_by(
                        tanque_id=tanque_id,
                        tipo_peca=tipo_peca,
                        produto_composto_id=produto_composto_id
                    ).first()
                    
                    if not vinculacao_existente:
                        nova_vinculacao = TanquesProdutoComposto(
                            tanque_id=tanque_id,
                            tipo_peca=tipo_peca,
                            produto_composto_id=produto_composto_id
                        )
                        nova_vinculacao.save()
                        vinculacoes_criadas += 1
                
                mensagem = 'Vinculação atualizada com sucesso!'
                if vinculacoes_criadas > 0:
                    mensagem += f'\n{vinculacoes_criadas} vinculação(ões) adicional(is) criada(s).'
                
                return jsonify({
                    'success': True,
                    'message': mensagem,
                    'vinculacao_atualizada': True,
                    'vinculacoes_criadas': vinculacoes_criadas
                })
            
            else:
                # Modo criação - criar novas vinculações por grupos
                grupo_ids = request.form.getlist('grupo_ids[]')
                
                # Fallback para formato antigo (tanque_ids individuais)
                if not grupo_ids:
                    tanque_ids = request.form.getlist('tanque_ids[]')
                    if not tanque_ids:
                        tanque_id = request.form.get('tanque_id', type=int)
                        if tanque_id:
                            tanque_ids = [tanque_id]
                else:
                    tanque_ids = []
                
                tipo_peca = request.form.get('tipo_peca')
                produto_composto_id = request.form.get('produto_composto_id', type=int)
                
                if not tipo_peca or not produto_composto_id:
                    return jsonify({'success': False, 'message': 'Tipo de peça e produto composto são obrigatórios'}), 400
                
                # Se grupos foram selecionados, buscar todos os tanques dos grupos
                if grupo_ids:
                    try:
                        grupo_ids = [int(gid) for gid in grupo_ids if gid]
                    except (ValueError, TypeError):
                        return jsonify({'success': False, 'message': 'IDs de grupos inválidos'}), 400
                    
                    if not grupo_ids:
                        return jsonify({'success': False, 'message': 'Selecione pelo menos um grupo'}), 400
                    
                    # Buscar todos os tanques dos grupos selecionados
                    tanque_ids = []
                    grupos_processados = []
                    for grupo_id in grupo_ids:
                        grupo = TanquesGrupos.query.get(grupo_id)
                        if grupo:
                            grupos_processados.append(grupo.nome)
                            for tanque in grupo.tanques:
                                if tanque.id not in tanque_ids:
                                    tanque_ids.append(tanque.id)
                
                if not tanque_ids:
                    return jsonify({'success': False, 'message': 'Nenhum tanque encontrado nos grupos selecionados'}), 400
                
                vinculacoes_criadas = 0
                vinculacoes_existentes = []
                erros = []
                
                # Criar vinculação para cada tanque
                for tanque_id in tanque_ids:
                    try:
                        # Verificar se já existe vinculação
                        vinculacao_existente = TanquesProdutoComposto.query.filter_by(
                            tanque_id=tanque_id,
                            tipo_peca=tipo_peca,
                            produto_composto_id=produto_composto_id
                        ).first()
                        
                        if vinculacao_existente:
                            tanque = Tanques.query.get(tanque_id)
                            vinculacoes_existentes.append(tanque.nome if tanque else f'Tanque ID {tanque_id}')
                            continue
                        
                        # Criar nova vinculação
                        nova_vinculacao = TanquesProdutoComposto(
                            tanque_id=tanque_id,
                            tipo_peca=tipo_peca,
                            produto_composto_id=produto_composto_id
                        )
                        nova_vinculacao.save()
                        vinculacoes_criadas += 1
                        
                    except Exception as e:
                        tanque = Tanques.query.get(tanque_id)
                        erros.append({
                            'tanque': tanque.nome if tanque else f'Tanque ID {tanque_id}',
                            'erro': str(e)
                        })
                        continue
                
                # Montar mensagem de resposta
                mensagem = f'{vinculacoes_criadas} vinculação(ões) criada(s) com sucesso!'
                if grupos_processados:
                    mensagem += f'\nGrupos processados: {", ".join(grupos_processados)}'
                if vinculacoes_existentes:
                    mensagem += f'\n{len(vinculacoes_existentes)} tanque(s) já possuíam vinculação.'
                if erros:
                    mensagem += f'\n{len(erros)} erro(s) durante o processamento.'
                
                return jsonify({
                    'success': True, 
                    'message': mensagem,
                    'vinculacoes_criadas': vinculacoes_criadas,
                    'vinculacoes_existentes': vinculacoes_existentes,
                    'erros': erros,
                    'grupos_processados': grupos_processados if grupo_ids else []
                })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Erro ao processar vinculação: {str(e)}'}), 500
    
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
    tipos_peca = db.session.query(TanquesPecas.tipo)\
        .filter(TanquesPecas.tanque_id == tanque_id)\
        .distinct()\
        .order_by(TanquesPecas.tipo)\
        .all()
    
    tipos_json = [t[0] for t in tipos_peca if t[0]]
    
    return jsonify({'tipos': tipos_json})

@peca.route('/api/tipos-peca-por-grupos')
def api_tipos_peca_por_grupos():
    """API para buscar tipos de peças de todos os tanques dos grupos selecionados, agrupados por tipo"""
    from sqlalchemy import func
    
    grupo_ids = request.args.getlist('grupo_ids[]')
    
    if not grupo_ids:
        return jsonify({'tipos': [], 'tipos_agrupados': []})
    
    try:
        grupo_ids = [int(gid) for gid in grupo_ids if gid]
    except (ValueError, TypeError):
        return jsonify({'tipos': [], 'tipos_agrupados': []})
    
    if not grupo_ids:
        return jsonify({'tipos': [], 'tipos_agrupados': []})
    
    # Buscar todos os tanques dos grupos selecionados
    tanque_ids = []
    for grupo_id in grupo_ids:
        grupo = GrupoTanque.query.get(grupo_id)
        if grupo:
            for tanque in grupo.tanques:
                if tanque.id not in tanque_ids:
                    tanque_ids.append(tanque.id)
    
    if not tanque_ids:
        return jsonify({'tipos': [], 'tipos_agrupados': []})
    
    # Buscar tipos de peças únicos com contagem de tanques por tipo
    tipos_agrupados = db.session.query(
        TanquesPecas.tipo,
        func.count(func.distinct(TanquesPecas.tanque_id)).label('total_tanques')
    ).filter(
        TanquesPecas.tanque_id.in_(tanque_ids),
        TanquesPecas.tipo.isnot(None),
        TanquesPecas.tipo != ''
    ).group_by(
        TanquesPecas.tipo
    ).order_by(
        TanquesPecas.tipo
    ).all()
    
    # Formatar resposta com tipos agrupados
    tipos_agrupados_json = []
    tipos_simples = []
    
    for tipo, total_tanques in tipos_agrupados:
        if tipo:
            tipos_agrupados_json.append({
                'tipo': tipo,
                'total_tanques': total_tanques
            })
            tipos_simples.append(tipo)
    
    return jsonify({
        'tipos': tipos_simples,  # Lista simples para compatibilidade com datalist
        'tipos_agrupados': tipos_agrupados_json,  # Lista agrupada com contagem
        'total_tanques': len(tanque_ids)
    })

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
    vinculacoes = TanquesProdutoComposto.query.filter_by(tanque_id=tanque_id).all()
    
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
    """API para buscar todas as vinculações com informações completas, incluindo grupos de tanques"""
    from sqlalchemy.orm import joinedload
    
    vinculacoes = TanquesProdutoComposto.query\
        .join(Tanques, TanquesProdutoComposto.tanque_id == Tanques.id)\
        .outerjoin(Contrato, Tanques.contrato_id == Contrato.id)\
        .join(ProdutoComposto, TanquesProdutoComposto.produto_composto_id == ProdutoComposto.id)\
        .options(joinedload(TanquesProdutoComposto.tanque).joinedload(Tanques.grupos))\
        .order_by(Tanques.nome, TanquesProdutoComposto.tipo_peca)\
        .all()
    
    vinculacoes_json = []
    for v in vinculacoes:
        # Acessar relacionamentos que já foram carregados pelo join
        tanque = v.tanque
        produto = v.produto_composto
        contrato = tanque.contrato if tanque else None
        
        # Buscar grupos do tanque (já carregados via joinedload)
        grupos_tanque = []
        if tanque and hasattr(tanque, 'grupos') and tanque.grupos:
            for grupo in tanque.grupos:
                grupos_tanque.append({
                    'id': grupo.id,
                    'nome': grupo.nome,
                    'cor': grupo.cor,
                    'icone': grupo.icone
                })
        
        # Se o tanque não tem grupos, usar "Sem grupo" como padrão
        grupo_principal = grupos_tanque[0] if grupos_tanque else {
            'id': None,
            'nome': 'Sem grupo',
            'cor': '#6c757d',
            'icone': 'fas fa-layer-group'
        }
        
        vinculacoes_json.append({
            'id': v.id,
            'tanque_id': v.tanque_id,
            'tanque_nome': tanque.nome if tanque else None,
            'tanque_sistema': tanque.sistema if tanque else None,
            'projeto_nome': contrato.nome if contrato else None,
            'projeto_id': contrato.id if contrato else None,
            'tipo_peca': v.tipo_peca,
            'produto_composto_id': v.produto_composto_id,
            'produto_composto_nome': produto.nome if produto else None,
            'criado_em': v.criado_em.strftime('%d/%m/%Y %H:%M') if v.criado_em else None,
            'grupo_id': grupo_principal['id'],
            'grupo_nome': grupo_principal['nome'],
            'grupo_cor': grupo_principal['cor'],
            'grupo_icone': grupo_principal['icone'],
            'grupos_todos': grupos_tanque  # Todos os grupos do tanque
        })
    
    return jsonify({'vinculacoes': vinculacoes_json})

@peca.route('/api/vinculacao/<int:id>')
def api_vinculacao_por_id(id):
    """API para buscar uma vinculação específica por ID"""
    try:
        from sqlalchemy.orm import joinedload
        
        vinculacao = TanquesProdutoComposto.query\
            .join(Tanques, TanquesProdutoComposto.tanque_id == Tanques.id)\
            .outerjoin(Contrato, Tanques.contrato_id == Contrato.id)\
            .join(ProdutoComposto, TanquesProdutoComposto.produto_composto_id == ProdutoComposto.id)\
            .options(joinedload(TanquesProdutoComposto.tanque).joinedload(Tanques.grupos))\
            .filter(TanquesProdutoComposto.id == id)\
            .first_or_404()
        
        tanque = vinculacao.tanque
        produto = vinculacao.produto_composto
        contrato = tanque.contrato if tanque else None
        
        # Buscar grupos do tanque
        grupos_tanque = []
        if tanque and hasattr(tanque, 'grupos') and tanque.grupos:
            for grupo in tanque.grupos:
                grupos_tanque.append({
                    'id': grupo.id,
                    'nome': grupo.nome,
                    'cor': grupo.cor,
                    'icone': grupo.icone
                })
        
        # Se o tanque não tem grupos, usar "Sem grupo" como padrão
        grupo_principal = grupos_tanque[0] if grupos_tanque else {
            'id': None,
            'nome': 'Sem grupo',
            'cor': '#6c757d',
            'icone': 'fas fa-layer-group'
        }
        
        vinculacao_json = {
            'id': vinculacao.id,
            'tanque_id': vinculacao.tanque_id,
            'tanque_nome': tanque.nome if tanque else None,
            'tanque_sistema': tanque.sistema if tanque else None,
            'projeto_nome': contrato.nome if contrato else None,
            'projeto_id': contrato.id if contrato else None,
            'tipo_peca': vinculacao.tipo_peca,
            'produto_composto_id': vinculacao.produto_composto_id,
            'produto_composto_nome': produto.nome if produto else None,
            'criado_em': vinculacao.criado_em.strftime('%d/%m/%Y %H:%M') if vinculacao.criado_em else None,
            'grupo_id': grupo_principal['id'],
            'grupo_nome': grupo_principal['nome'],
            'grupo_cor': grupo_principal['cor'],
            'grupo_icone': grupo_principal['icone']
        }
        
        return jsonify({'success': True, 'vinculacao': vinculacao_json})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao buscar vinculação: {str(e)}'}), 500

@peca.route('/vinculacao-produto-composto/<int:id>/excluir', methods=['POST'])
def excluir_vinculacao(id):
    """Exclui uma vinculação"""
    try:
        vinculacao = TanquesProdutoComposto.query.get_or_404(id)
        vinculacao.delete()
        return jsonify({'success': True, 'message': 'Vinculação excluída com sucesso!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao excluir vinculação: {str(e)}'}), 500

@peca.route('/api/resumo-concretagem', methods=['GET'])
def api_resumo_concretagem():
    """API para buscar resumo de peças concretadas por tanque e tipo com filtro de data"""
    try:
        from sqlalchemy import func
        from datetime import datetime as dt
        
        # Obter parâmetros de data
        data_inicial = request.args.get('data_inicial')
        data_final = request.args.get('data_final')
        
        # Query base: peças com data_concretagem preenchida
        query = db.session.query(
            Tanques.nome.label('tanque_nome'),
            Tanques.sistema.label('tanque_sistema'),
            Contrato.nome.label('projeto_nome'),
            TanquesPecas.tipo.label('tipo_peca'),
            func.count(TanquesPecas.id).label('quantidade'),
            func.min(TanquesPecas.data_concretagem).label('primeira_concretagem'),
            func.max(TanquesPecas.data_concretagem).label('ultima_concretagem')
        ).join(
            Tanques, TanquesPecas.tanque_id == Tanques.id
        ).outerjoin(
            Contrato, Tanques.contrato_id == Contrato.id
        ).filter(
            TanquesPecas.data_concretagem.isnot(None)
        )
        
        # Aplicar filtros de data se fornecidos
        if data_inicial:
            try:
                data_inicial_dt = dt.strptime(data_inicial, '%Y-%m-%d')
                query = query.filter(func.date(TanquesPecas.data_concretagem) >= data_inicial_dt.date())
            except ValueError:
                pass
        
        if data_final:
            try:
                data_final_dt = dt.strptime(data_final, '%Y-%m-%d')
                query = query.filter(func.date(TanquesPecas.data_concretagem) <= data_final_dt.date())
            except ValueError:
                pass
        
        # Agrupar por tanque e tipo
        query = query.group_by(
            Tanques.nome,
            Tanques.sistema,
            Contrato.nome,
            TanquesPecas.tipo
        ).order_by(
            Contrato.nome,
            Tanques.nome,
            TanquesPecas.tipo
        )
        
        resultados = query.all()
        
        # Formatar resultados
        resumo = []
        for r in resultados:
            resumo.append({
                'projeto_nome': r.projeto_nome or 'Sem projeto',
                'tanque_nome': r.tanque_nome,
                'tanque_sistema': r.tanque_sistema,
                'tipo_peca': r.tipo_peca,
                'quantidade': r.quantidade,
                'primeira_concretagem': r.primeira_concretagem.strftime('%d/%m/%Y %H:%M') if r.primeira_concretagem else None,
                'ultima_concretagem': r.ultima_concretagem.strftime('%d/%m/%Y %H:%M') if r.ultima_concretagem else None
            })
        
        # Calcular totais
        total_pecas = sum(r['quantidade'] for r in resumo)
        total_tanques = len(set((r['tanque_nome'], r['tanque_sistema']) for r in resumo))
        total_tipos = len(set(r['tipo_peca'] for r in resumo))
        
        return jsonify({
            'success': True,
            'resumo': resumo,
            'totais': {
                'total_pecas': total_pecas,
                'total_tanques': total_tanques,
                'total_tipos': total_tipos,
                'total_grupos': len(resumo)
            }
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'message': f'Erro ao buscar resumo: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500

def _processar_componentes_recursivo( produto_composto, quantidade_pecas, data_movimento, produto_composto_id, 
                                     data_dia, usuario_id, pecas_grupo, pecas_sem_estoque, produtos_processados, 
                                     nivel_recursao=0, prefixo_observacao='', log=False):
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
        quantidade_por_peca = componente.quantidade
        quantidade_total = quantidade_por_peca * quantidade_pecas
        
        # DEBUG: Verificar cálculo de quantidade
        if log:
            print(f"  Componente: estoque_id={estoque_id}, quantidade_por_peca={quantidade_por_peca}, quantidade_pecas={quantidade_pecas}, quantidade_total={quantidade_total}")
        
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
        
        # Verificar se já existe movimentação para este grupo específico
        # Usar uma combinação de estoque_id, produto_composto_id e data para identificar movimentações do grupo
        data_para_comparacao = data_dia if isinstance(data_dia, date_type) else data_dia.date() if isinstance(data_dia, datetime) else data_dia
        
        # Verificar se já existe movimentação para este estoque, produto composto e data
        # IMPORTANTE: Esta verificação garante que processamos todas as peças do grupo uma única vez
        # Cada componente (estoque_id diferente) deve ser processado separadamente
        # Mas para o mesmo estoque_id, produto_composto_id e data, só processamos uma vez
        movimentacao_existente = EstoqueMovimentacoes.query.filter(
            EstoqueMovimentacoes.estoque_id == estoque_id,
            EstoqueMovimentacoes.origem_id == produto_composto_id,
            EstoqueMovimentacoes.origem_tipo == 'producao_peca',
            func.date(EstoqueMovimentacoes.data_movimento) == data_para_comparacao
        ).first()
        
        if movimentacao_existente:
            # Já foi processado para este grupo e este componente específico, pular
            # Mas continuar processando outros componentes do produto composto (com estoque_id diferente)
            continue
        
        # Verificar disponibilidade de estoque
        if estoque.get_saldo_ate_data(data_movimento) < quantidade_total:
            material_nome = estoque.material.nome if estoque.material else f'Estoque ID {estoque_id}'
            pecas_sem_estoque.append({
                'produto_composto': produto_composto.nome,
                'data': data_dia.strftime('%d/%m/%Y') if isinstance(data_dia, date_type) else str(data_dia),
                'quantidade_pecas': quantidade_pecas,
                'material': material_nome,
                'necessario': float(quantidade_total),
                'disponivel': float(estoque.get_saldo_ate_data(data_movimento)),
                'nivel': nivel_recursao
            })
            
        
        # Criar uma única movimentação para todo o grupo
        movimentacao = EstoqueMovimentacoes()
        
        # Criar lista de peças para observação
        nomes_pecas = [f"{p.nome} (Tanque: {p.tanque.nome})" for p in pecas_grupo[:5]]
        if len(pecas_grupo) > 10:
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
            origem_tipo='producao_peca',
            usuario_id=usuario_id,
            motivo=observacao,
            log=log
        )
        movimentacao.data_movimento = data_movimento
        
        # Salvar movimentação (o método save() atualiza o estoque automaticamente)
        movimentacao.save(log=log)
        movimentacoes_criadas += 1
    
    return movimentacoes_criadas

@peca.route('/processar-producao', methods=['POST'])
@login_required
def processar_producao(log=False):

    """Processa a produção de peças concretadas, consumindo estoque baseado no produto composto vinculado
    Otimizado para agrupar por vinculação (produto composto) e por dia"""
    try:
        print("Processando produção...")
        EstoqueMovimentacoes.query.filter(EstoqueMovimentacoes.origem_tipo.like('%producao_peca%')).delete()
        db.session.commit()
        processar_producao_manual(log=log)
        return jsonify({
            'success': True,
            'message': 'Produção processada com sucesso!'
        }), 200
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'message': f'Erro ao processar produção: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500
    if False:
        try:
            from collections import defaultdict
            from datetime import date as date_type
            
            EstoqueMovimentacoes.query.filter(EstoqueMovimentacoes.origem_tipo.like('%producao_peca%')).delete()
            # Buscar todas as peças com data_concretagem preenchida
            pecas_concretadas = Peca.query.filter(Peca.data_concretagem.isnot(None),Peca.data_concretagem == '2025-12-09').all()
            
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
                    
                    # DEBUG: Verificar se todas as peças estão sendo processadas
                    if log:
                        print(f"Processando grupo: produto_composto_id={produto_composto_id}, data={data_dia}, quantidade_pecas={quantidade_pecas}")
                        print(f"Peças no grupo: {[f'{p.id}:{p.nome}' for p in pecas_grupo]}")
                    
                    # Converter data_dia para datetime (início do dia)
                    if isinstance(data_dia, date_type):
                        data_movimento = datetime.combine(data_dia, datetime.min.time())
                    else:
                        data_movimento = datetime.combine(data_dia, datetime.min.time())
                    
                    # Processar componentes do produto composto (recursivamente se necessário)
                    # IMPORTANTE: quantidade_pecas deve ser o número total de peças no grupo
                    movimentacoes_grupo = _processar_componentes_recursivo(
                        produto_composto=produto_composto,
                        quantidade_pecas=quantidade_pecas,  # Número total de peças no grupo
                        data_movimento=data_movimento,
                        produto_composto_id=produto_composto_id,
                        data_dia=data_dia,
                        usuario_id=usuario_id,
                        pecas_grupo=pecas_grupo,  # Lista completa de peças do grupo
                        pecas_sem_estoque=pecas_sem_estoque,
                        produtos_processados=set(),  # Para evitar loops infinitos
                        log=log
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
            
            # Agrupar pecas_sem_estoque por produto composto e data
            pecas_sem_estoque_agrupadas = {}
            for item in pecas_sem_estoque:
                chave = (item.get('produto_composto'), item.get('data'))
                if chave not in pecas_sem_estoque_agrupadas:
                    pecas_sem_estoque_agrupadas[chave] = {
                        'produto_composto': item.get('produto_composto'),
                        'data': item.get('data'),
                        'quantidade_pecas': item.get('quantidade_pecas', 0),
                        'materiais': []
                    }
                else:
                    # Garantir que usamos a maior quantidade de peças (caso haja inconsistência)
                    quantidade_atual = pecas_sem_estoque_agrupadas[chave]['quantidade_pecas']
                    quantidade_item = item.get('quantidade_pecas', 0)
                    if quantidade_item > quantidade_atual:
                        pecas_sem_estoque_agrupadas[chave]['quantidade_pecas'] = quantidade_item
                
                # Adicionar material à lista de materiais do grupo
                material_info = {}
                if 'material' in item:
                    material_info['material'] = item['material']
                if 'estoque_id' in item:
                    material_info['estoque_id'] = item['estoque_id']
                if 'necessario' in item:
                    material_info['necessario'] = item['necessario']
                if 'disponivel' in item:
                    material_info['disponivel'] = item['disponivel']
                if 'nivel' in item:
                    material_info['nivel'] = item['nivel']
                
                pecas_sem_estoque_agrupadas[chave]['materiais'].append(material_info)
            
            # Converter dicionário agrupado para lista
            pecas_sem_estoque_final = list(pecas_sem_estoque_agrupadas.values())
            
            mensagem = (
                f'Processamento concluído!\n'
                f'- {pecas_processadas} peça(s) processada(s)\n'
                f'- {movimentacoes_criadas} movimentação(ões) de estoque criada(s)\n'
                f'- {len(grupos_producao)} grupo(s) processado(s)'
            )
            
            if pecas_sem_vinculacao:
                mensagem += f'\n\n{len(pecas_sem_vinculacao)} peça(s) sem vinculação de produto composto.'
            
            if pecas_sem_estoque_final:
                mensagem += f'\n\n{len(pecas_sem_estoque_final)} grupo(s) com estoque insuficiente.'
            
            if erros:
                mensagem += f'\n\n{len(erros)} erro(s) durante o processamento.'
            
            msg = {
                'success': True,
                'message': mensagem,
                'pecas_processadas': pecas_processadas,
                'movimentacoes_criadas': movimentacoes_criadas,
                'grupos_processados': len(grupos_producao),
                'pecas_sem_vinculacao': pecas_sem_vinculacao,
                'pecas_sem_estoque': pecas_sem_estoque_final,
                'erros': erros
            }
            # Converter Decimal para float antes de serializar para JSON
            msg_serializavel = converter_decimal_para_float(msg)
            Logs(local='peca_processar_producao', data=datetime.now(), texto=json.dumps(msg_serializavel))
            return jsonify(msg_serializavel)
            
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({
                'success': False,
                'message': f'Erro ao processar produção: {str(e)}',
                'traceback': traceback.format_exc()
            }), 500

    
def processar_producao_manual(log):
    """Processa a produção de peças concretadas, consumindo estoque baseado no produto composto vinculado
    Otimizado para agrupar por vinculação (produto composto) e por dia, tipo e tanque"""
    dias = TanquesPecas.query.filter(TanquesPecas.data_concretagem.isnot(None)).group_by(TanquesPecas.data_concretagem).all()
    print(f"Processando {len(dias)} dias")
    for dia in dias:
        dia = dia.data_concretagem
        pecas_concretadas = TanquesPecas.query.filter(
            TanquesPecas.data_concretagem.isnot(None),
            TanquesPecas.data_concretagem == dia
        ).all()
        print(f"Processando dia: {dia} - {len(pecas_concretadas)} peças")
        if not pecas_concretadas:
            continue
        
        # Agrupar peças por tanque_id e tipo para otimizar processamento
        grupos = {}
        for peca in pecas_concretadas:
            chave = (peca.tanque_id, peca.tipo)
            if chave not in grupos:
                grupos[chave] = []
            grupos[chave].append(peca)
        
        materiais_necessarios = {}
        todas_pecas_processadas = []
        
        # Processar cada grupo (tanque + tipo) de uma vez
        for (tanque_id, tipo_peca), pecas_grupo in grupos.items():
            vinculacao = TanquesProdutoComposto.query.filter_by(
                tanque_id=tanque_id,
                tipo_peca=tipo_peca
            ).first()
            if not vinculacao:
                nomes_pecas_grupo = [p.nome or f"Peça {p.id}" for p in pecas_grupo]
                print(f"Peças {', '.join(nomes_pecas_grupo)} sem vinculação de produto composto (Tanque: {tanque_id}, Tipo: {tipo_peca})")
                continue
            
            produto_composto = ProdutoComposto.query.get(vinculacao.produto_composto_id)
            if not produto_composto:
                continue
            
            quantidade_grupo = len(pecas_grupo)
            nomes_pecas_grupo = [p.nome or f"Peça {p.id}" for p in pecas_grupo]
            todas_pecas_processadas.extend(nomes_pecas_grupo)
            
            if log:
                print(f"Processando grupo: Tanque {tanque_id}, Tipo {tipo_peca}, {quantidade_grupo} peça(s)")
            
            produtos_processados = set()  # isolado por grupo para não pular composições entre grupos
            produto_composto.produzir(
                quantidade=quantidade_grupo, 
                data_movimento=dia, 
                usuario_id=current_user.id, 
                log=log,
                produtos_processados=produtos_processados,
                materiais_necessarios=materiais_necessarios
            )

        print(f"Materiais necessários: {len(materiais_necessarios)}")
        if materiais_necessarios:
            # Processar materiais agrupados
            for info in materiais_necessarios.values():
                estoque = info['estoque']
                quantidade_total = info['quantidade']
                produto_id = info['produto_id']
                
                if log:
                    print(f"  -> Componente material: {estoque.material.nome} - Quantidade total agrupada: {quantidade_total}")
                
                mov = EstoqueMovimentacoes()
                mov.remover(
                    quantidade=quantidade_total, 
                    estoque_id=estoque.id, 
                    origem_id=produto_id, 
                    origem_tipo='producao_peca', 
                    usuario_id=current_user.id,
                    motivo=f'Produção das peças: {", ".join(todas_pecas_processadas)} - Quantidade total: {quantidade_total}',
                    log=log
                )
                # Definir data_movimento se fornecida
                mov.data_movimento = dia
                mov.save()
    return True

@peca.route('/importar-inspecao', methods=['POST'])
@login_required
def importar_inspecao():
    """Importa arquivo Excel de inspeção e processa as peças"""
    try:
        if 'arquivo' not in request.files:
            return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'}), 400
        
        arquivo = request.files['arquivo']
        if arquivo.filename == '':
            return jsonify({'success': False, 'message': 'Nenhum arquivo selecionado'}), 400
        
        # Verificar extensão
        if not arquivo.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'message': 'Apenas arquivos Excel (.xlsx ou .xls) são permitidos'}), 400
        
        # Salvar arquivo temporariamente
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f'inspecao_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
        arquivo.save(temp_path)
        
        try:
            # Processar arquivo usando a função do script
            resultado = processar_arquivo_inspecao(temp_path)

            processar_producao_manual(log=False)
            
            return jsonify({
                'success': True,
                'message': 'Arquivo processado com sucesso',
                'total_pecas': resultado.get('total_pecas', 0),
                'novas': resultado.get('novas', 0),
                'atualizadas': resultado.get('atualizadas', 0),
                'ignoradas': resultado.get('ignoradas', {})
            })
        finally:
            # Remover arquivo temporário
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
        
    except Exception as e:
        import traceback
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erro ao processar arquivo: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500

def processar_arquivo_inspecao(xlsx_path):
    """Processa o arquivo Excel de inspeção e retorna estatísticas"""
    import pandas as pd
    import re
    from models.nota_fiscal import NotaFiscal, CNPJS_MATRIZ
    
    log = {
        'total_pecas': 0,
        'novas': 0,
        'atualizadas': 0,
        'erros': {
            'quantidade': 0,
            'lista': []
        },
        'ignoradas': {
            'quantidade': 0,
            'lista': []
        },
        'linhas_ignoradas': []
    }
    
    def serialize_value(value):
        from datetime import date as date_type
        if isinstance(value, (pd.Timestamp, datetime, date_type)):
            if hasattr(value, 'strftime'):
                return value.strftime('%Y-%m-%d')
            return str(value)
        return value

    def serialize_nested(data):
        if isinstance(data, dict):
            return {k: serialize_nested(v) for k, v in data.items()}
        if isinstance(data, list):
            return [serialize_nested(item) for item in data]
        return serialize_value(data)
    
    # Ler o arquivo Excel na aba ' CADASTRO' (com espaço no início)
    df = pd.read_excel(xlsx_path, sheet_name=' CADASTRO', engine='openpyxl')
    
    pecas = []
    
    for index, row in df.iterrows():
        peca = {
            'tanque_id': None,
            'nome': None,
            'numero_sequencial': None,
            'numero_tanque': None,
            'data_concretagem': None,
            'tipo': None,
            'qualidade': {
                'acabamento': None,
                'chapa': None,
                'pista': None,
                'transporte': {
                    'data_transporte': None,
                    'nota': None,
                    'cte': None,
                    'placa_carreta': None,
                    'transportadora': None,
                }
            },
        }
        
        if row.iloc[5] == '-' or pd.isna(row.iloc[5]) or row.iloc[5] == None:
            log['ignoradas']['quantidade'] += 1
            log['ignoradas']['lista'].append(index)
            continue
        
        # Usa iloc para acessar por posição
        tipo_tanque_raw = row.iloc[4] if len(row) > 4 else None
        tipo_tanque = str(tipo_tanque_raw).strip() if pd.notna(tipo_tanque_raw) else None
        peca['tipo_tanque'] = None
        tanque = Tanques.query.filter(Tanques.nome.like(f'%{tipo_tanque}%')).first()
        
        if tanque:
            peca['tanque_id'] = tanque.id
        else:
            log['erros']['quantidade'] += 1
            log['erros']['lista'].append(index)
            log['ignoradas']['quantidade'] += 1
            log['ignoradas']['lista'].append(index)
            continue
        
        # Trata valores nan do pandas
        nome_part1 = row.iloc[5] if len(row) > 5 and pd.notna(row.iloc[5]) else ''
        nome_part2 = row.iloc[7] if len(row) > 7 and pd.notna(row.iloc[7]) else ''
        seq_match = re.search(r'\d+', str(nome_part2)) if nome_part2 != '' else None
        seq_formatado = seq_match.group(0).zfill(2) if seq_match else (str(nome_part2).strip() if nome_part2 != '' else '')
        peca['nome'] = f"{str(nome_part1).strip()}-{seq_formatado}"
        peca['numero_sequencial'] = seq_formatado if seq_formatado else (str(nome_part2).strip() if nome_part2 != '' else None)
        
        numerotanque_raw = tipo_tanque if tipo_tanque else None
        numerotanque_str = str(numerotanque_raw).strip() if numerotanque_raw else ''
        numero_tanque = None
        if numerotanque_str:
            match = re.search(r'(\d+)', numerotanque_str)
            if match:
                numero_tanque = int(match.group(1))
        peca['numero_tanque'] = numero_tanque if numero_tanque is not None else 3
        
        data_raw = row.iloc[1] if len(row) > 1 and pd.notna(row.iloc[1]) else None
        # Converte para datetime object ou None para salvar no MySQL
        if data_raw and hasattr(data_raw, 'strftime'):
            peca['data_concretagem'] = data_raw
        elif data_raw and isinstance(data_raw, str) and data_raw != '-':
            # Tenta parsear string no formato DD/MM/YYYY
            try:
                peca['data_concretagem'] = datetime.strptime(data_raw, '%d/%m/%Y')
            except:
                peca['data_concretagem'] = None
        else:
            peca['data_concretagem'] = None
        
        peca['tipo'] = row.iloc[9] if len(row) > 9 and pd.notna(row.iloc[9]) else None
        peca['qualidade']['pista'] = row.iloc[18] if len(row) > 18 and pd.notna(row.iloc[18]) else None
        peca['qualidade']['acabamento'] = row.iloc[17] if len(row) > 17 and pd.notna(row.iloc[17]) else None
        chapa_valor = row.iloc[16] if len(row) > 16 and pd.notna(row.iloc[16]) else None
        peca['qualidade']['chapa'] = '' if chapa_valor == 'NÃO TEM CHAPA' else (chapa_valor or '')
        
        # Trata data_transporte
        data_transporte_raw = row.iloc[20] if len(row) > 20 and pd.notna(row.iloc[20]) else None
        if data_transporte_raw and hasattr(data_transporte_raw, 'strftime'):
            peca['qualidade']['transporte']['data_transporte'] = data_transporte_raw.strftime('%Y-%m-%d')
        elif data_transporte_raw and isinstance(data_transporte_raw, str):
            try:
                dt = datetime.strptime(data_transporte_raw, '%d/%m/%Y')
                peca['qualidade']['transporte']['data_transporte'] = dt.strftime('%Y-%m-%d')
            except:
                peca['qualidade']['transporte']['data_transporte'] = data_transporte_raw
        else:
            peca['qualidade']['transporte']['data_transporte'] = None
        
        # Trata nota
        nota_raw = row.iloc[22] if len(row) > 23 else None
        if pd.notna(nota_raw) and nota_raw != '-':
            peca['qualidade']['transporte']['nota'] = int(nota_raw) if isinstance(nota_raw, (int, float)) else nota_raw
        else:
            peca['qualidade']['transporte']['nota'] = None

        # Buscar nota se tiver um valor válido
        nota = None
        if peca['qualidade']['transporte']['nota'] is not None and pd.notna(peca['qualidade']['transporte']['nota']) and type(peca['qualidade']['transporte']['nota']) == str:
            nota = NotaFiscal.query.filter(NotaFiscal.numero_nf==int(peca['qualidade']['transporte']['nota']),NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ)).first()
        if nota:
            cte = NotaFiscal.query.filter(NotaFiscal.dados_adicionais.like(f'%chave_nf:{nota.chave_acesso}%')).first()
            if cte:
                peca['qualidade']['transporte']['cte'] = cte.numero_nf
                peca['qualidade']['transporte']['transportadora'] = cte.nome_emitente

        peca['qualidade']['transporte']['placa_carreta'] = row.iloc[21] if len(row) > 21 and pd.notna(row.iloc[21]) else None
        
        pecas.append(peca)
        log['total_pecas'] += 1
    
    # Processar peças
    for peca in pecas:
        peca_existe = TanquesPecas.query.filter(
            TanquesPecas.nome==peca['nome'], 
            TanquesPecas.numero_sequencial==peca['numero_sequencial'], 
            TanquesPecas.tanque_id==peca['tanque_id']
        ).first()
        
        if not peca_existe:
            qualidade_serializada = json.dumps(serialize_nested(peca['qualidade']), ensure_ascii=False)
            log['novas'] += 1
            peca_dict = TanquesPecas(
                tanque_id=peca['tanque_id'],
                nome=peca['nome'],
                numero_sequencial=peca['numero_sequencial'],
                numero_tanque=peca['numero_tanque'],
                data_concretagem=peca['data_concretagem'],
                tipo=peca['tipo'],
                qualidade=qualidade_serializada
            )
            peca_dict.save()
        else:
            log['atualizadas'] += 1
            peca_existe.qualidade = json.dumps(serialize_nested(peca['qualidade']), ensure_ascii=False)
            peca_existe.data_concretagem = peca['data_concretagem']
            peca_existe.tipo = peca['tipo']
            peca_existe.numero_tanque = peca['numero_tanque']
            peca_existe.save()
    
    # Salvar log
    Logs(local='importar_inspecao', data=datetime.now(), texto=json.dumps(log))
    db.session.commit()
    
    return log

