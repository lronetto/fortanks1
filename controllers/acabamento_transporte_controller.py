from flask import Blueprint, render_template, request, jsonify
from models import Peca, Tanque, db
from flask_wtf.csrf import generate_csrf
from datetime import datetime
import json
from models.contrato import Contrato
from models.centro_custo import CentroCusto

acabamento_transporte_bp  = Blueprint('acabamento_transporte', __name__)

@acabamento_transporte_bp.route('/')
def index():
    filtro = request.args.get('filtro', 'todos')
    page = int(request.args.get('page', 1))
    per_page = 20
    pecas_query = Peca.query.join(Tanque).filter(Peca.qualidade.isnot(None))
    tanques = Tanque.query.order_by(Tanque.nome).all()
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
    # Aplicar filtro
    if filtro == 'acabadas':
        pecas = [p for p in pecas if p.acabamento]
        pecas.sort(key=lambda x: x.acabamento, reverse=True)
    elif filtro == 'transportadas':
        pecas = [p for p in pecas if p.transporte]
        pecas.sort(key=lambda x: x.transporte, reverse=True)
    elif filtro == 'acabada_nao_transportada':
        pecas = [p for p in pecas if p.acabamento and not p.transporte]
        pecas.sort(key=lambda x: x.transporte, reverse=True)
    # Paginação
    total = len(pecas)
    start = (page - 1) * per_page
    end = start + per_page
    pecas_paginadas = pecas[start:end]
    total_pages = (total + per_page - 1) // per_page
    return render_template('acabamento_transporte/index.html', 
                           pecas=pecas_paginadas,
                           tanques=tanques,
                           now=datetime.now().strftime('%Y-%m-%d'),
                           filtro=filtro,
                           page=page,
                           total_pages=total_pages)

@acabamento_transporte_bp.route('/acabamento', methods=['GET', 'POST'])
def acabamento():
    """Registra acabamento de uma ou mais peças"""
    if request.method == 'POST':
        tanque_id = request.form.get('tanque_id')
        peca_ids = request.form.getlist('peca_ids[]')
        data_acabamento = request.form.get('data_acabamento')
        if not data_acabamento:
            data_acabamento = datetime.now().strftime('%Y-%m-%d')
        try:
            pecas = Peca.query.filter(Peca.id.in_(peca_ids), Peca.tanque_id == tanque_id).all()
            if not pecas:
                return jsonify({'success': False, 'message': 'Nenhuma peça encontrada'}), 404
            for peca in pecas:
                qualidade = peca.qualidade or '{}'
                qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
                qualidade_dict['acabamento'] = data_acabamento
                peca.qualidade = json.dumps(qualidade_dict)
                peca.save()
            return jsonify({'success': True, 'pecas_afetadas': [p.id for p in pecas]})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    # GET: retorna o modal
    tanques = Tanque.query.order_by(Tanque.nome).all()
    csrf_token = generate_csrf()
    return render_template('acabamento_transporte/modais/acabamento.html', 
                           tanques=tanques, 
                           csrf_token=csrf_token,
                           now=datetime.now().strftime('%Y-%m-%d'))

@acabamento_transporte_bp.route('/transporte', methods=['GET', 'POST'])
def transporte():
    """Registra transporte de peças"""
    if request.method == 'POST':
        tanque_ids = request.form.getlist('tanque_ids')
        peca_ids = request.form.get('peca_ids', '').split(',')
        placas = request.form.getlist('placas')
        nota_fiscal = request.form.get('nota_fiscal')
        placa_carreta = request.form.get('placa_carreta')
        data_transporte = request.form.get('data_transporte')
        transportadora = request.form.get('transportadora')
        if not data_transporte:
            data_transporte = datetime.now().strftime('%Y-%m-%d')
        try:
            pecas = Peca.query.filter(Peca.id.in_(peca_ids)).all()
            for peca in pecas:
                qualidade = peca.qualidade or '{}'
                qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
                qualidade_dict['transporte'] = {
                    'data_transporte': data_transporte,
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
    return render_template('acabamento_transporte/modais/transporte.html', 
                           tanques=tanques, 
                           csrf_token=csrf_token,
                           now=datetime.now().strftime('%Y-%m-%d'))

@acabamento_transporte_bp.route('/api/pecas', methods=['GET'])
def api_pecas():
    """Retorna peças filtradas por tanques e nome (AJAX)"""
    tanque_ids = request.args.getlist('tanque_ids[]')
    nome = request.args.get('nome', '').strip()
    apenas_concretadas = request.args.get('apenas_concretadas', '0') == '1'
    apenas_acabadas = request.args.get('apenas_acabadas', '0') == '1'
    nao_acabadas = request.args.get('nao_acabadas', '0') == '1'
    query = Peca.query
    if tanque_ids:
        query = query.filter(Peca.tanque_id.in_(tanque_ids))
    if nome:
        query = query.filter(Peca.nome.ilike(f'%{nome}%'))
    if apenas_concretadas:
        query = query.filter(Peca.data_concretagem.isnot(None))
    pecas = query.order_by(Peca.tanque_id, Peca.numero_sequencial).all()
    pecas1 = pecas
    print('tamanho da lista', len(pecas1))
    if nao_acabadas:
        print('nao_acabadas')
        pecas = []
        for p in pecas1:
            qualidade = p.qualidade or '{}'
            qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
            if 'acabamento' in qualidade_dict and qualidade_dict['acabamento'] is None:
                pecas.append(p)
    if apenas_acabadas:
        print('apenas_acabadas')
        pecas = []
        for p in pecas1:
            qualidade = p.qualidade or '{}'
            qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
            if 'acabamento' in qualidade_dict and 'data_transporte' in qualidade_dict['transporte']:
                pecas.append(p)
        #pecas = [p for p in pecas if p.qualidade and 'acabamento' in (json.loads(p.qualidade) and 'data_acabamento' in json.loads(p.qualidade)['transporte'] if isinstance(p.qualidade, str) else p.qualidade)]
    result = [
        {
            'id': p.id,
            'nome': p.nome,
            'numero_sequencial': p.numero_sequencial,
            'tanque_id': p.tanque_id,
            'tanque_nome': p.tanque.nome
        }
        for p in pecas
    ]
    return jsonify(result) 

@acabamento_transporte_bp.route('/api/transportadoras', methods=['POST'])
def api_transportadoras():
    """Retorna transportadoras filtradas por tanques (AJAX)"""
    tanque_ids = request.form.getlist('tanque_ids[]')
    pecas = Peca.query.all()
    transportadoras = []
    for p in pecas:
        qualidade = p.qualidade or '{}'
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        if 'transporte' in qualidade_dict and 'transportadora' in qualidade_dict['transporte']:
            transportadoras.append(qualidade_dict['transporte']['transportadora'])
    transportadoras = list(set(transportadoras))
    return jsonify(transportadoras)