"""
Exportação SPED: gera Excel de CTE com abas Dentro do Estado e Fora do Estado.
Colunas: emissão, numero, transportadora, total, icms (12% do total).
"""
import io
import json
import logging

import pandas as pd
from flask import request, send_file
from flask_login import login_required

from .. import nota_fiscal_bp
from ..services.query_notas import api_get_dados_notas_fiscais

logger = logging.getLogger(__name__)

ALIQUOTA_ICMS_CTE = 0.12  # 12%


def _linha_cte_sped(nota):
    """Monta uma linha do Excel SPED para um CTE: emissão, numero, transportadora, total, icms."""
    valor_total = float(nota.valor_total) if nota.valor_total is not None else 0.0
    icms = round(valor_total * ALIQUOTA_ICMS_CTE, 2)
    return {
        "emissão": nota.data_emissao.strftime("%d/%m/%Y") if nota.data_emissao else "",
        "numero": nota.numero_nf or "",
        "transportadora": nota.nome_emitente or "",
        "total": valor_total,
        "icms": icms,
    }


def _cte_dentro_ou_fora_estado(nota):
    """
    Usa dados_adicionais (uf_inicio, uf_destino) para classificar CTE.
    Retorna 'dentro' se uf_inicio == uf_destino, senão 'fora'.
    Se não houver UF, considera 'fora'.
    """
    from models.fornecedor import Fornecedor
    fornecedor = Fornecedor.query.filter_by(cnpj=nota.cnpj_emitente).first()
    if not fornecedor:
        return "fora"
    uf = fornecedor.estado
    if uf == "ES":
        return "dentro"
    else:
        return "fora"


@nota_fiscal_bp.route("/exportar-sped")
@login_required
def exportar_sped():
    """
    Exporta CTEs filtrados para Excel SPED: uma planilha com abas
    "Dentro do Estado" e "Fora do Estado", colunas emissão, numero, transportadora, total, icms (12% do total).
    """
    query = api_get_dados_notas_fiscais(request)
    rows = query.all()

    dentro_estado = []
    fora_estado = []

    for row in rows:
        nota = getattr(row, "NotaFiscal", None) or row[0]
        if getattr(nota, "tipo", None) != 2:
            continue
        linha = _linha_cte_sped(nota)
        if _cte_dentro_ou_fora_estado(nota) == "dentro":
            dentro_estado.append(linha)
        else:
            fora_estado.append(linha)

    colunas = ["emissão", "numero", "transportadora", "total", "icms"]
    # Índice das colunas total e icms (0-based: D=3, E=4)
    col_total = 3
    col_icms = 4
    # Larguras das colunas (emissão, numero, transportadora, total, icms)
    larguras = [12.5, 15.2, 49, 17.2, 18.9]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        fmt_header = None
        fmt_geral = None
        fmt_moeda = None
        for nome_aba, dados in [
            ("1352-FRETE DENTRO DO ESTADO", dentro_estado),
            ("2352 - FRETE FORA DO ES", fora_estado),
        ]:
            if fmt_header is None:
                fmt_header = writer.book.add_format({
                    "bold": True,
                    "font_name": "Arial",
                    "font_size": 12,
                    "align": "center",
                })
                fmt_geral = writer.book.add_format({
                    "font_name": "Arial",
                    "font_size": 12,
                    "align": "center",
                })
                # Formato contábil: R$ #.##0,00 ; negativos entre parênteses
                fmt_moeda = writer.book.add_format({
                    "num_format": '_("R$"* #.##0,00_);_("R$"* (#.##0,00);_("R$"* "-"??_);_(@_)',
                    "font_name": "Arial",
                    "font_size": 12,
                    "align": "center",
                })
            df = pd.DataFrame(dados, columns=colunas)
            df.to_excel(writer, index=False, sheet_name=nome_aba)
            ws = writer.sheets[nome_aba]
            n = len(dados)
            # Larguras das colunas
            for col, larg in enumerate(larguras):
                ws.set_column(col, col, larg)
            # Cabeçalho em negrito, Arial 12, centro
            for col, titulo in enumerate(colunas):
                ws.write_string(0, col, titulo, fmt_header)
            # Dados: Arial 12, centro; total e icms com formato moeda
            for i in range(n):
                ws.write_string(i + 1, 0, dados[i]["emissão"], fmt_geral)
                ws.write_string(i + 1, 1, str(dados[i]["numero"]), fmt_geral)
                ws.write_string(i + 1, 2, dados[i]["transportadora"], fmt_geral)
                ws.write_number(i + 1, col_total, dados[i]["total"], fmt_moeda)
                ws.write_number(i + 1, col_icms, dados[i]["icms"], fmt_moeda)
            # Totalizador
            row_totalizador = n + 1
            last_row = n + 1
            ws.write_string(row_totalizador, 0, "", fmt_geral)
            ws.write_string(row_totalizador, 1, "", fmt_geral)
            ws.write_string(row_totalizador, 2, "Total", fmt_geral)
            ws.write_formula(
                row_totalizador, col_total, f"=SUM(D2:D{last_row})", fmt_moeda
            )
            ws.write_formula(
                row_totalizador, col_icms, f"=SUM(E2:E{last_row})", fmt_moeda
            )

    output.seek(0)
    return send_file(
        output,
        download_name="cte_sped.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
