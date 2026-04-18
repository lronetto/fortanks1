"""Modelos ORM do domínio tanque."""

from .tanques import Tanques
from .grupos import TanquesGrupos, tanques_grupos
from .pecas import TanquesPecas
from .produto_composto import TanquesProdutoComposto
from .transportes import TanquesTransportes

__all__ = [
    'Tanques',
    'TanquesGrupos',
    'TanquesPecas',
    'TanquesProdutoComposto',
    'TanquesTransportes',
    'tanques_grupos',
]
