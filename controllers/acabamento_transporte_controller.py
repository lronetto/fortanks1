from operator import or_
from flask import Blueprint, render_template, request, jsonify, send_file
from sqlalchemy import func
from models.concreto import (
    ConcretoConcretagensTanques,
    ConcretoUsinagens,
    qualidade_peca_remover_data_producao_de_dados_adicionais,
)
from models.database import db
from models.tanque import Tanques, TanquesPecas
from models.nota_fiscal import NotaFiscal, NotaFiscalItem, CNPJS_MATRIZ

from flask_wtf.csrf import generate_csrf
from datetime import datetime
import html
import json
import pandas as pd

acabamento_transporte_bp  = Blueprint('acabamento_transporte', __name__)


def _numeros_nf_ja_usados_em_transporte(excluir_peca_id=None):
    """Números de NF já gravados em qualidade.transporte.nota (outras peças)."""
    usados = set()
    qry = TanquesPecas.query.filter(TanquesPecas.qualidade.isnot(None))
    if excluir_peca_id is not None:
        qry = qry.filter(TanquesPecas.id != excluir_peca_id)
    for peca in qry.all():
        try:
            q = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else (peca.qualidade or {})
        except (json.JSONDecodeError, TypeError):
            continue
        transporte = q.get('transporte') or {}
        if not isinstance(transporte, dict):
            continue
        nota = transporte.get('nota')
        if nota is None or str(nota).strip() in ('', 'null'):
            continue
        usados.add(str(nota).strip())
    return usados


def get_pecas(filtros):
    filtro = filtros.get('filtro', 'todos')
    page = int(filtros.get('page', 1))
    per_page = 20
    nome_peca = filtros.get('nome_peca', '').strip()
    tanque_id = filtros.get('tanque_id', 'todos')
    pecas_query = TanquesPecas.query.join(Tanques)
    if nome_peca:
        pecas_query = pecas_query.filter(\
            TanquesPecas.nome.ilike(f'%{nome_peca}%'))
    if tanque_id and str(tanque_id) != 'todos':
        try:
            tanque_id_int = int(tanque_id)
            pecas_query = pecas_query.filter(TanquesPecas.tanque_id == tanque_id_int)
        except (TypeError, ValueError):
            pass
    if filtro == 'acabadas':
        pecas_query = pecas_query.filter(\
            TanquesPecas.qualidade.isnot(None), \
            func.json_extract(TanquesPecas.qualidade, '$.acabamento').isnot(None))
    elif filtro == 'transportadas':
        pecas_query = pecas_query.filter(\
            TanquesPecas.qualidade.isnot(None), \
            func.json_extract(TanquesPecas.qualidade, '$.transporte.data_transporte').notin_(None, 'null', 'None'))
    elif filtro == 'acabada_nao_transportada':
        print('acabada_nao_transportada')
        pecas_query = pecas_query.filter(\
            TanquesPecas.qualidade.isnot(None), \
            func.json_extract(TanquesPecas.qualidade, '$.acabamento').isnot(None), \
            func.json_extract(TanquesPecas.qualidade, '$.transporte.data_transporte').in_(None, 'null', 'None'))
    pecas_query = pecas_query.all()
    tanques = Tanques.query.order_by(Tanques.nome).all()
    pecas = []
    for peca in pecas_query:
        qualidade = peca.qualidade or '{}'
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        if 'acabamento' in qualidade_dict:
            peca.acabamento = qualidade_dict['acabamento']
        else:
            peca.acabamento = None
        if 'transporte' in qualidade_dict and 'data_transporte' in qualidade_dict['transporte']:
            peca.transporte = qualidade_dict['transporte']['data_transporte']
        else:
            peca.transporte = None
        if 'transporte' in qualidade_dict and 'transportadora' in qualidade_dict['transporte']:
            peca.transportadora = qualidade_dict['transporte']['transportadora']
        else:
            peca.transportadora = None
        if 'transporte' in qualidade_dict and 'placa_carreta' in qualidade_dict['transporte']:
            peca.placa_carreta = qualidade_dict['transporte']['placa_carreta']
        else:
            peca.placa_carreta = None
        if 'transporte' in qualidade_dict and 'nota' in qualidade_dict['transporte']:
            peca.nota_fiscal = qualidade_dict['transporte']['nota']
        else:
            peca.nota_fiscal = None
        pecas.append(peca)
   
    return pecas
@acabamento_transporte_bp.route('/')
def index():
    filtros = request.args.to_dict()
    tanques = Tanques.query.order_by(Tanques.nome).all()
    filtro = filtros.get('filtro', 'todos')
    nome_peca = filtros.get('nome_peca', '')
    tanque_id = filtros.get('tanque_id', 'todos')
    return render_template('acabamento_transporte/index.html',
                           tanques=tanques,
                           now=datetime.now().strftime('%Y-%m-%d'),
                           filtro=filtro,
                           nome_peca=nome_peca,
                           tanque_id=tanque_id)

@acabamento_transporte_bp.route('/acabamento', methods=['GET', 'POST'])
def acabamento():
    """Registra acabamento de uma ou mais peças"""
    if request.method == 'POST':
        tanque_id = request.form.get('acabamento-tanque_id')
        peca_ids = request.form.getlist('acabamento-peca_ids[]')
        data_acabamento = request.form.get('data_acabamento')
        print(f"form: {request.form}")
        if not data_acabamento:
            data_acabamento = datetime.now().strftime('%Y-%m-%d')
        try:
            pecas = TanquesPecas.query.filter(TanquesPecas.id.in_(peca_ids), TanquesPecas.tanque_id == tanque_id).all()
            if not pecas:
                return jsonify({'success': False, 'message': 'Nenhuma peça encontrada'}), 404
            for peca in pecas:
                qualidade = peca.qualidade or '{}'
                qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
                qualidade_dict['acabamento'] = data_acabamento
                qualidade_peca_remover_data_producao_de_dados_adicionais(qualidade_dict)
                peca.qualidade = json.dumps(qualidade_dict)
                peca.save()
            return jsonify({'success': True, 'pecas_afetadas': [p.id for p in pecas]})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    # GET: retorna o modal
    tanques = Tanques.query.order_by(Tanques.nome).all()
    csrf_token = generate_csrf()
    return render_template('acabamento_transporte/modais/acabamento.html', 
                           tanques=tanques, 
                           csrf_token=csrf_token,
                           now=datetime.now().strftime('%Y-%m-%d'))

@acabamento_transporte_bp.route('/transporte', methods=['GET', 'POST'])
def transporte():
    """Registra transporte de peças"""
    if request.method == 'POST':
       # print(request.form)
        tanque_ids = request.form.getlist('transporte-tanque_ids[]')
        peca_ids = request.form.getlist('transporte-peca_ids[]')
        print('tanques',tanque_ids)
        print('pecas',peca_ids)
        placas = request.form.getlist('placas')
        nota_fiscal = request.form.get('nota_fiscal')
        placa_carreta = request.form.get('placa_carreta')
        data_transporte = request.form.get('data_transporte')
        transportadora = request.form.get('transportadora')
        if not data_transporte:
            data_transporte = datetime.now().strftime('%Y-%m-%d')
        try:
            pecas = TanquesPecas.query.filter(TanquesPecas.id.in_(peca_ids)).all()
            for peca in pecas:
                qualidade = peca.qualidade or '{}'
                qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
                qualidade_dict['transporte'] = {
                    'data_transporte': data_transporte,
                    'nota': nota_fiscal,
                    'placa_carreta': placa_carreta,
                    'transportadora': transportadora
                }
                qualidade_peca_remover_data_producao_de_dados_adicionais(qualidade_dict)
                peca.qualidade = json.dumps(qualidade_dict)
                peca.data_entrega = data_transporte
                peca.save()
            return jsonify({'success': True, 'pecas_afetadas': [p.id for p in pecas]})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    # GET: retorna o modal
    tanques = Tanques.query.order_by(Tanques.nome).all()
    csrf_token = generate_csrf()
    return render_template('acabamento_transporte/modais/transporte.html', 
                           tanques=tanques, 
                           csrf_token=csrf_token,
                           now=datetime.now().strftime('%Y-%m-%d'))


@acabamento_transporte_bp.route('/api/datatables', methods=['GET'])
def api_datatables():
    """
    Endpoint AJAX para DataTables - retorna peças de acabamento/transporte em formato JSON.
    """
    try:
        draw = request.args.get('draw', 1, type=int)
        start = request.args.get('start', 0, type=int)
        length = request.args.get('length', 25, type=int)
        search_value = request.args.get('search[value]', '', type=str).strip()
        order_column_index = int(request.args.get('order[0][column]', 0))
        order_dir = request.args.get('order[0][dir]', 'asc')

        filtros = {
            'filtro': request.args.get('filtro', 'todos'),
            'tanque_id': request.args.get('tanque_id', 'todos'),
            'nome_peca': request.args.get('nome_peca', '').strip(),
        }
        pecas = get_pecas(filtros)

        # Converter para lista de dicts para busca/ordenação/paginação
        column_keys = ('tanque', 'nome', 'acabamento', 'data_transporte', 'transportadora', 'placa_carreta', 'nota_fiscal')
        rows = []
        for peca in pecas:
            tanque_nome = peca.tanque.nome if peca.tanque else ''
            peca_nome = peca.nome or ''
            acabamento = str(peca.acabamento) if peca.acabamento else ''
            data_transporte = str(peca.transporte) if peca.transporte else ''
            transportadora = str(peca.transportadora) if peca.transportadora else ''
            placa = str(peca.placa_carreta) if peca.placa_carreta else ''
            nota = str(peca.nota_fiscal) if peca.nota_fiscal else ''
            tanque_id = peca.tanque_id if peca.tanque_id else (peca.tanque.id if peca.tanque else None)
            peca_id = getattr(peca, 'id', None)
            # Botões de ação (escapar nomes para atributos HTML)
            nome_esc = html.escape(peca_nome)
            tanque_esc = html.escape(tanque_nome)
            acoes = (
                '<div class="btn-group btn-group-sm" role="group">'
                '<button type="button" class="btn btn-success btn-acao-acabamento" '
                'data-peca-id="{}" data-tanque-id="{}" data-peca-nome="{}" data-tanque-nome="{}" '
                'title="Registrar acabamento"><i class="fas fa-paint-roller"></i></button>'
                '<button type="button" class="btn btn-primary btn-acao-transporte" '
                'data-peca-id="{}" data-tanque-id="{}" data-peca-nome="{}" data-tanque-nome="{}" '
                'title="Registrar transporte"><i class="fas fa-truck"></i></button>'
                '</div>'
            ).format(peca_id or '', tanque_id or '', nome_esc, tanque_esc, peca_id or '', tanque_id or '', nome_esc, tanque_esc)
            rows.append({
                'tanque': tanque_nome,
                'nome': peca_nome,
                'acabamento': acabamento,
                'data_transporte': data_transporte,
                'transportadora': transportadora,
                'placa_carreta': placa,
                'nota_fiscal': nota,
                'peca_id': peca_id,
                'tanque_id': tanque_id,
                'acoes': acoes,
            })

        records_total = len(rows)

        # Busca global (search[value])
        if search_value:
            search_lower = search_value.lower()
            rows = [
                r for r in rows
                if search_lower in (r['tanque'] or '').lower()
                or search_lower in (r['nome'] or '').lower()
                or search_lower in (r['acabamento'] or '').lower()
                or search_lower in (r['data_transporte'] or '').lower()
                or search_lower in (r['transportadora'] or '').lower()
                or search_lower in (r['placa_carreta'] or '').lower()
                or search_lower in (r['nota_fiscal'] or '').lower()
            ]
        records_filtered = len(rows)

        # Ordenação
        if 0 <= order_column_index < len(column_keys):
            key = column_keys[order_column_index]
            reverse = order_dir == 'desc'
            rows.sort(key=lambda r: (r[key] or '').lower() if isinstance(r[key], str) else (r[key] or ''), reverse=reverse)

        # Paginação
        data = rows[start:start + length]

        return jsonify({
            'draw': draw,
            'recordsTotal': records_total,
            'recordsFiltered': records_filtered,
            'data': data,
        })
    except Exception as e:
        return jsonify({
            'draw': request.args.get('draw', 1, type=int),
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e),
        }), 500


@acabamento_transporte_bp.route('/api/pecas', methods=['GET'])
def api_pecas():
    """Retorna peças filtradas por tanques e nome (AJAX)"""
    filtros = request.args.to_dict()
    result = get_pecas(filtros)
    return jsonify(result) 

@acabamento_transporte_bp.route('/api/transportadoras', methods=['POST'])
def api_transportadoras():
    """Retorna transportadoras filtradas por tanques (AJAX)"""
    tanque_ids = request.form.getlist('tanque_ids[]')
    pecas = TanquesPecas.query.all()
    transportadoras = []
    for p in pecas:
        qualidade = p.qualidade or '{}'
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        if 'transporte' in qualidade_dict and 'transportadora' in qualidade_dict['transporte']:
            transportadoras.append(qualidade_dict['transporte']['transportadora'])
    transportadoras = list(set(transportadoras))
    return jsonify(transportadoras)
@acabamento_transporte_bp.route('/api/tanques', methods=['GET'])
def api_tanques():
    """Retorna tanques filtradas por tanques (AJAX)"""
    tanques = Tanques.query.all()
    return jsonify([tanque.to_dict() for tanque in tanques])


@acabamento_transporte_bp.route('/api/notas-venda-matriz', methods=['GET'])
def api_notas_venda_matriz():
    """
    Busca notas fiscais de venda emitidas pela matriz (NFe tipo 0 ou 1, cnpj_emitente matriz).
    Parâmetro: q (texto para filtrar por número da NF ou chave). Se vazio, retorna as mais recentes.
    Opcional: tanque_id — restringe a NFs que possuem item com código igual ao item_nf do tanque.
    Opcional: peca_id — ao excluir NFs já usadas, ignora a própria peça (ex.: reabertura do modal).
    """
    q = (request.args.get('q') or '').strip()
    tanque_id = request.args.get('tanque_id', type=int)
    peca_id = request.args.get('peca_id', type=int)

    query = (
        NotaFiscal.query.filter(
            NotaFiscal.tipo.in_([0, 1]),
            NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ),
            NotaFiscal.status_processamento != 'cancelada',
        )
    )

    if tanque_id:
        tanque = Tanques.query.get(tanque_id)
        if not tanque or tanque.item_nf is None:
            return jsonify([])
        nf_ids_com_item = (
            db.session.query(NotaFiscalItem.nf_id)
            .filter(
                Tanques.sql_codigo_nf_igual_item_nf_valor(
                    NotaFiscalItem.codigo, tanque.item_nf
                )
            )
            .distinct()
        )
        query = query.filter(NotaFiscal.id.in_(nf_ids_com_item))

        usados = _numeros_nf_ja_usados_em_transporte(excluir_peca_id=peca_id)
        if usados:
            query = query.filter(~NotaFiscal.numero_nf.in_(list(usados)))

    if q:
        termo = f'%{q}%'
        query = query.filter(
            (NotaFiscal.numero_nf.ilike(termo)) | (NotaFiscal.chave_acesso.ilike(termo))
        )
    query = query.order_by(NotaFiscal.data_emissao.desc()).limit(30)
    notas = query.all()
    return jsonify([
        {
            'id': n.id,
            'numero_nf': str(n.numero_nf) if n.numero_nf is not None else '',
            'chave_acesso': n.chave_acesso or '',
            'valor_total': float(n.valor_total) if n.valor_total else 0,
            'data_emissao': n.data_emissao.strftime('%d/%m/%Y') if n.data_emissao else '',
            'nome_destinatario': (n.nome_destinatario or '')[:100],
        }
        for n in notas
    ])


@acabamento_transporte_bp.route('/api/cte-por-nota', methods=['GET'])
def api_cte_por_nota():
    """
    Busca CT-e (frete) vinculado à nota fiscal pela chave da NFe.
    Parâmetro: chave_nf (chave de 44 caracteres da NFe).
    """
    print(f'[_api_cte_por_nota] Request: {request.args}')
    chave_nf = (request.args.get('chave_nf') or '').strip()
    if not chave_nf or len(chave_nf) < 10:
        return jsonify([])
    ctes = (
        NotaFiscal.query.filter(
            NotaFiscal.tipo == 2,
            NotaFiscal.status_processamento != 'cancelada',
            func.json_unquote(func.json_extract(NotaFiscal.dados_adicionais, '$.chave_nf')) == chave_nf,
        )
        .order_by(NotaFiscal.data_emissao.desc())
        .all()
    )
    print(f'[_api_cte_por_nota] CT-es: {ctes}')
    resultado = []
    for cte in ctes:
        dados = {}
        if cte.dados_adicionais:
            try:
                dados = json.loads(cte.dados_adicionais) if isinstance(cte.dados_adicionais, str) else cte.dados_adicionais
            except Exception:
                pass
        resultado.append({
            'id': cte.id,
            'numero_nf': cte.numero_nf,
            'chave_acesso': cte.chave_acesso,
            'valor_total': float(cte.valor_total) if cte.valor_total else 0,
            'data_emissao': cte.data_emissao.strftime('%d/%m/%Y') if cte.data_emissao else '',
            'nome_emitente': cte.nome_emitente or '',
            'placa': (dados.get('placa') or '').strip(),
            'motorista': (dados.get('motorista') or '').strip(),
        })
    return jsonify(resultado)


@acabamento_transporte_bp.route('/api/transporte-por-nota', methods=['GET'])
def api_transporte_por_nota():
    """
    Busca dados de transporte já registrados para uma nota fiscal.
    Retorna placa, transportadora e data caso a nota já tenha sido usada.
    """
    nota = (request.args.get('nota_fiscal') or '').strip()
    if not nota:
        return jsonify(None)
    pecas = TanquesPecas.query.filter(
        TanquesPecas.qualidade.isnot(None)
    ).all()
    for peca in pecas:
        try:
            q = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else (peca.qualidade or {})
        except (json.JSONDecodeError, TypeError):
            continue
        transporte = q.get('transporte')
        if transporte and str(transporte.get('nota', '')) == nota:
            return jsonify({
                'placa_carreta': transporte.get('placa_carreta', ''),
                'transportadora': transporte.get('transportadora', ''),
                'data_transporte': transporte.get('data_transporte', ''),
            })
    return jsonify(None)


@acabamento_transporte_bp.route('/exportar_excel')
def exportar_excel():
    filtros = request.args.to_dict()
    data = get_pecas(filtros)
    data1 = []
    for p in data:
        qualidade = p.qualidade or '{}'
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        data1.append({
            'nome': p.nome,
            'concretagem': p.data_concretagem,
            'acabamento': p.acabamento,
            'transporte': p.transporte,
            'transportadora': p.transportadora,
            'placa_carreta': p.placa_carreta,
            'nota_fiscal': p.nota_fiscal,
            'data_entrega': p.data_entrega,
            'tanque': p.tanque.nome,
        })
    df = pd.DataFrame(data1)
    # Gerar arquivo Excel em memória
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Pecas')
    output.seek(0)
    return send_file(output, download_name='pecas_acabamento_transporte.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')