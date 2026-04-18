"""Exportação Excel."""

from flask import request, send_file

from .. import acabamento_transporte_bp
from ..services.exportacao import exportar_excel_acabamento_transporte


@acabamento_transporte_bp.route("/exportar_excel")
def exportar_excel():
    filtros = request.args.to_dict()
    output = exportar_excel_acabamento_transporte(filtros)
    return send_file(
        output,
        download_name="pecas_acabamento_transporte.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
