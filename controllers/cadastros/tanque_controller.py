from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from datetime import datetime
import json
import pandas as pd
import io
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from models.database import db
from models.tanque import Tanques, TanquesPecas, TanquesGrupos
from models.contrato import Contrato
from models.material import Materiais
tanque_bp = Blueprint('tanque', __name__)

# Middleware para verificar se o usuário tem permissão
@tanque_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_gerente_ou_superior:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@tanque_bp.route('/')
def index():
    """
    Lista todos os tanques
    """
    contratos = Contrato.query.all()
    sistemas = ['SC-10', 'SC-14', 'SR-06']
    grupos = TanquesGrupos.get_all()
    return render_template('cadastros/tanques/index.html', contratos=contratos, sistemas=sistemas, grupos=grupos)


def _tanque_dados_adicionais_para_salvar(raw_str):
    """
    Converte string JSON do formulário em texto para a coluna dados_adicionais.
    Retorna None se vazio ou inválido.
    """
    if not raw_str or not str(raw_str).strip():
        return None
    try:
        d = json.loads(raw_str)
        if isinstance(d, dict):
            return json.dumps(d, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass
    return None


@tanque_bp.route('/api/tanques-resumo', methods=['GET'])
def api_tanques_resumo():
    """Lista id/nome/contrato para seletores (ex.: copiar índices entre tanques)."""
    try:
        rows = (
            db.session.query(Tanques.id, Tanques.nome, Contrato.nome)
            .outerjoin(Contrato, Tanques.contrato_id == Contrato.id)
            .order_by(Tanques.id.desc())
            .limit(4000)
            .all()
        )
        return jsonify({
            'success': True,
            'tanques': [
                {'id': r[0], 'nome': r[1] or '', 'contrato': r[2] or ''}
                for r in rows
            ],
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@tanque_bp.route('/api/indices-comparar', methods=['GET'])
def api_indices_comparar():
    """Retorna índices (dados_adicionais.indices) de vários tanques para comparação."""
    ids_param = (request.args.get('ids') or '').strip()
    if not ids_param:
        return jsonify({'success': False, 'error': 'Informe o parâmetro ids (ex.: ids=1,2,3)'}), 400
    ids = []
    for x in ids_param.split(','):
        x = x.strip()
        if x.isdigit():
            ids.append(int(x))
    if len(ids) < 2:
        return jsonify({'success': False, 'error': 'Selecione pelo menos 2 tanques'}), 400
    if len(ids) > 12:
        return jsonify({'success': False, 'error': 'Máximo de 12 tanques por comparação'}), 400
    out = []
    for tid in ids:
        t = Tanques.query.options(joinedload(Tanques.contrato)).get(tid)
        if not t:
            continue
        indices = []
        if t.dados_adicionais:
            try:
                d = json.loads(t.dados_adicionais)
                if isinstance(d, dict) and isinstance(d.get('indices'), list):
                    indices = d['indices']
            except (json.JSONDecodeError, TypeError):
                pass
        cname = ''
        if t.contrato:
            cname = t.contrato.nome or ''
        out.append({
            'id': t.id,
            'nome': t.nome or '',
            'contrato': cname,
            'indices': indices,
        })
    if len(out) < 2:
        return jsonify({'success': False, 'error': 'Não foi possível carregar pelo menos 2 tanques válidos'}), 400
    return jsonify({'success': True, 'tanques': out})


@tanque_bp.route('/api/tanques/<int:tanque_id>/indices', methods=['POST'])
def api_salvar_indices_tanque(tanque_id):
    """Atualiza apenas a lista indices em dados_adicionais, preservando demais chaves."""
    tanque = Tanques.query.get_or_404(tanque_id)
    data = request.get_json(silent=True) or {}
    indices = data.get('indices')
    if not isinstance(indices, list):
        return jsonify({'success': False, 'error': 'Campo indices deve ser uma lista'}), 400
    cleaned = []
    for it in indices:
        if not isinstance(it, dict):
            continue
        nome = (it.get('nome') or '').strip()
        valor = (it.get('valor') or '').strip()
        di = (it.get('data_inicio') or '').strip()
        df = (it.get('data_fim') or '').strip()
        if not nome and not valor and not di and not df:
            continue
        cleaned.append({
            'nome': nome,
            'valor': valor,
            'data_inicio': di,
            'data_fim': df,
        })
    base = {}
    if tanque.dados_adicionais:
        try:
            base = json.loads(tanque.dados_adicionais)
            if not isinstance(base, dict):
                base = {}
        except (json.JSONDecodeError, TypeError):
            base = {}
    base['indices'] = cleaned
    tanque.dados_adicionais = json.dumps(base, ensure_ascii=False)
    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@tanque_bp.route('/api/datatables', methods=['GET'])
def api_datatables():
    """
    Endpoint AJAX para DataTables - retorna dados de tanques em formato JSON
    """
    try:
        # Parâmetros do DataTables
        draw = request.args.get('draw', 1, type=int)
        start = request.args.get('start', 0, type=int)
        length = request.args.get('length', 25, type=int)
        search_value = request.args.get('search[value]', '', type=str).strip()
        
        # Parâmetros de ordenação
        order_column_index = int(request.args.get('order[0][column]', 1))
        order_dir = request.args.get('order[0][dir]', 'desc')
        
        # Mapear índice da coluna para campo de ordenação (após remover Sistema, Dimensões, Altura Útil e Quantidade)
        column_mapping = {
            1: Tanques.id,
            2: Contrato.nome,
            3: Tanques.nome,
            4: Tanques.altura_total,
            5: Tanques.placas_normais,
            6: Tanques.placas_fecho,
            7: Tanques.quantidade_bainhas,
            8: Tanques.item_nf,
            9: Tanques.valorUnitario
        }
        
        # Query base com joins necessários
        query = Tanques.query.join(Contrato, Tanques.contrato_id == Contrato.id)\
            .options(db.joinedload(Tanques.contrato), db.joinedload(Tanques.grupos))
        
        # Aplicar busca (apenas nas colunas visíveis)
        if search_value:
            query = query.filter(
                or_(
                    Tanques.nome.ilike(f'%{search_value}%'),
                    Contrato.nome.ilike(f'%{search_value}%')
                )
            )
        
        # Aplicar ordenação
        order_column = column_mapping.get(order_column_index, Tanques.id)
        if order_dir == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
        
        # Contar total de registros (antes da paginação)
        total_records = query.count()
        
        # Aplicar paginação
        tanques = query.offset(start).limit(length).all()
        
        # Formatar dados para o DataTables
        data = []
        for tanque in tanques:
            # Contar peças
            pecas_count = TanquesPecas.query.filter_by(tanque_id=tanque.id).count()
            
            # Formatar grupos
            grupos_html = ''
            if tanque.grupos:
                for grupo in tanque.grupos:
                    cor_grupo = grupo.cor if grupo.cor else '#007bff'
                    icone_grupo = grupo.icone if grupo.icone else 'fas fa-water'
                    grupos_html += f'<span class="badge" data-cor="{cor_grupo}"><i class="{icone_grupo}"></i> {grupo.nome}</span> '
            else:
                grupos_html = '<span class="text-muted">-</span>'
            
            # Formatar valor unitário
            valor_unitario_html = '-'
            if tanque.valorUnitario:
                valor_formatado = f"{tanque.valorUnitario:.2f}".replace('.', ',')
                valor_unitario_html = f'R$ {valor_formatado}'
            
            # Gerar CSRF token
            csrf_token = generate_csrf()
            
            # Escapar nome do tanque para JavaScript
            tanque_nome_escaped = tanque.nome.replace("'", "\\'").replace('"', '\\"')
            
            # HTML das ações
            contrato_nome_esc = tanque.contrato.nome.replace('"', '&quot;')
            acoes_html = (
                f'<div class="ft-acoes-dropdown dropdown">'
                f'<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false" title="Ações"><i class="fas fa-ellipsis-v"></i></button>'
                f'<ul class="dropdown-menu dropdown-menu-end">'
                f'<li><button type="button" class="dropdown-item btn-visualizar-tanque" data-id="{tanque.id}" data-contrato-nome="{contrato_nome_esc}"><i class="fas fa-eye text-info"></i> Visualizar</button></li>'
                f'<li><button type="button" class="dropdown-item btn-editar-tanque" data-id="{tanque.id}"><i class="fas fa-edit text-primary"></i> Editar</button></li>'
                f'<li><button type="button" class="dropdown-item btn-duplicar-tanque" data-id="{tanque.id}" data-nome="{tanque_nome_escaped}" data-url="/tanques/duplicar/{tanque.id}"><i class="fas fa-copy text-warning"></i> Duplicar</button></li>'
                f'<li><button type="button" class="dropdown-item" onclick="abrirModalAdicionarPecas(\'{tanque.id}\', \'{tanque_nome_escaped}\')"><i class="fas fa-plus-circle text-success"></i> Adicionar Peças</button></li>'
                f'<li><hr class="dropdown-divider"></li>'
                f'<li><form action="/tanques/excluir/{tanque.id}" method="POST" class="d-inline form-excluir">'
                f'<input type="hidden" name="csrf_token" value="{csrf_token}">'
                f'<button type="submit" class="dropdown-item text-danger"><i class="fas fa-trash text-danger"></i> Excluir</button>'
                f'</form></li>'
                f'</ul></div>'
            )
            
            # Checkbox com data attributes
            checkbox_html = f'''
                <input type="checkbox" class="tanque-checkbox" value="{tanque.id}" 
                       data-tanque-id="{tanque.id}"
                       data-quantidade="{tanque.quantidade}"
                       data-placas-normais="{tanque.placas_normais or 0}"
                       data-placas-fecho="{tanque.placas_fecho or 0}"
                       data-bainhas="{tanque.quantidade_bainhas or 0}"
                       data-altura-total="{tanque.altura_total}"
                       data-sistema="{tanque.sistema}">
            '''
            
            # Link do contrato
            contrato_html = f'''
                <a href="/contratos/visualizar/{tanque.contrato_id}" 
                   style="text-decoration: none; display: block; max-width: 200px;">
                    {tanque.contrato.nome}
                </a>
            '''
            
            data.append([
                checkbox_html,  # 0 - Checkbox
                str(tanque.id),  # 1 - ID
                contrato_html,  # 2 - Contrato
                tanque.nome,  # 3 - Nome
                grupos_html,  # 4 - Grupo
                f'{tanque.altura_total} m',  # 5 - Altura Total
                str(tanque.placas_normais) if tanque.placas_normais else '-',  # 6 - Placas Normais
                str(tanque.placas_fecho) if tanque.placas_fecho else '-',  # 7 - Placas Fecho
                str(tanque.quantidade_bainhas) if tanque.quantidade_bainhas else '-',  # 8 - Bainhas
                str(tanque.item_nf) if tanque.item_nf else '-',  # 9 - Item NF
                valor_unitario_html,  # 10 - Valor Unitário
                acoes_html  # 11 - Ações
            ])
        
        return jsonify({
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': total_records,
            'data': data
        })
        
    except Exception as e:
        return jsonify({
            'draw': request.args.get('draw', 1, type=int),
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e)
        }), 500

@tanque_bp.route('/contrato/<int:contrato_id>')
def listar_por_contrato(contrato_id):
    """
    Lista tanques de um contrato específico
    """
    contrato = Contrato.query.get_or_404(contrato_id)
    tanques = Tanques.query.filter_by(contrato_id=contrato_id).all()
    return render_template('cadastros/tanques/listar_por_contrato.html', tanques=tanques, contrato=contrato)

@tanque_bp.route('/novo', methods=['GET', 'POST'])
def novo():
    """
    Cria um novo tanque
    """
    contratos = Contrato.query.all()
    
    # Caso venha da página de contrato
    contrato_id = request.args.get('contrato_id')
    contrato_selecionado = None
    if contrato_id:
        contrato_selecionado = Contrato.query.get(contrato_id)
    
    sistemas = ['SC-10', 'SC-14', 'SR-06']
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        sistema = request.form.get('sistema')
        dimensoes = request.form.get('dimensoes')
        altura_total = request.form.get('altura_total')
        altura_util = request.form.get('altura_util')
        quantidade = request.form.get('quantidade', 1)
        cobertura = True if request.form.get('cobertura') == 'on' else False
        contrato_id = request.form.get('contrato_id')
        quantidade_bainhas = request.form.get('quantidade_bainhas')
        placas_normais = request.form.get('placas_normais')
        placas_fecho = request.form.get('placas_fecho')
        valor_unitario = request.form.get('valor_unitario')
        dados_adicionais_str = request.form.get('dados_adicionais', '').strip()
        
        # Extrair valores numéricos das dimensões
        diametro = None
        comprimento = None
        largura = None
        
        try:
            # Para tanques circulares, extrair o diâmetro
            if sistema.startswith('SC'):
                # Remover possíveis unidades e converter para float
                valor_str = dimensoes.replace('m', '').replace('M', '').strip()
                # Substituir vírgula por ponto para conversão
                valor_str = valor_str.replace(',', '.')
                diametro = float(valor_str)
            
            # Para tanques retangulares, extrair comprimento e largura
            elif sistema.startswith('SR'):
                # Espera-se formato como "4,0m x 5,0m" ou similar
                partes = dimensoes.lower().replace('m', '').split('x')
                if len(partes) >= 2:
                    # Substituir vírgula por ponto para conversão
                    comp_str = partes[0].strip().replace(',', '.')
                    larg_str = partes[1].strip().replace(',', '.')
                    comprimento = float(comp_str)
                    largura = float(larg_str)
        except (ValueError, IndexError) as e:
            flash(f'Erro ao extrair valores numéricos das dimensões: {str(e)}. Os valores serão salvos como texto.', 'warning')
        
        # Validação básica
        if not nome or not sistema or not dimensoes or not altura_total or not altura_util or not contrato_id:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('cadastros/tanques/novo.html', 
                                  contratos=contratos, 
                                  contrato_selecionado=contrato_selecionado,
                                  sistemas=sistemas)
        
        try:
            # Converter valores numéricos
            altura_total = float(altura_total)
            altura_util = float(altura_util)
            quantidade = int(quantidade)
            
            # Converter quantidades de placas se fornecidas
            if placas_normais:
                placas_normais = int(placas_normais)
            else:
                placas_normais = None
                
            if placas_fecho:
                placas_fecho = int(placas_fecho)
            else:
                placas_fecho = None
            
            # Converter quantidade de bainhas se fornecida
            if quantidade_bainhas:
                quantidade_bainhas = int(quantidade_bainhas)
            else:
                quantidade_bainhas = 0
            
            # Converter valor unitário se fornecido
            if valor_unitario:
                valor_unitario = float(valor_unitario)
            else:
                valor_unitario = None
            
            # Criar novo tanque
            novo_tanque = Tanques(
                # Definir o UN com base no método gerar_un
                un=Tanques.gerar_un(),
                nome=nome,
                sistema=sistema,
                dimensoes=dimensoes,
                diametro=diametro,
                comprimento=comprimento,
                largura=largura,
                altura_total=altura_total,
                altura_util=altura_util,
                quantidade=quantidade,
                cobertura=cobertura,
                quantidade_bainhas=quantidade_bainhas,
                placas_normais=placas_normais,
                placas_fecho=placas_fecho,
                valorUnitario=valor_unitario,
                contrato_id=contrato_id,
                dados_adicionais=_tanque_dados_adicionais_para_salvar(dados_adicionais_str),
            )
            
            # Salvar o tanque
            novo_tanque.save()
            
            flash('Tanque cadastrado com sucesso!', 'success')
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': 'Tanque cadastrado com sucesso!',
                    'tanque_id': novo_tanque.id
                })
            
            # Redirecionar para a página de contrato se veio de lá
            if contrato_selecionado:
                return redirect(url_for('tanque.listar_por_contrato', contrato_id=contrato_id))
            else:
                return redirect(url_for('tanque.index'))
            
        except Exception as e:
            error_msg = f'Erro ao cadastrar tanque: {str(e)}'
            flash(error_msg, 'danger')
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
    
    return render_template('cadastros/tanques/novo.html', 
                          contratos=contratos, 
                          contrato_selecionado=contrato_selecionado,
                          sistemas=sistemas)

@tanque_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """
    Edita um tanque existente
    """
    tanque = Tanques.query.get_or_404(id)
    contratos = Contrato.query.all()
    sistemas = ['SC-10', 'SC-14', 'SR-06']
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        sistema = request.form.get('sistema')
        dimensoes = request.form.get('dimensoes')
        altura_total = request.form.get('altura_total')
        altura_util = request.form.get('altura_util')
        quantidade = request.form.get('quantidade', 1)
        cobertura = True if request.form.get('cobertura') == 'on' else False
        contrato_id = request.form.get('contrato_id')
        quantidade_bainhas = request.form.get('quantidade_bainhas')
        placas_normais = request.form.get('placas_normais')
        placas_fecho = request.form.get('placas_fecho')
        item_nf = request.form.get('item_nf')
        valor_unitario = request.form.get('valor_unitario')
        dados_adicionais = request.form.get('dados_adicionais', '')
        
        # Extrair valores numéricos das dimensões
        diametro = None
        comprimento = None
        largura = None
        
        try:
            # Para tanques circulares, extrair o diâmetro
            if sistema.startswith('SC'):
                # Remover possíveis unidades e converter para float
                valor_str = dimensoes.replace('m', '').replace('M', '').strip()
                # Substituir vírgula por ponto para conversão
                valor_str = valor_str.replace(',', '.')
                diametro = float(valor_str)
            
            # Para tanques retangulares, extrair comprimento e largura
            elif sistema.startswith('SR'):
                # Espera-se formato como "4,0m x 5,0m" ou similar
                partes = dimensoes.lower().replace('m', '').split('x')
                if len(partes) >= 2:
                    # Substituir vírgula por ponto para conversão
                    comp_str = partes[0].strip().replace(',', '.')
                    larg_str = partes[1].strip().replace(',', '.')
                    comprimento = float(comp_str)
                    largura = float(larg_str)
        except (ValueError, IndexError) as e:
            flash(f'Erro ao extrair valores numéricos das dimensões: {str(e)}. Os valores serão salvos como texto.', 'warning')
        
        # Validação básica
        if not nome or not sistema or not dimensoes or not altura_total or not altura_util or not contrato_id:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('cadastros/tanques/editar.html', 
                                 tanque=tanque, 
                                 contratos=contratos, 
                                 sistemas=sistemas)
        
        try:
            # Converter valores numéricos
            altura_total = float(altura_total)
            altura_util = float(altura_util)
            quantidade = int(quantidade)
            
            # Converter quantidades de placas se fornecidas
            if placas_normais:
                placas_normais = int(placas_normais)
            else:
                placas_normais = None
                
            if placas_fecho:
                placas_fecho = int(placas_fecho)
            else:
                placas_fecho = None
            
            # Converter quantidade de bainhas se fornecida
            if quantidade_bainhas:
                quantidade_bainhas = int(quantidade_bainhas)
            else:
                quantidade_bainhas = 0
            
            # Converter item_nf se fornecida
            if item_nf:
                item_nf = int(item_nf)
            else:
                item_nf = None
            
            # Converter valor unitário se fornecido
            if valor_unitario:
                valor_unitario = float(valor_unitario)
            else:
                valor_unitario = None
            
            # Atualizar o tanque
            tanque.nome = nome
            tanque.sistema = sistema
            tanque.dimensoes = dimensoes
            tanque.diametro = diametro
            tanque.comprimento = comprimento
            tanque.largura = largura
            tanque.altura_total = altura_total
            tanque.altura_util = altura_util
            tanque.quantidade = quantidade
            tanque.cobertura = cobertura
            tanque.quantidade_bainhas = quantidade_bainhas
            tanque.placas_normais = placas_normais
            tanque.placas_fecho = placas_fecho
            tanque.contrato_id = contrato_id
            tanque.item_nf = item_nf
            tanque.valorUnitario = valor_unitario
            tanque.dados_adicionais = _tanque_dados_adicionais_para_salvar(dados_adicionais)
            
            # Salvar as alterações
            db.session.commit()
            
            flash('Tanque atualizado com sucesso!', 'success')
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': 'Tanque atualizado com sucesso!',
                    'tanque_id': tanque.id
                })
            
            return redirect(url_for('tanque.visualizar', id=tanque.id))
            
        except Exception as e:
            db.session.rollback()
            error_msg = f'Erro ao atualizar tanque: {str(e)}'
            flash(error_msg, 'danger')
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
    
    return render_template('cadastros/tanques/editar.html', 
                         tanque=tanque, 
                         contratos=contratos, 
                         sistemas=sistemas)

@tanque_bp.route('/visualizar/<int:id>')
def visualizar(id):
    """
    Visualiza os detalhes de um tanque
    """
    tanque = Tanques.query.get_or_404(id)
    return render_template('cadastros/tanques/visualizar.html', tanque=tanque)

@tanque_bp.route('/duplicar/<int:id>', methods=['POST'])
def duplicar(id):
    """
    Duplica um tanque existente (pode duplicar múltiplas vezes)
    """
    tanque_original = Tanques.query.get_or_404(id)
    
    try:
        # Obter parâmetros do formulário
        quantidade = int(request.form.get('quantidade', 1))
        formato_nome = request.form.get('formato_nome', 'copia')
        numero_inicial = int(request.form.get('numero_inicial', 1))
        renomear_original = request.form.get('renomear_original') == '1'
        
        # Validar quantidade
        if quantidade < 1:
            quantidade = 1
        if quantidade > 100:
            quantidade = 100
        
        # Validar número inicial
        if numero_inicial < 1:
            numero_inicial = 1
        
        tanques_criados = []
        
        # Guardar nome original antes de qualquer modificação
        nome_base_original = tanque_original.nome
        
        # Função auxiliar para gerar nome baseado no formato
        def gerar_nome(numero, nome_base, formato, qtd_total=1):
            if formato == 'sequencial':
                return f"{numero} - {nome_base}"
            elif formato == 'nome_zero':
                numero_formatado = f"{numero:02d}"
                return f"{nome_base} {numero_formatado}"
            elif formato == 'apenas_numero':
                numero_formatado = f"{numero:02d}"
                return numero_formatado
            elif formato == 'copia':
                if qtd_total == 1:
                    return f"{nome_base} (Cópia)"
                else:
                    return f"{nome_base} (Cópia {numero})"
            elif formato == 'sequencial_copia':
                return f"{numero} - {nome_base} (Cópia)"
            else:
                return f"{nome_base} (Cópia {numero})"
        
        # Se renomear original, renomear primeiro usando o nome base original
        if renomear_original:
            nome_original_renomeado = gerar_nome(numero_inicial, nome_base_original, formato_nome, quantidade)
            tanque_original.nome = nome_original_renomeado
            db.session.commit()
        
        # Criar múltiplas cópias
        # Se renomear original, as cópias começam em numero_inicial + 1
        inicio_copias = numero_inicial + 1 if renomear_original else numero_inicial
        
        for i in range(quantidade):
            # Gerar nome baseado no formato escolhido
            numero_atual = inicio_copias + i
            
            # Usar nome base original para as cópias
            novo_nome = gerar_nome(numero_atual, nome_base_original, formato_nome, quantidade)
            
            # Criar novo tanque com dados do original
            novo_tanque = Tanques(
                un=Tanques.gerar_un(),  # Gerar novo UN
                nome=novo_nome,
                sistema=tanque_original.sistema,
                dimensoes=tanque_original.dimensoes,
                diametro=tanque_original.diametro,
                comprimento=tanque_original.comprimento,
                largura=tanque_original.largura,
                altura_total=tanque_original.altura_total,
                altura_util=tanque_original.altura_util,
                quantidade=tanque_original.quantidade,
                cobertura=tanque_original.cobertura,
                ncabospn=tanque_original.ncabospn,
                ncabospf=tanque_original.ncabospf,
                quantidade_bainhas=tanque_original.quantidade_bainhas,
                placas_normais=tanque_original.placas_normais,
                placas_fecho=tanque_original.placas_fecho,
                valorUnitario=tanque_original.valorUnitario,
                contrato_id=tanque_original.contrato_id,
                item_nf=tanque_original.item_nf,
                dados_adicionais=tanque_original.dados_adicionais,
            )
            
            # Salvar o novo tanque
            novo_tanque.save()
            tanques_criados.append(novo_tanque.id)
        
        mensagem = f'{quantidade} cópia(s) do tanque "{tanque_original.nome}" criada(s) com sucesso!'
        flash(mensagem, 'success')
        
        # Verificar se é requisição AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': mensagem,
                'tanques_criados': tanques_criados,
                'quantidade': quantidade
            })
        
        # Redirecionar para a página de tanques
        return redirect(url_for('tanque.index'))
        
    except Exception as e:
        db.session.rollback()
        error_msg = f'Erro ao duplicar tanque: {str(e)}'
        flash(error_msg, 'danger')
        
        # Verificar se é requisição AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        return redirect(url_for('tanque.index'))

@tanque_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """
    Exclui um tanque
    """
    tanque = Tanques.query.get_or_404(id)
    contrato_id = tanque.contrato_id
    
    try:
        # Excluir o tanque
        tanque.delete()
        flash('Tanque excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir tanque: {str(e)}', 'danger')
    
    # Verificar se veio da página de contrato
    referrer = request.referrer
    if referrer and f'/contrato/{contrato_id}' in referrer:
        return redirect(url_for('tanque.listar_por_contrato', contrato_id=contrato_id))
    else:
        return redirect(url_for('tanque.index'))
@tanque_bp.route('/grupos', methods=['GET', 'POST'])
def grupos():
    """
    Lista e gerencia grupos de tanques
    """
    if request.method == 'POST':
        # Criar novo grupo
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        cor = request.form.get('cor', '#007bff')
        icone = request.form.get('icone', 'fas fa-water')
        
        if not nome:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'O nome do grupo é obrigatório!'}), 400
            flash('O nome do grupo é obrigatório!', 'danger')
            return redirect(url_for('tanque.grupos'))
        
        try:
            grupo = TanquesGrupos(
                nome=nome,
                descricao=descricao,
                cor=cor,
                icone=icone
            )
            grupo.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': f'Grupo "{nome}" criado com sucesso!',
                    'grupo': {
                        'id': grupo.id,
                        'nome': grupo.nome,
                        'total_tanques': grupo.total_tanques
                    }
                })
            
            flash(f'Grupo "{nome}" criado com sucesso!', 'success')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': str(e)}), 400
            flash(f'Erro ao criar grupo: {str(e)}', 'danger')
        
        return redirect(url_for('tanque.grupos'))
    
    grupos = TanquesGrupos.get_all()
    return render_template('cadastros/tanques/grupos.html', grupos=grupos)

@tanque_bp.route('/grupos/<int:id>/editar', methods=['POST'])
def editar_grupo(id):
    """
    Edita um grupo de tanques
    """
    grupo = TanquesGrupos.query.get_or_404(id)
    
    nome = request.form.get('nome')
    descricao = request.form.get('descricao')
    cor = request.form.get('cor', '#007bff')
    icone = request.form.get('icone', 'fas fa-water')
    
    if not nome:
        flash('O nome do grupo é obrigatório!', 'danger')
        return redirect(url_for('tanque.grupos'))
    
    try:
        grupo.nome = nome
        grupo.descricao = descricao
        grupo.cor = cor
        grupo.icone = icone
        grupo.save()
        flash(f'Grupo "{nome}" atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar grupo: {str(e)}', 'danger')
    
    return redirect(url_for('tanque.grupos'))

@tanque_bp.route('/grupos/<int:id>/excluir', methods=['POST'])
def excluir_grupo(id):
    """
    Exclui um grupo de tanques
    """
    grupo = TanquesGrupos.query.get_or_404(id)
    
    try:
        nome = grupo.nome
        grupo.delete()
        flash(f'Grupo "{nome}" excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir grupo: {str(e)}', 'danger')
    
    return redirect(url_for('tanque.grupos'))

@tanque_bp.route('/grupos/adicionar-tanques', methods=['POST'])
def adicionar_tanques_grupo():
    """
    Adiciona tanques selecionados a um grupo
    """
    grupo_id = request.form.get('grupo_id')
    tanque_ids = request.form.getlist('tanque_ids')
    
    if not grupo_id or not tanque_ids:
        flash('Selecione um grupo e pelo menos um tanque.', 'warning')
        return redirect(url_for('tanque.index'))
    
    grupo = TanquesGrupos.query.get_or_404(grupo_id)
    
    try:
        tanques_adicionados = 0
        tanques_ja_no_grupo = 0
        
        for tanque_id in tanque_ids:
            try:
                tanque_id_int = int(tanque_id)
                tanque = Tanques.query.get(tanque_id_int)
                if tanque:
                    if tanque not in grupo.tanques:
                        grupo.tanques.append(tanque)
                        tanques_adicionados += 1
                    else:
                        tanques_ja_no_grupo += 1
            except (ValueError, TypeError) as e:
                continue
        
        # Fazer commit de uma vez só
        if tanques_adicionados > 0:
            db.session.commit()
        
        mensagem = f'{tanques_adicionados} tanque(s) adicionado(s) ao grupo "{grupo.nome}"!'
        if tanques_ja_no_grupo > 0:
            mensagem += f' {tanques_ja_no_grupo} tanque(s) já estavam no grupo.'
        
        flash(mensagem, 'success' if tanques_adicionados > 0 else 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao adicionar tanques ao grupo: {str(e)}', 'danger')
    
    return redirect(url_for('tanque.index'))

@tanque_bp.route('/grupos/<int:grupo_id>/remover-tanque/<int:tanque_id>', methods=['POST'])
def remover_tanque_grupo(grupo_id, tanque_id):
    """
    Remove um tanque de um grupo
    """
    grupo = TanquesGrupos.query.get_or_404(grupo_id)
    tanque = Tanques.query.get_or_404(tanque_id)
    
    try:
        grupo.remover_tanque(tanque)
        flash(f'Tanque "{tanque.nome}" removido do grupo "{grupo.nome}"!', 'success')
    except Exception as e:
        flash(f'Erro ao remover tanque do grupo: {str(e)}', 'danger')
    
    return redirect(url_for('tanque.grupos')) 