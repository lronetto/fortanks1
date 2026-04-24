"""Montagem de listagens e resumos para APIs de concretagem."""

from collections import defaultdict

from models.concreto import ConcretoConcretagens, peca_obj_ja_produzida
from models.tanque import Tanques, TanquesPecas

from .estado import (
    concretagem_concluida,
    concretagem_formas_ok,
    concretagem_produzida,
    concretagem_tem_alongamentos,
    concretagem_tem_usinagens,
)


def montar_dados_api_listar(filtro_status: str) -> list:
    """Linhas JSON para GET /api/listar."""
    concretagens = ConcretoConcretagens.query.order_by(ConcretoConcretagens.data_concretagem.desc()).all()
    filtro_status = (filtro_status or '').strip().lower()

    data = []
    for conc in concretagens:
        concluida = concretagem_concluida(conc)
        status_val = 'concluido' if concluida else 'em_andamento'
        if filtro_status and status_val != filtro_status:
            continue
        data.append({
            'concretagem': conc.conc,
            'id': conc.id,
            'data_concretagem': conc.data_concretagem.isoformat() if conc.data_concretagem else None,
            'pista': conc.pista,
            'quantidade_pecas': len(conc.get_pecas()),
            'tem_formas': concretagem_formas_ok(conc),
            'tem_alongamentos': concretagem_tem_alongamentos(conc),
            'tem_usinagens': concretagem_tem_usinagens(conc),
            'produzida': concretagem_produzida(conc),
            'status': status_val,
            'concluida': concluida,
            'data_cadastro': conc.data_cadastro.isoformat() if conc.data_cadastro else None
        })
    return data


def montar_resumo_pecas_nao_produzidas() -> tuple[list, int]:
    """
    Agrega peças em concretagens ainda sem produção, por tanque e tipo.
    Retorna (linhas, total_geral).
    """
    cache_pecas = {}
    grupos = defaultdict(int)
    tanque_nomes = {}

    def peca_cached(nome, tid):
        key = (nome, tid)
        if key not in cache_pecas:
            cache_pecas[key] = TanquesPecas.query.filter_by(nome=nome, tanque_id=tid).first()
        return cache_pecas[key]

    concretagens = ConcretoConcretagens.query.order_by(ConcretoConcretagens.data_concretagem.desc()).all()
    for conc in concretagens:
        for item in conc.get_pecas():
            nome = item.get('nome') or item.get('placa')
            tanque_id_val = item.get('tanque_id') or item.get('tanque')
            if not nome or tanque_id_val is None:
                continue
            try:
                tid = int(tanque_id_val) if isinstance(tanque_id_val, str) else tanque_id_val
            except (ValueError, TypeError):
                continue
            peca = peca_cached(nome, tid)
            if not peca:
                continue
            if peca_obj_ja_produzida(peca):
                continue
            grupos[(tid, peca.tipo or '')] += 1
            if tid not in tanque_nomes:
                if peca.tanque:
                    tanque_nomes[tid] = peca.tanque.nome
                else:
                    t = Tanques.query.get(tid)
                    tanque_nomes[tid] = t.nome if t else f'Tanque #{tid}'

    linhas = []
    for (tid, tipo) in sorted(grupos.keys(), key=lambda k: (tanque_nomes.get(k[0], str(k[0])).lower(), (k[1] or '').lower())):
        linhas.append({
            'tanque_id': tid,
            'tanque_nome': tanque_nomes.get(tid, f'#{tid}'),
            'tipo': tipo or '—',
            'quantidade': grupos[(tid, tipo)],
        })
    total = sum(l['quantidade'] for l in linhas)
    return linhas, total
