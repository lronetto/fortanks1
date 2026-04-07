import re
from decimal import Decimal

from flask import request, jsonify
from sqlalchemy import or_
from sqlalchemy.orm import aliased

from models.database import db
from models.contrato import Contrato
from models.tanque import Tanques
from models.cronograma import CronogramaItem

from utils.cronograma_indice import (
    indice_para_sort_key,
    mensagem_indice_invalido,
    normalizar_indice,
)

from . import cronograma_bp, parse_date, parse_peso


def _sugerir_indice_raiz(contrato_id):
    """Próximo número de topo (1, 2, 3…) com base nos itens existentes."""
    rows = CronogramaItem.query.filter_by(contrato_id=contrato_id).all()
    m = 0
    for r in rows:
        ind = (r.indice or '').strip()
        if not ind:
            continue
        if not re.match(r'^\d+(\.\d+)*$', ind):
            continue
        first = ind.split('.')[0]
        if first.isdigit():
            m = max(m, int(first))
    return str(m + 1)


def _sucessores_transitivos(contrato_id, root_id):
    """IDs de itens que dependem (direta ou indiretamente) de root_id como predecessor."""
    if root_id is None:
        return set()
    out = set()
    stack = [root_id]
    while stack:
        x = stack.pop()
        for ch in CronogramaItem.query.filter_by(contrato_id=contrato_id, predecessor_id=x).all():
            if ch.id not in out:
                out.add(ch.id)
                stack.append(ch.id)
    return out


def _predecessor_criaria_ciclo(contrato_id, item_id, pred_id):
    """True se apontar item_id -> pred_id fecharia um ciclo na rede de predecessors."""
    if not pred_id:
        return False
    if item_id and pred_id == item_id:
        return True
    if item_id and pred_id in _sucessores_transitivos(contrato_id, item_id):
        return True
    return False


@cronograma_bp.route('/api/projeto/<int:contrato_id>/tanques-para-itens', methods=['GET'])
def api_projeto_tanques_para_itens(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    tanques = Tanques.query.filter(Tanques.contrato_id == contrato_id).order_by(Tanques.nome.asc()).all()
    return jsonify([{'id': t.id, 'un': t.un, 'nome': t.nome} for t in tanques])


@cronograma_bp.route('/api/projeto/<int:contrato_id>/itens-para-predecessor', methods=['GET'])
def api_projeto_itens_para_predecessor(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    exceto = request.args.get('exceto_id', type=int)
    q = CronogramaItem.query.filter_by(contrato_id=contrato_id).order_by(
        CronogramaItem.indice_sort.asc(), CronogramaItem.id.asc()
    )
    if exceto:
        q = q.filter(CronogramaItem.id != exceto)
    rows = q.all()
    return jsonify(
        [{'id': r.id, 'indice': r.indice or '', 'nome': r.nome or ''} for r in rows]
    )


@cronograma_bp.route('/api/projeto/<int:contrato_id>/itens-datatables', methods=['GET'])
def api_projeto_itens_datatables(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 50, type=int)
    search_value = request.args.get('search[value]', '', type=str).strip()

    Pred = aliased(CronogramaItem)
    q = (
        CronogramaItem.query.filter(CronogramaItem.contrato_id == contrato_id)
        .outerjoin(Tanques, CronogramaItem.tanque_id == Tanques.id)
        .outerjoin(Pred, CronogramaItem.predecessor_id == Pred.id)
    )
    if search_value:
        like = f'%{search_value}%'
        q = q.filter(
            or_(
                CronogramaItem.nome.ilike(like),
                CronogramaItem.indice.ilike(like),
                Tanques.nome.ilike(like),
                Tanques.un.ilike(like),
                Pred.indice.ilike(like),
                Pred.nome.ilike(like),
            )
        )
    total = CronogramaItem.query.filter_by(contrato_id=contrato_id).count()
    filt = q.count()
    order_column_index = int(request.args.get('order[0][column]', 0))
    order_dir = request.args.get('order[0][dir]', 'asc')
    order_map = {
        0: CronogramaItem.indice_sort,
        1: CronogramaItem.nome,
        2: CronogramaItem.peso,
        3: Pred.indice_sort,
        4: Tanques.nome,
        5: CronogramaItem.data_inicio,
    }
    order_col = order_map.get(order_column_index, CronogramaItem.indice_sort)
    if order_dir == 'desc':
        q = q.order_by(order_col.desc())
    else:
        q = q.order_by(order_col.asc())
    rows = q.offset(start).limit(length).all()
    data = []
    for it in rows:
        tanque_txt = '—'
        if it.tanque_id and it.tanque:
            tanque_txt = f'{it.tanque.un} — {it.tanque.nome}'
        pred_txt = '—'
        if it.predecessor_id and it.predecessor:
            pred_txt = f'{it.predecessor.indice} — {it.predecessor.nome}'
        peso_val = float(it.peso) if it.peso is not None else 0.0
        di = it.data_inicio.isoformat() if it.data_inicio else ''
        data.append({
            'item_id': it.id,
            'indice': it.indice or '',
            'nome': it.nome,
            'peso': peso_val,
            'predecessor_id': it.predecessor_id or '',
            'predecessor_label': pred_txt,
            'tanque_id': it.tanque_id or '',
            'tanque_label': tanque_txt,
            'data_inicio': di,
        })
    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filt,
        'data': data,
    })


@cronograma_bp.route('/projeto/<int:contrato_id>/item/salvar', methods=['POST'])
def projeto_item_salvar(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    item_id = request.form.get('item_id', type=int)
    nome = (request.form.get('nome') or '').strip()
    if not nome:
        return jsonify({'ok': False, 'message': 'Informe o nome do item.'}), 400

    indice_raw = request.form.get('indice')
    if item_id:
        norm = normalizar_indice(indice_raw)
        if not norm:
            return jsonify({'ok': False, 'message': mensagem_indice_invalido()}), 400
    else:
        if indice_raw is None or str(indice_raw).strip() == '':
            norm = _sugerir_indice_raiz(contrato_id)
        else:
            norm = normalizar_indice(indice_raw)
            if not norm:
                return jsonify({'ok': False, 'message': mensagem_indice_invalido()}), 400

    peso = parse_peso(request.form.get('peso'))

    tanque_id_raw = request.form.get('tanque_id')
    tanque_id = None
    if tanque_id_raw not in (None, ''):
        try:
            tanque_id = int(tanque_id_raw)
        except ValueError:
            return jsonify({'ok': False, 'message': 'Tanque inválido.'}), 400
        t = Tanques.query.filter_by(id=tanque_id, contrato_id=contrato_id).first()
        if not t:
            return jsonify({'ok': False, 'message': 'O tanque deve pertencer ao projeto.'}), 400

    sort_key = indice_para_sort_key(norm)
    if not sort_key:
        return jsonify({'ok': False, 'message': mensagem_indice_invalido()}), 400

    pred_raw = request.form.get('predecessor_id')
    predecessor_id = None
    if pred_raw not in (None, ''):
        try:
            predecessor_id = int(pred_raw)
        except ValueError:
            return jsonify({'ok': False, 'message': 'Predecessor inválido.'}), 400
        pred = CronogramaItem.query.filter_by(id=predecessor_id, contrato_id=contrato_id).first()
        if not pred:
            return jsonify({'ok': False, 'message': 'O predecessor deve ser um item deste projeto.'}), 400
        if item_id and predecessor_id == item_id:
            return jsonify({'ok': False, 'message': 'Um item não pode ser predecessor de si mesmo.'}), 400
        if _predecessor_criaria_ciclo(contrato_id, item_id, predecessor_id):
            return jsonify({
                'ok': False,
                'message': 'Predecessor inválido: geraria dependência circular (rede de sucessores).',
            }), 400

    data_inicio = parse_date(request.form.get('data_inicio'))

    if item_id:
        item = CronogramaItem.query.filter_by(id=item_id, contrato_id=contrato_id).first()
        if not item:
            return jsonify({'ok': False, 'message': 'Item não encontrado.'}), 404
    else:
        item = CronogramaItem(contrato_id=contrato_id)
        db.session.add(item)

    item.nome = nome
    item.indice = norm
    item.indice_sort = sort_key
    item.peso = Decimal(str(peso))
    item.tanque_id = tanque_id
    item.predecessor_id = predecessor_id
    item.data_inicio = data_inicio
    db.session.commit()
    return jsonify({'ok': True})


@cronograma_bp.route('/projeto/<int:contrato_id>/item/duplicar/<int:item_id>', methods=['POST'])
def projeto_item_duplicar(contrato_id, item_id):
    Contrato.query.get_or_404(contrato_id)
    orig = CronogramaItem.query.filter_by(id=item_id, contrato_id=contrato_id).first()
    if not orig:
        return jsonify({'ok': False, 'message': 'Item não encontrado.'}), 404

    norm = _sugerir_indice_raiz(contrato_id)
    sk = indice_para_sort_key(norm)
    if not sk:
        return jsonify({'ok': False, 'message': 'Não foi possível gerar índice para a cópia.'}), 400

    nome_base = (orig.nome or '').strip() or 'Item'
    novo_nome = f'{nome_base} (cópia)'

    novo = CronogramaItem(
        contrato_id=contrato_id,
        nome=novo_nome,
        indice=norm,
        indice_sort=sk,
        peso=orig.peso,
        tanque_id=orig.tanque_id,
        predecessor_id=orig.predecessor_id,
        data_inicio=orig.data_inicio,
    )
    db.session.add(novo)
    db.session.commit()
    return jsonify({'ok': True, 'id': novo.id})


@cronograma_bp.route('/projeto/<int:contrato_id>/item/excluir/<int:item_id>', methods=['POST'])
def projeto_item_excluir(contrato_id, item_id):
    Contrato.query.get_or_404(contrato_id)
    item = CronogramaItem.query.filter_by(id=item_id, contrato_id=contrato_id).first()
    if not item:
        return jsonify({'ok': False, 'message': 'Item não encontrado.'}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({'ok': True})
