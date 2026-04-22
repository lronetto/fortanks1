"""
Domínio de materiais: cadastro, grupos de inventário e vínculos.

Imports públicos mantêm compatibilidade com `from models.material import ...`.
"""

from models.database import db

from .constants import (
    TABELA_GRUPOS,
    TABELA_GRUPOS_ITENS,
    TABELA_MATERIAIS,
)
from .entities import Materiais, MateriaisGrupos, materiais_grupos
from .services.cadastro_edicao import aplicar_edicao_formulario, construir_material_novo
from .services.exclusao import (
    coletar_bloqueios_exclusao,
    excluir_material_validando_vinculos,
    mensagem_vinculos_impedem_exclusao,
)

Material = Materiais

__all__ = [
    "db",
    "TABELA_GRUPOS",
    "TABELA_GRUPOS_ITENS",
    "TABELA_MATERIAIS",
    "Material",
    "Materiais",
    "MateriaisGrupos",
    "materiais_grupos",
    "construir_material_novo",
    "aplicar_edicao_formulario",
    "coletar_bloqueios_exclusao",
    "excluir_material_validando_vinculos",
    "mensagem_vinculos_impedem_exclusao",
]
