from flask import Blueprint, redirect, url_for, flash
from flask_login import login_required, current_user

cronograma_bp = Blueprint('cronograma', __name__)


def parse_date(s):
    from datetime import datetime

    if not s or not str(s).strip():
        return None
    try:
        return datetime.strptime(str(s).strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def parse_peso(s):
    if s is None or not str(s).strip():
        return 0.0
    try:
        return float(str(s).replace(',', '.').strip())
    except ValueError:
        return 0.0


def requer_cronograma():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    if not current_user.is_permissao('cronograma'):
        flash('Você não tem permissão para acessar o módulo Cronograma.', 'danger')
        return redirect(url_for('dashboard.index'))
    return None


@cronograma_bp.before_request
@login_required
def _before_cronograma():
    return requer_cronograma()


from . import routes  # noqa: E402,F401
from . import item_routes  # noqa: E402,F401
from . import matriz_routes  # noqa: E402,F401
from . import calendario_routes  # noqa: E402,F401
from . import vinculo_calendario_routes  # noqa: E402,F401
