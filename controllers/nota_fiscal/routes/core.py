import logging
import time
from datetime import datetime

from flask import render_template, request
from flask_login import login_required
from sqlalchemy import func

from models.database import db
from models.nota_fiscal import CNPJS_FILIAIS, CNPJS_MATRIZ, NotaFiscal, NotaFiscalItem

from .. import nota_fiscal_bp
from ..services.query_notas import api_get_dados_notas_fiscais

logger = logging.getLogger(__name__)


@nota_fiscal_bp.before_request
@login_required
def verificar_permissao():
    # Mantido por compatibilidade. Caso volte a existir regra, centralizar aqui.
    return None


@nota_fiscal_bp.route("/")
@login_required
def index():
    return render_template("notas_fiscais/index.html")


@nota_fiscal_bp.route("/tabela-notas-fiscais")
@login_required
def tabela_notas_fiscais():
    inicio = time.time()
    page = request.args.get("page", 1, type=int)
    per_page = 50

    query = api_get_dados_notas_fiscais(request)
    logger.debug(f"query montada em {time.time() - inicio:.3f}s")

    # Soma total com filtros aplicados (usando where criteria da query)
    valor_total_raw = (
        db.session.query(func.coalesce(func.sum(NotaFiscal.valor_total), 0))
        .select_from(NotaFiscal)
        .join(NotaFiscalItem)
        .filter(NotaFiscalItem.nf_id == NotaFiscal.id, *query._where_criteria)
        .scalar()
    )
    valor_total = float(valor_total_raw) if valor_total_raw else 0.0
    valor_total_formatado = f"R$ {valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    notas_fiscais_pagina = pagination.items

    notas_fiscais_pagina_upload = []
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

        nota_dict = {
            "NotaFiscal": nota.NotaFiscal,
            "pagamento": getattr(nota, "pagamento", 0),
            "upload": getattr(nota, "upload", 0),
            "upload_protocolo": getattr(nota, "upload_protocolo", 0),
            "upload_reembolso": getattr(nota, "upload_reembolso", 0),
            "upload_arquivei": getattr(nota, "upload_arquivei", 0),
            "vencimento": vencimento_str,
            "vencimento_formatado": vencimento_formatado,
            "id": nota.NotaFiscal.id,
            "numero_nf": nota.NotaFiscal.numero_nf,
        }

        nota_dict["emitente"] = (
            "Matriz"
            if nota.NotaFiscal.cnpj_emitente in CNPJS_MATRIZ
            else "Filiais"
            if nota.NotaFiscal.cnpj_emitente in CNPJS_FILIAIS
            else "Terceiros"
        )
        nota_dict["destinatario"] = (
            "Matriz"
            if nota.NotaFiscal.cnpj_destinatario in CNPJS_MATRIZ
            else "Filiais"
            if nota.NotaFiscal.cnpj_destinatario in CNPJS_FILIAIS
            else "Terceiros"
        )

        try:
            nota_dict["NotaFiscal"].emitente = nota_dict["emitente"]
            nota_dict["NotaFiscal"].destinatario = nota_dict["destinatario"]
        except (AttributeError, TypeError):
            pass

        notas_fiscais_pagina_upload.append(nota_dict)

    filtros_params = dict(request.args)
    filtros_params.pop("page", None)

    return render_template(
        "notas_fiscais/notas_tabela.html",
        pagination=pagination,
        notas_fiscais=notas_fiscais_pagina_upload,
        total_resultados=pagination.total,
        valor_total=valor_total_formatado,
        filtros_params=filtros_params,
    )


