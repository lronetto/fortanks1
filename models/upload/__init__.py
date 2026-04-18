"""
Domínio de uploads (tabela `Uploads`): anexos em base64 com metadados.

Reexporta a API usada pelo monólito: ``from models.upload import Upload``.
"""
from .constants import TIPOS_UPLOAD
from .entities import Upload
from .utils.armazenamento import normalizar_blob_para_armazenamento
from .utils.imagem_filestorage import (
    ALLOWED_PHOTO_MT,
    guess_image_mime_from_bytes,
    salvar_upload_imagem_filestorage,
)

__all__ = [
    "Upload",
    "TIPOS_UPLOAD",
    "normalizar_blob_para_armazenamento",
    "ALLOWED_PHOTO_MT",
    "guess_image_mime_from_bytes",
    "salvar_upload_imagem_filestorage",
]
