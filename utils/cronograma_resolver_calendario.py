"""
Resolve qual CronogramaCalendario se aplica a um índice de item, por vínculos no contrato.
Prefixo mais específico (mais segmentos) prevalece: ex. 1.2 vence 1 para o índice 1.2.3.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from models.cronograma import CronogramaCalendario, CronogramaVinculoCalendario


def _segmentos(indice: str) -> int:
    s = (indice or '').strip()
    if not s:
        return 0
    return len(s.split('.'))


def indice_caso_prefixo(indice_item: str, prefixo: str) -> bool:
    """True se o item pertence à subárvore do prefixo (igual ou descendente)."""
    ix = (indice_item or '').strip()
    p = (prefixo or '').strip()
    if not ix or not p:
        return False
    if ix == p:
        return True
    return ix.startswith(p + '.')


def resolver_calendario_para_indice(
    contrato_id: int,
    indice: str,
    cache_vinculos: Optional[List[CronogramaVinculoCalendario]] = None,
) -> Optional[CronogramaCalendario]:
    """
    Retorna o calendário do vínculo cujo prefixo é o mais específico que cobre `indice`.
    """
    ix = (indice or '').strip()
    if not ix:
        return None
    rows = cache_vinculos
    if rows is None:
        rows = (
            CronogramaVinculoCalendario.query.filter(
                CronogramaVinculoCalendario.contrato_id == contrato_id,
            )
            .all()
        )
    best: Optional[CronogramaVinculoCalendario] = None
    best_seg = -1
    for v in rows:
        p = (v.indice_prefixo or '').strip()
        if not p:
            continue
        if not indice_caso_prefixo(ix, p):
            continue
        seg = _segmentos(p)
        if seg > best_seg:
            best_seg = seg
            best = v
        elif seg == best_seg and best is not None and v.id < best.id:
            best = v
    if not best:
        return None
    return best.calendario


def mapa_feriados_por_calendario(calendario_ids: List[int]) -> Dict[int, Set]:
    """Datas de feriado por calendario_id (para uso em is_dia_util)."""
    from models.cronograma import CronogramaCalendarioFeriado

    if not calendario_ids:
        return {}
    ids = list({i for i in calendario_ids if i})
    out: Dict[int, Set] = {}
    for cid in ids:
        out[cid] = set()
    rows = CronogramaCalendarioFeriado.query.filter(
        CronogramaCalendarioFeriado.calendario_id.in_(ids),
    ).all()
    for r in rows:
        if r.data and r.calendario_id in out:
            out[r.calendario_id].add(r.data)
    return out
