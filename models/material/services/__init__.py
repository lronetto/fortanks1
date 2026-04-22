"""Serviços do domínio de materiais."""

from .cadastro_edicao import aplicar_edicao_formulario, construir_material_novo
from .exclusao import (
    coletar_bloqueios_exclusao,
    excluir_material_validando_vinculos,
    mensagem_vinculos_impedem_exclusao,
)
__all__ = [
    "aplicar_edicao_formulario",
    "construir_material_novo",
    "coletar_bloqueios_exclusao",
    "excluir_material_validando_vinculos",
    "mensagem_vinculos_impedem_exclusao",
]
