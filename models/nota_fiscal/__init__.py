"""
Domínio Nota Fiscal: modelos ORM, constantes fiscais e utilitários de XML/movimentação.

Imports públicos mantêm compatibilidade com `from models.nota_fiscal import ...`.
"""
from .constants import (
    CFOPS_COMPRA,
    CFOPS_TRANSFERENCIA,
    CFOPS_VENDA,
    CNPJS_FILIAIS,
    CNPJS_MATRIZ,
    CNPJS_MATRIZ_FILIAIS,
)
from .entities import NotaFiscal, NotaFiscalItem
from .movimentacao_estoque import determinar_movimentacoes_estoque
from .xml_utils import _parse_nfe_data_emissao_xml, get_xml_text

__all__ = [
    "CFOPS_COMPRA",
    "CFOPS_TRANSFERENCIA",
    "CFOPS_VENDA",
    "CNPJS_FILIAIS",
    "CNPJS_MATRIZ",
    "CNPJS_MATRIZ_FILIAIS",
    "NotaFiscal",
    "NotaFiscalItem",
    "_parse_nfe_data_emissao_xml",
    "determinar_movimentacoes_estoque",
    "get_xml_text",
]
