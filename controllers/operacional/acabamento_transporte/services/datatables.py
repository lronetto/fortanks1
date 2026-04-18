"""Montagem do payload JSON para DataTables (acabamento/transporte)."""

from __future__ import annotations

import html

from utils.datatable_helper import DataTableParams

from .pecas import get_pecas

# Primeira coluna no cliente é checkbox (sem ordenação no servidor).
COLUMN_KEYS_DATATABLES = (
    "_checkbox",
    "tanque",
    "nome",
    "pista",
    "acabamento",
    "data_transporte",
    "transportadora",
    "placa_carreta",
    "nota_fiscal",
)


def montar_payload_datatables(dt: DataTableParams, filtros: dict):
    pecas = get_pecas(filtros)
    rows = []
    for peca in pecas:
        tanque_nome = peca.tanque.nome if peca.tanque else ""
        peca_nome = peca.nome or ""
        pista = str(peca.pista) if getattr(peca, "pista", None) else ""
        acabamento = str(peca.acabamento) if peca.acabamento else ""
        data_transporte = str(peca.transporte) if peca.transporte else ""
        transportadora = str(peca.transportadora) if peca.transportadora else ""
        placa = str(peca.placa_carreta) if peca.placa_carreta else ""
        nota = str(peca.nota_fiscal) if peca.nota_fiscal else ""
        tanque_id = peca.tanque_id if peca.tanque_id else (peca.tanque.id if peca.tanque else None)
        peca_id = getattr(peca, "id", None)
        nome_esc = html.escape(peca_nome)
        tanque_esc = html.escape(tanque_nome)
        acoes = (
            '<div class="btn-group btn-group-sm" role="group">'
            '<button type="button" class="btn btn-success btn-acao-acabamento" '
            'data-peca-id="{}" data-tanque-id="{}" data-peca-nome="{}" data-tanque-nome="{}" '
            'title="Registrar acabamento"><i class="fas fa-paint-roller"></i></button>'
            '<button type="button" class="btn btn-primary btn-acao-transporte" '
            'data-peca-id="{}" data-tanque-id="{}" data-peca-nome="{}" data-tanque-nome="{}" '
            'title="Registrar transporte"><i class="fas fa-truck"></i></button>'
            "</div>"
        ).format(
            peca_id or "",
            tanque_id or "",
            nome_esc,
            tanque_esc,
            peca_id or "",
            tanque_id or "",
            nome_esc,
            tanque_esc,
        )
        rows.append(
            {
                "tanque": tanque_nome,
                "nome": peca_nome,
                "pista": pista,
                "acabamento": acabamento,
                "data_transporte": data_transporte,
                "transportadora": transportadora,
                "placa_carreta": placa,
                "nota_fiscal": nota,
                "peca_id": peca_id,
                "tanque_id": tanque_id,
                "acoes": acoes,
            }
        )

    records_total = len(rows)

    if dt.search:
        search_lower = dt.search.lower()
        rows = [
            r
            for r in rows
            if search_lower in (r["tanque"] or "").lower()
            or search_lower in (r["nome"] or "").lower()
            or search_lower in (r["pista"] or "").lower()
            or search_lower in (r["acabamento"] or "").lower()
            or search_lower in (r["data_transporte"] or "").lower()
            or search_lower in (r["transportadora"] or "").lower()
            or search_lower in (r["placa_carreta"] or "").lower()
            or search_lower in (r["nota_fiscal"] or "").lower()
        ]
    records_filtered = len(rows)

    if 0 <= dt.order_col < len(COLUMN_KEYS_DATATABLES):
        key = COLUMN_KEYS_DATATABLES[dt.order_col]
        if key != "_checkbox":
            reverse = dt.order_dir == "desc"
            rows.sort(
                key=lambda r: (r[key] or "").lower() if isinstance(r[key], str) else (r[key] or ""),
                reverse=reverse,
            )

    if dt.length == -1:
        data = rows[dt.start :]
    else:
        per_page = max(1, min(dt.length, 500))
        data = rows[dt.start : dt.start + per_page]

    return dt.resposta(data, records_total, records_filtered)
