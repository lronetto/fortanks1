"""
Orquestração DB-aware do download de XMLs fiscais.

A camada de domínio (clientes HTTP, dataclasses, BuscadorXMLs) vive em
`models.sefaz_distribuicao`. Este pacote acrescenta:

    orquestrador      - integra o BuscadorXMLs com models.nota_fiscal.NotaFiscal
    cli               - entrypoint argparse com app.app_context()
    checkpoint        - persistência simples (arquivo) do último NSU
    testar_import     - smoke-test isolado do pipeline NotaFiscal

Para um modelo sem acesso ao banco, use diretamente
`from models.sefaz_distribuicao import BuscadorXMLs`.
"""

from .orquestrador import Resumo, baixar_e_importar

__all__ = ["Resumo", "baixar_e_importar"]
