"""Entidades ORM do domínio PLR."""

from .modelo import ModeloPLR, modelos_plr_departamentos
from .avaliacoes import PLRColaborador
from .efetivos import EfetivoPLR
from .assiduidade import PlrAssiduidade

__all__ = [
    "ModeloPLR",
    "modelos_plr_departamentos",
    "PLRColaborador",
    "EfetivoPLR",
    "PlrAssiduidade",
]
