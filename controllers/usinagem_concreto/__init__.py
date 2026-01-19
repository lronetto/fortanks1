"""
Pacote de rotas de Usinagem de Concreto.

Objetivo:
- Separar endpoints de usinagem e rompimentos em módulos distintos
- Facilitar manutenção e evolução do código
"""

from flask import Blueprint

usinagem_concreto = Blueprint('usinagem_concreto', __name__)

# Registrar rotas de usinagem
from . import usinagens  # noqa: E402,F401

# Registrar rotas de rompimentos
from . import rompimentos  # noqa: E402,F401
