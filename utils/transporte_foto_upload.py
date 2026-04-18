"""Foto opcional no registro de transporte: Upload tipo 10 + referência em TanquesTransportes.dados_adicionais."""
from __future__ import annotations

from typing import Optional

from werkzeug.datastructures import FileStorage

from models.upload import salvar_upload_imagem_filestorage

PAI_TRANSPORTE = "TanquesTransportes"
TIPO_FOTO_TRANSPORTE = 10


def salvar_foto_transporte(transportes_id: int, file_storage: FileStorage) -> Optional[int]:
    """Grava imagem em Upload (pai TanquesTransportes) e retorna o id, ou None se inválida/ausente."""
    return salvar_upload_imagem_filestorage(
        file_storage,
        pai=PAI_TRANSPORTE,
        pai_id=transportes_id,
        tipo=TIPO_FOTO_TRANSPORTE,
        prefixo_arquivo=f"transp{transportes_id}_",
        nome_sem_arquivo="foto_transporte",
        nome_seguro_fallback="foto.jpg",
    )
