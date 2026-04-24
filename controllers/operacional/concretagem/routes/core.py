"""Páginas HTML principais — concretagens."""

from flask import render_template
from flask_login import login_required

from .. import concretagem


@concretagem.route('/')
@login_required
def index():
    """Lista todas as concretagens cadastradas."""
    return render_template('operacional/concretagens/index.html')
