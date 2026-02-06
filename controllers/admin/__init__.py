from flask import Blueprint
from flask_login import login_required, current_user
from flask import redirect, url_for, flash
import logging

logger = logging.getLogger(__name__)

# Importar modelos de permissões
try:
    from models.permissoes import Modulo, Permissao
    PERMISSOES_DISPONIVEL = True
except ImportError:
    PERMISSOES_DISPONIVEL = False
    logger.warning("Modelos de permissões não encontrados. Interface de permissões não estará disponível.")

# Criar o blueprint
admin_bp = Blueprint('admin', __name__)

# Middleware para verificar se o usuário é administrador
@admin_bp.before_request
@login_required
def verificar_admin():
    if not current_user.is_permissao('admin'):
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

# Importar as rotas
from controllers.admin import main, permissoes
