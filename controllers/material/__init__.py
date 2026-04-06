"""
Pacote de rotas de Material.

- Rotas de página (templates/redirects) ficam em `controllers/material/routes/*`.
- Endpoints de API (JSON/AJAX) ficam em `controllers/api/material_api.py`.
"""

from flask import Blueprint

material_bp = Blueprint("material", __name__, url_prefix="/materiais")

# Registrar APIs centralizadas
from controllers.api.material_api import register as _register_material_api  # noqa: E402

_register_material_api(material_bp)

# Registrar rotas de página
from .routes.core import *  # noqa: E402,F401,F403
from .routes.datatables import *  # noqa: E402,F401,F403
from .routes.importacao import *  # noqa: E402,F401,F403
from .routes.exportacoes import *  # noqa: E402,F401,F403


