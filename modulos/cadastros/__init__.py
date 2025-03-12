# coding: utf-8
# modulos/cadastros/__init__.py
from .app import mod_cadastros


def init_app(app):
    """Inicializa o módulo cadastros na aplicação Flask principal"""
    # O blueprint já é registrado no app.py principal
    # Não precisamos registrá-lo novamente aqui

    # Inicializar o submódulo equipamentos
    from .app import init_equipamentos
    # init_equipamentos(mod_cadastros)

    # Inicializar o submódulo centros_custo
    from .app import init_centros_custo
    # init_centros_custo(mod_cadastros)

    # Inicializar o submódulo materiais
    from .app import init_materiais
    # init_materiais(mod_cadastros)

    # Inicializar o submódulo plano_contas
    from .app import init_plano_contas
    # init_plano_contas(mod_cadastros)

    # Inicializar o submódulo credenciais_erp
    from .app import init_credenciais_erp
    # init_credenciais_erp(mod_cadastros)

    return app


__all__ = ["mod_cadastros", "init_app"]
