"""Limpa `NotaFiscal.xml_data` após importação, sem duplicar XML na SEFAZ."""

import logging

from models.database import db
from models.upload import Upload
from models.upload.constants import TIPO_UPLOAD_XML_NOTA_FISCAL
from models.documento_sefaz.services.xml_por_chave_nota import (
    obter_upload_xml_pela_chave_nota,
)

from ..constants import DA_XML_UPLOAD_ID
from utils.utils import parse_dados_json, set_dados_json_item

logger = logging.getLogger(__name__)


def migrar_xml_coluna_para_upload(nota) -> None:
    """
    Zera `xml_data` após gravar a nota. Se já existir `DocumentoSefaz` + `Upload`
    para a chave de acesso, não cria novo `Upload` na nota. Caso contrário,
    mantém o fallback (`Upload` vinculado à nota + `xml_upload_id`).
    """
    if not getattr(nota, "id", None):
        return
    raw = getattr(nota, "xml_data", None)
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return

    if obter_upload_xml_pela_chave_nota(getattr(nota, "chave_acesso", None)):
        nota.xml_data = None
        db.session.add(nota)
        db.session.commit()
        return

    da = parse_dados_json(nota.dados_adicionais)
    if da.get(DA_XML_UPLOAD_ID):
        nota.xml_data = None
        db.session.add(nota)
        db.session.commit()
        return

    chave = (nota.chave_acesso or str(nota.id))[:80]
    try:
        up = Upload.registrar(
            pai="NotaFiscal",
            pai_id=nota.id,
            tipo=TIPO_UPLOAD_XML_NOTA_FISCAL,
            filename=f"{chave}.xml",
            mimetype="application/xml",
            blob=raw,
        )
        nota.dados_adicionais = set_dados_json_item(
            nota.dados_adicionais, DA_XML_UPLOAD_ID, up.id
        )
        nota.xml_data = None
        db.session.add(nota)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Falha ao migrar XML para Upload nota id=%s: %s", nota.id, exc
        )
        db.session.rollback()
