"""Domínio PLR (Participação nos Lucros e Resultados).

Utilitários em ``models.plr.utils`` (cálculo e importação de planilhas).
"""

from .entities import (
    EfetivoPLR,
    ModeloPLR,
    PLRColaborador,
    PlrAssiduidade,
    modelos_plr_departamentos,
)

__all__ = [
    "ModeloPLR",
    "modelos_plr_departamentos",
    "PLRColaborador",
    "EfetivoPLR",
    "PlrAssiduidade",
]
