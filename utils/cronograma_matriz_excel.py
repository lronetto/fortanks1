"""
Exportação da matriz semanal para Excel (xlsxwriter): cores por posição no tempo e heatmap de dias.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List

import xlsxwriter


def _hex_gradiente_tempo(indice_semana: int, n_semanas: int) -> str:
    """Colunas de semana: gradiente do início ao fim do intervalo (azul claro → verde claro)."""
    if n_semanas <= 0:
        return 'FFFFFF'
    t = 0.0 if n_semanas == 1 else indice_semana / (n_semanas - 1)
    r1, g1, b1 = 221, 235, 247
    r2, g2, b2 = 198, 239, 206
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f'{r:02X}{g:02X}{b:02X}'


def _hex_heatmap_dias(val: float, vmax: float) -> str:
    """Branco → azul conforme intensidade (dias / máximo da folha)."""
    if vmax <= 1e-12:
        return 'FFFFFF'
    t = max(0.0, min(1.0, float(val) / vmax))
    r = int(255 - (255 - 91) * t)
    g = int(255 - (255 - 155) * t)
    b = int(255 - (255 - 213) * t)
    return f'{r:02X}{g:02X}{b:02X}'


def _fmt_heatmap_cached(
    workbook: 'xlsxwriter.Workbook',
    cache: Dict[str, Any],
    hex_color: str,
    *,
    bold: bool = False,
    num_format: str = '0.00',
) -> Any:
    key = (hex_color, bold, num_format)
    if key not in cache:
        cache[key] = workbook.add_format(
            {
                'bg_color': hex_color,
                'border': 1,
                'num_format': num_format,
                'bold': bold,
            }
        )
    return cache[key]


def build_matriz_semanal_xlsx_bytes(
    *,
    nome_projeto: str,
    semanas: List[Dict[str, Any]],
    linhas: List[Dict[str, Any]],
    barras_dias_semana: List[float],
    max_dias_previsto_grid: float,
    max_dias_barras_totais: float,
) -> bytes:
    """
    Duas abas:
    - Matriz: P/R/PA/RA por semana com fundo em gradiente temporal nas colunas de semana.
    - Dias: dias previstos por item × semana com heatmap; totais na última linha.
    """
    n = len(semanas)
    week_keys = [s['key'] for s in semanas]

    buf = BytesIO()
    workbook = xlsxwriter.Workbook(buf, {'in_memory': True})
    fmt_cache: Dict[str, Any] = {}

    fmt_title = workbook.add_format({'bold': True, 'font_size': 14})
    fmt_meta = workbook.add_format({'italic': True, 'font_color': '666666'})
    fmt_head_fix = workbook.add_format({'bold': True, 'bg_color': 'E7E6E6', 'border': 1, 'text_wrap': True})
    fmt_cell_fix = workbook.add_format({'border': 1, 'valign': 'top'})
    fmt_prazo = workbook.add_format({'border': 1, 'num_format': '0.00', 'align': 'right'})
    fmt_dc = workbook.add_format({'border': 1, 'num_format': '0', 'align': 'right'})

    # --- Aba 1: Matriz (placas) ---
    ws1 = workbook.add_worksheet('Matriz placas')
    ws1.set_row(0, 38)
    ws1.merge_range(0, 0, 0, 3 + n, f'Matriz semanal — {nome_projeto}', fmt_title)
    ws1.write(1, 0, 'Previsto = placas; Real = concretagens na semana; PA/RA = acumulados.', fmt_meta)

    header_row = 3
    ws1.write(header_row, 0, 'Índice', fmt_head_fix)
    ws1.write(header_row, 1, 'Item', fmt_head_fix)
    ws1.write(header_row, 2, 'Prazo (dias)', fmt_head_fix)
    ws1.write(header_row, 3, 'Dias corridos', fmt_head_fix)

    for j in range(n):
        s = semanas[j]
        lab = s.get('label', '')
        lf = s.get('label_full', '')
        fh = workbook.add_format(
            {
                'bold': True,
                'bg_color': _hex_gradiente_tempo(j, n),
                'border': 1,
                'text_wrap': True,
                'align': 'center',
                'valign': 'vcenter',
            }
        )
        ws1.write(header_row, 4 + j, f'{lab}\n{lf}', fh)

    data_start = header_row + 1
    for i, row in enumerate(linhas):
        r = data_start + i
        ws1.write(r, 0, row.get('indice') or '', fmt_cell_fix)
        ws1.write(r, 1, row.get('nome') or '', fmt_cell_fix)
        ws1.write_number(r, 2, float(row.get('prazo_dias_total') or 0), fmt_prazo)
        ws1.write_number(r, 3, int(row.get('dias_corridos') or 0), fmt_dc)
        for j in range(n):
            wk = week_keys[j]
            pv = float(row.get('previsto', {}).get(wk, 0) or 0)
            rv = float(row.get('real', {}).get(wk, 0) or 0)
            pav = float(row.get('previsto_acum', {}).get(wk, 0) or 0)
            rav = float(row.get('real_acum', {}).get(wk, 0) or 0)
            txt = f'P {pv:.0f}\nR {rv:.0f}\nPA {pav:.0f}\nRA {rav:.0f}'
            fc = workbook.add_format(
                {
                    'bg_color': _hex_gradiente_tempo(j, n),
                    'border': 1,
                    'text_wrap': True,
                    'valign': 'top',
                    'font_size': 9,
                }
            )
            ws1.write(r, 4 + j, txt, fc)

    ws1.set_column(0, 0, 10)
    ws1.set_column(1, 1, 36)
    ws1.set_column(2, 2, 11)
    ws1.set_column(3, 3, 10)
    for j in range(n):
        ws1.set_column(4 + j, 4 + j, 11)
    if n > 0:
        ws1.freeze_panes(header_row + 1, 4)

    # --- Aba 2: Dias (heatmap no tempo) ---
    ws2 = workbook.add_worksheet('Dias previsto')
    ws2.merge_range(0, 0, 0, 3 + n, f'Dias de trabalho previstos — {nome_projeto}', fmt_title)
    ws2.write(1, 0, 'Células coloridas por intensidade (dias); colunas com gradiente temporal.', fmt_meta)

    hrow = 3
    ws2.write(hrow, 0, 'Índice', fmt_head_fix)
    ws2.write(hrow, 1, 'Item', fmt_head_fix)
    ws2.write(hrow, 2, 'Prazo (dias)', fmt_head_fix)
    ws2.write(hrow, 3, 'Dias corridos', fmt_head_fix)
    for j in range(n):
        s = semanas[j]
        lab = s.get('label', '')
        lf = s.get('label_full', '')
        fh = workbook.add_format(
            {
                'bold': True,
                'bg_color': _hex_gradiente_tempo(j, n),
                'border': 1,
                'text_wrap': True,
                'align': 'center',
            }
        )
        ws2.write(hrow, 4 + j, f'{lab}\n{lf}', fh)

    dstart = hrow + 1
    vmax = max(float(max_dias_previsto_grid or 1), 1e-9)

    for i, row in enumerate(linhas):
        r = dstart + i
        ws2.write(r, 0, row.get('indice') or '', fmt_cell_fix)
        ws2.write(r, 1, row.get('nome') or '', fmt_cell_fix)
        ws2.write_number(r, 2, float(row.get('prazo_dias_total') or 0), fmt_prazo)
        ws2.write_number(r, 3, int(row.get('dias_corridos') or 0), fmt_dc)
        dps = row.get('dias_previsto_semana') or {}
        for j in range(n):
            wk = week_keys[j]
            val = float(dps.get(wk, 0) or 0)
            hx = _hex_heatmap_dias(val, vmax)
            f = _fmt_heatmap_cached(workbook, fmt_cache, hx, bold=False)
            ws2.write_number(r, 4 + j, val, f)

    # Linha total
    if barras_dias_semana and len(barras_dias_semana) == n:
        tr = dstart + len(linhas)
        ws2.merge_range(tr, 0, tr, 1, 'Total (dias / semana)', fmt_head_fix)
        ws2.merge_range(tr, 2, tr, 3, '', fmt_head_fix)
        vmax_tot = max(float(max_dias_barras_totais or 1), 1e-9)
        for j in range(n):
            val = float(barras_dias_semana[j] or 0)
            hx = _hex_heatmap_dias(val, vmax_tot)
            f = _fmt_heatmap_cached(workbook, fmt_cache, hx, bold=True)
            ws2.write_number(tr, 4 + j, val, f)

    ws2.set_column(0, 0, 10)
    ws2.set_column(1, 1, 36)
    ws2.set_column(2, 2, 11)
    ws2.set_column(3, 3, 10)
    for j in range(n):
        ws2.set_column(4 + j, 4 + j, 10)
    if n > 0:
        ws2.freeze_panes(hrow + 1, 4)

    workbook.close()
    buf.seek(0)
    return buf.getvalue()
