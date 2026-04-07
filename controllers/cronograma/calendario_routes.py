"""Cadastro de calendários (dias úteis na semana + feriados por calendário)."""

from flask import flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_

from models.database import db
from models.cronograma import CronogramaCalendario, CronogramaCalendarioFeriado
from utils.feriados_brasil_api import (
    UFS_BR,
    consolidar_feriados_para_importacao,
    parse_codigo_ibge_municipio,
)

from . import cronograma_bp, parse_date


def _resumo_dias_uteis(c: CronogramaCalendario) -> str:
    nomes = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
    flags = [c.seg_util, c.ter_util, c.qua_util, c.qui_util, c.sex_util, c.sab_util, c.dom_util]
    partes = [nomes[i] for i, u in enumerate(flags) if u]
    return ', '.join(partes) if partes else '—'


def _dia_util(name: str) -> bool:
    """Checkbox envia '1' quando marcado; ausente = falso."""
    return request.form.get(name) == '1'


@cronograma_bp.route('/calendario')
def calendario():
    return render_template('cronograma/calendario.html')


@cronograma_bp.route('/api/calendario-datatables', methods=['GET'])
def api_calendario_datatables():
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '', type=str).strip()
    q = CronogramaCalendario.query
    if search_value:
        like = f'%{search_value}%'
        q = q.filter(
            or_(
                CronogramaCalendario.nome.ilike(like),
                CronogramaCalendario.observacao.ilike(like),
            )
        )
    total = CronogramaCalendario.query.count()
    filt = q.count()
    rows = q.order_by(CronogramaCalendario.nome.asc()).offset(start).limit(length).all()
    data = []
    for r in rows:
        nfer = CronogramaCalendarioFeriado.query.filter(
            CronogramaCalendarioFeriado.calendario_id == r.id
        ).count()
        data.append({
            'id': r.id,
            'nome': r.nome,
            'dias_uteis': _resumo_dias_uteis(r),
            'n_feriados': nfer,
            'observacao': r.observacao or '',
            'seg_util': r.seg_util,
            'ter_util': r.ter_util,
            'qua_util': r.qua_util,
            'qui_util': r.qui_util,
            'sex_util': r.sex_util,
            'sab_util': r.sab_util,
            'dom_util': r.dom_util,
        })
    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filt,
        'data': data,
    })


@cronograma_bp.route('/calendario/novo', methods=['POST'])
def calendario_novo():
    nome = (request.form.get('nome') or '').strip()
    if not nome:
        flash('Informe o nome do calendário.', 'warning')
        return redirect(url_for('cronograma.calendario'))
    c = CronogramaCalendario(
        nome=nome[:160],
        observacao=(request.form.get('observacao') or '').strip() or None,
        seg_util=_dia_util('seg_util'),
        ter_util=_dia_util('ter_util'),
        qua_util=_dia_util('qua_util'),
        qui_util=_dia_util('qui_util'),
        sex_util=_dia_util('sex_util'),
        sab_util=_dia_util('sab_util'),
        dom_util=_dia_util('dom_util'),
    )
    db.session.add(c)
    db.session.commit()
    flash('Calendário cadastrado.', 'success')
    return redirect(url_for('cronograma.calendario'))


@cronograma_bp.route('/calendario/editar/<int:calendario_id>', methods=['POST'])
def calendario_editar(calendario_id):
    c = CronogramaCalendario.query.get_or_404(calendario_id)
    nome = (request.form.get('nome') or '').strip()
    if nome:
        c.nome = nome[:160]
    c.observacao = (request.form.get('observacao') or '').strip() or None
    c.seg_util = _dia_util('seg_util')
    c.ter_util = _dia_util('ter_util')
    c.qua_util = _dia_util('qua_util')
    c.qui_util = _dia_util('qui_util')
    c.sex_util = _dia_util('sex_util')
    c.sab_util = _dia_util('sab_util')
    c.dom_util = _dia_util('dom_util')
    db.session.commit()
    flash('Calendário atualizado.', 'success')
    return redirect(url_for('cronograma.calendario'))


@cronograma_bp.route('/calendario/excluir/<int:calendario_id>', methods=['POST'])
def calendario_excluir(calendario_id):
    c = CronogramaCalendario.query.get_or_404(calendario_id)
    db.session.delete(c)
    db.session.commit()
    flash('Calendário removido.', 'success')
    return redirect(url_for('cronograma.calendario'))


@cronograma_bp.route('/api/calendario/<int:calendario_id>/feriados-datatables', methods=['GET'])
def api_calendario_feriados_datatables(calendario_id):
    CronogramaCalendario.query.get_or_404(calendario_id)
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '', type=str).strip()
    q = CronogramaCalendarioFeriado.query.filter(
        CronogramaCalendarioFeriado.calendario_id == calendario_id
    )
    if search_value:
        like = f'%{search_value}%'
        q = q.filter(
            or_(
                CronogramaCalendarioFeriado.nome.ilike(like),
                CronogramaCalendarioFeriado.observacao.ilike(like),
            )
        )
    total = CronogramaCalendarioFeriado.query.filter(
        CronogramaCalendarioFeriado.calendario_id == calendario_id
    ).count()
    filt = q.count()
    rows = q.order_by(CronogramaCalendarioFeriado.data.desc()).offset(start).limit(length).all()
    data = []
    for r in rows:
        data.append({
            'id': r.id,
            'data': r.data.strftime('%d/%m/%Y') if r.data else '',
            'data_iso': r.data.isoformat() if r.data else '',
            'nome': r.nome,
            'observacao': r.observacao or '',
        })
    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filt,
        'data': data,
    })


@cronograma_bp.route('/calendario/<int:calendario_id>/feriado/novo', methods=['POST'])
def calendario_feriado_novo(calendario_id):
    CronogramaCalendario.query.get_or_404(calendario_id)
    d = parse_date(request.form.get('data'))
    if not d:
        flash('Informe a data do feriado.', 'warning')
        return redirect(url_for('cronograma.calendario'))
    nome = (request.form.get('nome') or '').strip() or 'Feriado'
    ex = CronogramaCalendarioFeriado.query.filter_by(calendario_id=calendario_id, data=d).first()
    if ex:
        flash('Já existe feriado nesta data para este calendário.', 'warning')
        return redirect(url_for('cronograma.calendario'))
    f = CronogramaCalendarioFeriado(
        calendario_id=calendario_id,
        data=d,
        nome=nome[:200],
        observacao=(request.form.get('observacao') or '').strip() or None,
    )
    db.session.add(f)
    db.session.commit()
    flash('Feriado cadastrado.', 'success')
    return redirect(url_for('cronograma.calendario'))


@cronograma_bp.route('/calendario/<int:calendario_id>/feriado/editar/<int:feriado_id>', methods=['POST'])
def calendario_feriado_editar(calendario_id, feriado_id):
    f = CronogramaCalendarioFeriado.query.filter_by(
        id=feriado_id, calendario_id=calendario_id
    ).first_or_404()
    d = parse_date(request.form.get('data'))
    if d and d != f.data:
        dup = CronogramaCalendarioFeriado.query.filter_by(
            calendario_id=calendario_id, data=d
        ).filter(CronogramaCalendarioFeriado.id != feriado_id).first()
        if dup:
            flash('Já existe feriado nesta data para este calendário.', 'warning')
            return redirect(url_for('cronograma.calendario'))
        f.data = d
    f.nome = (request.form.get('nome') or '').strip() or f.nome
    f.observacao = (request.form.get('observacao') or '').strip() or None
    db.session.commit()
    flash('Feriado atualizado.', 'success')
    return redirect(url_for('cronograma.calendario'))


@cronograma_bp.route('/calendario/<int:calendario_id>/feriado/excluir/<int:feriado_id>', methods=['POST'])
def calendario_feriado_excluir(calendario_id, feriado_id):
    f = CronogramaCalendarioFeriado.query.filter_by(
        id=feriado_id, calendario_id=calendario_id
    ).first_or_404()
    db.session.delete(f)
    db.session.commit()
    flash('Feriado removido.', 'success')
    return redirect(url_for('cronograma.calendario'))


@cronograma_bp.route('/api/calendario/<int:calendario_id>/importar-feriados-api', methods=['POST'])
def api_calendario_importar_feriados_api(calendario_id):
    """Importa feriados nacionais, estaduais e/ou municipais (Brasil API + dataset feriados-brasil)."""
    CronogramaCalendario.query.get_or_404(calendario_id)
    if not request.is_json:
        return jsonify({'ok': False, 'error': 'Envie JSON (Content-Type application/json).'}), 400
    payload = request.get_json(silent=True) or {}
    token = payload.get('csrf_token')
    if not token:
        return jsonify({'ok': False, 'error': 'Token CSRF ausente.'}), 400
    try:
        from flask_wtf.csrf import validate_csrf
        validate_csrf(token)
    except Exception:
        return jsonify({'ok': False, 'error': 'Sessão expirou ou token CSRF inválido. Recarregue a página.'}), 403

    ano = payload.get('ano')
    try:
        ano = int(ano)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Ano inválido.'}), 400
    if ano < 1900 or ano > 2199:
        return jsonify({'ok': False, 'error': 'Ano deve estar entre 1900 e 2199.'}), 400

    incluir_nacionais = bool(payload.get('incluir_nacionais', True))
    incluir_estaduais = bool(payload.get('incluir_estaduais', False))
    incluir_municipais = bool(payload.get('incluir_municipais', False))
    if not incluir_nacionais and not incluir_estaduais and not incluir_municipais:
        return jsonify({
            'ok': False,
            'error': 'Marque ao menos uma opção: nacionais, estaduais ou municipais.',
        }), 400

    uf = (payload.get('uf') or '').strip().upper()
    if incluir_estaduais:
        if len(uf) != 2 or uf not in UFS_BR:
            return jsonify({'ok': False, 'error': 'Para feriados estaduais informe uma UF válida.'}), 400

    cod_ibge = parse_codigo_ibge_municipio(payload.get('codigo_ibge'))
    if incluir_municipais and cod_ibge is None:
        return jsonify({
            'ok': False,
            'error': 'Para feriados municipais informe o código IBGE do município (7 dígitos).',
        }), 400

    lista, msg_erro = consolidar_feriados_para_importacao(
        ano,
        uf if incluir_estaduais else None,
        incluir_nacionais,
        incluir_estaduais,
        incluir_municipais=incluir_municipais,
        codigo_ibge=cod_ibge if incluir_municipais else None,
    )
    if not lista and msg_erro:
        return jsonify({'ok': False, 'error': msg_erro}), 422
    if not lista:
        return jsonify({
            'ok': True,
            'inseridos': 0,
            'ignorados': 0,
            'aviso': msg_erro or 'Nenhum feriado retornado para os filtros informados.',
        })

    inseridos = 0
    ignorados = 0
    for item in lista:
        d = item['data']
        ex = CronogramaCalendarioFeriado.query.filter_by(
            calendario_id=calendario_id, data=d
        ).first()
        if ex:
            ignorados += 1
            continue
        nome = (item.get('nome') or 'Feriado')[:200]
        obs = (item.get('observacao') or '').strip() or None
        db.session.add(CronogramaCalendarioFeriado(
            calendario_id=calendario_id,
            data=d,
            nome=nome,
            observacao=obs,
        ))
        inseridos += 1
    db.session.commit()

    aviso = None
    if msg_erro:
        aviso = 'Aviso: ' + msg_erro

    return jsonify({
        'ok': True,
        'inseridos': inseridos,
        'ignorados': ignorados,
        'aviso': aviso,
    })
