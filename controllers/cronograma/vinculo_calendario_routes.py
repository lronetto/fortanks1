"""Vínculo calendário × prefixo de índice por contrato (subárvore do cronograma)."""

from flask import jsonify, request
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from models.database import db
from models.contrato import Contrato
from models.cronograma import CronogramaCalendario, CronogramaVinculoCalendario

from utils.cronograma_indice import indice_para_sort_key, mensagem_indice_invalido, normalizar_indice

from . import cronograma_bp


@cronograma_bp.route('/api/calendarios-opcoes', methods=['GET'])
def api_calendarios_opcoes():
    rows = CronogramaCalendario.query.order_by(CronogramaCalendario.nome.asc()).all()
    return jsonify([{'id': r.id, 'nome': r.nome or f'#{r.id}'} for r in rows])


@cronograma_bp.route('/api/projeto/<int:contrato_id>/vinculos-calendario-datatables', methods=['GET'])
def api_projeto_vinculos_calendario_datatables(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '', type=str).strip()

    q = (
        CronogramaVinculoCalendario.query.options(joinedload(CronogramaVinculoCalendario.calendario))
        .filter(CronogramaVinculoCalendario.contrato_id == contrato_id)
    )
    if search_value:
        like = f'%{search_value}%'
        q = q.filter(
            or_(
                CronogramaVinculoCalendario.indice_prefixo.ilike(like),
                CronogramaVinculoCalendario.calendario.has(CronogramaCalendario.nome.ilike(like)),
            )
        )
    total = CronogramaVinculoCalendario.query.filter_by(contrato_id=contrato_id).count()
    filt = q.count()
    rows = (
        q.order_by(CronogramaVinculoCalendario.indice_sort.asc(), CronogramaVinculoCalendario.id.asc())
        .offset(start)
        .limit(length)
        .all()
    )
    data = []
    for r in rows:
        cal = r.calendario
        data.append({
            'id': r.id,
            'indice_prefixo': r.indice_prefixo or '',
            'calendario_id': r.calendario_id,
            'calendario_nome': (cal.nome if cal else '') or f'#{r.calendario_id}',
        })
    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filt,
        'data': data,
    })


@cronograma_bp.route('/projeto/<int:contrato_id>/vinculo-calendario/salvar', methods=['POST'])
def projeto_vinculo_calendario_salvar(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    vid = request.form.get('vinculo_id', type=int)
    raw_ind = request.form.get('indice_prefixo', '')
    ind = normalizar_indice(raw_ind)
    if not ind:
        return jsonify({'ok': False, 'error': mensagem_indice_invalido()}), 400
    cal_id = request.form.get('calendario_id', type=int)
    if not cal_id:
        return jsonify({'ok': False, 'error': 'Selecione o calendário.'}), 400
    if not CronogramaCalendario.query.get(cal_id):
        return jsonify({'ok': False, 'error': 'Calendário não encontrado.'}), 400

    sort_key = indice_para_sort_key(ind)
    if vid:
        v = CronogramaVinculoCalendario.query.filter_by(id=vid, contrato_id=contrato_id).first()
        if not v:
            return jsonify({'ok': False, 'error': 'Vínculo não encontrado.'}), 404
        other = CronogramaVinculoCalendario.query.filter(
            CronogramaVinculoCalendario.contrato_id == contrato_id,
            CronogramaVinculoCalendario.indice_prefixo == ind,
            CronogramaVinculoCalendario.id != vid,
        ).first()
        if other:
            return jsonify({'ok': False, 'error': 'Já existe vínculo para este índice.'}), 400
        v.indice_prefixo = ind
        v.indice_sort = sort_key
        v.calendario_id = cal_id
    else:
        ex = CronogramaVinculoCalendario.query.filter_by(
            contrato_id=contrato_id, indice_prefixo=ind,
        ).first()
        if ex:
            return jsonify({'ok': False, 'error': 'Já existe vínculo para este índice.'}), 400
        v = CronogramaVinculoCalendario(
            contrato_id=contrato_id,
            indice_prefixo=ind,
            indice_sort=sort_key,
            calendario_id=cal_id,
        )
        db.session.add(v)
    db.session.commit()
    return jsonify({'ok': True})


@cronograma_bp.route('/projeto/<int:contrato_id>/vinculo-calendario/excluir/<int:vinculo_id>', methods=['POST'])
def projeto_vinculo_calendario_excluir(contrato_id, vinculo_id):
    v = CronogramaVinculoCalendario.query.filter_by(id=vinculo_id, contrato_id=contrato_id).first_or_404()
    db.session.delete(v)
    db.session.commit()
    return jsonify({'ok': True})
