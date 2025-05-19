"""
Comandos CLI para estoque
"""
import click
from flask.cli import with_appcontext
from scripts.migracao_epi_para_estoque import migrar_epi_para_estoque

def register_commands(app):
    """
    Registrar comandos CLI para estoque
    """
    @app.cli.command('migrar-epi-estoque')
    @with_appcontext
    def migrar_epi_estoque_command():
        """Migra os EPIs existentes para o sistema de estoque principal."""
        migrar_epi_para_estoque()
        click.echo('Migração de EPI para estoque concluída com sucesso!') 