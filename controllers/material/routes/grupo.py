import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models.database import db
from models.material import Materiais
from models.plano_conta import PlanoConta
from models.unidade import Unidades

from .. import grupo_material_bp

logger = logging.getLogger(__name__)


@grupo_material_bp.before_request
def before_request():
    if not current_user.is_permissao('material'):
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('dashboard.index'))
@grupo_material_bp.route("/")
@login_required
def index():
    return render_template("materiais/grupos/index.html")