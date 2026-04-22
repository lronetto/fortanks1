"""Helpers de texto do domínio de orçamentos."""


def normalizar_texto_item(texto: str | None) -> str:
    """Normaliza texto livre de item para buscas e comparação simples."""
    return (texto or "").strip()
