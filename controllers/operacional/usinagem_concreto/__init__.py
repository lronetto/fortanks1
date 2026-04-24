"""
Usinagem de concreto e rompimentos (operacional).

Separação em `routes/` e `services/`; o nome do blueprint permanece `usinagem_concreto`
para compatibilidade com `url_for` nos templates.
"""

from flask import Blueprint

usinagem_concreto = Blueprint('usinagem_concreto', __name__)

from .routes.usinagens import *  # noqa: E402,F401,F403
from .routes.rompimentos import *  # noqa: E402,F401,F403
