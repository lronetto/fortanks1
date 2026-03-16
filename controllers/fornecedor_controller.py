from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from sqlalchemy import or_

from models.database import db
from models.fornecedor import Fornecedor


fornecedor_bp = Blueprint('fornecedor', __name__)


@fornecedor_bp.route('/')
@login_required
def index():
    return render_template('fornecedores/index.html')


@fornecedor_bp.route('/datatables', methods=['POST'])
@login_required
def datatables():
    """
    Endpoint DataTables server-side para Fornecedores
    """
    draw = int(request.form.get('draw', 1))
    start = int(request.form.get('start', 0))
    length = int(request.form.get('length', 10))
    search_value = request.form.get('search[value]', '').strip()

    query = Fornecedor.query

    records_total = query.count()

    if search_value:
        query = query.filter(
            or_(
                Fornecedor.nome.like(f'%{search_value}%'),
                Fornecedor.cnpj.like(f'%{search_value}%'),
                Fornecedor.estado.like(f'%{search_value}%'),
            )
        )

    records_filtered = query.count()

    # Ordenação
    order_col_index = request.form.get('order[0][column]', '0')
    order_dir = request.form.get('order[0][dir]', 'asc')
    col_map = {
        '0': Fornecedor.nome,
        '1': Fornecedor.cnpj,
        '2': Fornecedor.estado,
        '3': Fornecedor.ativo,
    }
    order_col = col_map.get(str(order_col_index), Fornecedor.nome)
    if order_dir == 'desc':
        query = query.order_by(order_col.desc())
    else:
        query = query.order_by(order_col.asc())

    fornecedores = query.offset(start).limit(length).all()

    data = []
    for f in fornecedores:
        data.append({
            'id': f.id,
            'nome': f.nome,
            'cnpj': f.cnpj,
            'estado': f.estado or '',
            'ativo': bool(f.ativo),
        })

    return jsonify({
        'draw': draw,
        'recordsTotal': records_total,
        'recordsFiltered': records_filtered,
        'data': data,
    })


@fornecedor_bp.route('/get', methods=['GET'])
@login_required
def get():
    fornecedor_id = request.args.get('id', type=int)
    if not fornecedor_id:
        return jsonify({'error': 'ID não informado'}), 400

    f = Fornecedor.query.get_or_404(fornecedor_id)
    return jsonify(f.to_dict())


@fornecedor_bp.route('/salvar', methods=['POST'])
@login_required
def salvar():
    fornecedor_id = request.form.get('id', type=int)

    nome = (request.form.get('nome') or '').strip()
    cnpj = (request.form.get('cnpj') or '').strip()
    estado = (request.form.get('estado') or '').strip() or None
    contatos = request.form.get('contatos')
    enderecos = request.form.get('enderecos')
    ativo = True if request.form.get('ativo') in ('on', 'true', 'True', '1') else False

    if not nome or not cnpj:
        return jsonify({'success': False, 'message': 'Nome e CNPJ são obrigatórios.'}), 400

    try:
        # Verificar duplicidade de CNPJ sem forçar autoflush
        with db.session.no_autoflush:
            q_dup = Fornecedor.query.filter(Fornecedor.cnpj == cnpj)
            if fornecedor_id:
                q_dup = q_dup.filter(Fornecedor.id != fornecedor_id)
            if q_dup.first():
                return jsonify({'success': False, 'message': 'Já existe um fornecedor com este CNPJ.'}), 400

        if fornecedor_id:
            f = Fornecedor.query.get_or_404(fornecedor_id)
        else:
            f = Fornecedor()
            db.session.add(f)

        f.nome = nome
        f.cnpj = cnpj
        f.estado = estado
        f.contatos = contatos
        f.enderecos = enderecos
        f.ativo = ativo

        db.session.commit()
        return jsonify({'success': True, 'id': f.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@fornecedor_bp.route('/excluir', methods=['POST'])
@login_required
def excluir():
    data = request.get_json(silent=True) or {}
    fornecedor_id = data.get('id')
    if not fornecedor_id:
        return jsonify({'success': False, 'message': 'ID não informado.'}), 400

    f = Fornecedor.query.get_or_404(int(fornecedor_id))
    try:
        db.session.delete(f)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

