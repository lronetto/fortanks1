"""
Domínio de uploads (tabela `Uploads`): anexos em base64 com metadados.

Reexporta a API usada pelo monólito: ``from models.upload import Upload``.

Serviço de armazenamento em MinIO (envio/exclusão em lote):
    from models.upload import minio_service
"""
from .constants import TIPOS_UPLOAD
from .entities import Upload
from .services import minio_service
from .utils.armazenamento import normalizar_blob_para_armazenamento
from .utils.imagem_filestorage import (
    ALLOWED_PHOTO_MT,
    guess_image_mime_from_bytes,
    salvar_upload_imagem_filestorage,
)

__all__ = [
    "Upload",
    "TIPOS_UPLOAD",
    "minio_service",
    "normalizar_blob_para_armazenamento",
    "ALLOWED_PHOTO_MT",
    "guess_image_mime_from_bytes",
    "salvar_upload_imagem_filestorage",
]
