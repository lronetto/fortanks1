"""
Cálculo de cronograma a partir das peças (TanquesPecas) e índices do tanque (dados_adicionais.indices).

- TEMPO_* : dias por peça (ex.: TEMPO_PN = 0,22).
- TEMPOS_* : placas por semana (ex.: TEMPOS_PN = 10); a carga é convertida em unidades para a mesma distribuição da matriz.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from models.tanque import Tanques, TanquesPecas


def _parse_float_br(s: Any) -> Optional[float]:
    if s is None:
        return None
    t = str(s).strip().replace(',', '.')
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def indices_tanque_para_mapa(dados_adicionais_raw: Optional[str]) -> Dict[str, float]:
    """Converte JSON dados_adicionais em mapa nome do índice -> valor numérico."""
    out: Dict[str, float] = {}
    if not dados_adicionais_raw or not str(dados_adicionais_raw).strip():
        return out
    try:
        d = json.loads(dados_adicionais_raw)
    except (json.JSONDecodeError, TypeError):
        return out
    if not isinstance(d, dict):
        return out
    indices = d.get('indices')
    if not isinstance(indices, list):
        return out
    for it in indices:
        if not isinstance(it, dict):
            continue
        nome = (it.get('nome') or '').strip()
        if not nome:
            continue
        v = _parse_float_br(it.get('valor'))
        if v is not None:
            out[nome.upper()] = v
    return out


def _normalizar_tipo(tipo: Optional[str]) -> str:
    return (tipo or '').strip().upper()


def _primeira_chave_existente(chaves: Dict[str, float], candidatos: List[str]) -> Optional[str]:
    for c in candidatos:
        if c in chaves:
            return c
    return None


def chave_tempo_para_tipo(tipo: Optional[str], chaves_indices: Dict[str, float]) -> Optional[str]:
    """
    Mapeia o tipo da peça para o índice no tanque (dados_adicionais.indices).

    - TEMPOS_T : se existir no tanque, vale para **todos** os tipos de placa; demais índices TEMPO_* / TEMPOS_* são ignorados.
    - TEMPO_* : dias por peça (ritmo em dias).
    - TEMPOS_* : placas por semana (ritmo semanal); preferido se existir para o grupo (exceto quando TEMPOS_T domina).

    Grupos: PN / PF / PE e fallbacks TEMPO_{TIPO} ou TEMPOS_{TIPO}.
    Nomes no JSON são normalizados em maiúsculas.
    """
    if 'TEMPOS_T' in chaves_indices:
        return 'TEMPOS_T'
    t = _normalizar_tipo(tipo)
    if not t:
        return None
    keys = set(chaves_indices.keys())

    # --- Grupo PF (PF, PFI): verificar antes de PN porque "PF" começa com P ---
    if t == 'PF' or t == 'PFI' or t.startswith('PFI') or (t.startswith('PF') and not t.startswith('PN')):
        k = _primeira_chave_existente(
            chaves_indices,
            ['TEMPOS_PF', 'TEMPOS_PLACA_FECHO', 'TEMPO_PF', 'TEMPO_PLACA_FECHO'],
        )
        return k

    # --- Grupo PN (P, PN, PNI) ---
    if t == 'P':
        k = _primeira_chave_existente(
            chaves_indices,
            ['TEMPOS_PN', 'TEMPOS_PLACA_NORMAL', 'TEMPO_PN', 'TEMPO_PLACA_NORMAL'],
        )
        return k
    if t.startswith('PNI'):
        k = _primeira_chave_existente(
            chaves_indices,
            ['TEMPOS_PN', 'TEMPOS_PLACA_NORMAL', 'TEMPO_PN', 'TEMPO_PLACA_NORMAL'],
        )
        return k
    if t.startswith('PN'):
        k = _primeira_chave_existente(
            chaves_indices,
            ['TEMPOS_PN', 'TEMPOS_PLACA_NORMAL', 'TEMPO_PN', 'TEMPO_PLACA_NORMAL'],
        )
        return k
    if 'NORMAL' in t or ('PLACA' in t and 'NORMAL' in t):
        k = _primeira_chave_existente(
            chaves_indices,
            ['TEMPOS_PN', 'TEMPOS_PLACA_NORMAL', 'TEMPO_PN', 'TEMPO_PLACA_NORMAL'],
        )
        return k

    # Legado: texto "fecho" / placa fecho → PF
    if 'FECHO' in t or ('PLACA' in t and 'FECHO' in t):
        k = _primeira_chave_existente(
            chaves_indices,
            ['TEMPOS_PF', 'TEMPOS_PLACA_FECHO', 'TEMPO_PF', 'TEMPO_PLACA_FECHO'],
        )
        return k

    # --- Grupo PE: todos os outros ---
    k = _primeira_chave_existente(chaves_indices, ['TEMPOS_PE', 'TEMPO_PE'])
    if k:
        return k

    candidato_s = f'TEMPOS_{t}'
    if candidato_s in keys:
        return candidato_s
    candidato = f'TEMPO_{t}'
    if candidato in keys:
        return candidato
    for key in keys:
        if key.startswith('TEMPOS_') and t in key.replace('TEMPOS_', ''):
            return key
    for key in keys:
        if key.startswith('TEMPO_') and t in key.replace('TEMPO_', ''):
            return key
    return None


def _indice_ritmo_cronograma(k: str) -> bool:
    """TEMPO_* (dias/peça) ou TEMPOS_* (placas/semana)."""
    kn = str(k).upper().strip()
    return kn.startswith('TEMPO_') or kn.startswith('TEMPOS_')


def _merge_indices_tanque_simulacao(
    chaves: Dict[str, float],
    tid: int,
    indices_por_tanque: Optional[Dict[int, Dict[str, float]]],
) -> Dict[str, float]:
    """Sobrepõe valores TEMPO_* / TEMPOS_* vindos da simulação (mantém demais chaves do cadastro)."""
    if not indices_por_tanque:
        return chaves
    extra = indices_por_tanque.get(tid)
    if not extra:
        return chaves
    out = dict(chaves)
    for k, v in extra.items():
        if v is None:
            continue
        kn = str(k).upper().strip()
        if not _indice_ritmo_cronograma(kn):
            continue
        try:
            out[kn] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def calcular_projeto_pecas(
    contrato_id: int,
    indices_por_tanque: Optional[Dict[int, Dict[str, float]]] = None,
) -> Tuple[
    List[Dict[str, Any]],
    List[str],
    float,
]:
    """
    Agrega peças por tanque e tipo. Índices TEMPO_* = dias por peça; TEMPOS_* = placas por semana
    (carga equivalente: semanas × 7 para distribuição na matriz). Retorna (linhas_detalhe, avisos, total_dias_projeto).
    """
    tanques = Tanques.query.filter(Tanques.contrato_id == contrato_id).all()
    tid_nome = {t.id: (t.nome or f'#{t.id}', t) for t in tanques}

    linhas: List[Dict[str, Any]] = []
    avisos: List[str] = []
    total_geral = 0.0

    for tid, (nome_tanque, tanque) in sorted(tid_nome.items(), key=lambda x: (x[1][0] or '').lower()):
        chaves = _merge_indices_tanque_simulacao(
            indices_tanque_para_mapa(tanque.dados_adicionais),
            tid,
            indices_por_tanque,
        )
        pecas = TanquesPecas.query.filter(TanquesPecas.tanque_id == tid).all()

        # (tipo_original, chave_tempo) -> quantidade
        grupos: Dict[Tuple[str, Optional[str]], int] = defaultdict(int)
        for p in pecas:
            tipo_o = (p.tipo or '').strip() or '(sem tipo)'
            ck = chave_tempo_para_tipo(p.tipo, chaves)
            grupos[(tipo_o, ck)] += 1

        for (tipo_o, ck), qtd in sorted(grupos.items(), key=lambda x: x[0][0].lower()):
            if not ck:
                avisos.append(
                    f'Tanque "{nome_tanque}": tipo "{tipo_o}" sem índice TEMPO_* ou TEMPOS_* correspondente nos dados adicionais.'
                )
                dias_por_peca = 0.0
                dias_tipo = 0.0
            elif str(ck).upper().startswith('TEMPOS_'):
                placas_sem = float(chaves.get(ck, 0.0) or 0.0)
                dias_por_peca = 0.0
                if placas_sem <= 1e-12:
                    dias_tipo = 0.0
                    avisos.append(
                        f'Tanque "{nome_tanque}": tipo "{tipo_o}" índice {ck} inválido ou zero (placas/semana).'
                    )
                else:
                    # Semanas necessárias × 7 = unidades no mesmo eixo de distribuição que "dias" de TEMPO_*
                    dias_tipo = round((float(qtd) / placas_sem) * 7.0, 4)
            else:
                dias_por_peca = float(chaves.get(ck, 0.0))
                dias_tipo = round(qtd * dias_por_peca, 4)
            valor_ritmo = float(chaves.get(ck, 0.0) or 0.0) if ck else 0.0
            linhas.append({
                'tanque_id': tid,
                'tanque_nome': nome_tanque,
                'tipo_peca': tipo_o,
                'chave_indice': ck or '—',
                'quantidade': qtd,
                'dias_por_peca': dias_por_peca,
                'valor_ritmo': valor_ritmo,
                'dias_total': dias_tipo,
            })

    total_geral = round(sum(r['dias_total'] for r in linhas), 4)
    return linhas, avisos, total_geral


def total_dias_por_tanque_contrato(
    contrato_id: int,
    indices_por_tanque: Optional[Dict[int, Dict[str, float]]] = None,
) -> Dict[int, float]:
    """Soma dos dias (peça × índice) por tanque no contrato."""
    linhas, _, _ = calcular_projeto_pecas(contrato_id, indices_por_tanque=indices_por_tanque)
    acc: Dict[int, float] = defaultdict(float)
    for r in linhas:
        acc[r['tanque_id']] += float(r['dias_total'])
    return {k: round(v, 4) for k, v in acc.items()}


def total_placas_por_tanque_contrato(contrato_id: int) -> Dict[int, int]:
    """Quantidade de peças (placas) cadastradas por tanque no contrato."""
    tanques = Tanques.query.filter(Tanques.contrato_id == contrato_id).all()
    out: Dict[int, int] = {}
    for t in tanques:
        n = TanquesPecas.query.filter(TanquesPecas.tanque_id == t.id).count()
        out[t.id] = int(n)
    return out


def segunda_feira_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


def distribuir_dias_por_semana(total_dias: float, inicio: date) -> List[Dict[str, Any]]:
    """
    Distribui a carga (dias corridos) a partir de `inicio`, preenchendo semanas de segunda a domingo.
    """
    if total_dias <= 0:
        return []

    out: List[Dict[str, Any]] = []
    restante = float(total_dias)
    cur = inicio

    while restante > 1e-9:
        ws = segunda_feira_semana(cur)
        we = ws + timedelta(days=6)
        dias_ate_fim = (we - cur).days + 1
        if dias_ate_fim < 1:
            dias_ate_fim = 1
        aloc = min(restante, float(dias_ate_fim))
        semana_iso = cur.isocalendar()
        out.append({
            'semana_inicio': ws,
            'semana_fim': we,
            'dias': round(aloc, 4),
            'semana_numero': semana_iso[1],
            'ano_iso': semana_iso[0],
            'label': f'S{semana_iso[1]:02d}/{semana_iso[0]} — {ws.strftime("%d/%m")} a {we.strftime("%d/%m/%Y")}',
        })
        restante -= aloc
        cur = we + timedelta(days=1)

    return out


def primeiro_dia_apos_trabalho(total_unidades: float, inicio: date) -> date:
    """
    Primeiro dia em que um sucessor pode iniciar (finish-to-start):
    dia seguinte ao último dia da semana de término da distribuição.
    `total_unidades` pode ser dias ou quantidade de placas (mesmo algoritmo de distribuição).
    Sem carga ou sem distribuição, retorna `inicio` (pode alinhar com max(..., base do sucessor)).
    """
    if total_unidades <= 1e-9:
        return inicio
    dist = distribuir_dias_por_semana(total_unidades, inicio)
    if not dist:
        return inicio
    return dist[-1]['semana_fim'] + timedelta(days=1)


def semanas_no_intervalo(data_inicio: date, data_fim: date) -> List[Dict[str, Any]]:
    """Lista de semanas (segunda a domingo) que intersectam o intervalo [data_inicio, data_fim]."""
    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio
    out: List[Dict[str, Any]] = []
    cur = segunda_feira_semana(data_inicio)
    while cur <= data_fim:
        we = cur + timedelta(days=6)
        iso = cur.isocalendar()
        out.append({
            'key': cur.isoformat(),
            'semana_inicio': cur,
            'semana_fim': we,
            'semana_numero': iso[1],
            'ano_iso': iso[0],
            'label': f"S{iso[1]:02d}/{iso[0]}",
            'label_full': f"{cur.strftime('%d/%m')} – {we.strftime('%d/%m/%Y')}",
        })
        cur += timedelta(days=7)
    return out


def dados_simulacao_indices_tanques_contrato(contrato_id: int) -> Dict[str, Any]:
    """
    Monta dados para tabela de simulação: tanques × colunas TEMPO_* (dias/peça) e TEMPOS_* (placas/semana).
    Retorna colunas ordenadas e uma linha por tanque com dict valores por coluna.
    """
    tanques = Tanques.query.filter(Tanques.contrato_id == contrato_id).order_by(Tanques.nome.asc()).all()
    todas_chaves: set = set()
    brutos: List[tuple] = []
    for t in tanques:
        m = indices_tanque_para_mapa(t.dados_adicionais)
        temp = {k: float(v) for k, v in m.items() if _indice_ritmo_cronograma(k)}
        todas_chaves.update(temp.keys())
        brutos.append((t.id, t.nome or f'#{t.id}', temp))

    ordem_pref = [
        'TEMPOS_T',
        'TEMPO_PN',
        'TEMPO_PLACA_NORMAL',
        'TEMPO_PF',
        'TEMPO_PLACA_FECHO',
        'TEMPO_PE',
        'TEMPOS_PN',
        'TEMPOS_PLACA_NORMAL',
        'TEMPOS_PF',
        'TEMPOS_PLACA_FECHO',
        'TEMPOS_PE',
    ]
    colunas = [x for x in ordem_pref if x in todas_chaves]
    colunas.extend(sorted(k for k in todas_chaves if k not in colunas))

    linhas: List[Dict[str, Any]] = []
    for tid, nome, temp in brutos:
        linhas.append(
            {
                'tanque_id': tid,
                'nome': nome,
                'valores': {c: temp.get(c) for c in colunas},
            }
        )

    return {
        'tem_tanques': len(tanques) > 0,
        'colunas': colunas,
        'linhas': linhas,
    }
