"""
Domínio de tanques: modelos ORM, utilitários de data e serviços (dimensões, estatísticas).

Imports públicos mantêm compatibilidade com `from models.tanque import ...`.
"""

from .entities import (
    Tanques,
    TanquesGrupos,
    TanquesPecas,
    TanquesProdutoComposto,
    TanquesTransportes,
    tanques_grupos,
)
from .services import (
    atualizar_dimensoes_numericas,
    calcular_estatisticas_tanque,
    contar_concretadas,
    listar_ids_pecas_com_data_concretagem,
    obter_pecas_ids_concretadas_via_concretagens,
    peca_in_concretagem,
)
from .utils.datas import parse_data_ate

__all__ = [
    'Tanques',
    'TanquesGrupos',
    'TanquesPecas',
    'TanquesProdutoComposto',
    'TanquesTransportes',
    'atualizar_dimensoes_numericas',
    'calcular_estatisticas_tanque',
    'contar_concretadas',
    'listar_ids_pecas_com_data_concretagem',
    'obter_pecas_ids_concretadas_via_concretagens',
    'peca_in_concretagem',
    'parse_data_ate',
    'tanques_grupos',
]
