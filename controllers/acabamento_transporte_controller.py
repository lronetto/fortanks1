from flask import Blueprint, render_template, request, jsonify, send_file
from models import Peca, Tanque, db
from flask_wtf.csrf import generate_csrf
from datetime import datetime
import json
from models.contrato import Contrato
from models.centro_custo import CentroCusto
import pandas as pd

acabamento_transporte_bp  = Blueprint('acabamento_transporte', __name__)

def get_pecas(filtros):
    filtro = filtros.get('filtro', 'todos')
    page = int(filtros.get('page', 1))
    per_page = 20
    nome_peca = filtros.get('nome_peca', '').strip()
    pecas_query = Peca.query.join(Tanque)
    if nome_peca:
        pecas_query = pecas_query.filter(Peca.nome.ilike(f'%{nome_peca}%'))
    pecas_query = pecas_query.all()
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
    return pecas
@acabamento_transporte_bp.route('/')
def index():
    filtros = request.args.to_dict()
    pecas = get_pecas(filtros)
    page = int(request.args.get('page', 1))
    per_page = 20
    tanques = Tanque.query.order_by(Tanque.nome).all()
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
                           filtro=filtros,
                           page=page,
                           total_pages=total_pages,
                           nome_peca=filtros.get('nome_peca', ''))

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
    filtros = request.args.to_dict()
    result = get_pecas(filtros)
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
@acabamento_transporte_bp.route('/api/tanques', methods=['GET'])
def api_tanques():
    """Retorna tanques filtradas por tanques (AJAX)"""
    tanques = Tanque.query.all()
    return jsonify([tanque.to_dict() for tanque in tanques])

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