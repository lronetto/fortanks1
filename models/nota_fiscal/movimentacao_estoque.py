"""Regras de movimentação de estoque a partir do papel da NF (CNPJ emitente/destinatário)."""
import logging

from .constants import CNPJS_FILIAIS, CNPJS_MATRIZ, CNPJS_MATRIZ_FILIAIS

logger = logging.getLogger(__name__)


def determinar_movimentacoes_estoque(nota_fiscal):
    """
    Determina as movimentações de estoque necessárias baseado nos CNPJs da nota fiscal.

    Args:
        nota_fiscal: Instância de NotaFiscal

    Returns:
        list: Lista de tuplas (local, tipo_movimento) que devem ser processadas
    """
    movimentacoes = []
    logger.debug("cnpj_emitente: %s", nota_fiscal.cnpj_emitente)
    logger.debug("cnpj_destinatario: %s", nota_fiscal.cnpj_destinatario)
    # Apenas processar notas fiscais (tipo 1)
    if nota_fiscal.tipo > 1:
        return movimentacoes

    cnpj_emitente = nota_fiscal.cnpj_emitente
    cnpj_destinatario = nota_fiscal.cnpj_destinatario

    # Caso 1: Compra externa para Matriz
    if cnpj_emitente not in CNPJS_MATRIZ_FILIAIS and cnpj_destinatario in CNPJS_MATRIZ:
        movimentacoes.append(("Estoque Matriz", "entrada"))

    # Caso 2: Compra externa para Filial
    elif cnpj_emitente not in CNPJS_MATRIZ_FILIAIS and cnpj_destinatario in CNPJS_FILIAIS:
        movimentacoes.append((f"Estoque Filial {cnpj_destinatario}", "entrada"))

    # Caso 3: Transferência Matriz -> Filial
    elif cnpj_emitente in CNPJS_MATRIZ and cnpj_destinatario in CNPJS_FILIAIS:
        movimentacoes.append(("Estoque Matriz", "saida"))
        movimentacoes.append((f"Estoque Filial {cnpj_destinatario}", "entrada"))

    # Caso 4: Transferência Filial -> Matriz
    elif cnpj_emitente in CNPJS_FILIAIS and cnpj_destinatario in CNPJS_MATRIZ:
        movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "saida"))
        movimentacoes.append(("Estoque Matriz", "entrada"))
    # Caso 5: Transferência interna para externa
    elif cnpj_emitente in CNPJS_MATRIZ_FILIAIS and cnpj_destinatario not in CNPJS_MATRIZ_FILIAIS:
        if cnpj_emitente in CNPJS_MATRIZ:
            if nota_fiscal.tipo == 1:
                movimentacoes.append(("Estoque Matriz", "saida"))
            else:
                movimentacoes.append(("Estoque Matriz", "entrada"))
        if cnpj_emitente in CNPJS_FILIAIS:
            if nota_fiscal.tipo == 1:
                movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "saida"))
            else:
                movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "entrada"))
    # Caso 6: Transferência matriz para matriz
    elif cnpj_emitente in CNPJS_MATRIZ and cnpj_destinatario in CNPJS_MATRIZ:
        if nota_fiscal.tipo == 1:
            movimentacoes.append(("Estoque Matriz", "saida"))
        else:
            movimentacoes.append(("Estoque Matriz", "entrada"))
    # Caso 7: Transferência filial para filial
    elif cnpj_emitente in CNPJS_FILIAIS and cnpj_destinatario in CNPJS_FILIAIS:
        if nota_fiscal.tipo == 1:
            movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "saida"))
        else:
            movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "entrada"))
    return movimentacoes
