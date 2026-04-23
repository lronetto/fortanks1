"""Service de DataTables para orçamentos."""

from __future__ import annotations

from sqlalchemy import func, or_

from flask import url_for

from models.database import db
from models.orcamento import ItemOrcamento, Orcamento
from models.contrato import Contrato
from utils.datatable_helper import DataTableParams


COLUMN_KEYS = (
    "id",
    "nome",
    "data",
    "status",
    "contrato",
    "itens",
    "criado_em",
    "_acoes",
)


def _fmt_data(valor):
    if not valor:
        return ""
    return valor.strftime("%d/%m/%Y")


def montar_payload_datatables_orcamentos(dt: DataTableParams, filtros: dict):
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
            Contrato.nome.label("contrato_nome"),
            func.coalesce(subq_itens.c.qtd_itens, 0).label("qtd_itens"),
        )
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

    if 0 <= dt.order_col < len(COLUMN_KEYS):
        chave = COLUMN_KEYS[dt.order_col]
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
                row.nome or "",
                _fmt_data(row.data),
                row.status or "",
                row.contrato_nome or "—",
                int(row.qtd_itens or 0),
                _fmt_data(row.criado_em),
                acoes_html,
            ]
        )

    return dt.resposta(data, total_geral, total_filtrado)
