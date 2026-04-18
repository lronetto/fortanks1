"""Serviços relacionados ao JSON qualidade da peça e vínculo com concretagens."""

from models.concreto import (
    ConcretoConcretagens,
    extrair_ids_pecas_concretagem,
    normalizar_chave_peca,
)


def peca_in_concretagem(peca):
    """
    Retorna True se a peça já consta no JSON `pecas` de algum ConcretoConcretagens,
    por `peca_id` ou por nome + tanque_id (mesma convenção de acabamento/pista).

    Espera objeto com atributos `id`, `nome` e `tanque_id` (ex.: TanquesPecas).
    Peça ainda não persistida (sem `id`) retorna False.
    """
    if peca is None:
        return False
    peca_id = getattr(peca, 'id', None)
    nome = getattr(peca, 'nome', None)
    tanque_id = getattr(peca, 'tanque_id', None)
    if peca_id is None or nome is None or tanque_id is None:
        return False

    chave = normalizar_chave_peca(nome, tanque_id)
    indice_nome_tanque = {chave: [peca_id]} if chave else None

    for (pecas_raw,) in ConcretoConcretagens.query.with_entities(ConcretoConcretagens.pecas).all():
        ids = extrair_ids_pecas_concretagem(pecas_raw, indice_nome_tanque=indice_nome_tanque)
        if peca_id in ids:
            return True
    return False
