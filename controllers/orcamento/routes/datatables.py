"""Endpoints e lógica DataTables do módulo de orçamentos."""

from __future__ import annotations

import logging

from flask import jsonify, request, url_for
from flask_login import login_required
from sqlalchemy import case, func, or_
from sqlalchemy.orm import aliased

from models.contrato import Contrato
from models.database import db
from models.material import Materiais
from models.orcamento import ItemOrcamento, Orcamento
from utils.datatable_helper import DataTableParams
from utils.formatting import formatar_decimal_br, formatar_moeda
from utils.parser import ToDecimal

from .. import orcamento_bp

logger = logging.getLogger(__name__)


ORCAMENTOS_COLUMN_KEYS = (
    "id",
    "nome",
    "data",
    "status",
    "contrato",
    "itens",
    "criado_em",
    "_acoes",
)

ITENS_COLUMN_KEYS = (
    "id",
    "descricao_item",
    "material",
    "unidade",
    "quantidade",
    "valor",
    "total",
    "valor_num",
    "total_num",
    "grupo",
)


def _fmt_data(valor):
    if not valor:
        return ""
    return valor.strftime("%d/%m/%Y")


def montar_payload_datatables_orcamentos(dt: DataTableParams, filtros: dict):
    orcamento_pai = aliased(Orcamento)
    grupo_orcamento_id = func.coalesce(
        orcamento_pai.vinculado_a_orcamento_id,
        Orcamento.vinculado_a_orcamento_id,
        Orcamento.id,
    )
    ordem_no_grupo = case(
        (Orcamento.vinculado_a_orcamento_id.is_(None), 0),
        else_=1,
    )

    subq_itens = (
        db.session.query(
            ItemOrcamento.orcamento_id.label("orcamento_id"),
            func.count(ItemOrcamento.id).label("qtd_itens"),
        )
        .group_by(ItemOrcamento.orcamento_id)
        .subquery()
    )

    base = (
        db.session.query(
            Orcamento.id,
            Orcamento.nome,
            Orcamento.data,
            Orcamento.status,
            Orcamento.criado_em,
            Orcamento.vinculado_a_orcamento_id,
            Contrato.nome.label("contrato_nome"),
            func.coalesce(subq_itens.c.qtd_itens, 0).label("qtd_itens"),
        )
        .outerjoin(orcamento_pai, orcamento_pai.id == Orcamento.vinculado_a_orcamento_id)
        .outerjoin(Contrato, Contrato.id == Orcamento.contrato_id)
        .outerjoin(subq_itens, subq_itens.c.orcamento_id == Orcamento.id)
    )

    status = (filtros.get("status") or "").strip()
    if status:
        base = base.filter(Orcamento.status == status)

    total_geral = base.count()

    if dt.search:
        termo = f"%{dt.search}%"
        base = base.filter(
            or_(
                Orcamento.nome.ilike(termo),
                Orcamento.status.ilike(termo),
                Contrato.nome.ilike(termo),
            )
        )

    total_filtrado = base.count()

    if 0 <= dt.order_col < len(ORCAMENTOS_COLUMN_KEYS):
        chave = ORCAMENTOS_COLUMN_KEYS[dt.order_col]
    else:
        chave = "nome"

    order_map = {
        "id": Orcamento.id,
        "nome": Orcamento.nome,
        "data": Orcamento.data,
        "status": Orcamento.status,
        "contrato": Contrato.nome,
        "itens": func.coalesce(subq_itens.c.qtd_itens, 0),
        "criado_em": Orcamento.criado_em,
    }
    coluna_ordenacao = order_map.get(chave, Orcamento.nome)
    base = base.order_by(grupo_orcamento_id.asc(), ordem_no_grupo.asc())
    if dt.order_dir == "desc":
        base = base.order_by(coluna_ordenacao.desc())
    else:
        base = base.order_by(coluna_ordenacao.asc())

    if dt.length == -1:
        rows = base.offset(dt.start).all()
    else:
        per_page = max(1, min(dt.length, 500))
        rows = base.offset(dt.start).limit(per_page).all()

    data = []
    for row in rows:
        nome_exibicao = row.nome or ""
        if row.vinculado_a_orcamento_id:
            nome_exibicao = f"-> {nome_exibicao}"

        viz_url = url_for("orcamento.visualizar", orcamento_id=row.id)
        acoes_html = (
            '<div class="ft-acoes-dropdown dropdown">'
            '<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button"'
            ' data-bs-toggle="dropdown" aria-expanded="false" title="Ações">'
            '<i class="fas fa-ellipsis-v"></i></button>'
            '<ul class="dropdown-menu dropdown-menu-end">'
            f'<li><a class="dropdown-item" href="{viz_url}">'
            '<i class="fas fa-eye text-info"></i> Visualizar</a></li>'
            '<li><button type="button" class="dropdown-item ft-editar-orcamento"'
            f' data-orcamento-id="{row.id}">'
            '<i class="fas fa-edit text-primary"></i> Editar</button></li>'
            '<li><button type="button" class="dropdown-item text-danger ft-excluir-orcamento"'
            f' data-orcamento-id="{row.id}"><i class="fas fa-trash-alt me-1"></i>Apagar</button></li>'
            "</ul></div>"
        )
        data.append(
            [
                row.id,
                nome_exibicao,
                _fmt_data(row.data),
                row.status or "",
                row.contrato_nome or "—",
                int(row.qtd_itens or 0),
                _fmt_data(row.criado_em),
                acoes_html,
            ]
        )

    return dt.resposta(data, total_geral, total_filtrado)


def montar_payload_datatables_itens_orcamento(
    orcamento_id: int,
    dt: DataTableParams,
    filtros: dict | None = None,
):
    _ = filtros or {}

    base = (
        db.session.query(
            ItemOrcamento.id,
            ItemOrcamento.descricao_item,
            Materiais.nome.label("material_nome"),
            ItemOrcamento.unidade,
            ItemOrcamento.quantidade,
            ItemOrcamento.valor,
            (ItemOrcamento.quantidade * ItemOrcamento.valor).label("valor_total"),
            ItemOrcamento.grupo,
        )
        .outerjoin(Materiais, Materiais.id == ItemOrcamento.material_id)
        .filter(ItemOrcamento.orcamento_id == orcamento_id)
    )

    total_geral = base.count()

    if dt.search:
        termo = f"%{dt.search}%"
        base = base.filter(
            or_(
                ItemOrcamento.descricao_item.ilike(termo),
                ItemOrcamento.grupo.ilike(termo),
                ItemOrcamento.unidade.ilike(termo),
                Materiais.nome.ilike(termo),
            )
        )

    total_filtrado = base.count()

    if 0 <= dt.order_col < len(ITENS_COLUMN_KEYS):
        chave = ITENS_COLUMN_KEYS[dt.order_col]
    else:
        chave = "id"

    order_map = {
        "id": ItemOrcamento.id,
        "descricao_item": ItemOrcamento.descricao_item,
        "material": Materiais.nome,
        "unidade": ItemOrcamento.unidade,
        "quantidade": ItemOrcamento.quantidade,
        "valor": ItemOrcamento.valor,
        "total": ItemOrcamento.quantidade * ItemOrcamento.valor,
        "valor_num": ItemOrcamento.valor,
        "total_num": ItemOrcamento.quantidade * ItemOrcamento.valor,
        "grupo": ItemOrcamento.grupo,
    }
    coluna_ordenacao = order_map.get(chave, ItemOrcamento.id)
    if dt.order_dir == "desc":
        base = base.order_by(coluna_ordenacao.desc())
    else:
        base = base.order_by(coluna_ordenacao.asc())

    if dt.length == -1:
        rows = base.offset(dt.start).all()
    else:
        per_page = max(1, min(dt.length, 500))
        rows = base.offset(dt.start).limit(per_page).all()

    data = []
    for row in rows:
        vu = ToDecimal(row.valor) if row.valor is not None else 0.0
        vt = ToDecimal(row.valor_total) if row.valor_total is not None else 0.0
        data.append(
            {
                "id": row.id,
                "descricao_item": row.descricao_item or "-",
                "material": row.material_nome or "-",
                "unidade": row.unidade or "-",
                "quantidade": formatar_decimal_br(row.quantidade,2),
                "valor": formatar_moeda(row.valor),
                "total": formatar_moeda(row.valor_total),
                "valor_num": vu,
                "total_num": vt,
                "grupo": row.grupo.strip() if row.grupo else "",
            }
        )

    return dt.resposta(data, total_geral, total_filtrado)


@orcamento_bp.route("/api/datatables", methods=["GET"])
@login_required
def api_datatables():
    dt = DataTableParams()
    try:
        filtros = {
            "status": (request.args.get("status") or "").strip(),
        }
        return montar_payload_datatables_orcamentos(dt, filtros)
    except Exception as exc:
        logger.exception("Erro em api_datatables (orçamentos)")
        return (
            jsonify(
                {
                    "draw": dt.draw,
                    "recordsTotal": 0,
                    "recordsFiltered": 0,
                    "data": [],
                    "error": str(exc),
                }
            ),
            500,
        )


@orcamento_bp.route("/<int:orcamento_id>/api/itens/datatables", methods=["GET"])
@login_required
def api_datatables_itens(orcamento_id):
    dt = DataTableParams()
    try:
        filtros = {}
        return montar_payload_datatables_itens_orcamento(orcamento_id, dt, filtros)
    except Exception as exc:
        logger.exception("Erro em api_datatables_itens (orçamento %s)", orcamento_id)
        return (
            jsonify(
                {
                    "draw": dt.draw,
                    "recordsTotal": 0,
                    "recordsFiltered": 0,
                    "data": [],
                    "error": str(exc),
                }
            ),
            500,
        )
