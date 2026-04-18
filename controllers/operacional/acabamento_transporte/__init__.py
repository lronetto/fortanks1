"""
Acabamento e transporte de peças (operacional).

Separação em subpacotes `routes/` e `services/` (mesmo estilo que `controllers/nota_fiscal`).
"""

from flask import Blueprint

acabamento_transporte_bp = Blueprint("acabamento_transporte", __name__)

from .routes.core import *  # noqa: E402,F401,F403
from .routes.datatables import *  # noqa: E402,F401,F403
from .routes.api import *  # noqa: E402,F401,F403
from .routes.exportacao import *  # noqa: E402,F401,F403
