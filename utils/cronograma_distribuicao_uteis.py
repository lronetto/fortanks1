"""
Distribuição de carga em semanas usando dias úteis (calendário + feriados).
Sem calendário, delega ao comportamento original (dias corridos).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set

from models.cronograma import CronogramaCalendario

from utils.cronograma_calculo_pecas import (
    distribuir_dias_por_semana,
    primeiro_dia_apos_trabalho,
    segunda_feira_semana,
)


def is_dia_util(d: date, cal: CronogramaCalendario, feriados: Set[date]) -> bool:
    if d in feriados:
        return False
    w = d.weekday()
    flags = [
        cal.seg_util, cal.ter_util, cal.qua_util, cal.qui_util,
        cal.sex_util, cal.sab_util, cal.dom_util,
    ]
    return bool(flags[w])


def distribuir_dias_uteis_por_semana(
    total_dias: float,
    inicio: date,
    cal: CronogramaCalendario,
    feriados: Set[date],
) -> List[Dict[str, Any]]:
    """Mesma forma de saída de distribuir_dias_por_semana, consumindo só dias úteis."""
    if total_dias <= 0:
        return []

    out: List[Dict[str, Any]] = []
    restante = float(total_dias)
    cur = inicio
    outer_guard = 0

    while restante > 1e-9:
        outer_guard += 1
        if outer_guard > 8000:
            break
        ws = segunda_feira_semana(cur)
        we = ws + timedelta(days=6)
        week_dias = 0.0
        d = cur
        while d <= we and restante > 1e-9:
            if is_dia_util(d, cal, feriados):
                chunk = min(restante, 1.0)
                week_dias += chunk
                restante -= chunk
            d += timedelta(days=1)
        if week_dias > 1e-9:
            semana_iso = cur.isocalendar()
            out.append({
                'semana_inicio': ws,
                'semana_fim': we,
                'dias': round(week_dias, 4),
                'semana_numero': semana_iso[1],
                'ano_iso': semana_iso[0],
                'label': (
                    f'S{semana_iso[1]:02d}/{semana_iso[0]} — '
                    f'{ws.strftime("%d/%m")} a {we.strftime("%d/%m/%Y")}'
                ),
            })
        if restante > 1e-9:
            cur = we + timedelta(days=1)

    return out


def primeiro_dia_apos_trabalho_uteis(
    total_unidades: float,
    inicio: date,
    cal: CronogramaCalendario,
    feriados: Set[date],
) -> date:
    if total_unidades <= 1e-9:
        return inicio
    dist = distribuir_dias_uteis_por_semana(total_unidades, inicio, cal, feriados)
    if not dist:
        return inicio
    return dist[-1]['semana_fim'] + timedelta(days=1)


def distribuir_carga_por_semana(
    total_dias: float,
    inicio: date,
    calendario: Optional[CronogramaCalendario],
    feriados: Optional[Set[date]],
) -> List[Dict[str, Any]]:
    if calendario is None:
        return distribuir_dias_por_semana(total_dias, inicio)
    return distribuir_dias_uteis_por_semana(
        total_dias, inicio, calendario, feriados if feriados is not None else set(),
    )


def primeiro_dia_apos_carga(
    total_unidades: float,
    inicio: date,
    calendario: Optional[CronogramaCalendario],
    feriados: Optional[Set[date]],
) -> date:
    if calendario is None:
        return primeiro_dia_apos_trabalho(total_unidades, inicio)
    return primeiro_dia_apos_trabalho_uteis(
        total_unidades, inicio, calendario, feriados if feriados is not None else set(),
    )


def dias_corridos_na_carga(
    total_dias: float,
    inicio: date,
    calendario: Optional[CronogramaCalendario],
    feriados: Optional[Set[date]],
) -> int:
    """
    Dias corridos de calendário entre o primeiro e o último dia da carga prevista (inclusive).
    Usa a mesma lógica de distribuição que `distribuir_carga_por_semana` / `primeiro_dia_apos_carga`.
    """
    if total_dias <= 1e-9:
        return 0
    prox = primeiro_dia_apos_carga(total_dias, inicio, calendario, feriados)
    ultimo = prox - timedelta(days=1)
    if ultimo < inicio:
        return 0
    return (ultimo - inicio).days + 1
