"""Endpoint DataTables para listagem de orçamentos."""

import logging

from flask import jsonify, request
from flask_login import login_required

from utils.datatable_helper import DataTableParams

from .. import orcamento_bp
from ..services.datatables import montar_payload_datatables_orcamentos

logger = logging.getLogger(__name__)


def _draw_para_erro():
    try:
        return int(request.values.get("draw", 1))
    except (TypeError, ValueError):
        return 1


@orcamento_bp.route("/api/datatables", methods=["GET"])
@login_required
def api_datatables():
    try:
        dt = DataTableParams()
        filtros = {
            "status": (request.args.get("status") or "").strip(),
        }
        return montar_payload_datatables_orcamentos(dt, filtros)
    except Exception as exc:
        logger.exception("Erro em api_datatables (orçamentos)")
        return (
            jsonify(
                {
                    "draw": _draw_para_erro(),
                    "recordsTotal": 0,
                    "recordsFiltered": 0,
                    "data": [],
                    "error": str(exc),
                }
            ),
            500,
        )
