"""Normalização de conteúdo para a coluna `Uploads.blob` (texto base64)."""
from __future__ import annotations

import base64


def normalizar_blob_para_armazenamento(blob):
    """
    Coluna `blob` armazena texto base64.
    Aceita bytes (codifica), str (usa como já persistido) ou None.
    """
    if blob is None:
        return None
    if isinstance(blob, (bytes, bytearray)):
        return base64.b64encode(bytes(blob)).decode("utf-8")
    if isinstance(blob, str):
        return blob
    raise TypeError(f"blob deve ser bytes, bytearray ou str; recebido {type(blob)!r}")
