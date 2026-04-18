"""
Pista da concretagem (ConcretoConcretagens) por peça (TanquesPecas).

Usado por operacional/acabamento_transporte e relatórios/acabamento_pecas.
"""

import json

import logging
logger = logging.getLogger(__name__)
def normalizar_chave_peca(nome, tanque_id):
    if not nome or tanque_id in (None, ""):
        return None
    try:
        tanque_id_int = int(tanque_id)
    except (TypeError, ValueError):
        return None
    return (str(nome).strip().lower(), tanque_id_int)


def nome_e_tanque_do_item_concretagem(peca):
    """Mesma convenção que operacional/concretagem_controller: nome/placa e tanque_id/tanque."""
    if not isinstance(peca, dict):
        return None, None
    nome = peca.get("nome") or peca.get("placa")
    tanque_id_val = peca.get("tanque_id")
    if tanque_id_val is None:
        tanque_id_val = peca.get("tanque")
    return nome, tanque_id_val


def extrair_ids_pecas_concretagem(pecas_raw, indice_nome_tanque=None):
    if not pecas_raw:
        return []
    try:
        pecas_list = json.loads(pecas_raw) if isinstance(pecas_raw, str) else pecas_raw
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(pecas_list, list):
        return []

    ids = []
    for peca in pecas_list:
        if not isinstance(peca, dict):
            continue
        peca_id = peca.get("peca_id")
        if peca_id not in (None, ""):
            try:
                ids.append(int(peca_id))
                continue
            except (TypeError, ValueError):
                pass

        if not indice_nome_tanque:
            continue
        nome_item, tanque_item = nome_e_tanque_do_item_concretagem(peca)
        chave = normalizar_chave_peca(nome_item, tanque_item)
        if not chave:
            continue
        for pid in indice_nome_tanque.get(chave) or ():
            ids.append(pid)
    return ids


def montar_mapa_pista_por_peca(pecas):
    """
    Para cada id de TanquesPecas em `pecas`, retorna a pista (str) da concretagem mais recente
    que lista essa peça no JSON `pecas` (por peca_id ou fallback nome/placa + tanque).
    """
    # Import lazy: evita ciclo concretagens → services → acabamento_pista → concretagens
    from ..entities.concretagens import ConcretoConcretagens

    if not pecas:
        return {}

    ids_alvo = {peca.id for peca in pecas}
    indice_nome_tanque = {}
    for peca in pecas:
        chave = normalizar_chave_peca(peca.nome, peca.tanque_id)
        #print(chave)
        if chave:
            indice_nome_tanque.setdefault(chave, []).append(peca.id)
    #logger.info("indice_nome_tanque: " + str(indice_nome_tanque))
    mapa = {}
    concretagens = (
        ConcretoConcretagens.query.with_entities(
            ConcretoConcretagens.id,
            ConcretoConcretagens.data_concretagem,
            ConcretoConcretagens.pista,
            ConcretoConcretagens.pecas,
        )
        .order_by(ConcretoConcretagens.data_concretagem.desc(), ConcretoConcretagens.id.desc())
        .all()
    )

    for concretagem in concretagens:
        pista = concretagem.pista.strip() if isinstance(concretagem.pista, str) else concretagem.pista
        for peca_id in extrair_ids_pecas_concretagem(concretagem.pecas, indice_nome_tanque=indice_nome_tanque):
            if peca_id not in ids_alvo:
                continue
            if peca_id not in mapa:
                mapa[peca_id] = pista

    return mapa
