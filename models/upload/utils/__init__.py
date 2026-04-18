"""
Utilitários do domínio upload.

Não importar ``imagem_filestorage`` aqui: evita ciclo com ``entities.upload``
(``entities`` carrega ``utils.armazenamento`` ao inicializar). Use
``from models.upload.utils.imagem_filestorage import ...`` ou o reexport em
``models.upload``.
"""
from .armazenamento import normalizar_blob_para_armazenamento

__all__ = ["normalizar_blob_para_armazenamento"]
