"""Patrimônio, fotos (Upload) e modelo de checklist padrão em dados_adicionais (JSON)."""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from models.upload import Upload

PAI_EQUIPAMENTO = "Equipamento"
# Upload.tipo — fotos anexadas ao equipamento (ver comentário em models/upload.py)
TIPO_FOTO_EQUIPAMENTO = 8

ALLOWED_PHOTO_MT = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
})


def _extras_vazios() -> Dict[str, Any]:
    return {"patrimonio": "", "fotos": [], "checklist_modelo_id": None}


def _normaliza_checklist_modelo_id(val: Any) -> int | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s.isdigit():
        return None
    return int(s)


def parse_extras(text: str | None) -> Dict[str, Any]:
    if not text or not str(text).strip():
        return _extras_vazios()
    try:
        d = json.loads(text)
        if not isinstance(d, dict):
            return _extras_vazios()
        out: Dict[str, Any] = dict(d)
        p = out.get("patrimonio", "")
        out["patrimonio"] = "" if p is None else str(p).strip()
        fotos = out.get("fotos", [])
        if not isinstance(fotos, list):
            out["fotos"] = []
        else:
            limpa: List[int] = []
            for x in fotos:
                try:
                    limpa.append(int(x))
                except (TypeError, ValueError):
                    continue
            out["fotos"] = limpa
        out["checklist_modelo_id"] = _normaliza_checklist_modelo_id(
            out.get("checklist_modelo_id")
        )
        return out
    except (json.JSONDecodeError, TypeError):
        return _extras_vazios()


def dump_extras(data: Dict[str, Any]) -> str:
    """Serializa dict (ex.: resultado de parse_extras após ajustes)."""
    pat = (data.get("patrimonio") or "") if isinstance(data.get("patrimonio"), str) else str(
        data.get("patrimonio") or ""
    )
    fotos = data.get("fotos", [])
    if not isinstance(fotos, list):
        fotos = []
    base = dict(data)
    base["patrimonio"] = pat.strip()
    base["fotos"] = [int(x) for x in fotos if str(x).isdigit()]
    cm = _normaliza_checklist_modelo_id(base.get("checklist_modelo_id"))
    if cm is not None:
        base["checklist_modelo_id"] = cm
    else:
        base.pop("checklist_modelo_id", None)
    return json.dumps(base, ensure_ascii=False)


def set_patrimonio_e_fotos(old_text: str | None, patrimonio: str, foto_ids: List[int]) -> str:
    d = parse_extras(old_text)
    d["patrimonio"] = (patrimonio or "").strip()
    d["fotos"] = list(foto_ids)
    return dump_extras(d)


def process_foto_uploads(
    equipamento_id: int,
    files_storage,
    field_name: str = "fotos",
) -> List[int]:
    """Grava arquivos em Upload e retorna os novos ids."""
    new_ids: List[int] = []
    if not files_storage:
        return new_ids
    incoming = files_storage.getlist(field_name) if hasattr(files_storage, "getlist") else []
    for f in incoming:
        if not f or not isinstance(f, FileStorage):
            continue
        if not f.filename:
            continue
        mt = f.mimetype or f.content_type or "application/octet-stream"
        if mt not in ALLOWED_PHOTO_MT:
            continue
        raw = f.read()
        if not raw:
            continue
        safe = secure_filename(f.filename) or "foto"
        unique_name = f"eq{equipamento_id}_{uuid.uuid4().hex[:12]}_{safe}"
        Upload(
            pai=PAI_EQUIPAMENTO,
            pai_id=equipamento_id,
            tipo=TIPO_FOTO_EQUIPAMENTO,
            filename=unique_name,
            mimetype=mt,
            blob=raw,
        )
        reg = Upload.query.filter_by(
            pai=PAI_EQUIPAMENTO,
            pai_id=equipamento_id,
            tipo=TIPO_FOTO_EQUIPAMENTO,
            filename=unique_name,
        ).first()
        if reg:
            new_ids.append(reg.id)
    return new_ids
