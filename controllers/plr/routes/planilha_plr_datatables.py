"""DataTables server-side do relatório planilha PLR."""

from flask import jsonify, request

from utils.datatable_helper import DataTableParams

from .. import plr_bp
from ..services.planilha_plr_calculo import montar_relatorio_planilha_datatables
from ..services.relatorio_planilha_payload import carregar_payload_planilha, parse_filtros_planilha


@plr_bp.route('/relatorio-planilha/datatables', methods=['GET', 'POST'])
def relatorio_planilha_datatables():
    """DataTables server-side (POST recomendado: parâmetros aninhados do DT)."""
    dt = DataTableParams()
    try:
        err, filtros = parse_filtros_planilha(request.values)
        if err:
            return (
                jsonify(
                    {
                        'draw': dt.draw,
                        'recordsTotal': 0,
                        'recordsFiltered': 0,
                        'data': [],
                        'meses_colunas': [],
                        'data_fechamento': None,
                        'error': err,
                    }
                ),
                400,
            )
        payload = carregar_payload_planilha(filtros)
        return montar_relatorio_planilha_datatables(dt, payload)
    except Exception as e:
        return (
            jsonify(
                {
                    'draw': dt.draw,
                    'recordsTotal': 0,
                    'recordsFiltered': 0,
                    'data': [],
                    'meses_colunas': [],
                    'data_fechamento': None,
                    'error': str(e),
                }
            ),
            500,
        )
