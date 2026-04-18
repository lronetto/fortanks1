"""Endpoint DataTables para a tabela de acabamento/transporte."""

from flask import jsonify, request

from utils.datatable_helper import DataTableParams

from .. import acabamento_transporte_bp
from ..services.datatables import montar_payload_datatables


@acabamento_transporte_bp.route("/api/datatables", methods=["GET"])
def api_datatables():
    """Endpoint AJAX para DataTables — peças de acabamento/transporte."""
    dt = DataTableParams()
    try:
        filtros = {
            "filtro": request.args.get("filtro", "todos"),
            "tanque_id": request.args.get("tanque_id", "todos"),
            "nome_peca": request.args.get("nome_peca", "").strip(),
            "inicio_acabamento": request.args.get("inicio_acabamento", "").strip(),
            "termino_acabamento": request.args.get("termino_acabamento", "").strip(),
            "inicio_transporte": request.args.get("inicio_transporte", "").strip(),
            "termino_transporte": request.args.get("termino_transporte", "").strip(),
        }
        return montar_payload_datatables(dt, filtros)
    except Exception as e:
        return (
            jsonify(
                {
                    "draw": dt.draw,
                    "recordsTotal": 0,
                    "recordsFiltered": 0,
                    "data": [],
                    "error": str(e),
                }
            ),
            500,
        )
