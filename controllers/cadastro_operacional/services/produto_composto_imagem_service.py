import base64
import io
import logging
from typing import Tuple

from PIL import Image

logger = logging.getLogger(__name__)


def comprimir_imagem_base64(imagem_base64: str, max_size: Tuple[int, int] = (400, 300), quality: int = 70):
    """
    Comprime uma imagem em Base64, reduzindo seu tamanho de forma mais agressiva.

    Retorna (imagem_base64_comprimida, mime_type).
    """
    try:
        if not imagem_base64 or not imagem_base64.startswith("data:image/"):
            logger.error("Formato de imagem inválido")
            return imagem_base64, "image/jpeg"

        header, encoded = imagem_base64.split(",", 1)
        mime_type = header.split(";")[0].split(":")[1]

        dados_imagem = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(dados_imagem))

        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)

        dados_comprimidos = buffer.getvalue()
        base64_comprimido = base64.b64encode(dados_comprimidos).decode("utf-8")

        return f"data:image/jpeg;base64,{base64_comprimido}", "image/jpeg"
    except Exception as e:
        logger.error(f"Erro ao comprimir imagem: {str(e)}")
        return imagem_base64, "image/jpeg"

