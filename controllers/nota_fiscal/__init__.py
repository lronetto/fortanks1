"""
Pacote de rotas de Nota Fiscal.

Objetivo:
- Manter o blueprint `nota_fiscal_bp` em um lugar único e importar rotas por domínio
  (core/tabela, itens/estoque, documentos, importações, análises, exportações).
- Facilitar manutenção e evitar um único controller gigante.
"""

from flask import Blueprint

nota_fiscal_bp = Blueprint("nota_fiscal", __name__)

# Reexport público (compatibilidade com imports antigos)
from .services.query_notas import api_get_dados_notas_fiscais  # noqa: E402,F401

# Registrar APIs (JSON/AJAX) concentradas em `controllers/api/`
from controllers.api.nota_fiscal_api import register as _register_nota_fiscal_api  # noqa: E402

_register_nota_fiscal_api(nota_fiscal_bp)

# Registrar rotas (side-effect: decoradores no blueprint)
from .routes.core import *  # noqa: E402,F401,F403
from .routes.importacoes import *  # noqa: E402,F401,F403
from .routes.documentos import *  # noqa: E402,F401,F403
from .routes.itens_estoque import *  # noqa: E402,F401,F403
from .routes.analises import *  # noqa: E402,F401,F403
from .routes.exportacoes import *  # noqa: E402,F401,F403


