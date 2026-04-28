"""Página HTML e endpoint JSON legado do relatório planilha PLR."""

from datetime import date, datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, url_for

from models.centro_custo import CentroCusto
from models.database import db
from models.departamento import Departamento
from models.plr import ModeloPLR
from models.plr import PLRColaborador

from .. import plr_bp
from ..services.avaliacoes import equipes_distintas_plr as _equipes_distintas_plr
from ..services.relatorio_planilha_payload import (
    carregar_payload_planilha,
    filtros_para_template_boot,
    parse_filtros_planilha,
)


@plr_bp.route('/relatorio-planilha/dados')
def relatorio_planilha_dados():
    """Retorna JSON com os dados da planilha (AJAX legado / uso simples)."""
    err, filtros = parse_filtros_planilha(request.values)
    if err:
        return jsonify(
            {
                'error': err,
                'data': [],
                'meses_colunas': [],
                'data_fechamento': None,
            }
        ), 400
    try:
        payload = carregar_payload_planilha(filtros)
    except Exception as e:
        return jsonify(
            {
                'error': str(e),
                'data': [],
                'meses_colunas': [],
                'data_fechamento': None,
            }
        ), 500

    return jsonify(
        {
            # Mesmo formato da tabela (``pct_*``), para DataTables no cliente.
            'data': payload['rows_datatables'],
            'meses_colunas': payload['meses_colunas_json'],
            'data_fechamento': payload['data_fechamento_br'],
        }
    )


@plr_bp.route('/relatorio-planilha/obras')
def relatorio_planilha_obras():
    """Lista obras (centros de custo) únicas nas avaliações do período informado."""
    err, filtros = parse_filtros_planilha(request.values)
    if err:
        return jsonify({'error': err, 'obras': []}), 400

    ano_i = int(filtros['ano_inicio'])
    mes_i = int(filtros['mes_inicio'])
    ano_f = int(filtros['ano_fim'])
    mes_f = int(filtros['mes_fim'])
    data_inicio = date(ano_i, mes_i, 1)
    data_fim = date(ano_f, mes_f, 1) + timedelta(days=32)
    data_fim = data_fim.replace(day=1) - timedelta(days=1)

    q = (
        db.session.query(CentroCusto.id, CentroCusto.codigo, CentroCusto.nome)
        .join(PLRColaborador, PLRColaborador.centro_custo_id == CentroCusto.id)
        .filter(
            PLRColaborador.data >= data_inicio,
            PLRColaborador.data <= data_fim,
        )
    )
    if filtros.get('modelo_plr_id'):
        q = q.filter(PLRColaborador.PlrModelo_id == int(filtros['modelo_plr_id']))
    if filtros.get('equipe_filtro'):
        equipe = filtros['equipe_filtro']
        avals = (
            PLRColaborador.query.filter(
                PLRColaborador.data >= data_inicio,
                PLRColaborador.data <= data_fim,
            )
            .all()
        )
        ids_av = {
            av.id
            for av in avals
            if av.equipe_alocada and isinstance(av.equipe_alocada, list)
            and equipe in [str(e).strip() for e in av.equipe_alocada if e]
        }
        if ids_av:
            q = q.filter(PLRColaborador.id.in_(ids_av))
        else:
            return jsonify({'obras': []})

    rows = q.distinct().order_by(CentroCusto.codigo.asc(), CentroCusto.nome.asc()).all()
    obras = [
        {
            'id': str(row.id),
            'codigo': row.codigo or '',
            'nome': row.nome or '',
            'label': f"{(row.codigo or '').strip()} - {(row.nome or '').strip()}".strip(' -'),
        }
        for row in rows
    ]
    return jsonify({'obras': obras})


def _render_planilha(modelos_list, equipes, departamentos, ano_sugerido, planilha_json=None):
    return render_template(
        'plr/relatorio_planilha.html',
        modelos=modelos_list,
        equipes=equipes,
        departamentos=departamentos,
        ano_sugerido=ano_sugerido,
        planilha_json=planilha_json,
    )


@plr_bp.route('/relatorio-planilha/', methods=['GET', 'POST'])
def relatorio_planilha():
    """Página do relatório planilha: filtros e tabela (dados via AJAX ou POST)."""
    modelos_list = ModeloPLR.query.filter_by(ativo=True).order_by(ModeloPLR.nome).all()
    equipes = _equipes_distintas_plr()
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    ano_sugerido = datetime.now().year

    if request.method == 'POST':
        modelo_plr_id = request.form.get('modelo_plr_id', '')
        equipe_filtro = request.form.get('equipe', '').strip() or None
        departamentos_ids = [int(x) for x in request.form.getlist('departamento_id') if x and str(x).isdigit()]
        periodo_inicio = request.form.get('periodo_inicio')
        periodo_fim = request.form.get('periodo_fim')
        obras_centro_custo_ids = [
            int(x) for x in request.form.getlist('obra_centro_custo_id') if x and str(x).isdigit()
        ]

        if periodo_inicio and periodo_fim:
            parts_i = periodo_inicio.split('-')
            parts_f = periodo_fim.split('-')
            ano_inicio = int(parts_i[0])
            mes_inicio = parts_i[1].lstrip('0') or '1'
            ano_fim = int(parts_f[0])
            mes_fim = parts_f[1].lstrip('0') or '12'
            if ano_inicio > ano_fim or (ano_inicio == ano_fim and int(mes_inicio) > int(mes_fim)):
                flash('A data de início deve ser anterior ou igual à data de fim.', 'danger')
                return _render_planilha(modelos_list, equipes, departamentos, ano_sugerido)
        else:
            ano_inicio = request.form.get('ano_inicio') or request.form.get('ano')
            ano_fim = request.form.get('ano_fim') or ano_inicio
            mes_inicio = request.form.get('mes_inicio', '1')
            mes_fim = request.form.get('mes_fim', '12')
            if not ano_inicio:
                flash('Informe o período.', 'danger')
                return _render_planilha(modelos_list, equipes, departamentos, ano_sugerido)
            ano_inicio = int(ano_inicio)
            ano_fim = int(ano_fim)

        salario_pg = request.form.get('salario_por_grupo') == '1'
        filtros_post = {
            'ano_inicio': ano_inicio,
            'mes_inicio': mes_inicio,
            'ano_fim': ano_fim,
            'mes_fim': mes_fim,
            'modelo_plr_id': modelo_plr_id or '',
            'equipe_filtro': equipe_filtro,
            'obras_centro_custo_ids': obras_centro_custo_ids or None,
            'departamentos_ids': departamentos_ids or None,
            'salario_por_grupo': salario_pg,
        }
        try:
            payload = carregar_payload_planilha(filtros_post)
        except Exception as e:
            flash(f'Erro ao gerar relatório: {e}', 'danger')
            return _render_planilha(modelos_list, equipes, departamentos, ano_sugerido)

        planilha_json = {
            'meses_colunas': payload['meses_colunas_json'],
            'data_fechamento': payload['data_fechamento_br'],
            'filtros': filtros_para_template_boot(filtros_post),
        }
        return _render_planilha(
            modelos_list, equipes, departamentos, ano_sugerido,
            planilha_json=planilha_json,
        )

    return _render_planilha(modelos_list, equipes, departamentos, ano_sugerido, planilha_json=None)
