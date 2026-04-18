"""Exportação Excel da listagem de acabamento/transporte."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from .pecas import get_pecas


def exportar_excel_acabamento_transporte(filtros):
    data = get_pecas(filtros)
    rows = []
    for p in data:
        rows.append(
            {
                "nome": p.nome,
                "concretagem": p.data_concretagem,
                "acabamento": p.acabamento,
                "transporte": p.transporte,
                "transportadora": p.transportadora,
                "placa_carreta": p.placa_carreta,
                "nota_fiscal": p.nota_fiscal,
                "data_entrega": p.data_entrega,
                "tanque": p.tanque.nome,
            }
        )
    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Pecas")
    output.seek(0)
    return output
