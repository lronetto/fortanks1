"""
Pacote PLR: avaliações do colaborador, modelos de PLR, efetivo e relatórios.

O blueprint `plr_bp` é definido aqui; as rotas são distribuídas em:
- efetivo: importação/listagem/edição de efetivo PLR
- avaliacao: avaliações PLR (listagem, nova/editar/excluir, importar, por-mês)
- modelos: modelos de PLR e cargos-salários
- relatorio_avaliacao: relatório de avaliação (filtro modelo/período)
- relatorio_planilha: relatório planilha (cálculo, dados JSON, export Excel, página)
"""
from flask import Blueprint, redirect, url_for
from flask_login import login_required

plr_bp = Blueprint('plr', __name__, url_prefix='/plr')


@plr_bp.before_request
@login_required
def _login_required():
    pass


# Registrar rotas dos submódulos (decoradores vinculam ao plr_bp)
from . import efetivo  # noqa: E402
from . import avaliacao  # noqa: E402
from . import modelos  # noqa: E402
from . import relatorio_avaliacao  # noqa: E402, F401
from . import relatorio_planilha  # noqa: E402, F401
from . import assiduidade  # noqa: E402, F401


@plr_bp.route('/')
def index():
    """Redireciona para avaliações."""
    return redirect(url_for('plr.avaliacoes_index'))
