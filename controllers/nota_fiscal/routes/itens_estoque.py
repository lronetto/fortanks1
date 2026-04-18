import logging
from flask_login import login_required

from .. import nota_fiscal_bp

logger = logging.getLogger(__name__)


@nota_fiscal_bp.route("/_health/itens-estoque")
@login_required
def _health_itens_estoque():
    """
    Healthcheck simples para manter o arquivo com uma rota (evita arquivo vazio).
    As rotas de API deste domínio foram movidas para `controllers/nota_fiscal/routes/api.py`.
    """
    return "ok"


