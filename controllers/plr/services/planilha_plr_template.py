"""
Geração do relatório PLR preenchendo o template controllers/templates_excel/PLANILHA_PLR.xlsx.

Uma aba por mês (cópia da aba MES ou de uma aba-mês existente) e aba PAGAMENTO MOD.
Linhas de dados mensais: col. A id ``{colaborador_id}-{índice_segmento}`` (MATCH na PAGAMENTO);
a partir da col. B (bloco de dados a partir da linha 35: estilos 35 / 36 / 38). Critérios e P (%) só no mês em que o segmento vigora; demais
meses da linha em branco. P (%) mês e acumulado em
fórmulas; na PAGAMENTO MOD, meses/SOMA/P média/salário PLR/VPO/valor também em fórmulas
(reserva de dados 25–28: estilos 25 / 26 / 28; total a partir da linha 29).
Colaboradores com mudança de função no período geram uma linha por segmento.
"""
from __future__ import annotations

import calendar
import re
from copy import copy
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from models.cargo import Cargo
from models.cargo_salario import CargoSalario
from models.colaborador.utils.mudanca_funcao import funcao_id_vigente_em

from models.plr.constants import (
    CARGO_AJUDANTE,
    CARGO_OFICIAL,
    CARGOS_AJUDANTE,
    CARGOS_OFICIAL,
)
from models.plr.utils import tempo_de_casa_meses

from ..constantes import CRITERIOS_PADRAO_PLR

MESES_ABREV = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ']

PLANILHA_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / 'templates_excel' / 'PLANILHA_PLR.xlsx'
)

ABAS_MES_REGEX = re.compile(
    r'^(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s+\d{4}$',
    re.I,
)

FMT_EXCEL_PCT = '0.00%'
FMT_EXCEL_DATA = 'dd/mm/yyyy'
# Contábil (BRL) — padrão Excel: positivo; negativo entre parênteses; zero; texto
FMT_EXCEL_MOEDA_CONTABIL = (
    '_("R$ "* #.##0,00_);_("R$ "* (#.##0,00);_("R$ "* "-"??_);_(@_)'
)

# Aba mês: template com 4 linhas de reserva (35–38): 35 = primeira, 36 = meio (copiar ao inserir),
# 38 = última linha de dados; após a linha 71 replicamos o estilo da linha 36. Col. A = chave (MATCH).
MES_ROW_DATA_FIRST = 35
MES_ROW_STYLE_MIDDLE = 36
MES_ROW_STYLE_LAST_DATA = 38
MES_ROW_FORMAT_LAST = 71
MES_MAX_COL_STYLE = 31
FONT_INDEX_BRANCO = 'FFFFFF'

# PAGAMENTO MOD: reserva 25–28 (primeira / meio / última); linha 29+ = total e rodapé (preservar).
PAGAMENTO_ROW_DATA_FIRST = 25
PAGAMENTO_ROW_STYLE_MIDDLE = 26
PAGAMENTO_ROW_STYLE_LAST_DATA = 28
PAGAMENTO_ROW_TOTAL_FIRST = 29
PAGAMENTO_ROWS_DATA_TEMPLATE = PAGAMENTO_ROW_TOTAL_FIRST - PAGAMENTO_ROW_DATA_FIRST

# Template: meses em K–P (até 6); totais fixos Q–U, anotação V, Sal. atualizado X (col. 24)
PAGAMENTO_COL_MES_INI = 11  # K
PAGAMENTO_MESES_TEMPLATE_MAX = 6
PAGAMENTO_COL_SOMA = 17  # Q
PAGAMENTO_COL_P_MED = 18  # R
PAGAMENTO_COL_SAL_PLR = 19  # S
PAGAMENTO_COL_VPO = 20  # T
PAGAMENTO_COL_VALOR = 21  # U
PAGAMENTO_COL_ANOT = 22  # V
PAGAMENTO_COL_SAL_ATUAL = 24  # X (W vazio)


def _pagamento_mapa_colunas(num_meses: int) -> dict:
    """
    Colunas SOMA → Sal. atualizado no PAGAMENTO MOD.
    Até 6 meses: mesmo layout do template (K–P meses; Q–U totais; X salário base tabela).
    Mais de 6 meses: bloco de totais deslocado após a última coluna de mês (com coluna em branco antes do sal. atual).
    """
    if num_meses <= PAGAMENTO_MESES_TEMPLATE_MAX:
        return {
            'soma': PAGAMENTO_COL_SOMA,
            'p_med': PAGAMENTO_COL_P_MED,
            'sal_plr': PAGAMENTO_COL_SAL_PLR,
            'vpo': PAGAMENTO_COL_VPO,
            'valor': PAGAMENTO_COL_VALOR,
            'anot': PAGAMENTO_COL_ANOT,
            'sal_atual': PAGAMENTO_COL_SAL_ATUAL,
        }
    base = PAGAMENTO_COL_MES_INI + num_meses
    return {
        'soma': base,
        'p_med': base + 1,
        'sal_plr': base + 2,
        'vpo': base + 3,
        'valor': base + 4,
        'anot': base + 5,
        'sal_atual': base + 7,
    }


def _n_linhas_pagamento(resultado: list[dict], data_inicio: date, data_fechamento: date) -> int:
    """Quantidade de linhas de dados (colaborador × segmento de função)."""
    n = 0
    for linha_res in resultado:
        colab = linha_res.get('colaborador')
        if not colab:
            continue
        segs = segmentos_funcao_periodo(colab, data_inicio, data_fechamento)
        n += len(segs)
    return n


def _chapa_texto_7_digitos(chapa) -> str | None:
    """Chapa como texto com 7 dígitos (zeros à esquerda); só dígitos são considerados."""
    if chapa is None:
        return None
    s = ''.join(c for c in str(chapa).strip() if c.isdigit())
    if not s:
        return None
    if len(s) > 7:
        s = s[-7:]
    return s.zfill(7)


def _titulo_aba_mes(mes: int, ano: int) -> str:
    idx = int(mes) - 1
    mes_nome = MESES_ABREV[idx] if 0 <= idx < len(MESES_ABREV) else f'{mes:02d}'
    return f'{mes_nome} {ano}'


def _titulo_pagamento_curto(mes: int, ano: int) -> str:
    idx = int(mes) - 1
    abrev = MESES_ABREV[idx] if 0 <= idx < len(MESES_ABREV) else f'{mes:02d}'
    return f'{abrev} {str(ano)[-2:]}'


def _pesos_por_tipo():
    return {c['tipo']: (c.get('peso') or 0) for c in CRITERIOS_PADRAO_PLR}


def _valor_criterio_para_excel_pct(val):
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v <= 10:
        v = v * 10.0
    return min(100.0, max(0.0, v)) / 100.0


def _valor_criterio_ponderado_excel(val, peso):
    if val is None or peso is None:
        return None
    pct = _valor_criterio_para_excel_pct(val)
    if pct is None:
        return None
    try:
        p = float(peso)
    except (TypeError, ValueError):
        return None
    return pct * p


def _last_day_month(ano: int, mes: int) -> date:
    last = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, last)


def _parse_data_transferencia(dados: dict):
    if not dados:
        return None
    for key in ('transferencia', 'data_transferencia', 'Transferencia', 'DATA_TRANSFERENCIA'):
        val = dados.get(key)
        if val is None or val == '':
            continue
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        s = str(val).strip()
        if not s:
            continue
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(s[:10], fmt).date()
            except ValueError:
                continue
    return None


def segmentos_funcao_periodo(colab, data_inicio: date, data_fechamento: date) -> list[dict]:
    dados = colab.get_dados_adicionais_dict()
    from models.colaborador.utils.mudanca_funcao import _historico_bruto, _parse_data_iso

    mudancas = []
    for item in _historico_bruto(dados):
        d = _parse_data_iso(str(item.get('data') or ''))
        if d and data_inicio < d <= data_fechamento:
            mudancas.append(d)
    mudancas = sorted(set(mudancas))

    if not mudancas:
        return [{'inicio': data_inicio, 'fim': data_fechamento}]

    out = []
    cursor = data_inicio
    for md in mudancas:
        fim_seg = md - timedelta(days=1)
        if fim_seg >= cursor:
            out.append({'inicio': cursor, 'fim': min(fim_seg, data_fechamento)})
        cursor = md
    if cursor <= data_fechamento:
        out.append({'inicio': cursor, 'fim': data_fechamento})
    return [s for s in out if s['inicio'] <= s['fim']]


def segmento_intersecta_mes(seg_ini: date, seg_fim: date, mes: int, ano: int) -> bool:
    mi = date(ano, mes, 1)
    mf = _last_day_month(ano, mes)
    return seg_fim >= mi and seg_ini <= mf


def _salario_cargo_em(cargo_id: int | None, data_ref: date) -> float | None:
    if not cargo_id:
        return None
    cs = (
        CargoSalario.query.filter(
            CargoSalario.cargo_id == cargo_id,
            CargoSalario.data <= data_ref,
        )
        .order_by(CargoSalario.data.desc())
        .first()
    )
    return float(cs.salario) if cs and cs.salario is not None else None


def salario_atualizado_exportacao(
    colab, data_fechamento: date, salario_por_grupo: bool
) -> float | None:
    """
    Salário “atualizado” (col. X / tabela PLR): só depende do colaborador, da **data de
    fechamento** (com demissão, se anterior), da função vigente nessa data — incluindo
    mudança de função — e do modo grupo vs. cargo (``salario_por_grupo``).

    **Não** usa a data de início do período da planilha; o recorte de segmentos vai da
    admissão (ou da própria data de fechamento) até o fechamento.
    """
    if not colab:
        return None
    dados = colab.get_dados_adicionais_dict()
    data_inicio_seg = colab.data_admissao or data_fechamento
    if data_inicio_seg > data_fechamento:
        data_inicio_seg = data_fechamento
    segs = segmentos_funcao_periodo(colab, data_inicio_seg, data_fechamento)
    if not segs:
        return None
    seg = None
    for s in segs:
        if s['inicio'] <= data_fechamento <= s['fim']:
            seg = s
            break
    if seg is None:
        seg = segs[-1]
    ref_seg_fim = min(seg['fim'], data_fechamento)
    if colab.data_demissao and colab.data_demissao <= data_fechamento:
        ref_seg_fim = min(ref_seg_fim, colab.data_demissao)
    fid = funcao_id_vigente_em(dados, ref_seg_fim, cargo_id_padrao=colab.cargo_id)
    sal_cargo = _cargo_id_salario_atualizado(fid, salario_por_grupo)
    return _salario_cargo_em(sal_cargo, ref_seg_fim)


def _cargo_id_salario_atualizado(cargo_vigente_id: int | None, salario_por_grupo: bool) -> int | None:
    """
    Cargo cuja vigência em ``CargoSalario`` alimenta a col. X (Sal. Atualizado).

    Com ``salario_por_grupo`` e constantes em ``models.plr.constants`` preenchidas,
    mapeia cargos listados em ``CARGOS_OFICIAL`` / ``CARGOS_AJUDANTE`` para
    ``CARGO_OFICIAL`` / ``CARGO_AJUDANTE``. Caso contrário usa o cargo vigente (FID).
    """
    if not cargo_vigente_id or not salario_por_grupo:
        return cargo_vigente_id
    if CARGOS_OFICIAL and cargo_vigente_id in CARGOS_OFICIAL and CARGO_OFICIAL is not None:
        return CARGO_OFICIAL
    if CARGOS_AJUDANTE and cargo_vigente_id in CARGOS_AJUDANTE and CARGO_AJUDANTE is not None:
        return CARGO_AJUDANTE
    return cargo_vigente_id


def _resolve_template_month_sheet(wb, meses_colunas: list[tuple[int, int]]) -> str:
    if 'MES' in wb.sheetnames:
        return 'MES'
    for m, a in meses_colunas:
        tit = _titulo_aba_mes(m, a)
        if tit in wb.sheetnames:
            return tit
    for name in wb.sheetnames:
        if ABAS_MES_REGEX.match(name.strip()):
            return name
    raise ValueError(
        'Template PLANILHA_PLR.xlsx: defina a aba "MES" ou inclua uma aba no formato "AGO 2025".'
    )


def _nome_aba_excel_seguro(title: str) -> str:
    t = re.sub(r'[\[\]:*?/\\]', ' ', title).strip()
    return t[:31] if len(t) > 31 else t


def _limpa_linhas_dados_mes(ws, min_row: int = 35, max_row: int = 500):
    for r in range(min_row, max_row + 1):
        for c in range(1, 32):
            ws.cell(row=r, column=c, value=None)


def _cargo_por_id(cargo_id: int | None):
    if not cargo_id:
        return None
    return Cargo.query.get(cargo_id)


def _quote_sheet(s: str) -> str:
    """Nome de aba para referência Excel (aspas simples se necessário)."""
    t = s.replace("'", "''")
    return f"'{t}'"


def _formula_pct_mes_soma_criterios(row: int, col_ini: int = 13, col_fim: int = 16) -> str:
    """P (%) do mês = soma dos quatro critérios ponderados (colunas M:P → 13–16 na aba mês)."""
    c0 = get_column_letter(col_ini)
    c1 = get_column_letter(col_fim)
    return f'=SUM({c0}{row}:{c1}{row})'


def _celula_estilo_snapshot(cell):
    """Borda, preenchimento, alinhamento, número e fonte (para reaplicar após insert_rows)."""
    fl = cell.fill
    return {
        'border': copy(cell.border),
        'fill': copy(fl) if fl is not None else None,
        'alignment': copy(cell.alignment) if cell.alignment is not None else None,
        'number_format': cell.number_format,
        'font': copy(cell.font) if cell.font is not None else None,
    }


def _aplica_estilo_celula_de_snapshot(snap: dict, dst) -> None:
    """Replica estilo do snapshot na célula destino, preservando ``dst.value``."""
    v = dst.value
    if snap.get('border') is not None:
        dst.border = copy(snap['border'])
    fill = snap.get('fill')
    if fill is not None and getattr(fill, 'fill_type', None) not in (None, 'none', 'None', ''):
        dst.fill = copy(fill)
    al = snap.get('alignment')
    if al is not None:
        dst.alignment = copy(al)
    dst.number_format = snap.get('number_format') or 'General'
    ft = snap.get('font')
    if ft is not None and getattr(ft, 'name', None) is not None:
        dst.font = copy(ft)
    dst.value = v


def _snapshot_linha_estilo(ws, row: int, max_col: int) -> list[dict]:
    return [_celula_estilo_snapshot(ws.cell(row=row, column=c)) for c in range(1, max_col + 1)]


def _aplica_snapshot_linha_estilo(ws, row: int, snaps: list[dict], max_col: int) -> None:
    for c in range(1, max_col + 1):
        _aplica_estilo_celula_de_snapshot(snaps[c - 1], ws.cell(row=row, column=c))


def _pagamento_remove_merges_desde_footer(ws, linha_min: int) -> list[dict]:
    """
    Desfaz merges cuja primeira linha >= ``linha_min`` (rodapé do template a partir da linha do total).
    Retorna metadados para recriar após delete_rows/insert_rows (openpyxl não ajusta merges).
    """
    salvos: list[dict] = []
    for m in list(ws.merged_cells.ranges):
        if m.min_row >= linha_min:
            tl = ws.cell(m.min_row, m.min_col)
            salvos.append(
                {
                    'min_r': m.min_row,
                    'max_r': m.max_row,
                    'min_c': m.min_col,
                    'max_c': m.max_col,
                    'value': tl.value,
                }
            )
    for m in list(ws.merged_cells.ranges):
        if m.min_row >= linha_min:
            ws.unmerge_cells(str(m))
    return salvos


def _pagamento_remerge_footer_deslocado(ws, salvos: list[dict], n_linhas_dados: int) -> None:
    """Recria merges do rodapé: linhas originais >= total passam por -4 (bloco dados) + n inseridas."""
    for s in salvos:
        nr1 = s['min_r'] - PAGAMENTO_ROWS_DATA_TEMPLATE + n_linhas_dados
        nr2 = s['max_r'] - PAGAMENTO_ROWS_DATA_TEMPLATE + n_linhas_dados
        ws.merge_cells(start_row=nr1, start_column=s['min_c'], end_row=nr2, end_column=s['max_c'])
        ws.cell(nr1, s['min_c']).value = s['value']


def _aplica_fonte_index_branco(cell) -> None:
    """Coluna A (id linha/segmento): branco, mantendo tamanho/negrito quando houver fonte de referência."""
    old = cell.font
    if old and getattr(old, 'name', None):
        cell.font = Font(
            name=old.name,
            sz=old.sz,
            b=old.b,
            i=old.i,
            u=old.u,
            strike=old.strike,
            color=FONT_INDEX_BRANCO,
        )
    else:
        cell.font = Font(color=FONT_INDEX_BRANCO)


def _copia_estilo_celula_aba_mes(proveniencia, destino) -> None:
    """
    Copia borda, preenchimento, alinhamento, número e fonte da célula modelo
    na célula de destino, mantendo o valor de destino.
    """
    src, dst = proveniencia, destino
    v = dst.value
    if src.border is not None:
        dst.border = copy(src.border)
    if src.fill is not None and getattr(src.fill, 'fill_type', None) not in (None, 'none', 'None', ''):
        dst.fill = copy(src.fill)
    if src.alignment is not None:
        dst.alignment = copy(src.alignment)
    dst.number_format = src.number_format
    if src.font is not None and getattr(src.font, 'name', None) is not None:
        dst.font = copy(src.font)
    dst.value = v


def _estende_formatacao_aba_mes_fim_template(
    ws,
    ultima_linha_dados: int,
    ref_row: int = MES_ROW_STYLE_MIDDLE,
    max_col: int = MES_MAX_COL_STYLE,
    ref_ws=None,
) -> None:
    """Repete a formatação da ``ref_row`` (linha 36 = meio) nas linhas após ``MES_ROW_FORMAT_LAST``."""
    if ultima_linha_dados <= MES_ROW_FORMAT_LAST:
        return
    src = ref_ws if ref_ws is not None else ws
    for r in range(MES_ROW_FORMAT_LAST + 1, ultima_linha_dados + 1):
        for c in range(1, max_col + 1):
            _copia_estilo_celula_aba_mes(
                src.cell(row=ref_row, column=c),
                ws.cell(row=r, column=c),
            )


def _formula_acum_media_abas(row: int, idx_mes: int, titulos_abas: list[str]) -> str:
    """
    P (%) acumulado até o mês = média do P (%) mês (col. Q) nas abas do 1º mês até o atual,
    mesma linha PLR na col. A (id colaborador + segmento; CPF pode repetir entre segmentos).
    """
    parts = []
    col_q = 'Q'
    col_a = 'A'
    for j in range(idx_mes + 1):
        tab = _quote_sheet(titulos_abas[j])
        parts.append(
            f'IFERROR(INDEX({tab}!${col_q}:${col_q},MATCH(${col_a}{row},{tab}!${col_a}:${col_a},0)),0)'
        )
    n = idx_mes + 1
    return f'=({"+".join(parts)})/{n}'


def gerar_planilha_plr_xlsx_template_io(
    resultado: list[dict],
    meses_colunas: list[tuple[int, int]],
    data_inicio: date,
    data_fechamento: date,
    cpf_para_chapa: dict,
    criterios_por_colab_mes: dict,
    salario_por_grupo: bool = False,
) -> BytesIO:
    """
    Preenche o template PLANILHA_PLR.xlsx e retorna BytesIO posicionado no início.

    ``salario_por_grupo``: col. X (Sal. Atualizado) usa ``CargoSalario`` do cargo de
    referência definido em ``models/plr.constants`` (CARGOS_* → CARGO_*).
    """
    if not PLANILHA_TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f'Template não encontrado: {PLANILHA_TEMPLATE_PATH}')

    wb = load_workbook(PLANILHA_TEMPLATE_PATH)

    nomes_meses = [_titulo_aba_mes(m, a) for m, a in meses_colunas]
    src_name = _resolve_template_month_sheet(wb, meses_colunas)

    base = wb.copy_worksheet(wb[src_name])
    base.title = _nome_aba_excel_seguro('__TPL_MES__')
    _limpa_linhas_dados_mes(base)

    if src_name in wb.sheetnames:
        wb.remove(wb[src_name])

    for tit in nomes_meses:
        if tit in wb.sheetnames:
            wb.remove(wb[tit])

    pesos = _pesos_por_tipo()
    titulos_abas_export: list[str] = []

    for idx_abas, (mes, ano) in enumerate(meses_colunas):
        titulo = _nome_aba_excel_seguro(_titulo_aba_mes(mes, ano))
        ws_novo = wb.copy_worksheet(base)
        ws_novo.title = titulo
        titulos_abas_export.append(titulo)

        primeira_mes = date(ano, mes, 1)
        ws_novo['A32'] = primeira_mes
        ws_novo['M2'] = len(meses_colunas)

        row = 35
        for linha_res in resultado:
            colab = linha_res['colaborador']
            if not colab:
                continue
            dados = colab.get_dados_adicionais_dict()
            trans_d = _parse_data_transferencia(dados)
            cpf = colab.cpf or '-'
            chapa_raw = cpf_para_chapa.get(cpf, '') if cpf != '-' else ''
            chapa = _chapa_texto_7_digitos(chapa_raw)

            segs = segmentos_funcao_periodo(colab, data_inicio, data_fechamento)
            if not segs:
                continue

            idx_mes = next(
                (i for i, (mm, aa) in enumerate(meses_colunas) if mm == mes and aa == ano),
                None,
            )
            if idx_mes is None:
                continue

            for seg_i, seg in enumerate(segs):
                ativo_neste_mes = segmento_intersecta_mes(seg['inicio'], seg['fim'], mes, ano)

                ref_seg_fim = min(seg['fim'], data_fechamento)
                if colab.data_demissao and colab.data_demissao <= data_fechamento:
                    ref_seg_fim = min(ref_seg_fim, colab.data_demissao)

                fid = funcao_id_vigente_em(dados, ref_seg_fim, cargo_id_padrao=colab.cargo_id)
                cargo = _cargo_por_id(fid)
                nome_funcao = cargo.nome if cargo else '-'

                crit_colab = criterios_por_colab_mes.get(colab.id, {})
                crit_mes = crit_colab.get((mes, ano), {}) if crit_colab else {}
                if ativo_neste_mes:
                    assid = _valor_criterio_ponderado_excel(
                        crit_mes.get('Assiduidade'), pesos.get('Assiduidade')
                    )
                    zero_ac = _valor_criterio_ponderado_excel(
                        crit_mes.get('Zero Acidente'), pesos.get('Zero Acidente')
                    )
                    segur = _valor_criterio_ponderado_excel(
                        crit_mes.get('Segurança, Limpeza, Organização'),
                        pesos.get('Segurança, Limpeza, Organização'),
                    )
                    prazo = _valor_criterio_ponderado_excel(crit_mes.get('Prazo'), pesos.get('Prazo'))
                else:
                    assid = zero_ac = segur = prazo = None

                if colab.data_demissao and data_fechamento and colab.data_demissao <= data_fechamento:
                    dem_f = colab.data_demissao
                else:
                    dem_f = data_fechamento

                linha_plr_id = f'{colab.id}-{seg_i}'
                ws_novo.cell(row=row, column=1, value=linha_plr_id)
                # Coluna A = id estável por segmento (MATCH na PAGAMENTO); dados a partir de B.
                ws_novo.cell(row=row, column=2, value=cpf)
                cel_chapa_m = ws_novo.cell(row=row, column=3, value=chapa)
                if chapa is not None:
                    cel_chapa_m.number_format = '@'
                ws_novo.cell(row=row, column=4, value=colab.data_admissao)
                ws_novo.cell(row=row, column=4).number_format = FMT_EXCEL_DATA
                ws_novo.cell(row=row, column=5, value=dem_f)
                ws_novo.cell(row=row, column=5).number_format = FMT_EXCEL_DATA
                ws_novo.cell(row=row, column=6, value=None)
                ws_novo.cell(row=row, column=7, value=None)
                ws_novo.cell(row=row, column=8, value=None)
                ws_novo.cell(row=row, column=9, value='MOD')
                ws_novo.cell(row=row, column=10, value=trans_d)
                ws_novo.cell(row=row, column=10).number_format = FMT_EXCEL_DATA
                ws_novo.cell(row=row, column=11, value=(colab.nome or '').upper())
                ws_novo.cell(row=row, column=12, value=nome_funcao)
                ws_novo.cell(row=row, column=13, value=assid)
                ws_novo.cell(row=row, column=14, value=zero_ac)
                ws_novo.cell(row=row, column=15, value=segur)
                ws_novo.cell(row=row, column=16, value=prazo)
                if ativo_neste_mes:
                    ws_novo.cell(row=row, column=17, value=_formula_pct_mes_soma_criterios(row))
                    ws_novo.cell(row=row, column=18, value=_formula_acum_media_abas(row, idx_abas, titulos_abas_export))
                    for col_pct in range(13, 19):
                        ws_novo.cell(row=row, column=col_pct).number_format = FMT_EXCEL_PCT
                else:
                    ws_novo.cell(row=row, column=17, value=None)
                    ws_novo.cell(row=row, column=18, value=None)

                ws_novo.cell(row=row, column=19, value=None)

                row += 1

        # Primeira (35), meio (36) e última (38) do template em ``base``; linhas 71+ usam estilo da 36.
        last_data = row - 1
        if last_data >= MES_ROW_DATA_FIRST:
            n_linhas_mes = last_data - MES_ROW_DATA_FIRST + 1
            for r in range(MES_ROW_DATA_FIRST, last_data + 1):
                i = r - MES_ROW_DATA_FIRST
                if n_linhas_mes == 1:
                    ref_r = MES_ROW_DATA_FIRST
                elif i == 0:
                    ref_r = MES_ROW_DATA_FIRST
                elif i == n_linhas_mes - 1:
                    ref_r = MES_ROW_STYLE_LAST_DATA
                else:
                    ref_r = MES_ROW_STYLE_MIDDLE
                for c in range(1, MES_MAX_COL_STYLE + 1):
                    _copia_estilo_celula_aba_mes(base.cell(row=ref_r, column=c), ws_novo.cell(row=r, column=c))
            _estende_formatacao_aba_mes_fim_template(ws_novo, last_data, ref_ws=base)
            for r in range(MES_ROW_DATA_FIRST, last_data + 1):
                c17 = ws_novo.cell(row=r, column=17)
                for col_data in (4, 5, 10):
                    ws_novo.cell(row=r, column=col_data).number_format = FMT_EXCEL_DATA
                if isinstance(c17.value, str) and str(c17.value).startswith('='):
                    for col_pct in range(13, 19):
                        ws_novo.cell(row=r, column=col_pct).number_format = FMT_EXCEL_PCT
                cv = ws_novo.cell(row=r, column=3).value
                if cv is not None and _chapa_texto_7_digitos(cv):
                    ws_novo.cell(row=r, column=3).number_format = '@'
            for r in range(MES_ROW_DATA_FIRST, last_data + 1):
                _aplica_fonte_index_branco(ws_novo.cell(row=r, column=1))

    wb.remove(base)

    num_meses = len(meses_colunas)
    col_ini_meses = 11

    if 'PAGAMENTO MOD' in wb.sheetnames:
        ws_p = wb['PAGAMENTO MOD']

        col_map = _pagamento_mapa_colunas(num_meses)
        col_max_layout = max(col_map['sal_atual'] + 8, ws_p.max_column or 28, 36)
        n_linhas_dados = _n_linhas_pagamento(resultado, data_inicio, data_fechamento)

        snap_pag_primeira: list[dict] = []
        snap_pag_meio: list[dict] = []
        snap_pag_ultima: list[dict] = []
        if ws_p.max_row >= PAGAMENTO_ROW_STYLE_LAST_DATA:
            snap_pag_primeira = _snapshot_linha_estilo(ws_p, PAGAMENTO_ROW_DATA_FIRST, col_max_layout)
            snap_pag_meio = _snapshot_linha_estilo(ws_p, PAGAMENTO_ROW_STYLE_MIDDLE, col_max_layout)
            snap_pag_ultima = _snapshot_linha_estilo(ws_p, PAGAMENTO_ROW_STYLE_LAST_DATA, col_max_layout)

        merges_footer: list[dict] = []
        if ws_p.max_row >= PAGAMENTO_ROW_TOTAL_FIRST:
            merges_footer = _pagamento_remove_merges_desde_footer(ws_p, PAGAMENTO_ROW_TOTAL_FIRST)
            ws_p.delete_rows(PAGAMENTO_ROW_DATA_FIRST, PAGAMENTO_ROWS_DATA_TEMPLATE)
            if n_linhas_dados > 0:
                ws_p.insert_rows(PAGAMENTO_ROW_DATA_FIRST, n_linhas_dados)
            _pagamento_remerge_footer_deslocado(ws_p, merges_footer, n_linhas_dados)
        elif ws_p.max_row >= PAGAMENTO_ROW_DATA_FIRST:
            ws_p.delete_rows(PAGAMENTO_ROW_DATA_FIRST, ws_p.max_row - PAGAMENTO_ROW_DATA_FIRST + 1)
            if n_linhas_dados > 0:
                ws_p.insert_rows(PAGAMENTO_ROW_DATA_FIRST, n_linhas_dados)

        for i, (mm, aa) in enumerate(meses_colunas):
            ws_p.cell(row=24, column=col_ini_meses + i, value=_titulo_pagamento_curto(mm, aa))

        ws_p.cell(row=24, column=col_map['soma'], value='SOMA')
        ws_p.cell(row=24, column=col_map['p_med'], value='P(%) Média acumulada')
        ws_p.cell(row=24, column=col_map['sal_plr'], value='SALÁRIO BASE PARA PLR')
        ws_p.cell(row=24, column=col_map['vpo'], value='VPO')
        ws_p.cell(row=24, column=col_map['valor'], value='VALOR TOTAL                   A PAGAR')
        ws_p.cell(row=24, column=col_map['anot'], value='ANOTAÇÃO')
        ws_p.cell(row=24, column=col_map['sal_atual'], value='Sal. Atualizado')

        row_p = 25
        col_primeiro_mes = get_column_letter(PAGAMENTO_COL_MES_INI)
        col_ultimo_mes = get_column_letter(PAGAMENTO_COL_MES_INI + max(0, num_meses - 1))

        for linha_res in resultado:
            colab = linha_res['colaborador']
            if not colab:
                continue
            dados = colab.get_dados_adicionais_dict()
            cpf = colab.cpf or '-'
            chapa_raw = cpf_para_chapa.get(cpf, '') if cpf != '-' else ''
            chapa = _chapa_texto_7_digitos(chapa_raw)

            segs = segmentos_funcao_periodo(colab, data_inicio, data_fechamento)
            if not segs:
                continue

            for seg_i, seg in enumerate(segs):
                ref_seg_fim = min(seg['fim'], data_fechamento)
                if colab.data_demissao and colab.data_demissao <= data_fechamento:
                    ref_seg_fim = min(ref_seg_fim, colab.data_demissao)

                fid = funcao_id_vigente_em(dados, ref_seg_fim, cargo_id_padrao=colab.cargo_id)
                cargo = _cargo_por_id(fid)
                nome_funcao = cargo.nome if cargo else '-'

                # Tempo de casa: mesmo do relatório (admissão → fechamento ou demissão), não o fim do segmento.
                tempo_m = linha_res.get('tempo_casa_meses')
                if tempo_m is None:
                    tempo_m = tempo_de_casa_meses(colab.data_admissao, ref_seg_fim)
                sal_cargo = _cargo_id_salario_atualizado(fid, salario_por_grupo)
                # Sal. atualizado: vigência na data de referência do segmento (fim capado ao fechamento);
                # não depende da data de início do período da planilha.
                sal_x = _salario_cargo_em(sal_cargo, ref_seg_fim)

                adm_s = colab.data_admissao
                dem_s = colab.data_demissao if colab.data_demissao else data_fechamento

                c_idx = ws_p.cell(row=row_p, column=1, value=f'{colab.id}-{seg_i}')
                _aplica_fonte_index_branco(c_idx)
                ws_p.cell(row=row_p, column=2, value=cpf)
                cel_chapa_p = ws_p.cell(row=row_p, column=3, value=chapa)
                if chapa is not None:
                    cel_chapa_p.number_format = '@'
                ws_p.cell(row=row_p, column=4, value=(colab.nome or '').upper())
                ws_p.cell(row=row_p, column=5, value='MOD')
                ws_p.cell(row=row_p, column=6, value=None)
                ws_p.cell(row=row_p, column=7, value=adm_s)
                ws_p.cell(row=row_p, column=8, value=dem_s)
                ws_p.cell(row=row_p, column=7).number_format = FMT_EXCEL_DATA
                ws_p.cell(row=row_p, column=8).number_format = FMT_EXCEL_DATA
                ws_p.cell(row=row_p, column=9, value=tempo_m)
                ws_p.cell(row=row_p, column=10, value=nome_funcao)

                if titulos_abas_export:
                    for i_m, tab_name in enumerate(titulos_abas_export):
                        ci = col_ini_meses + i_m
                        qt = _quote_sheet(tab_name)
                        ws_p.cell(
                            row=row_p,
                            column=ci,
                            value=(
                                f'=IFERROR(INDEX({qt}!$Q:$Q,'
                                f'MATCH($A{row_p},{qt}!$A:$A,0)),"")'
                            ),
                        )

                rng_meses = f'{col_primeiro_mes}{row_p}:{col_ultimo_mes}{row_p}'
                ws_p.cell(
                    row=row_p,
                    column=col_map['soma'],
                    value=f'=SUM({rng_meses})',
                )
                ws_p.cell(
                    row=row_p,
                    column=col_map['p_med'],
                    value=f'=IFERROR(AVERAGE({rng_meses}),"")',
                )

                letter_i = get_column_letter(9)
                letter_sal_x = get_column_letter(col_map['sal_atual'])
                letter_sal_plr = get_column_letter(col_map['sal_plr'])
                letter_vpo = get_column_letter(col_map['vpo'])
                letter_p_med = get_column_letter(col_map['p_med'])

                ws_p.cell(
                    row=row_p,
                    column=col_map['sal_atual'],
                    value=sal_x,
                )
                ws_p.cell(
                    row=row_p,
                    column=col_map['sal_plr'],
                    value=(
                        f'=IF(ISNUMBER({letter_sal_x}{row_p}),'
                        f'IF({letter_i}{row_p}>=18,{letter_sal_x}{row_p}*1.2,{letter_sal_x}{row_p}),"")'
                    ),
                )
                ws_p.cell(
                    row=row_p,
                    column=col_map['vpo'],
                    value=f'=IF(ISNUMBER({letter_sal_plr}{row_p}),({letter_sal_plr}{row_p}/12)*6,"")',
                )
                ws_p.cell(
                    row=row_p,
                    column=col_map['valor'],
                    value=(
                        f'=IF(AND(ISNUMBER({letter_vpo}{row_p}),ISNUMBER({letter_p_med}{row_p})),'
                        f'{letter_vpo}{row_p}*{letter_p_med}{row_p},"")'
                    ),
                )
                ws_p.cell(row=row_p, column=col_map['anot'], value=None)

                for col_pct in range(PAGAMENTO_COL_MES_INI, PAGAMENTO_COL_MES_INI + num_meses):
                    ws_p.cell(row=row_p, column=col_pct).number_format = FMT_EXCEL_PCT
                ws_p.cell(row=row_p, column=col_map['soma']).number_format = FMT_EXCEL_PCT
                ws_p.cell(row=row_p, column=col_map['p_med']).number_format = FMT_EXCEL_PCT
                for col_moeda in (
                    col_map['sal_plr'],
                    col_map['vpo'],
                    col_map['valor'],
                    col_map['sal_atual'],
                ):
                    ws_p.cell(row=row_p, column=col_moeda).number_format = FMT_EXCEL_MOEDA_CONTABIL

                idx_p = row_p - PAGAMENTO_ROW_DATA_FIRST
                if snap_pag_primeira and snap_pag_meio and snap_pag_ultima:
                    if n_linhas_dados == 1:
                        _aplica_snapshot_linha_estilo(ws_p, row_p, snap_pag_primeira, col_max_layout)
                    elif idx_p == 0:
                        _aplica_snapshot_linha_estilo(ws_p, row_p, snap_pag_primeira, col_max_layout)
                    elif idx_p == n_linhas_dados - 1:
                        _aplica_snapshot_linha_estilo(ws_p, row_p, snap_pag_ultima, col_max_layout)
                    else:
                        _aplica_snapshot_linha_estilo(ws_p, row_p, snap_pag_meio, col_max_layout)
                ws_p.cell(row=row_p, column=7).number_format = FMT_EXCEL_DATA
                ws_p.cell(row=row_p, column=8).number_format = FMT_EXCEL_DATA

                row_p += 1

        if n_linhas_dados <= 0:
            total_row = PAGAMENTO_ROW_DATA_FIRST
        else:
            total_row = PAGAMENTO_ROW_DATA_FIRST + n_linhas_dados

        col_valor = col_map['valor']
        letter_valor = get_column_letter(col_valor)
        if n_linhas_dados <= 0:
            ws_p.cell(row=total_row, column=col_valor, value='=0')
        else:
            ultima_linha_dado = PAGAMENTO_ROW_DATA_FIRST + n_linhas_dados - 1
            ws_p.cell(
                row=total_row,
                column=col_valor,
                value=(
                    f'=SUM({letter_valor}{PAGAMENTO_ROW_DATA_FIRST}:'
                    f'{letter_valor}{ultima_linha_dado})'
                ),
            )
        ws_p.cell(row=total_row, column=col_valor).number_format = FMT_EXCEL_MOEDA_CONTABIL
        if col_valor != PAGAMENTO_COL_VALOR:
            cell_u = ws_p.cell(row=total_row, column=PAGAMENTO_COL_VALOR)
            if isinstance(cell_u.value, str) and str(cell_u.value).startswith('='):
                cell_u.value = None

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
