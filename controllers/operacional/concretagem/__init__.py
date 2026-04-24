"""
Concretagens (operacional).

Blueprint único `concretagem`; prefixo `/concretagens` é aplicado em `app.register_blueprint`.
"""

from flask import Blueprint

concretagem = Blueprint('concretagem', __name__)

from .routes.core import *  # noqa: E402,F401,F403
from .routes.api import *  # noqa: E402,F401,F403
from .routes.exportacao import *  # noqa: E402,F401,F403
