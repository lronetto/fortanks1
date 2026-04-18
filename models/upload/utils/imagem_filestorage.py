"""Persistência de imagem a partir de ``FileStorage`` (Werkzeug) na tabela ``Uploads``."""
from __future__ import annotations

import uuid
from typing import Optional

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..entities import Upload

ALLOWED_PHOTO_MT = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
})


def guess_image_mime_from_bytes(head: bytes) -> Optional[str]:
    """JPEG/PNG/GIF/WebP pelos primeiros bytes (clipboard costuma vir octet-stream)."""
    if not head or len(head) < 12:
        return None
    if head[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(head) >= 8 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(head) >= 6 and head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def salvar_upload_imagem_filestorage(
    file_storage: FileStorage,
    *,
    pai: str,
    pai_id: int,
    tipo: int,
    prefixo_arquivo: str,
    nome_sem_arquivo: str = "foto",
    nome_seguro_fallback: str = "imagem",
) -> Optional[int]:
    """
    Valida MIME, grava em `Upload` e devolve o id.

    `prefixo_arquivo` — prefixo único antes do uuid (ex.: ``f\"mat{5}_\"``, ``f\"transp{12}_\"``).
    `nome_sem_arquivo` — base do nome quando `filename` vem vazio (extensão deduzida do MIME).
    `nome_seguro_fallback` — valor se `secure_filename` esvaziar (ex.: ``\"imagem\"`` ou ``\"foto.jpg\"``).
    """
    if not file_storage or not isinstance(file_storage, FileStorage):
        return None
    raw = file_storage.read()
    if not raw:
        return None
    mt = (file_storage.mimetype or file_storage.content_type or "").strip().lower() or "application/octet-stream"
    if mt not in ALLOWED_PHOTO_MT:
        guessed = guess_image_mime_from_bytes(raw[:64])
        if guessed:
            mt = guessed
        else:
            return None
    orig_name = (file_storage.filename or "").strip()
    if not orig_name:
        ext = "jpg" if mt == "image/jpeg" else (mt.split("/")[-1] if "/" in mt else "png")
        orig_name = f"{nome_sem_arquivo}.{ext}"
    safe = secure_filename(orig_name) or nome_seguro_fallback
    unique_name = f"{prefixo_arquivo}{uuid.uuid4().hex[:12]}_{safe}"
    reg = Upload.registrar(
        pai=pai,
        pai_id=pai_id,
        tipo=tipo,
        filename=unique_name,
        mimetype=mt,
        blob=raw,
    )
    return reg.id if reg else None
