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
