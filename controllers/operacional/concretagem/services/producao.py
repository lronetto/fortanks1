"""Operações de produção / estoque ligadas a concretagens."""

from datetime import datetime, date as date_type

from sqlalchemy import func

from models.concreto import ConcretoConcretagens
from models.database import db
from models.estoque import EstoqueMovimentacoes
from models.tanque import TanquesPecas, TanquesProdutoComposto


def remover_movimentacoes_producao_peca_escopo_concretagens(concretagem_ids):
    """
    Remove movimentações origem_tipo producao_peca associadas às concretagens informadas.
    Retorna quantidade de movimentações removidas.
    """
    mov_ids = set()
    for cid in concretagem_ids:
        conc = ConcretoConcretagens.query.get(cid)
        if not conc or not conc.data_concretagem:
            continue
        dc = conc.data_concretagem
        if isinstance(dc, datetime):
            data_d = dc.date()
        elif isinstance(dc, date_type):
            data_d = dc
        else:
            try:
                data_d = datetime.strptime(str(dc)[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue
        for pref in conc.get_pecas():
            try:
                nome = (pref.get('nome') or '').strip()
                tid = int(pref['tanque_id'])
            except (KeyError, TypeError, ValueError):
                continue
            if not nome:
                continue
            peca_obj = TanquesPecas.query.filter_by(nome=nome, tanque_id=tid).first()
            if not peca_obj:
                continue
            vinc = TanquesProdutoComposto.query.filter_by(
                tanque_id=tid,
                tipo_peca=peca_obj.tipo,
            ).first()
            if not vinc:
                continue
            pid = vinc.produto_composto_id
            qry = EstoqueMovimentacoes.query.filter(
                EstoqueMovimentacoes.origem_tipo == 'producao_peca',
                EstoqueMovimentacoes.origem_id == pid,
                func.date(EstoqueMovimentacoes.data_movimento) == data_d,
                EstoqueMovimentacoes.observacao.like(f'%{nome}%'),
            )
            for m in qry.all():
                mov_ids.add(m.id)
    n = 0
    for mid in mov_ids:
        m = EstoqueMovimentacoes.query.get(mid)
        if m:
            m.delete()
            n += 1
    return n
