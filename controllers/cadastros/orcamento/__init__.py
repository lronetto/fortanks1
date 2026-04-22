"""Módulo de Orçamentos (cadastros)."""

from flask import Blueprint

orcamento_bp = Blueprint("orcamento", __name__)

from .routes.core import *  # noqa: E402,F401,F403
from .routes.datatables import *  # noqa: E402,F401,F403
