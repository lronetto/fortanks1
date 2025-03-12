# modulo_importacao_nf/__init__.py
from .app import mod_importacao_nf


def init_app(app):
    """Função para inicializar o módulo com a aplicação Flask"""
    return app


__all__ = ['mod_importacao_nf', 'init_app']
