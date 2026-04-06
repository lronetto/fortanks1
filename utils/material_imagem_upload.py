"""Imagem de cadastro de material: Upload + chave imagem_upload_id em dados_adicionais (JSON)."""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from models.upload import Upload

PAI_MATERIAL = "Materiais"
TIPO_IMAGEM_MATERIAL = 9

ALLOWED_PHOTO_MT = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
})


def guess_image_mime_from_bytes(head: bytes) -> Optional[str]:
    """Identifica JPEG/PNG/GIF/WebP pelos primeiros bytes (clipboard costuma vir octet-stream)."""
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


def parse_dados_json(text: Optional[str]) -> Dict[str, Any]:
    if not text or not str(text).strip():
        return {}
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def dump_dados_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def get_imagem_upload_id(text: Optional[str]) -> Optional[int]:
    v = parse_dados_json(text).get("imagem_upload_id")
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def set_imagem_upload_id(text: Optional[str], upload_id: Optional[int]) -> str:
    d = parse_dados_json(text)
    if upload_id is None:
        d.pop("imagem_upload_id", None)
    else:
        d["imagem_upload_id"] = int(upload_id)
    return dump_dados_json(d)


def salvar_imagem_material(material_id: int, file_storage: FileStorage) -> Optional[int]:
    """
    Grava arquivo em Upload e retorna o id.
    """
    if not file_storage or not isinstance(file_storage, FileStorage):
        return None
    mt = (file_storage.mimetype or file_storage.content_type or "").strip().lower() or "application/octet-stream"
    raw = file_storage.read()
    if not raw:
        return None
    if mt not in ALLOWED_PHOTO_MT:
        guessed = guess_image_mime_from_bytes(raw[:64])
        if guessed:
            mt = guessed
        else:
            return None
    orig_name = (file_storage.filename or "").strip()
    if not orig_name:
        ext = "jpg" if mt == "image/jpeg" else (mt.split("/")[-1] if "/" in mt else "png")
        orig_name = f"clipboard.{ext}"
    safe = secure_filename(orig_name) or "imagem"
    unique_name = f"mat{material_id}_{uuid.uuid4().hex[:12]}_{safe}"
    Upload(
        pai=PAI_MATERIAL,
        pai_id=material_id,
        tipo=TIPO_IMAGEM_MATERIAL,
        filename=unique_name,
        mimetype=mt,
        blob=raw,
    )
    reg = Upload.query.filter_by(
        pai=PAI_MATERIAL,
        pai_id=material_id,
        tipo=TIPO_IMAGEM_MATERIAL,
        filename=unique_name,
    ).first()
    return reg.id if reg else None


def remover_upload_material_se_existir(upload_id: int, material_id: int) -> None:
    u = Upload.query.get(upload_id)
    if u and u.pai == PAI_MATERIAL and u.pai_id == material_id and u.tipo == TIPO_IMAGEM_MATERIAL:
        u.delete()
