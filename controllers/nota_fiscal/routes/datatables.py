import logging
from datetime import datetime

from flask import jsonify, request
from flask_login import login_required
from sqlalchemy import func

from models.database import db
from models.nota_fiscal import NotaFiscal
from utils.datatable_helper import DataTableParams
from ..services.query_notas import api_get_dados_notas_fiscais
from .. import nota_fiscal_bp

logger = logging.getLogger(__name__)


@nota_fiscal_bp.route("/api/notas-fiscais/ajax", methods=["GET", "POST"])
@login_required
def api_get_ajax_notas_fiscais():
    query = api_get_dados_notas_fiscais(request)
    return jsonify([nota.to_dict() for nota in query.all()])


@nota_fiscal_bp.route("/api/datatables", methods=["GET"])
@login_required
def api_get_datatables_notas_fiscais():
    """
    Retorna dados formatados para DataTables via AJAX
    """
    from models.nota_fiscal import CNPJS_FILIAIS, CNPJS_MATRIZ

    dt = DataTableParams()

    column_mapping = {
        1: "numero_nf",
        2: "tipo",
        3: "data_emissao",
        4: "vencimento",
        5: "cnpj_emitente",
        6: "cnpj_destinatario",
        7: "nome_emitente",
        8: "valor_total",
    }

    order_by = column_mapping.get(dt.order_col, "data_emissao")
    order_dir = "desc" if dt.order_dir == "desc" else "asc"

    json_filtros = request.args.to_dict()
    json_filtros["order_by"] = order_by
    json_filtros["order_dir"] = order_dir
    query = api_get_dados_notas_fiscais(json_filtros)

    total_geral = db.session.query(func.count(NotaFiscal.id)).scalar() or 0
    total_filtrado = query.count()

    if dt.length == -1:
        notas_fiscais_pagina = query.offset(dt.start).all()
    else:
        per_page = max(1, min(dt.length, 500))
        pagination = query.paginate(page=dt.page, per_page=per_page, error_out=False)
        notas_fiscais_pagina = pagination.items

    data = []
    for nota in notas_fiscais_pagina:
        vencimento_str = getattr(nota.NotaFiscal, "vencimento", None) if hasattr(nota.NotaFiscal, "vencimento") else None
        vencimento_formatado = "-"
        if vencimento_str:
            try:
                if isinstance(vencimento_str, str) and len(vencimento_str) == 10 and "-" in vencimento_str:
                    vencimento_date = datetime.strptime(vencimento_str, "%Y-%m-%d").date()
                    vencimento_formatado = vencimento_date.strftime("%d/%m/%Y")
                else:
                    vencimento_formatado = str(vencimento_str)
            except (ValueError, AttributeError):
                vencimento_formatado = str(vencimento_str) if vencimento_str else "-"

        emitente = (
            "Matriz"
            if nota.NotaFiscal.cnpj_emitente in CNPJS_MATRIZ
            else "Filiais"
            if nota.NotaFiscal.cnpj_emitente in CNPJS_FILIAIS
            else "Terceiros"
        )
        destinatario = (
            "Matriz"
            if nota.NotaFiscal.cnpj_destinatario in CNPJS_MATRIZ
            else "Filiais"
            if nota.NotaFiscal.cnpj_destinatario in CNPJS_FILIAIS
            else "Terceiros"
        )

        percentual = getattr(nota, "percentual_importacao", 0) if hasattr(nota, "percentual_importacao") else 0
        if percentual is None:
            percentual = -1

        liberada = getattr(nota, "liberada", 0) if hasattr(nota, "liberada") else 0
        if liberada is None:
            liberada = 0

        status_html = ""
        nf_cancelada = nota.NotaFiscal.status_processamento == "cancelada"
        if nf_cancelada:
            status_html = '<span class="badge bg-danger">Cancelada</span>'
        else:
            status_html = ""
            if percentual == 0:
                status_html += '<span class="badge bg-danger">Pend</span>'
            elif percentual == 100:
                status_html += '<span class="badge bg-success">Impo</span>'
            elif percentual > 0:
                status_html += f'<span class="badge bg-warning">Parc ({int(percentual)}%)</span>'
            else:
                status_html += '<span class="badge bg-secondary">N/A</span>'

            if liberada == 1:
                status_html += ' <span class="badge bg-primary ms-1" title="Liberada"><i class="fas fa-check-circle"></i> Lib</span>'
            else:
                status_html += ' <span class="badge bg-secondary ms-1" title="Não Liberada"><i class="fas fa-times-circle"></i> NLib</span>'

            upload = getattr(nota, "upload", 0)
            if upload > 0:
                upload_protocolo = getattr(nota, "upload_protocolo", 0)
                upload_arquivei = getattr(nota, "upload_arquivei", 0)
                upload_reembolso = getattr(nota, "upload_reembolso", 0)

                if upload_protocolo == 1:
                    status_html += ' <span class="badge bg-info ms-1" title="protocolo"><i class="fas fa-paperclip" style="color: green;"></i></span>'
                if upload_arquivei == 1:
                    status_html += ' <span class="badge bg-info ms-1" title="arquivei"><i class="fas fa-paperclip"></i></span>'
                if upload_reembolso == 1:
                    status_html += ' <span class="badge bg-info ms-1" title="reembolso"><i class="fas fa-paperclip" style="color: red;"></i></span>'

            pagamento = getattr(nota, "pagamento", 0)
            if pagamento is not None:
                status_html += ' <span class="badge bg-success ms-1" title="Pago ' + pagamento.strftime("%d/%m/%Y") + '"><i class="fas fa-check"></i></span>'

        liberada = getattr(nota, "liberada", 0) if hasattr(nota, "liberada") else 0
        if liberada is None:
            liberada = 0

        btn_liberar_icon = "fa-unlock" if liberada == 0 else "fa-lock"
        btn_liberar_title = "Liberar" if liberada == 0 else "Desliberar"
        btn_cancelar_icon = "fa-ban" if not nf_cancelada else "fa-undo"
        btn_cancelar_title = "Cancelar nota fiscal" if not nf_cancelada else "Reverter cancelamento da nota fiscal"

        acoes_html = (
            f'<div class="ft-acoes-dropdown dropdown">'
            f'<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false" title="Ações"><i class="fas fa-ellipsis-v"></i></button>'
            f'<ul class="dropdown-menu dropdown-menu-end">'
            f'<li><button type="button" class="dropdown-item visualizar-itens" data-id="{nota.NotaFiscal.id}"><i class="fas fa-list text-primary"></i> Visualizar Itens</button></li>'
            f'<li><button type="button" class="dropdown-item importar-itens" data-id="{nota.NotaFiscal.id}"><i class="fas fa-file-import text-success"></i> Importar para Estoque</button></li>'
            f'<li><button type="button" class="dropdown-item vincular-material" data-id="{nota.NotaFiscal.id}"><i class="fas fa-link text-warning"></i> Vincular Material</button></li>'
            f'<li><button type="button" class="dropdown-item liberar-nota" data-id="{nota.NotaFiscal.id}" data-numero="{nota.NotaFiscal.numero_nf}" data-liberada="{liberada}"><i class="fas {btn_liberar_icon} text-info"></i> {btn_liberar_title}</button></li>'
            f'<li><button type="button" class="dropdown-item cancelar-nota" data-id="{nota.NotaFiscal.id}" data-numero="{nota.NotaFiscal.numero_nf}" data-cancelada="{1 if nf_cancelada else 0}"><i class="fas {btn_cancelar_icon} text-secondary"></i> {btn_cancelar_title}</button></li>'
            f'<li><hr class="dropdown-divider"></li>'
            f'<li><button type="button" class="dropdown-item text-danger excluir-nota" data-id="{nota.NotaFiscal.id}" data-numero="{nota.NotaFiscal.numero_nf}"><i class="fas fa-trash text-danger"></i> Excluir</button></li>'
            f"</ul></div>"
        )

        fornecedor_html = f"""
                <a href="javascript:void(0);" class="visualizar-docs" data-id="{nota.NotaFiscal.id}" data-numero="{nota.NotaFiscal.numero_nf}" title="Visualizar Documentos">
                    {nota.NotaFiscal.nome_emitente or '-'}
                </a>
            """

        checkbox_html = (
            f'<input type="checkbox" class="form-check-input nf-checkbox" '
            f'value="{nota.NotaFiscal.id}" data-id="{nota.NotaFiscal.id}" '
            f'aria-label="Selecionar nota {nota.NotaFiscal.numero_nf}">'
        )

        tipo_doc = getattr(nota.NotaFiscal, "tipo", None)
        if tipo_doc == 2:
            tipo_doc_label = "CTE"
        elif tipo_doc == 3:
            tipo_doc_label = "NFS"
        else:
            tipo_doc_label = "NFE"

        data.append(
            [
                checkbox_html,
                nota.NotaFiscal.numero_nf or "",
                tipo_doc_label,
                nota.NotaFiscal.data_emissao.strftime("%d/%m/%Y") if nota.NotaFiscal.data_emissao else "",
                vencimento_formatado,
                emitente,
                destinatario,
                fornecedor_html,
                f"R$ {nota.NotaFiscal.valor_total:.2f}" if nota.NotaFiscal.valor_total else "R$ 0.00",
                status_html,
                acoes_html,
            ]
        )

    return dt.resposta(data, total_geral, total_filtrado)
