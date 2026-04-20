"""
Domínio de concreto: modelos ORM, utilitários de qualidade e serviço de produção por peças.

Imports públicos permanecem em `from models.concreto import ...` (compatível com o monólito anterior).
"""

from .utils import (
    limpar_data_producao_dados_adicionais_usinagem_str,
    limpar_data_producao_em_qualidade_str,
    peca_obj_ja_produzida,
    qualidade_dict_tem_data_producao,
    qualidade_peca_remover_data_producao_de_dados_adicionais,
)
from .entities import (
    ConcretoConcretagens,
    ConcretoTracos,
    ConcretoTracosItens,
    ConcretoUsinagens,
    ConcretoUsinagensMateriais,
    ConcretoUsinagensRompimentos,
)
from .services import (
    extrair_ids_pecas_concretagem,
    montar_mapa_pista_por_peca,
    nome_e_tanque_do_item_concretagem,
    normalizar_chave_peca,
    processar_producao_por_pecas,
    registrar_entrada_estoque_produto_composto_producao_peca,
)

__all__ = [
    'ConcretoConcretagens',
    'ConcretoTracos',
    'ConcretoTracosItens',
    'ConcretoUsinagens',
    'ConcretoUsinagensMateriais',
    'ConcretoUsinagensRompimentos',
    'limpar_data_producao_dados_adicionais_usinagem_str',
    'limpar_data_producao_em_qualidade_str',
    'extrair_ids_pecas_concretagem',
    'montar_mapa_pista_por_peca',
    'nome_e_tanque_do_item_concretagem',
    'normalizar_chave_peca',
    'peca_obj_ja_produzida',
    'processar_producao_por_pecas',
    'qualidade_dict_tem_data_producao',
    'qualidade_peca_remover_data_producao_de_dados_adicionais',
    'registrar_entrada_estoque_produto_composto_producao_peca',
]
