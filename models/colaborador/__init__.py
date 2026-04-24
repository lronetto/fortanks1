"""
Domínio colaborador: cadastro, dados bancários e histórico de mudança de função em JSON.
"""

from .constants import (
    CHAVE_MUDANCA_FUNCAO,
    CHAVE_MUDANCA_FUNCAO_LEGACY,
    TAB_COLABORADORES,
    TAB_DADOS_BANCARIOS,
)
from .entities import Colaborador, DadosBancarios

__all__ = [
    "Colaborador",
    "DadosBancarios",
    "TAB_COLABORADORES",
    "TAB_DADOS_BANCARIOS",
    "CHAVE_MUDANCA_FUNCAO",
    "CHAVE_MUDANCA_FUNCAO_LEGACY",
]
