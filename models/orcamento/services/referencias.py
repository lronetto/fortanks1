"""Serviços de referência texto -> material para orçamentos."""

from models.orcamento.entities.referencias import ItemOrcamentoReferenciaMaterial
from models.orcamento.utils import normalizar_texto_item


def buscar_referencias_por_texto_item(texto_item: str | None):
    """Busca referências de materiais associadas ao texto do item."""
    texto_norm = normalizar_texto_item(texto_item)
    if not texto_norm:
        return []

    return ItemOrcamentoReferenciaMaterial.query.filter_by(texto_item=texto_norm).all()
