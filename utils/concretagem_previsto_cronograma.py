"""
Previsto mensal (placas) a partir do cronograma, alinhado aos meses do relatório de concretagem.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from models.database import db
from models.tanque import Tanques, tanques_grupos

from utils.cronograma_matriz_semanal import (
    data_fim_horizonte_matriz,
    montar_matriz_previsto_real,
    trim_trailing_semanas_sem_previsto_nem_real,
)


def pecas_previsto_por_mes_alinhado(
    contrato_id: int,
    data_inicio: date,
    data_fim: date,
    dados_mes: Dict[str, Any],
    *,
    tanque_id: Optional[int] = None,
    grupo_id: Optional[int] = None,
    indices_por_tanque: Optional[Dict[int, Dict[str, float]]] = None,
) -> List[float]:
    """
    Soma placas previstas por mês (semana do cronograma → mês da segunda-feira da semana),
    alinhada à ordem de `dados_mes` (chave ano-mês).
    Só linhas com `curva_s_contar` e respeitando filtro de tanque/grupo.
    """
    if not contrato_id or not dados_mes:
        return []

    data_fim_calc = data_fim_horizonte_matriz(contrato_id, data_inicio, data_fim)
    semanas, linhas, barras = montar_matriz_previsto_real(
        contrato_id,
        data_inicio,
        data_fim_calc,
        indices_por_tanque=indices_por_tanque,
        ordenar_por_indice=False,
    )
    semanas, linhas, _data_fim_t, barras = trim_trailing_semanas_sem_previsto_nem_real(
        semanas, linhas, barras
    )

    grupo_tank_ids: Optional[set] = None
    if grupo_id:
        rows = (
            db.session.query(Tanques.id)
            .join(
                tanques_grupos,
                tanques_grupos.c.tanque_id == Tanques.id,
            )
            .filter(
                tanques_grupos.c.grupo_id == grupo_id,
                Tanques.contrato_id == contrato_id,
            )
            .all()
        )
        grupo_tank_ids = {r[0] for r in rows}

    acc: Dict[str, float] = defaultdict(float)
    for row in linhas:
        if not row.get('curva_s_contar'):
            continue
        tid = row.get('tanque_id')
        if tanque_id and tid != tanque_id:
            continue
        if grupo_tank_ids is not None:
            if tid is None or tid not in grupo_tank_ids:
                continue
        prev = row.get('previsto') or {}
        for wk, val in prev.items():
            try:
                d0 = date.fromisoformat(str(wk)[:10])
            except ValueError:
                continue
            mk = f"{d0.year}-{d0.month:02d}"
            acc[mk] += float(val or 0)

    aligned: List[float] = []
    for v in dados_mes.values():
        mk = f"{v['ano']}-{v['mes']:02d}"
        aligned.append(round(acc.get(mk, 0.0), 4))
    return aligned
