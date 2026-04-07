"""
Matriz semanal: itens do cronograma × semanas, previsto e real em quantidade de placas (peças).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func

from models.database import db
from models.cronograma import (
    CronogramaCalendario,
    CronogramaItem,
    CronogramaTanque,
    CronogramaVinculoCalendario,
)
from models.tanque import Tanques, TanquesPecas

from utils.cronograma_calculo_pecas import (
    segunda_feira_semana,
    semanas_no_intervalo,
    total_dias_por_tanque_contrato,
    total_placas_por_tanque_contrato,
)
from utils.cronograma_distribuicao_uteis import (
    distribuir_carga_por_semana,
    primeiro_dia_apos_carga,
)
from utils.cronograma_resolver_calendario import (
    mapa_feriados_por_calendario,
    resolver_calendario_para_indice,
)


def _to_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return None


def minima_segunda_feira_anchor_cronograma(contrato_id: int) -> Optional[date]:
    """
    Segunda-feira da semana da menor data de ancoragem do projeto:
    CronogramaItem.data_inicio e CronogramaTanque.data_inicio_prevista.

    Usada como padrão do intervalo da matriz/curva S quando o usuário não escolhe
    o campo Intervalo — início, para a primeira coluna alinhar à semana do primeiro
    início planejado (ex.: item em 17/03 → coluna da semana correspondente).
    """
    datas: List[date] = []
    for it in CronogramaItem.query.filter(
        CronogramaItem.contrato_id == contrato_id,
        CronogramaItem.data_inicio.isnot(None),
    ).all():
        d = _to_date(it.data_inicio)
        if d:
            datas.append(d)
    for r in CronogramaTanque.query.filter(CronogramaTanque.contrato_id == contrato_id).all():
        if r.data_inicio_prevista:
            datas.append(r.data_inicio_prevista)
    if not datas:
        return None
    return segunda_feira_semana(min(datas))


def _peso_share_por_item(itens: List[CronogramaItem]) -> Dict[int, float]:
    """Para itens com mesmo tanque, reparte peso 1 conforme campo peso (ou igual se soma zero)."""
    by_tank: Dict[int, List[CronogramaItem]] = defaultdict(list)
    for it in itens:
        if it.tanque_id:
            by_tank[it.tanque_id].append(it)

    share: Dict[int, float] = {}
    for tid, lst in by_tank.items():
        if tid is None:
            continue
        pesos = [float(it.peso or 0) for it in lst]
        soma = sum(pesos)
        if soma <= 0:
            n = len(lst)
            for it in lst:
                share[it.id] = 1.0 / n if n else 0.0
        else:
            for it in lst:
                share[it.id] = float(it.peso or 0) / soma
    return share


def _parent_indice_str(indice: str) -> Optional[str]:
    """Pai imediato na hierarquia (ex.: 1.2.3 → 1.2)."""
    ix = (indice or '').strip()
    if not ix:
        return None
    parts = ix.split('.')
    if len(parts) <= 1:
        return None
    return '.'.join(parts[:-1])


def _tem_descendente_indice(indice: str, todos: List[str]) -> bool:
    """True se existir algum índice que seja descendente direto ou indireto (prefixo indice + '.')."""
    p = (indice or '').strip() + '.'
    if len(p) <= 1:
        return False
    return any(o.startswith(p) for o in todos)


def _filhos_diretos_indice(parent_indice: str, itens: List[CronogramaItem]) -> List[CronogramaItem]:
    """
    Filhos diretos na árvore de índices (ex.: 1.3 -> 1.3.1, 1.3.2; não 1.3.1.1).
    """
    p = (parent_indice or '').strip()
    if not p:
        return []
    prefix = p + '.'
    out: List[CronogramaItem] = []
    for it in itens:
        qi = (it.indice or '').strip()
        if not qi.startswith(prefix):
            continue
        sufixo = qi[len(prefix) :]
        if '.' in sufixo:
            continue
        out.append(it)
    return out


def _placas_efetivas_por_item(
    itens: List[CronogramaItem],
    share: Dict[int, float],
    placas_tank: Dict[int, int],
) -> Dict[int, float]:
    """
    Itens com tanque: placas do tanque × peso.
    Sem tanque: soma das placas efetivas dos filhos diretos (ex.: 1.3 totaliza 1.3.x).
    """
    memo: Dict[int, float] = {}

    def calc(it: CronogramaItem) -> float:
        if it.id in memo:
            return memo[it.id]
        if it.tanque_id and it.id in share:
            v = float(placas_tank.get(it.tanque_id, 0)) * float(share[it.id])
            memo[it.id] = round(v, 4)
            return memo[it.id]
        filhos = _filhos_diretos_indice(it.indice or '', itens)
        if not filhos:
            memo[it.id] = 0.0
            return 0.0
        v = sum(calc(ch) for ch in filhos)
        memo[it.id] = round(v, 4)
        return memo[it.id]

    for it in itens:
        calc(it)
    return memo


def _dias_efetivos_por_item(
    itens: List[CronogramaItem],
    share: Dict[int, float],
    dias_tank: Dict[int, float],
) -> Dict[int, float]:
    """
    Mesma lógica das placas efetivas: dias totais do tanque (peça × índices TEMPO_*)
    repartidos pelo peso; itens sem tanque somam os filhos na hierarquia.
    """
    memo: Dict[int, float] = {}

    def calc(it: CronogramaItem) -> float:
        if it.id in memo:
            return memo[it.id]
        if it.tanque_id and it.id in share:
            v = float(dias_tank.get(it.tanque_id, 0.0)) * float(share[it.id])
            memo[it.id] = round(v, 4)
            return memo[it.id]
        filhos = _filhos_diretos_indice(it.indice or '', itens)
        if not filhos:
            memo[it.id] = 0.0
            return 0.0
        v = sum(calc(ch) for ch in filhos)
        memo[it.id] = round(v, 4)
        return memo[it.id]

    for it in itens:
        calc(it)
    return memo


def _ordenar_itens_topologico(itens: List[CronogramaItem]) -> List[CronogramaItem]:
    """Predecessores antes dos dependentes; ciclo ou pred inexistente quebra com fallback."""
    by_id = {i.id: i for i in itens}
    ids = set(by_id.keys())
    ordered: List[CronogramaItem] = []
    remaining = set(ids)
    while remaining:
        prontos = [
            i for i in remaining
            if by_id[i].predecessor_id is None
            or by_id[i].predecessor_id not in ids
            or by_id[i].predecessor_id not in remaining
        ]
        if not prontos:
            restantes = [by_id[i] for i in remaining]
            restantes.sort(key=lambda x: (x.indice_sort or '', x.id))
            ordered.extend(restantes)
            break
        prontos.sort(key=lambda x: (by_id[x].indice_sort or '', by_id[x].id))
        for i in prontos:
            ordered.append(by_id[i])
            remaining.discard(i)
    return ordered


def _real_placas_por_tanque_semana(
    contrato_id: int,
    week_keys: set,
) -> Dict[int, Dict[str, float]]:
    """Contagem de placas concretadas na semana (data_concretagem), por tanque."""
    tanques = Tanques.query.filter(Tanques.contrato_id == contrato_id).all()
    out: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for t in tanques:
        pecas = TanquesPecas.query.filter(TanquesPecas.tanque_id == t.id).all()
        for p in pecas:
            d_conv = _to_date(p.data_concretagem)
            if not d_conv:
                continue
            wk = segunda_feira_semana(d_conv).isoformat()
            if wk not in week_keys:
                continue
            out[t.id][wk] += 1.0

    return {tid: dict(weeks) for tid, weeks in out.items()}


def runs_intervalos_dias_semana_horizontais(
    dias_por_semana: Dict[str, float],
    week_keys: List[str],
) -> List[Dict[str, Any]]:
    """
    Agrupa semanas consecutivas com dias > 0 para desenhar uma barra horizontal contínua
    cuja largura = duração (número de semanas) e espessura ~ max(dias) no intervalo.
    Índices start/end são 0-based em week_keys (inclusivos).
    """
    n = len(week_keys)
    runs: List[Dict[str, Any]] = []
    i = 0
    while i < n:
        wk = week_keys[i]
        dv = float(dias_por_semana.get(wk, 0) or 0)
        if dv <= 1e-9:
            i += 1
            continue
        j = i
        peak = dv
        while j + 1 < n:
            wkn = week_keys[j + 1]
            dn = float(dias_por_semana.get(wkn, 0) or 0)
            if dn <= 1e-9:
                break
            j += 1
            if dn > peak:
                peak = dn
        runs.append({'start': i, 'end': j, 'max_dias': round(peak, 4)})
        i = j + 1
    return runs


def montar_matriz_previsto_real(
    contrato_id: int,
    data_inicio: date,
    data_fim: date,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[float]]:
    """
    Retorna (semanas, linhas, barras_dias_por_semana).
    Cada linha: indice, nome, tanque_nome, previsto e real em quantidade de placas por week_key.
    As linhas vêm ordenadas pelo início efetivo do previsto (cronológico), não só pelo índice hierárquico.

    Início do previsto (antes de predecessor): data do item, senão data prevista do tanque no cronograma,
    senão o início do intervalo da matriz. Com predecessor que tem tanque (execução direta), finish-to-start
    usa o fim da carga distribuída desse item. Predecessor sem tanque (apenas índice agregador) não soma
    as placas dos filhos como duração; o sucessor alinha ao início efetivo do predecessor (marco).

    Se existir vínculo CronogramaVinculoCalendario por prefixo de índice, a distribuição do previsto
    (e o FS do predecessor com tanque) usa dias úteis e feriados daquele calendário; prefixo mais longo
    prevalece. Sem vínculo, mantém o comportamento anterior (dias corridos nas semanas).
    """
    semanas = semanas_no_intervalo(data_inicio, data_fim)
    week_keys = [s['key'] for s in semanas]
    week_keys_set = set(week_keys)
    if not week_keys:
        return semanas, [], []

    placas_tank = total_placas_por_tanque_contrato(contrato_id)
    dias_tank = total_dias_por_tanque_contrato(contrato_id)
    ct_map = {
        r.tanque_id: r
        for r in CronogramaTanque.query.filter(CronogramaTanque.contrato_id == contrato_id).all()
    }

    itens = (
        CronogramaItem.query.filter(CronogramaItem.contrato_id == contrato_id)
        .order_by(CronogramaItem.indice_sort.asc(), CronogramaItem.id.asc())
        .all()
    )
    share = _peso_share_por_item(itens)
    vinculos_cal = CronogramaVinculoCalendario.query.filter_by(contrato_id=contrato_id).all()
    cal_por_item: Dict[int, Optional[CronogramaCalendario]] = {}
    cal_ids_usados: List[int] = []
    for it in itens:
        c = resolver_calendario_para_indice(
            contrato_id, it.indice or '', cache_vinculos=vinculos_cal,
        )
        cal_por_item[it.id] = c
        if c:
            cal_ids_usados.append(c.id)
    feriados_por_cal = mapa_feriados_por_calendario(cal_ids_usados)
    real_tank = _real_placas_por_tanque_semana(contrato_id, week_keys_set)

    tanque_nomes = {
        t.id: t.nome or f'#{t.id}'
        for t in Tanques.query.filter(Tanques.contrato_id == contrato_id).all()
    }

    by_id = {i.id: i for i in itens}
    placas_efetivas = _placas_efetivas_por_item(itens, share, placas_tank)
    dias_efetivos = _dias_efetivos_por_item(itens, share, dias_tank)

    # Data base do previsto (antes de predecessor FS): prioridade explícita
    # 1) CronogramaItem.data_inicio (sempre, inclusive com tanque)
    # 2) CronogramaTanque.data_inicio_prevista do tanque do item
    # 3) início do intervalo da matriz (filtro da tela)
    inicio_base_por_item: Dict[int, date] = {}
    for it in itens:
        if it.data_inicio:
            inicio_base_por_item[it.id] = it.data_inicio
        elif it.tanque_id:
            ct = ct_map.get(it.tanque_id)
            inicio_base_por_item[it.id] = (
                ct.data_inicio_prevista if ct and ct.data_inicio_prevista else data_inicio
            )
        else:
            inicio_base_por_item[it.id] = data_inicio

    ordenados = _ordenar_itens_topologico(itens)
    inicio_efetivo: Dict[int, date] = {}
    previsto_por_item: Dict[int, Dict[str, float]] = {}

    for it in ordenados:
        base = inicio_base_por_item.get(it.id, data_inicio)
        pid = it.predecessor_id
        if pid and pid in by_id and pid in inicio_efetivo:
            pred = by_id[pid]
            ip = inicio_efetivo[pid]
            # FS: dia após o fim da carga do predecessor quando ele tem execução no tanque.
            # Predecessor sem tanque (só agrega filhos na hierarquia): não usar a soma das
            # placas dos filhos como duração — isso empurrava o sucessor meses adiante e
            # esvaziava o previsto nas semanas do item âncora (ex.: 1.3 → 1.3.1).
            if pred.tanque_id and pred.id in share:
                placas_pred = placas_efetivas.get(pid, 0.0)
            else:
                placas_pred = 0.0
            pred_cal = cal_por_item.get(pid)
            pred_fer: Optional[Set] = (
                feriados_por_cal.get(pred_cal.id) if pred_cal else None
            )
            prox = primeiro_dia_apos_carga(placas_pred, ip, pred_cal, pred_fer)
            inicio_eff = max(prox, base)
        else:
            inicio_eff = base
        inicio_efetivo[it.id] = inicio_eff

        pecas_item = placas_efetivas.get(it.id, 0.0)
        pweek: Dict[str, float] = {k: 0.0 for k in week_keys}
        if it.tanque_id and it.id in share:
            it_cal = cal_por_item.get(it.id)
            it_fer: Optional[Set] = (
                feriados_por_cal.get(it_cal.id) if it_cal else None
            )
            dist = distribuir_carga_por_semana(pecas_item, inicio_eff, it_cal, it_fer)
            for seg in dist:
                k = seg['semana_inicio'].isoformat()
                if k in pweek:
                    pweek[k] = round(pweek[k] + float(seg['dias']), 4)
        previsto_por_item[it.id] = pweek

    # Itens sem tanque: previsto = soma dos filhos diretos (já com previsto preenchido, do mais profundo ao topo)
    itens_por_profundidade = sorted(
        itens,
        key=lambda x: (-len((x.indice or '').split('.')), -(len(x.indice_sort or '')), -x.id),
    )
    for it in itens_por_profundidade:
        if it.tanque_id and it.id in share:
            continue
        filhos = _filhos_diretos_indice(it.indice or '', itens)
        if not filhos:
            continue
        acc = {k: 0.0 for k in week_keys}
        for ch in filhos:
            pw = previsto_por_item.get(ch.id, {k: 0.0 for k in week_keys})
            for k in week_keys:
                acc[k] = round(acc[k] + float(pw.get(k, 0.0)), 4)
        previsto_por_item[it.id] = acc

    real_por_item: Dict[int, Dict[str, float]] = {}
    for it in itens:
        rw: Dict[str, float] = {k: 0.0 for k in week_keys}
        if it.tanque_id and it.id in share:
            tid = it.tanque_id
            rt = real_tank.get(tid, {})
            for wk in week_keys:
                rw[wk] = round(float(rt.get(wk, 0.0)) * float(share[it.id]), 4)
        real_por_item[it.id] = rw

    for it in itens_por_profundidade:
        if it.tanque_id and it.id in share:
            continue
        filhos = _filhos_diretos_indice(it.indice or '', itens)
        if not filhos:
            continue
        acc = {k: 0.0 for k in week_keys}
        for ch in filhos:
            rw = real_por_item.get(ch.id, {k: 0.0 for k in week_keys})
            for k in week_keys:
                acc[k] = round(acc[k] + float(rw.get(k, 0.0)), 4)
        real_por_item[it.id] = acc

    todos_indices = [(x.indice or '').strip() for x in itens]

    # Ordem das linhas na tela/export: cronológica pelo início efetivo do previsto (FS + calendário);
    # desempate pelo índice para estabilidade.
    itens_ordem_crono = sorted(
        itens,
        key=lambda x: (
            inicio_efetivo.get(x.id, data_inicio),
            x.indice_sort or '',
            x.id,
        ),
    )

    linhas: List[Dict[str, Any]] = []
    for it in itens_ordem_crono:
        prev = previsto_por_item.get(it.id, {k: 0.0 for k in week_keys})
        real: Dict[str, float] = real_por_item.get(it.id, {k: 0.0 for k in week_keys})

        acc_p = 0.0
        acc_r = 0.0
        previsto_acum: Dict[str, float] = {}
        real_acum: Dict[str, float] = {}
        for wk in week_keys:
            acc_p = round(acc_p + float(prev.get(wk, 0.0)), 4)
            acc_r = round(acc_r + float(real.get(wk, 0.0)), 4)
            previsto_acum[wk] = acc_p
            real_acum[wk] = acc_r

        ix_s = (it.indice or '').strip()
        parts = ix_s.split('.') if ix_s else []
        linhas.append({
            'item_id': it.id,
            'indice': it.indice or '',
            'nome': it.nome or '',
            'tanque_nome': tanque_nomes.get(it.tanque_id, '—') if it.tanque_id else '—',
            'prazo_dias_total': round(dias_efetivos.get(it.id, 0.0), 4),
            'previsto': prev,
            'real': real,
            'previsto_acum': previsto_acum,
            'real_acum': real_acum,
            'parent_indice': _parent_indice_str(ix_s),
            'profundidade': len(parts),
            'tem_filhos': _tem_descendente_indice(ix_s, todos_indices),
        })

    # Dias de trabalho por semana (só itens com tanque): prazo total × (previsto na semana / placas totais do item)
    dias_previsto_por_item: Dict[int, Dict[str, float]] = {}
    for it in itens:
        dias_previsto_por_item[it.id] = {k: 0.0 for k in week_keys}
    barras_por_semana: Dict[str, float] = {k: 0.0 for k in week_keys}
    for it in itens:
        if not (it.tanque_id and it.id in share):
            continue
        pec = float(placas_efetivas.get(it.id, 0.0) or 0.0)
        if pec <= 1e-9:
            continue
        dias_i = float(dias_efetivos.get(it.id, 0.0) or 0.0)
        prev = previsto_por_item.get(it.id, {})
        for wk in week_keys:
            p = float(prev.get(wk, 0.0) or 0.0)
            val = round(dias_i * (p / pec), 4)
            barras_por_semana[wk] = round(barras_por_semana[wk] + val, 4)
            dias_previsto_por_item[it.id][wk] = val
    barras_dias_semana = [barras_por_semana[wk] for wk in week_keys]

    for row in linhas:
        dps = dias_previsto_por_item.get(row['item_id'], {k: 0.0 for k in week_keys})
        row['dias_previsto_semana'] = dps
        row['dias_previsto_runs'] = runs_intervalos_dias_semana_horizontais(dps, week_keys)

    return semanas, linhas, barras_dias_semana


def agregar_curva_s_projeto(
    semanas: List[Dict[str, Any]],
    linhas: List[Dict[str, Any]],
) -> Tuple[List[str], List[float], List[float], List[float], List[float], float]:
    """
    Agrega todos os itens por semana e calcula acumulados (curva S).
    Retorna labels, placas acum. previsto/real, % acum. (base = previsto final no período),
    e max_y sugerido para o eixo (>=100 se real ultrapassar a meta).
    """
    week_keys = [s['key'] for s in semanas]
    labels = [s.get('label_full') or s.get('label', '') for s in semanas]
    acc_p = 0.0
    acc_r = 0.0
    curve_p: List[float] = []
    curve_r: List[float] = []
    for wk in week_keys:
        sp = sum(float(row['previsto'].get(wk, 0.0)) for row in linhas)
        sr = sum(float(row['real'].get(wk, 0.0)) for row in linhas)
        acc_p = round(acc_p + sp, 4)
        acc_r = round(acc_r + sr, 4)
        curve_p.append(acc_p)
        curve_r.append(acc_r)
    total_p = curve_p[-1] if curve_p else 0.0
    if total_p <= 0:
        pct_p = [0.0 for _ in curve_p]
        pct_r = [0.0 for _ in curve_r]
    else:
        pct_p = [round(100.0 * x / total_p, 2) for x in curve_p]
        pct_r = [round(100.0 * x / total_p, 2) for x in curve_r]
    max_pct = 100.0
    if pct_p:
        max_pct = max(max_pct, max(pct_p))
    if pct_r:
        max_pct = max(max_pct, max(pct_r))
    max_y = max(100.0, round(max_pct + 5.0, 0))
    return labels, curve_p, curve_r, pct_p, pct_r, max_y


def max_data_concretagem_contrato(contrato_id: int) -> Optional[date]:
    """Última data de concretagem (peças) em tanques do contrato."""
    r = (
        db.session.query(func.max(TanquesPecas.data_concretagem))
        .join(Tanques, TanquesPecas.tanque_id == Tanques.id)
        .filter(Tanques.contrato_id == contrato_id)
    ).scalar()
    if r is None:
        return None
    if isinstance(r, datetime):
        return r.date()
    return r


def data_fim_horizonte_matriz(
    contrato_id: int,
    data_inicio: date,
    data_fim_formulario: Optional[date],
) -> date:
    """
    Limite superior para o cálculo da matriz: precisa cobrir previsto longo e última concretagem real.
    """
    horizonte_prev = data_inicio + timedelta(days=366 * 15)
    fecha_real = max_data_concretagem_contrato(contrato_id)
    candidates = [data_inicio + timedelta(days=7), horizonte_prev]
    if data_fim_formulario:
        candidates.append(data_fim_formulario)
    if fecha_real:
        candidates.append(fecha_real)
    return max(candidates)


def trim_trailing_semanas_sem_previsto_nem_real(
    semanas: List[Dict[str, Any]],
    linhas: List[Dict[str, Any]],
    barras_dias: Optional[List[float]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], date, Optional[List[float]]]:
    """
    Encerra o intervalo na última semana em que alguma linha tenha previsto ou real > 0.
    Recalcula previsto_acum / real_acum no período exibido.
    Opcionalmente corta barras_dias na mesma proporção das semanas.
    """
    if not semanas:
        return semanas, linhas, date.today(), barras_dias

    week_keys = [s['key'] for s in semanas]
    last_active = -1
    for i in range(len(week_keys) - 1, -1, -1):
        wk = week_keys[i]
        found = False
        for row in linhas:
            if float(row.get('previsto', {}).get(wk, 0) or 0) > 1e-9:
                found = True
                break
            if float(row.get('real', {}).get(wk, 0) or 0) > 1e-9:
                found = True
                break
        if found:
            last_active = i
            break

    if last_active < 0:
        ult = semanas[-1]
        return semanas, linhas, ult['semana_fim'], barras_dias

    semanas_cut = semanas[: last_active + 1]
    wk_keep = [s['key'] for s in semanas_cut]
    new_linhas: List[Dict[str, Any]] = []
    for row in linhas:
        prev = {wk: float(row['previsto'].get(wk, 0) or 0) for wk in wk_keep}
        real = {wk: float(row['real'].get(wk, 0) or 0) for wk in wk_keep}
        acc_p = 0.0
        acc_r = 0.0
        p_acum: Dict[str, float] = {}
        r_acum: Dict[str, float] = {}
        for wk in wk_keep:
            acc_p = round(acc_p + prev[wk], 4)
            acc_r = round(acc_r + real[wk], 4)
            p_acum[wk] = acc_p
            r_acum[wk] = acc_r
        nr = dict(row)
        nr['previsto'] = prev
        nr['real'] = real
        nr['previsto_acum'] = p_acum
        nr['real_acum'] = r_acum
        if 'dias_previsto_semana' in row:
            nr['dias_previsto_semana'] = {
                wk: float(row['dias_previsto_semana'].get(wk, 0) or 0) for wk in wk_keep
            }
            nr['dias_previsto_runs'] = runs_intervalos_dias_semana_horizontais(
                nr['dias_previsto_semana'], wk_keep
            )
        new_linhas.append(nr)

    data_fim = semanas_cut[-1]['semana_fim']
    barras_cut: Optional[List[float]] = None
    if barras_dias is not None and len(barras_dias) == len(week_keys):
        barras_cut = barras_dias[: last_active + 1]
    return semanas_cut, new_linhas, data_fim, barras_cut
