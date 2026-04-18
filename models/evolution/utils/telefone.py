"""Normalização de número para envio WhatsApp (formato internacional sem '+')."""
from __future__ import annotations

import re
from typing import Optional


def normalizar_numero_whatsapp_br(numero: str) -> Optional[str]:
    """
    Mantém apenas dígitos; se vier 11 dígitos (DDD+celular BR), prefixa 55.

    Retorna ``None`` se estiver vazio ou muito curto para ser um destino válido.
    """
    d = re.sub(r"\D", "", (numero or "").strip())
    if not d:
        return None
    if len(d) == 11 and not d.startswith("55"):
        d = "55" + d
    if len(d) < 12:
        return None
    return d
