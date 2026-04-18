"""
Módulo de relatório de acabamento de peças.

Separa responsabilidades entre:
- routes: definição de endpoints Flask
- services: regras de negócio e transformação de dados
"""

from flask import Blueprint

acabamento_pecas_bp = Blueprint(
    "relatorios_acabamento_pecas",
    __name__,
    url_prefix="/relatorios/acabamento-pecas",
)

from .routes import *  # noqa: E402,F401,F403

