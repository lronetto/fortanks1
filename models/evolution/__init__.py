"""
Domínio Evolution API (WhatsApp): cliente HTTP e utilitários compartilhados.

Imports públicos: ``from models.evolution import EvolutionCliente, ...``.
"""

from models.evolution.constants import (
    DEFAULT_BASE_URL,
    ENV_BASE_URL,
    ENV_INSTANCE,
    ENV_TOKEN,
    MEDIA_TYPE_DOCUMENT,
    MEDIA_TYPE_IMAGE,
    ROTA_SEND_MEDIA,
    ROTA_SEND_TEXT,
    TIMEOUT_SEGUNDOS_PADRAO,
)
from models.evolution.services.cliente import EvolutionCliente, obter_cliente_evolution
from models.evolution.utils.telefone import normalizar_numero_whatsapp_br

__all__ = [
    "DEFAULT_BASE_URL",
    "ENV_BASE_URL",
    "ENV_INSTANCE",
    "ENV_TOKEN",
    "EvolutionCliente",
    "MEDIA_TYPE_DOCUMENT",
    "MEDIA_TYPE_IMAGE",
    "ROTA_SEND_MEDIA",
    "ROTA_SEND_TEXT",
    "TIMEOUT_SEGUNDOS_PADRAO",
    "normalizar_numero_whatsapp_br",
    "obter_cliente_evolution",
]
