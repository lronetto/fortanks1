"""Payload DataTables server-side para a lista de cargos x salário (PLR)."""

from __future__ import annotations

from flask import url_for

from utils.datatable_helper import DataTableParams

from models.cargo_salario import CargoSalario

# Ordem das colunas no HTML/JS (0 = Cargo … 4 = Ações).
COLUMN_KEYS = ("cargo", "mes", "ano", "salario", "acoes")


def _formatar_salario_br(val) -> str:
    if val is None:
        return "-"
    try:
        s = f"{float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return s
    except (TypeError, ValueError):
        return "-"


def montar_payload_cargos_salarios_datatables(dt: DataTableParams, csrf_token: str):
    q = CargoSalario.query.order_by(CargoSalario.data.desc(), CargoSalario.id.desc())
    internas = []
    for item in q:
        cargo_nome = item.cargo.nome if item.cargo else "-"
        mes = item.mes
        ano = item.ano
        sal_fmt = _formatar_salario_br(item.salario)
        excluir_url = url_for("plr.cargo_salario_excluir", id=item.id)
        acoes = (
            f'<button type="button" class="btn btn-sm btn-primary btn-editar-cargo-salario" '
            f'data-id="{item.id}" title="Editar"><i class="fas fa-edit"></i></button> '
            f'<form method="POST" action="{excluir_url}" class="d-inline" '
            f'onsubmit="return confirm(\'Excluir este registro?\');">'
            f'<input type="hidden" name="csrf_token" value="{csrf_token}">'
            f'<button type="submit" class="btn btn-sm btn-danger" title="Excluir">'
            f'<i class="fas fa-trash"></i></button></form>'
        )
        internas.append(
            {
                "cargo": cargo_nome,
                "mes": str(mes) if mes is not None else "-",
                "ano": str(ano) if ano is not None else "-",
                "salario": sal_fmt,
                "acoes": acoes,
                "_cargo_lower": (cargo_nome or "").lower(),
                "_mes": int(mes) if mes is not None else 0,
                "_ano": int(ano) if ano is not None else 0,
                "_sal": float(item.salario) if item.salario is not None else 0.0,
                "_data_ord": item.data.toordinal() if item.data else 0,
                "_id": item.id,
            }
        )

    records_total = len(internas)

    if dt.search:
        qtxt = dt.search.lower()
        internas = [
            r
            for r in internas
            if qtxt in r["_cargo_lower"]
            or qtxt in (r["mes"] or "").lower()
            or qtxt in (r["ano"] or "").lower()
            or qtxt in (r["salario"] or "").lower()
        ]
    records_filtered = len(internas)

    if 0 <= dt.order_col < len(COLUMN_KEYS):
        key = COLUMN_KEYS[dt.order_col]
        rev = dt.order_dir == "desc"
        if key == "cargo":
            internas.sort(key=lambda r: r["_cargo_lower"], reverse=rev)
        elif key == "mes":
            internas.sort(key=lambda r: (r["_mes"], r["_data_ord"]), reverse=rev)
        elif key == "ano":
            internas.sort(key=lambda r: (r["_ano"], r["_mes"]), reverse=rev)
        elif key == "salario":
            internas.sort(key=lambda r: r["_sal"], reverse=rev)
        elif key == "acoes":
            internas.sort(key=lambda r: r["_data_ord"], reverse=True)

    chaves_publicas = ("cargo", "mes", "ano", "salario", "acoes")
    if dt.length == -1:
        fatia = internas[dt.start :]
    else:
        per_page = max(1, min(dt.length, 500))
        fatia = internas[dt.start : dt.start + per_page]
    data = [{k: r[k] for k in chaves_publicas} for r in fatia]

    return dt.resposta(data, records_total, records_filtered)
