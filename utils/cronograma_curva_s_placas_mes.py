"""
Placas previstas e realizadas por mês calendário a partir da matriz semanal da Curva S.
Cada semana (segunda a domingo) conta no mês da segunda-feira.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Tuple


def placas_previsto_e_real_por_mes(
    semanas: List[Dict[str, Any]],
    linhas: List[Dict[str, Any]],
) -> Tuple[List[str], List[float], List[float]]:
    """
    Só linhas com `curva_s_contar`. Retorna labels MM/AAAA e listas alinhadas de previsto/real por mês.
    """
    week_keys = [s['key'] for s in semanas]
    acc_p: Dict[str, float] = defaultdict(float)
    acc_r: Dict[str, float] = defaultdict(float)

    for row in linhas:
        if not row.get('curva_s_contar'):
            continue
        prev = row.get('previsto') or {}
        real = row.get('real') or {}
        for wk in week_keys:
            v_prev = float(prev.get(wk, 0) or 0)
            v_real = float(real.get(wk, 0) or 0)
            if abs(v_prev) < 1e-12 and abs(v_real) < 1e-12:
                continue
            try:
                d0 = date.fromisoformat(str(wk)[:10])
            except ValueError:
                continue
            mk = f"{d0.year}-{d0.month:02d}"
            acc_p[mk] += v_prev
            acc_r[mk] += v_real

    meses = sorted(set(acc_p.keys()) | set(acc_r.keys()))
    labels: List[str] = []
    vals_p: List[float] = []
    vals_r: List[float] = []
    for mk in meses:
        y, m = int(mk[:4]), int(mk[5:7])
        labels.append(f"{m:02d}/{y}")
        vals_p.append(round(acc_p.get(mk, 0.0), 4))
        vals_r.append(round(acc_r.get(mk, 0.0), 4))
    return labels, vals_p, vals_r
