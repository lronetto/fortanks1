"""
Pacote de rotas de Material.

- Rotas de página em `controllers/material/routes/core.py`, etc.
- Endpoints JSON/AJAX em `controllers/material/routes/api.py`.
"""

from flask import Blueprint

material_bp = Blueprint("material", __name__)
grupo_material_bp = Blueprint("grupo_material", __name__)

from .routes import api  # noqa: E402,F401 — registra rotas JSON no blueprint

from .routes.core import *  # noqa: E402,F401,F403
from .routes.datatables import *  # noqa: E402,F401,F403
from .routes.importacao import *  # noqa: E402,F401,F403
from .routes.exportacoes import *  # noqa: E402,F401,F403
from .routes.grupo import *  # noqa: E402,F401,F403

