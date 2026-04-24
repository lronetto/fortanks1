"""
Helpers de negócio para avaliações PLR.

Mantém lógica reutilizável fora das rotas HTTP.
"""

import re

from models.plr import PLRColaborador

from ..constantes import CRITERIOS_PADRAO_PLR


def avaliacao_list_for_form(avaliacao_field):
    """Converte campo avaliacao (JSON) em lista de dicts para o formulário."""
    if not avaliacao_field:
        return list(CRITERIOS_PADRAO_PLR)
    if isinstance(avaliacao_field, list):
        return [x if isinstance(x, dict) else {"tipo": "", "valor": x} for x in avaliacao_field]
    if isinstance(avaliacao_field, dict):
        return [avaliacao_field]
    return list(CRITERIOS_PADRAO_PLR)


def valor_por_tipo(avaliacao, tipo):
    """Retorna o valor do critério pelo tipo na lista avaliacao, ou None."""
    if not avaliacao or not isinstance(avaliacao, list):
        return None
    for item in avaliacao:
        if isinstance(item, dict) and item.get("tipo") == tipo:
            valor = item.get("valor")
            if valor is not None:
                try:
                    return float(valor)
                except (TypeError, ValueError):
                    return None
    return None


def equipes_distintas_plr():
    """Retorna lista de nomes de equipe distintos em PLRColaborador.equipe_alocada."""
    registros = PLRColaborador.query.filter(PLRColaborador.equipe_alocada.isnot(None)).all()
    vistos = set()
    resultado = []
    for av in registros:
        if not isinstance(av.equipe_alocada, list):
            continue
        for nome in av.equipe_alocada:
            if not nome or not isinstance(nome, str):
                continue
            nome_limpo = nome.strip()
            if nome_limpo and nome_limpo not in vistos:
                vistos.add(nome_limpo)
                resultado.append(nome_limpo)
    return sorted(resultado)


def cpf_apenas_digitos(cpf):
    """Retorna CPF apenas com dígitos para comparação."""
    if cpf is None:
        return ""
    return re.sub(r"\D", "", str(cpf))
