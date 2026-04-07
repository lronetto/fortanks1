import re
from datetime import date, timedelta
from io import BytesIO

from flask import flash, redirect, render_template, request, send_file, url_for

from models.contrato import Contrato

from utils.cronograma_matriz_excel import build_matriz_semanal_xlsx_bytes
from utils.cronograma_matriz_semanal import (
    agregar_curva_s_projeto,
    data_fim_horizonte_matriz,
    minima_segunda_feira_anchor_cronograma,
    montar_matriz_previsto_real,
    runs_intervalos_dias_semana_horizontais,
    trim_trailing_semanas_sem_previsto_nem_real,
)

from . import cronograma_bp, parse_date


def _max_dias_previsto_grid(linhas: list, semanas: list) -> float:
    """Maior valor de dias previstos em uma célula (item × semana), para escala das barras."""
    if not linhas or not semanas:
        return 1.0
    keys = [s.get('key') for s in semanas if s.get('key')]
    m = 0.0
    for row in linhas:
        dct = row.get('dias_previsto_semana') or {}
        for k in keys:
            try:
                v = float(dct.get(k, 0) or 0)
            except (TypeError, ValueError):
                v = 0.0
            if v > m:
                m = v
    return m if m > 1e-9 else 1.0


def _barras_dias_runs_totais(barras_vals: list, semanas: list) -> list:
    """Intervalos horizontais para a linha de totais (mesma lógica dos itens)."""
    if not barras_vals or not semanas:
        return []
    keys = [s.get('key') for s in semanas if s.get('key')]
    if len(keys) != len(barras_vals):
        return []
    d = {keys[i]: float(barras_vals[i] or 0) for i in range(len(keys))}
    return runs_intervalos_dias_semana_horizontais(d, keys)


def _max_dias_lista(vals: list) -> float:
    m = 0.0
    for v in vals or []:
        try:
            x = float(v or 0)
        except (TypeError, ValueError):
            continue
        if x > m:
            m = x
    return m if m > 1e-9 else 1.0


@cronograma_bp.route('/matriz-semanal')
def matriz_semanal():
    """Itens do cronograma × semanas: previsto (cálculo) e real (concretagem)."""
    contratos = (
        Contrato.query.filter(Contrato.ativo.is_(True))
        .order_by(Contrato.nome.asc())
        .all()
    )

    contrato_id = request.args.get('contrato_id', type=int)
    hoje = date.today()
    raw_di = request.args.get('data_inicio')
    raw_df = request.args.get('data_fim')
    data_inicio = parse_date(raw_di) if raw_di not in (None, '') else None
    data_fim_form = parse_date(raw_df) if raw_df not in (None, '') else None
    data_fim = data_fim_form
    if not data_fim:
        data_fim = hoje + timedelta(weeks=24)

    semanas: list = []
    linhas: list = []
    barras_dias_semana: list = []
    contrato = None

    if contrato_id:
        contrato = Contrato.query.filter(
            Contrato.id == contrato_id,
            Contrato.ativo.is_(True),
        ).first()
        if not contrato:
            flash('Contrato não encontrado ou inativo.', 'warning')
            if not data_inicio:
                data_inicio = hoje - timedelta(weeks=4)
        else:
            if not data_inicio:
                data_inicio = (
                    minima_segunda_feira_anchor_cronograma(contrato_id)
                    or (hoje - timedelta(weeks=4))
                )
            data_fim_calc = data_fim_horizonte_matriz(contrato_id, data_inicio, data_fim_form)
            semanas, linhas, barras_dias_semana = montar_matriz_previsto_real(
                contrato_id, data_inicio, data_fim_calc
            )
            semanas, linhas, data_fim, barras_dias_semana = trim_trailing_semanas_sem_previsto_nem_real(
                semanas, linhas, barras_dias_semana
            )
            if barras_dias_semana is None:
                barras_dias_semana = []
    elif not data_inicio:
        data_inicio = hoje - timedelta(weeks=4)

    if not data_inicio:
        data_inicio = hoje - timedelta(weeks=4)

    max_dias_previsto_grid = _max_dias_previsto_grid(linhas, semanas)
    barras_dias_runs = _barras_dias_runs_totais(barras_dias_semana or [], semanas)
    max_dias_barras_totais = _max_dias_lista(barras_dias_semana or [])

    return render_template(
        'cronograma/matriz_semanal.html',
        contratos=contratos,
        contrato=contrato,
        contrato_id=contrato_id,
        semanas=semanas,
        linhas=linhas,
        data_inicio=data_inicio,
        data_fim=data_fim,
        barras_dias_semana=barras_dias_semana,
        barras_dias_runs=barras_dias_runs,
        max_dias_previsto_grid=max_dias_previsto_grid,
        max_dias_barras_totais=max_dias_barras_totais,
    )


def _nome_arquivo_matriz_excel(nome_projeto: str) -> str:
    base = re.sub(r'[^\w\s\-_.\u0080-\u024F]', '', (nome_projeto or '').strip(), flags=re.UNICODE)
    base = re.sub(r'\s+', '_', base).strip('_')[:80]
    return base or 'matriz_semanal'


@cronograma_bp.route('/matriz-semanal/exportar-excel')
def matriz_semanal_exportar_excel():
    """Excel com duas abas: matriz de placas e dias previstos, cores por tempo e intensidade."""
    contrato_id = request.args.get('contrato_id', type=int)
    if not contrato_id:
        flash('Selecione um projeto na matriz e tente exportar novamente.', 'warning')
        return redirect(url_for('cronograma.matriz_semanal'))

    hoje = date.today()
    raw_di = request.args.get('data_inicio')
    raw_df = request.args.get('data_fim')
    data_inicio = parse_date(raw_di) if raw_di not in (None, '') else None
    data_fim_form = parse_date(raw_df) if raw_df not in (None, '') else None
    data_fim = data_fim_form
    if not data_fim:
        data_fim = hoje + timedelta(weeks=24)

    contrato = Contrato.query.filter(
        Contrato.id == contrato_id,
        Contrato.ativo.is_(True),
    ).first()
    if not contrato:
        flash('Contrato não encontrado ou inativo.', 'warning')
        return redirect(url_for('cronograma.matriz_semanal'))

    if not data_inicio:
        data_inicio = (
            minima_segunda_feira_anchor_cronograma(contrato_id) or (hoje - timedelta(weeks=4))
        )
    data_fim_calc = data_fim_horizonte_matriz(contrato_id, data_inicio, data_fim_form)
    semanas, linhas, barras_dias_semana = montar_matriz_previsto_real(
        contrato_id, data_inicio, data_fim_calc
    )
    semanas, linhas, data_fim, barras_dias_semana = trim_trailing_semanas_sem_previsto_nem_real(
        semanas, linhas, barras_dias_semana
    )
    if barras_dias_semana is None:
        barras_dias_semana = []

    if not semanas or not linhas:
        flash('Não há dados de matriz para exportar neste intervalo.', 'warning')
        return redirect(
            url_for(
                'cronograma.matriz_semanal',
                contrato_id=contrato_id,
                data_inicio=data_inicio.strftime('%Y-%m-%d'),
                data_fim=data_fim.strftime('%Y-%m-%d'),
            )
        )

    max_dias_previsto_grid = _max_dias_previsto_grid(linhas, semanas)
    max_dias_barras_totais = _max_dias_lista(barras_dias_semana or [])

    payload = build_matriz_semanal_xlsx_bytes(
        nome_projeto=contrato.nome or 'Projeto',
        semanas=semanas,
        linhas=linhas,
        barras_dias_semana=barras_dias_semana,
        max_dias_previsto_grid=max_dias_previsto_grid,
        max_dias_barras_totais=max_dias_barras_totais,
    )

    safe = _nome_arquivo_matriz_excel(contrato.nome or '')
    download = f'matriz_semanal_{safe}_{data_inicio.strftime("%Y%m%d")}_{data_fim.strftime("%Y%m%d")}.xlsx'

    return send_file(
        BytesIO(payload),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=download,
    )


@cronograma_bp.route('/projeto/<int:contrato_id>/curva-s')
def projeto_curva_s(contrato_id):
    """Gráfico curva S: % acumulado previsto x real (base = previsto total no intervalo)."""
    contrato = Contrato.query.filter(
        Contrato.id == contrato_id,
        Contrato.ativo.is_(True),
    ).first()
    if not contrato:
        flash('Contrato não encontrado ou inativo.', 'warning')
        return redirect(url_for('cronograma.matriz_semanal'))

    hoje = date.today()
    raw_di = request.args.get('data_inicio')
    raw_df = request.args.get('data_fim')
    data_inicio = parse_date(raw_di) if raw_di not in (None, '') else None
    data_fim_form = parse_date(raw_df) if raw_df not in (None, '') else None
    if not data_inicio:
        data_inicio = (
            minima_segunda_feira_anchor_cronograma(contrato_id)
            or (hoje - timedelta(weeks=4))
        )
    if not data_fim_form:
        data_fim_form = hoje + timedelta(weeks=24)

    data_fim_calc = data_fim_horizonte_matriz(contrato_id, data_inicio, data_fim_form)
    semanas, linhas, _barras = montar_matriz_previsto_real(contrato_id, data_inicio, data_fim_calc)
    semanas, linhas, data_fim, _ = trim_trailing_semanas_sem_previsto_nem_real(
        semanas, linhas, _barras
    )
    if not linhas or not semanas:
        flash('Não há dados no cronograma para este intervalo.', 'warning')
        return redirect(url_for('cronograma.matriz_semanal', contrato_id=contrato_id))

    labels, cum_p, cum_r, pct_p, pct_r, max_y = agregar_curva_s_projeto(semanas, linhas)
    total_prev = cum_p[-1] if cum_p else 0.0
    total_real = cum_r[-1] if cum_r else 0.0

    return render_template(
        'cronograma/curva_s.html',
        contrato=contrato,
        labels=labels,
        cum_p=cum_p,
        cum_r=cum_r,
        pct_p=pct_p,
        pct_r=pct_r,
        max_y=max_y,
        total_previsto_placas=total_prev,
        total_real_placas=total_real,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
