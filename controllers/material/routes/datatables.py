"""
DataTables server-side para listagem de materiais.
"""
import logging

from flask import jsonify, request, url_for
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


def _esc(val):
    """Escapa valor para uso em atributo HTML."""
    return (
        str(val or "")
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _mat_code(val):
    """Envolve código em span monospace."""
    if val:
        return f'<span class="mat-code">{_esc(val)}</span>'
    return "—"


def _imagem_html(img_id, nome):
    """Gera HTML da miniatura ou traço."""
    if not img_id:
        return '<span class="text-muted small">—</span>'
    src = url_for("material.material_imagem_inline", upload_id=img_id)
    return (
        f'<img src="{_esc(src)}" alt="" role="button" tabindex="0"'
        f' title="Clique para ampliar"'
        f' class="img-thumbnail rounded ft-thumb materiais-thumb-img materiais-thumb-ampliar"'
        f' data-full-src="{_esc(src)}" data-nome-material="{_esc(nome)}">'
    )


def _acoes_html(m, mascara, codigo_sox, codigo_alterdata, codigo_mega,
                plano_codigo, plano_desc, unidade_id, unidade_nome, em_uso, img_id):
    """Gera HTML do dropdown de ações."""
    excluir_url = url_for("material.excluir", id=m.id)

    vis_attrs = (
        f'data-id="{m.id}"'
        f' data-codigo="{_esc(codigo_sox)}"'
        f' data-codigo_erp="{_esc(codigo_alterdata)}"'
        f' data-codigo-alterdata="{_esc(codigo_alterdata)}"'
        f' data-codigo-mega="{_esc(codigo_mega)}"'
        f' data-nome="{_esc(m.nome or "")}"'
        f' data-categoria="{_esc(m.categoria or "")}"'
        f' data-unidade="{_esc(unidade_id)}"'
        f' data-unidade-nome="{_esc(unidade_nome)}"'
        f' data-plano_conta="{_esc(plano_codigo)}"'
        f' data-plano-descricao="{_esc(plano_desc)}"'
        f' data-descricao="{_esc(m.descricao or "")}"'
    )

    edit_attrs = (
        f'data-id="{m.id}"'
        f' data-codigo="{_esc(codigo_sox)}"'
        f' data-codigo-erp="{_esc(codigo_alterdata)}"'
        f' data-nome="{_esc(m.nome or "")}"'
        f' data-codigo-alterdata="{_esc(codigo_alterdata)}"'
        f' data-codigo-mega="{_esc(codigo_mega)}"'
        f' data-categoria="{_esc(m.categoria or "")}"'
        f' data-plano-conta="{_esc(plano_codigo)}"'
        f' data-descricao="{_esc(m.descricao or "")}"'
        f' data-unidade="{_esc(unidade_id)}"'
        f' data-mascara="{_esc(mascara)}"'
        f' data-formula-calculo="{_esc(m.formula_calculo or "")}"'
        f' data-imagem-upload-id="{_esc(str(img_id) if img_id else "")}"'
    )

    excluir_label    = "Em uso" if em_uso else "Excluir"
    excluir_icon_cor = "secondary" if em_uso else "danger"
    excluir_class    = f'dropdown-item btn-excluir-material{" disabled" if em_uso else ""}'
    excluir_attrs    = (
        f'data-id="{m.id}"'
        f' data-nome="{_esc(m.nome or "")}"'
        f' data-excluir-url="{_esc(excluir_url)}"'
        + (' disabled' if em_uso else '')
    )

    return (
        '<div class="ft-acoes-dropdown dropdown">'
        '<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button"'
        ' data-bs-toggle="dropdown" aria-expanded="false" title="Ações">'
        '<i class="fas fa-ellipsis-v"></i></button>'
        '<ul class="dropdown-menu dropdown-menu-end">'
        f'<li><button type="button" class="dropdown-item btn-visualizar" {vis_attrs}>'
        '<i class="fas fa-eye text-info"></i> Visualizar</button></li>'
        f'<li><button type="button" class="dropdown-item btn-editar" {edit_attrs}>'
        '<i class="fas fa-edit text-primary"></i> Editar</button></li>'
        '<li><hr class="dropdown-divider"></li>'
        f'<li><button type="button" class="{excluir_class}" {excluir_attrs}>'
        f'<i class="fas fa-trash text-{excluir_icon_cor}"></i> {excluir_label}</button></li>'
        '</ul></div>'
    )


@material_bp.route("/datatables", methods=["GET"])
@login_required
def materiais_datatables():
    """JSON server-side para DataTables da listagem de materiais."""
    try:
        draw   = int(request.args.get("draw", 1))
        start  = int(request.args.get("start", 0))
        length = int(request.args.get("length", 25))

        # Filtros vindos do formulário (padrão serializado no front) + fallback legado
        search_value = (
            request.args.get("search_term")
            or request.args.get("search")
            or request.args.get("search[value]")
            or ""
        ).strip()

        category_filters = []
        categorias_lista = [c.strip() for c in request.args.getlist("categoria") if c and c.strip()]
        if categorias_lista:
            category_filters = categorias_lista
        else:
            cats_csv = (request.args.get("filtro_categorias_csv") or "").strip()
            if cats_csv:
                category_filters = [c.strip() for c in cats_csv.split(",") if c.strip()]

        query = (
            Materiais.query
            .outerjoin(Unidades,   Materiais.unidade_id    == Unidades.id)
            .outerjoin(PlanoConta, Materiais.plano_conta_id == PlanoConta.id)
        )

        records_total = Materiais.query.count()

        if search_value:
            term = f"%{search_value}%"
            clauses = [
                Materiais.nome.ilike(term),
                Materiais.dados_adicionais.ilike(term),
                Materiais.mascara.ilike(term),
            ]
            if search_value.isdigit():
                clauses.append(Materiais.id == int(search_value))
            query = query.filter(or_(*clauses))

        if category_filters:
            query = query.filter(Materiais.categoria.in_(category_filters))

        records_filtered = query.count()

        order_column_index = int(request.args.get("order[0][column]", 6))
        order_dir          = request.args.get("order[0][dir]", "asc")

        # índices alinhados com a posição na array de dados retornada abaixo
        # índice 5 (Cód. Mega) omitido — calculado de dados_adicionais, não é coluna ordenável
        column_map = {
            1:  Materiais.id,
            2:  Materiais.mascara,
            3:  Materiais.id,
            4:  Materiais.dados_adicionais,
            6:  Materiais.nome,
            7:  Materiais.categoria,
            8:  Unidades.nome,
            9:  PlanoConta.descricao,
            10: Materiais.criado_em,
        }

        order_col = column_map.get(order_column_index, Materiais.nome)
        if order_dir == "desc":
            query = query.order_by(order_col.desc())
        else:
            query = query.order_by(order_col.asc())

        if length == -1:
            remaining = max(0, (records_filtered or 0) - start)
            cap   = min(remaining, 10000)
            items = query.offset(start).limit(cap).all() if cap else []
        else:
            lim   = max(1, min(length, 500))
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
            extras           = parse_dados_json(m.dados_adicionais)
            mascara          = _normalizar_codigo_inteiro(m.mascara)
            codigo_sox       = _normalizar_codigo_inteiro(extras.get("codigo_sox"))
            codigo_alterdata = _normalizar_codigo_inteiro(extras.get("codigo_alterdata"))
            codigo_mega      = _normalizar_codigo_inteiro(extras.get("codigo_mega") or extras.get("cod_mega"))
            plano_codigo     = m.plano_conta or ""
            plano_desc       = (m.plano_conta_obj.descricao if m.plano_conta_obj else (m.plano_conta or "")).strip()
            unidade_id       = m.unidade_id or ""
            unidade_nome     = m.unidade_obj.nome if m.unidade_obj else ""
            img_id           = m.imagem_upload_id
            em_uso           = (uso_por.get(m.id, 0) or 0) > 0

            data.append([
                _imagem_html(img_id, m.nome or ""),                           # 0  Img
                m.id,                                                          # 1  ID
                _mat_code(mascara),                                            # 2  Máscara
                _mat_code(codigo_sox),                                         # 3  Cód. SOX
                _mat_code(codigo_alterdata),                                   # 4  Cód. Alterdata
                _mat_code(codigo_mega),                                        # 5  Cód. Mega
                m.nome or "",                                                  # 6  Nome
                m.categoria or "",                                             # 7  Categoria
                unidade_nome or "—",                                           # 8  Unidade
                plano_desc or "—",                                             # 9  Plano de Conta
                m.criado_em.strftime("%d/%m/%Y") if m.criado_em else "",      # 10 Criado em
                _acoes_html(                                                    # 11 Ações
                    m, mascara, codigo_sox, codigo_alterdata, codigo_mega,
                    plano_codigo, plano_desc, unidade_id, unidade_nome, em_uso, img_id,
                ),
            ])

        return jsonify({
            "draw":            draw,
            "recordsTotal":    records_total,
            "recordsFiltered": records_filtered or 0,
            "data":            data,
        })

    except Exception as e:
        logger.error("Erro materiais_datatables: %s", e, exc_info=True)
        return jsonify({
            "draw":            int(request.args.get("draw", 1)),
            "recordsTotal":    0,
            "recordsFiltered": 0,
            "data":            [],
            "error":           str(e),
        }), 500
