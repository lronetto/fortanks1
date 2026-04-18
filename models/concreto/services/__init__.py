"""Serviços de domínio concreto (produção por peças, etc.)."""

# producao_pecas antes de acabamento_pista: import de subpacote carrega este __init__
# e acabamento_pista não pode importar ConcretoConcretagens no topo do módulo.
from .producao_pecas import (
    processar_producao_por_pecas,
    registrar_entrada_estoque_produto_composto_producao_peca,
)
from .acabamento_pista import (
    extrair_ids_pecas_concretagem,
    montar_mapa_pista_por_peca,
    nome_e_tanque_do_item_concretagem,
    normalizar_chave_peca,
)

__all__ = [
    "extrair_ids_pecas_concretagem",
    "montar_mapa_pista_por_peca",
    "nome_e_tanque_do_item_concretagem",
    "normalizar_chave_peca",
    "processar_producao_por_pecas",
    "registrar_entrada_estoque_produto_composto_producao_peca",
]
