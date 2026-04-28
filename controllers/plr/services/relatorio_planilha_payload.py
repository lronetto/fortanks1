"""
Payload único da planilha PLR: mesmos filtros do formulário em ``relatorio_planilha.html``
(periodo_inicio/fim viram ano/mês via query; DataTables envia ano_inicio, mes_inicio, …).

``parse_filtros_planilha`` normaliza entradas; ``carregar_payload_planilha`` executa o cálculo
uma vez e devolve estruturas reutilizáveis na tabela (DataTables) e nas exportações Excel.
"""

from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any, Mapping


def _getlist(values: Mapping[str, Any], key: str) -> list:
    if hasattr(values, 'getlist'):
        return list(values.getlist(key))
    v = values.get(key)
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def parse_filtros_planilha(values: Mapping[str, Any]) -> tuple[str | None, dict | None]:
    """
    Lê filtros alinhados ao front (GET/POST / ``request.values``).

    Retorna ``(mensagem_erro, None)`` ou ``(None, filtros_dict)`` com chaves:
    ``ano_inicio``, ``mes_inicio``, ``ano_fim``, ``mes_fim``, ``modelo_plr_id``,
    ``equipe_filtro``, ``departamentos_ids``, ``obras_centro_custo_ids``,
    ``salario_por_grupo``.
    """
    ano_inicio = values.get('ano_inicio') or values.get('ano')
    ano_fim = values.get('ano_fim') or ano_inicio
    mes_inicio = values.get('mes_inicio', '1')
    mes_fim = values.get('mes_fim', '12')
    modelo_plr_id = values.get('modelo_plr_id', '') or ''
    equipe_filtro = (values.get('equipe') or '').strip() or None
    obras_centro_custo_ids = [
        int(x) for x in _getlist(values, 'obra_centro_custo_id') if x and str(x).isdigit()
    ]
    departamentos_ids = [
        int(x) for x in _getlist(values, 'departamento_id') if x and str(x).isdigit()
    ]
    salario_por_grupo = str(values.get('salario_grupo', '')).strip().lower() in (
        '1',
        'true',
        'on',
        'yes',
        'sim',
    )

    if not ano_inicio:
        return 'Informe o período.', None
    try:
        ano_inicio_i = int(ano_inicio)
        ano_fim_i = int(ano_fim)
    except (ValueError, TypeError):
        return 'Ano inválido.', None

    return None, {
        'ano_inicio': ano_inicio_i,
        'mes_inicio': mes_inicio,
        'ano_fim': ano_fim_i,
        'mes_fim': mes_fim,
        'modelo_plr_id': modelo_plr_id,
        'equipe_filtro': equipe_filtro,
        'obras_centro_custo_ids': obras_centro_custo_ids or None,
        'departamentos_ids': departamentos_ids or None,
        'salario_por_grupo': salario_por_grupo,
    }


def _mes_para_date(ano: int, mes) -> tuple[int, int]:
    m = int(str(mes).lstrip('0') or '1')
    return ano, max(1, min(12, m))


def filtros_para_template_boot(filtros: dict) -> dict:
    """Filtros serializáveis para ``window.PLANILHA_BOOT`` / espelho do ``ultimoFiltro`` JS."""
    dep = filtros.get('departamentos_ids') or []
    ai, mi = _mes_para_date(filtros['ano_inicio'], filtros['mes_inicio'])
    af, mf = _mes_para_date(filtros['ano_fim'], filtros['mes_fim'])
    return {
        'ano_inicio': ai,
        'mes_inicio': mi,
        'ano_fim': af,
        'mes_fim': mf,
        'modelo_plr_id': filtros.get('modelo_plr_id') or '',
        'equipe': (filtros.get('equipe_filtro') or ''),
        'obras_centro_custo_ids': [str(x) for x in (filtros.get('obras_centro_custo_ids') or [])],
        'departamentos': [str(x) for x in dep],
        'salario_por_grupo': bool(filtros.get('salario_por_grupo')),
    }


def carregar_payload_planilha(filtros: dict) -> dict:
    """
    Executa ``relatorio_planilha_calcular`` e monta o payload para DataTables + Excel.

    Retorno (dict) inclui:
    - ``filtros``: cópia dos filtros recebidos
    - ``resultado``: linhas internas por colaborador (exportações Excel / critérios)
    - ``linhas_exibicao``: uma linha por segmento de função (DataTables / JSON)
    - ``meses_colunas``, ``data_inicio``, ``data_fechamento``
    - ``meses_colunas_json``, ``data_fechamento_br``
    - ``data_json``: linhas ``_row_planilha_para_json`` a partir de ``linhas_exibicao``
    - ``rows_datatables``: mesmas linhas com ``pct_0``..``pct_n`` (server-side DataTables)
    - ``cpf_para_chapa``, ``criterios_por_colab_mes``: uso nas exportações / template MOD
    """
    rp = import_module('controllers.plr.services.planilha_plr_calculo')

    resultado, meses_colunas, data_fechamento = rp.relatorio_planilha_calcular(
        filtros['ano_inicio'],
        filtros['mes_inicio'],
        filtros['ano_fim'],
        filtros['mes_fim'],
        filtros['modelo_plr_id'],
        filtros['equipe_filtro'],
        filtros.get('obras_centro_custo_ids'),
        filtros['departamentos_ids'],
        salario_por_grupo=filtros.get('salario_por_grupo', False),
    )

    ai, mi = _mes_para_date(filtros['ano_inicio'], filtros['mes_inicio'])
    data_inicio = date(ai, mi, 1)

    cpf_para_chapa = rp._excel_cpf_para_chapa(resultado, data_inicio, data_fechamento)
    criterios_por_colab_mes = rp._excel_criterios_por_colab_mes(
        resultado,
        meses_colunas,
        data_inicio,
        data_fechamento,
        filtros.get('modelo_plr_id') or '',
        filtros.get('equipe_filtro'),
        filtros.get('obras_centro_custo_ids'),
    )

    linhas_exibicao = rp.expandir_resultado_planilha_por_segmento_funcao(
        resultado,
        data_inicio,
        data_fechamento,
        meses_colunas,
        filtros.get('salario_por_grupo', False),
    )
    data_json = [rp._row_planilha_para_json(r) for r in linhas_exibicao]
    rows_datatables = [
        rp._row_planilha_flat_row_dict(r, meses_colunas) for r in linhas_exibicao
    ]

    return {
        'filtros': dict(filtros),
        'resultado': resultado,
        'linhas_exibicao': linhas_exibicao,
        'meses_colunas': meses_colunas,
        'meses_colunas_json': [{'mes': m, 'ano': a} for (m, a) in meses_colunas],
        'data_inicio': data_inicio,
        'data_fechamento': data_fechamento,
        'data_fechamento_br': data_fechamento.strftime('%d/%m/%Y') if data_fechamento else None,
        'data_json': data_json,
        'rows_datatables': rows_datatables,
        'cpf_para_chapa': cpf_para_chapa,
        'criterios_por_colab_mes': criterios_por_colab_mes,
    }
