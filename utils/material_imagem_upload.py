"""Imagem de cadastro de material: Upload + chave imagem_upload_id em dados_adicionais (JSON)."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from werkzeug.datastructures import FileStorage

from models.upload import Upload, guess_image_mime_from_bytes, salvar_upload_imagem_filestorage

PAI_MATERIAL = "Materiais"
TIPO_IMAGEM_MATERIAL = 9


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
    """Grava arquivo em Upload e retorna o id."""
    return salvar_upload_imagem_filestorage(
        file_storage,
        pai=PAI_MATERIAL,
        pai_id=material_id,
        tipo=TIPO_IMAGEM_MATERIAL,
        prefixo_arquivo=f"mat{material_id}_",
        nome_sem_arquivo="clipboard",
        nome_seguro_fallback="imagem",
    )


def remover_upload_material_se_existir(upload_id: int, material_id: int) -> None:
    u = Upload.query.get(upload_id)
    if u and u.pai == PAI_MATERIAL and u.pai_id == material_id and u.tipo == TIPO_IMAGEM_MATERIAL:
        u.delete()
