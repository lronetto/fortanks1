"""Entidades ORM do domínio de materiais."""

from .associacao import materiais_grupos
from .grupos import MateriaisGrupos
from .materiais import Materiais

__all__ = [
    "materiais_grupos",
    "Materiais",
    "MateriaisGrupos",
]
