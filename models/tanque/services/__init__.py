"""Serviços do domínio tanque."""

from models.evolution import normalizar_numero_whatsapp_br

from .dimensoes_e_estatisticas import (
    atualizar_dimensoes_numericas,
    calcular_estatisticas_tanque,
    contar_concretadas,
    listar_ids_pecas_com_data_concretagem,
    obter_pecas_ids_concretadas_via_concretagens,
)
from .qualidade import peca_in_concretagem
from .whatsapp_transporte import (
    enviar_whatsapp_transporte,
    montar_texto_whatsapp_transporte,
)

__all__ = [
    'atualizar_dimensoes_numericas',
    'calcular_estatisticas_tanque',
    'contar_concretadas',
    'listar_ids_pecas_com_data_concretagem',
    'obter_pecas_ids_concretadas_via_concretagens',
    'peca_in_concretagem',
    'enviar_whatsapp_transporte',
    'montar_texto_whatsapp_transporte',
    'normalizar_numero_whatsapp_br',
]
