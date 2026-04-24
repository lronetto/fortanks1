"""
Pacote PLR: avaliações do colaborador, modelos de PLR, efetivo e relatórios.

O blueprint `plr_bp` é definido aqui; as rotas são distribuídas em:
- efetivo: importação/listagem/edição de efetivo PLR
- avaliacao: avaliações PLR (listagem, nova/editar/excluir, importar, por-mês)
- modelos: modelos de PLR e cargos-salários
- relatorio_avaliacao: relatório de avaliação (filtro modelo/período)
- planilha_plr (routes planilha_plr_* + services): relatório planilha (cálculo, DataTables, Excel, assiduidade)

A estrutura segue o padrão `routes/` + `services/`, mantendo um único blueprint.
"""
from flask import Blueprint, redirect, url_for
from flask_login import login_required

plr_bp = Blueprint('plr', __name__, url_prefix='/plr')


@plr_bp.before_request
@login_required
def _login_required():
    pass


# Registrar rotas dos submódulos (decoradores vinculam ao plr_bp)
from .routes.efetivo import *  # noqa: E402,F401,F403
from .routes.avaliacao import *  # noqa: E402,F401,F403
from .routes.modelos import *  # noqa: E402,F401,F403
from .routes.relatorio_avaliacao import *  # noqa: E402,F401,F403
from .routes.planilha_plr_core import *  # noqa: E402,F401,F403
from .routes.planilha_plr_datatables import *  # noqa: E402,F401,F403
from .routes.planilha_plr_exportacao import *  # noqa: E402,F401,F403
from .routes.planilha_plr_assiduidade import *  # noqa: E402,F401,F403
from .routes.assiduidade import *  # noqa: E402,F401,F403


@plr_bp.route('/')
def index():
    """Redireciona para avaliações."""
    return redirect(url_for('plr.avaliacoes_index'))
