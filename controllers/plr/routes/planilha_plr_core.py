"""Página HTML e endpoint JSON legado do relatório planilha PLR."""

from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, url_for

from models.departamento import Departamento
from models.plr import ModeloPLR

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
