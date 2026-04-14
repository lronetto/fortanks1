"""
DataTables server-side para listagem de materiais.
"""
import logging

from flask import jsonify, request
from flask_login import login_required
from sqlalchemy import func, or_

from models.database import db
from models.material import Materiais
from models.plano_conta import PlanoConta
from models.solicitacao import SolicitacoesItens
from models.unidade import Unidades
from utils.material_imagem_upload import parse_dados_json

from .. import material_bp

logger = logging.getLogger(__name__)


def _normalizar_codigo_inteiro(valor):
    txt = str(valor or "").strip()
    if not txt:
        return ""
    txt = txt.replace(",", ".")
    try:
        return str(int(float(txt)))
    except (TypeError, ValueError):
        if "." in txt:
            return txt.split(".", 1)[0]
        return txt


@material_bp.route("/datatables", methods=["POST"])
@login_required
def materiais_datatables():
    """JSON server-side para DataTables da listagem de materiais."""
    try:
        draw = int(request.form.get("draw", 1))
        start = int(request.form.get("start", 0))
        length = int(request.form.get("length", 25))

        search_value = (request.form.get("search[value]") or "").strip()

        cats_csv = (request.form.get("filtro_categorias_csv") or "").strip()
        category_filters = [c.strip() for c in cats_csv.split(",") if c.strip()]

        query = (
            Materiais.query.outerjoin(Unidades, Materiais.unidade_id == Unidades.id)
            .outerjoin(PlanoConta, Materiais.plano_conta_id == PlanoConta.id)
        )

        records_total = Materiais.query.count()

        if search_value:
            term = f"%{search_value}%"
            clauses = [
                Materiais.nome.ilike(term),
                Materiais.codigo.ilike(term),
                Materiais.codigo_erp.ilike(term),
                Materiais.mascara.ilike(term),
            ]
            if search_value.isdigit():
                clauses.append(Materiais.id == int(search_value))
            query = query.filter(or_(*clauses))

        if category_filters:
            query = query.filter(Materiais.categoria.in_(category_filters))

        records_filtered = query.count()

        order_column_index = int(request.form.get("order[0][column]", 6))
        order_dir = request.form.get("order[0][dir]", "asc")

        column_map = {
            1: Materiais.id,
            2: Materiais.mascara,
            3: Materiais.codigo,
            4: Materiais.codigo_erp,
            5: Materiais.codigo_erp,
            6: Materiais.nome,
            7: Materiais.categoria,
            8: Unidades.nome,
            9: PlanoConta.descricao,
            10: Materiais.criado_em,
        }

        order_col = column_map.get(order_column_index, Materiais.nome)
        if order_dir == "desc":
            query = query.order_by(order_col.desc())
        else:
            query = query.order_by(order_col.asc())

        if length == -1:
            remaining = max(0, (records_filtered or 0) - start)
            cap = min(remaining, 10000)
            items = query.offset(start).limit(cap).all() if cap else []
        else:
            lim = max(1, min(length, 500))
            items = query.offset(start).limit(lim).all()

        ids = [m.id for m in items]
        uso_por = {}
        if ids:
            rows = (
                db.session.query(SolicitacoesItens.material_id, func.count(SolicitacoesItens.id))
                .filter(SolicitacoesItens.material_id.in_(ids))
                .group_by(SolicitacoesItens.material_id)
                .all()
            )
            uso_por = {r[0]: r[1] for r in rows}

        data = []
        for m in items:
            extras = parse_dados_json(m.dados_adicionais)
            mascara = _normalizar_codigo_inteiro(m.mascara)
            codigo_sox = _normalizar_codigo_inteiro(extras.get("codigo_sox") or m.codigo)
            codigo_alterdata = _normalizar_codigo_inteiro(extras.get("codigo_alterdata") or m.codigo_erp)
            codigo_mega = _normalizar_codigo_inteiro(extras.get("codigo_mega") or extras.get("cod_mega"))
            plano_codigo = m.plano_conta or ""
            if m.plano_conta_obj:
                plano_desc = m.plano_conta_obj.descricao or ""
            else:
                plano_desc = (m.plano_conta or "").strip()
            unidade_id = m.unidade_id or ""
            unidade_nome = m.unidade_obj.nome if m.unidade_obj else ""
            img_id = m.imagem_upload_id
            data.append(
                {
                    "id": m.id,
                    "mascara": mascara,
                    "codigo_erp": codigo_alterdata,
                    "codigo": codigo_sox,
                    "codigo_sox": codigo_sox,
                    "codigo_alterdata": codigo_alterdata,
                    "codigo_mega": codigo_mega,
                    "nome": m.nome or "",
                    "categoria": m.categoria or "",
                    "unidade_id": unidade_id,
                    "unidade_nome": unidade_nome,
                    "plano_conta": plano_codigo,
                    "plano_conta_descricao": plano_desc if plano_desc else "-",
                    "criado_em": m.criado_em.strftime("%d/%m/%Y") if m.criado_em else "",
                    "descricao": m.descricao or "",
                    "formula_calculo": m.formula_calculo or "",
                    "imagem_upload_id": img_id,
                    "em_uso": (uso_por.get(m.id, 0) or 0) > 0,
                }
            )

        return jsonify(
            {
                "draw": draw,
                "recordsTotal": records_total,
                "recordsFiltered": records_filtered or 0,
                "data": data,
            }
        )
    except Exception as e:
        logger.error("Erro materiais_datatables: %s", e, exc_info=True)
        return (
            jsonify(
                {
                    "draw": int(request.form.get("draw", 1)),
                    "recordsTotal": 0,
                    "recordsFiltered": 0,
                    "data": [],
                    "error": str(e),
                }
            ),
            500,
        )
