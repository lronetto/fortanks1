from datetime import date, datetime
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import current_user
from sqlalchemy import or_

from models.database import db
from models.contrato import Contrato
from models.tanque import Tanques
from models.centro_custo import CentroCusto
from models.cronograma import (
    CronogramaTanque,
    CronogramaLinhaBase,
    CronogramaLinhaBaseTanque,
)

from . import cronograma_bp, parse_date

from utils.cronograma_calculo_pecas import calcular_projeto_pecas, distribuir_dias_por_semana


@cronograma_bp.route('/')
def index():
    return render_template('cronograma/index.html')


@cronograma_bp.route('/api/contratos-datatables', methods=['GET'])
def api_contratos_datatables():
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '', type=str).strip()
    order_column_index = int(request.args.get('order[0][column]', 0))
    order_dir = request.args.get('order[0][dir]', 'asc')

    column_mapping = {
        0: Contrato.id,
        1: Contrato.nome,
        2: CentroCusto.codigo,
        3: Contrato.cidade,
    }
    query = Contrato.query.outerjoin(CentroCusto, Contrato.centro_custo_id == CentroCusto.id).filter(
        Contrato.ativo.is_(True)
    )
    if search_value:
        like = f'%{search_value}%'
        conds = [
            Contrato.nome.ilike(like),
            Contrato.cidade.ilike(like),
            Contrato.estado.ilike(like),
        ]
        if search_value.isdigit():
            conds.append(Contrato.id == int(search_value))
        query = query.filter(or_(*conds))
    total_records = Contrato.query.filter(Contrato.ativo.is_(True)).count()
    records_filtered = query.count()
    order_column = column_mapping.get(order_column_index, Contrato.nome)
    if order_dir == 'desc':
        query = query.order_by(order_column.desc())
    else:
        query = query.order_by(order_column.asc())
    contratos = query.offset(start).limit(length).all()

    data = []
    for c in contratos:
        cc = f'{c.centro_custo.codigo} — {c.centro_custo.nome}' if c.centro_custo else '—'
        local = f'{c.cidade or ""}/{c.estado or ""}'.strip('/') or '—'
        url_proj = url_for('cronograma.projeto', contrato_id=c.id)
        acoes = (
            f'<a href="{url_proj}" class="btn btn-sm btn-primary">'
            f'<i class="fas fa-calendar-week"></i> Cronograma</a>'
        )
        data.append({
            'id': c.id,
            'nome': c.nome,
            'centro_custo': cc,
            'local': local,
            'acoes': acoes,
        })
    return jsonify({
        'draw': draw,
        'recordsTotal': total_records,
        'recordsFiltered': records_filtered,
        'data': data,
    })


@cronograma_bp.route('/projeto/<int:contrato_id>')
def projeto(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    if not contrato.ativo:
        flash('Contrato inativo.', 'warning')
        return redirect(url_for('cronograma.index'))
    return render_template('cronograma/projeto.html', contrato=contrato)


@cronograma_bp.route('/projeto/<int:contrato_id>/calculo-pecas')
def projeto_calculo_pecas(contrato_id):
    """Cálculo de dias por tipo de peça (índices no tanque) e distribuição por semana."""
    contrato = Contrato.query.get_or_404(contrato_id)
    if not contrato.ativo:
        flash('Contrato inativo.', 'warning')
        return redirect(url_for('cronograma.index'))

    data_inicio = parse_date(request.args.get('data_inicio'))
    if not data_inicio:
        data_inicio = date.today()

    linhas, avisos, total_dias = calcular_projeto_pecas(contrato_id)
    semanas = distribuir_dias_por_semana(total_dias, data_inicio)
    acum = 0.0
    semanas_com_acumulado = []
    for s in semanas:
        acum += float(s['dias'])
        row = dict(s)
        row['acumulado'] = round(acum, 4)
        semanas_com_acumulado.append(row)

    resumo_tanques = []
    for tid in sorted({r['tanque_id'] for r in linhas}):
        sub = [r for r in linhas if r['tanque_id'] == tid]
        resumo_tanques.append({
            'tanque_id': tid,
            'tanque_nome': sub[0]['tanque_nome'],
            'dias': sum(g['dias_total'] for g in sub),
        })

    return render_template(
        'cronograma/calculo_pecas.html',
        contrato=contrato,
        linhas=linhas,
        avisos=avisos,
        total_dias=total_dias,
        semanas=semanas_com_acumulado,
        data_inicio=data_inicio,
        resumo_tanques=resumo_tanques,
    )


@cronograma_bp.route('/api/projeto/<int:contrato_id>/tanques-datatables', methods=['GET'])
def api_projeto_tanques_datatables(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 50, type=int)
    search_value = request.args.get('search[value]', '', type=str).strip()

    q = Tanques.query.filter(Tanques.contrato_id == contrato_id)
    if search_value:
        like = f'%{search_value}%'
        q = q.filter(or_(Tanques.nome.ilike(like), Tanques.un.ilike(like)))
    total = Tanques.query.filter(Tanques.contrato_id == contrato_id).count()
    filt = q.count()
    tanques = q.order_by(Tanques.nome.asc()).offset(start).limit(length).all()
    ct_map = {
        r.tanque_id: r
        for r in CronogramaTanque.query.filter(CronogramaTanque.contrato_id == contrato_id).all()
    }
    data = []
    for t in tanques:
        row = ct_map.get(t.id)
        data.append({
            'tanque_id': t.id,
            'un': t.un,
            'nome': t.nome,
            'sistema': t.sistema,
            'data_inicio_prevista': row.data_inicio_prevista.isoformat() if row and row.data_inicio_prevista else '',
            'data_fim_prevista': row.data_fim_prevista.isoformat() if row and row.data_fim_prevista else '',
            'data_inicio_real': row.data_inicio_real.isoformat() if row and row.data_inicio_real else '',
            'data_fim_real': row.data_fim_real.isoformat() if row and row.data_fim_real else '',
            'observacao': (row.observacao or '') if row else '',
        })
    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filt,
        'data': data,
    })


@cronograma_bp.route('/projeto/<int:contrato_id>/tanque/salvar', methods=['POST'])
def projeto_tanque_salvar(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    tanque_id = request.form.get('tanque_id', type=int)
    if not tanque_id:
        return jsonify({'ok': False, 'message': 'Tanque inválido.'}), 400
    tanque = Tanques.query.filter_by(id=tanque_id, contrato_id=contrato_id).first()
    if not tanque:
        return jsonify({'ok': False, 'message': 'Tanque não pertence ao projeto.'}), 400
    row = CronogramaTanque.query.filter_by(contrato_id=contrato_id, tanque_id=tanque_id).first()
    if not row:
        row = CronogramaTanque(contrato_id=contrato_id, tanque_id=tanque_id)
        db.session.add(row)
    row.data_inicio_prevista = parse_date(request.form.get('data_inicio_prevista'))
    row.data_fim_prevista = parse_date(request.form.get('data_fim_prevista'))
    row.data_inicio_real = parse_date(request.form.get('data_inicio_real'))
    row.data_fim_real = parse_date(request.form.get('data_fim_real'))
    obs = request.form.get('observacao', '') or ''
    row.observacao = obs.strip() or None
    db.session.commit()
    return jsonify({'ok': True})


@cronograma_bp.route('/projeto/<int:contrato_id>/linha-base/salvar', methods=['POST'])
def projeto_linha_base_salvar(contrato_id):
    Contrato.query.get_or_404(contrato_id)
    nome = (request.form.get('nome') or '').strip()
    if not nome:
        flash('Informe o nome da linha de base.', 'danger')
        return redirect(url_for('cronograma.projeto', contrato_id=contrato_id))
    descricao = (request.form.get('descricao') or '').strip() or None
    tanques = Tanques.query.filter(Tanques.contrato_id == contrato_id).all()
    if not tanques:
        flash('Não há tanques neste projeto.', 'warning')
        return redirect(url_for('cronograma.projeto', contrato_id=contrato_id))
    lb = CronogramaLinhaBase(
        contrato_id=contrato_id,
        nome=nome,
        descricao=descricao,
        data_snapshot=datetime.now(),
        usuario_id=current_user.id,
    )
    db.session.add(lb)
    db.session.flush()
    ct_rows = {
        r.tanque_id: r
        for r in CronogramaTanque.query.filter(CronogramaTanque.contrato_id == contrato_id).all()
    }
    for t in tanques:
        r = ct_rows.get(t.id)
        db.session.add(
            CronogramaLinhaBaseTanque(
                linha_base_id=lb.id,
                tanque_id=t.id,
                data_inicio_prevista=r.data_inicio_prevista if r else None,
                data_fim_prevista=r.data_fim_prevista if r else None,
            )
        )
    db.session.commit()
    flash('Linha de base criada com sucesso.', 'success')
    return redirect(url_for('cronograma.projeto', contrato_id=contrato_id))


@cronograma_bp.route('/linhas-base')
def linhas_base():
    contratos = Contrato.query.filter(Contrato.ativo.is_(True)).order_by(Contrato.nome).all()
    return render_template('cronograma/linhas_base.html', contratos=contratos)


@cronograma_bp.route('/api/linhas-base-datatables', methods=['GET'])
def api_linhas_base_datatables():
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '', type=str).strip()
    raw_cid = request.args.get('contrato_id')
    contrato_filtro = None
    if raw_cid not in (None, ''):
        try:
            contrato_filtro = int(raw_cid)
        except (TypeError, ValueError):
            contrato_filtro = None

    q = CronogramaLinhaBase.query.join(Contrato, CronogramaLinhaBase.contrato_id == Contrato.id)
    if contrato_filtro:
        q = q.filter(CronogramaLinhaBase.contrato_id == contrato_filtro)
    if search_value:
        like = f'%{search_value}%'
        q = q.filter(or_(CronogramaLinhaBase.nome.ilike(like), Contrato.nome.ilike(like)))
    total = CronogramaLinhaBase.query.count()
    filt = q.count()
    order_column_index = int(request.args.get('order[0][column]', 2))
    order_dir = request.args.get('order[0][dir]', 'desc')
    order_map = {
        0: Contrato.nome,
        1: CronogramaLinhaBase.nome,
        2: CronogramaLinhaBase.data_snapshot,
    }
    order_col = order_map.get(order_column_index, CronogramaLinhaBase.data_snapshot)
    if order_dir == 'desc':
        q = q.order_by(order_col.desc())
    else:
        q = q.order_by(order_col.asc())
    rows = q.offset(start).limit(length).all()
    data = []
    for lb in rows:
        url_proj = url_for('cronograma.projeto', contrato_id=lb.contrato_id)
        data.append({
            'id': lb.id,
            'contrato': lb.contrato.nome if lb.contrato else '',
            'contrato_id': lb.contrato_id,
            'nome': lb.nome,
            'data_snapshot': lb.data_snapshot.strftime('%d/%m/%Y %H:%M') if lb.data_snapshot else '',
            'usuario': lb.usuario.nome if lb.usuario else '—',
            'url_projeto': url_proj,
        })
    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filt,
        'data': data,
    })


@cronograma_bp.route('/api/linha-base/<int:linha_base_id>/detalhes', methods=['GET'])
def api_linha_base_detalhes(linha_base_id):
    lb = CronogramaLinhaBase.query.get_or_404(linha_base_id)
    itens = (
        CronogramaLinhaBaseTanque.query.filter_by(linha_base_id=lb.id)
        .join(Tanques, CronogramaLinhaBaseTanque.tanque_id == Tanques.id)
        .order_by(Tanques.nome)
        .all()
    )
    out = []
    for it in itens:
        out.append({
            'tanque_id': it.tanque_id,
            'un': it.tanque.un if it.tanque else '',
            'nome': it.tanque.nome if it.tanque else '',
            'data_inicio_prevista': it.data_inicio_prevista.isoformat() if it.data_inicio_prevista else '',
            'data_fim_prevista': it.data_fim_prevista.isoformat() if it.data_fim_prevista else '',
        })
    return jsonify({
        'ok': True,
        'linha_base': {
            'id': lb.id,
            'nome': lb.nome,
            'descricao': lb.descricao or '',
            'contrato': lb.contrato.nome if lb.contrato else '',
            'data_snapshot': lb.data_snapshot.strftime('%d/%m/%Y %H:%M') if lb.data_snapshot else '',
        },
        'itens': out,
    })


@cronograma_bp.route('/linhas-base/excluir/<int:linha_base_id>', methods=['POST'])
def linhas_base_excluir(linha_base_id):
    lb = CronogramaLinhaBase.query.get_or_404(linha_base_id)
    db.session.delete(lb)
    db.session.commit()
    flash('Linha de base excluída.', 'success')
    return redirect(url_for('cronograma.linhas_base'))
