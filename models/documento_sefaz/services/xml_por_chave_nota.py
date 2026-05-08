"""
Resolve o `Upload` do XML a partir da chave de acesso em `DocumentoSefaz`.

Fluxo: `NotaFiscal.chave_acesso` → `DocumentoSefaz` (tipo nfe/cte/nfse) →
`dados_adicionais.upload_id` → `Upload`.
"""
from __future__ import annotations

from typing import Optional

from models.database import db
from models.upload import Upload
from utils.utils import parse_dados_json

from ..constants import DA_UPLOAD_ID, TIPOS_DOCUMENTO_XML_COMPLETO
from ..entities import DocumentoSefaz


def obter_upload_xml_pela_chave_nota(chave_acesso: Optional[str]) -> Optional[Upload]:
    """
    Retorna o registro `Upload` do XML armazenado pelo pipeline SEFAZ para a chave,
    ou None se não houver documento completo com `upload_id`.
    """
    if not chave_acesso or not str(chave_acesso).strip():
        return None
    chave = str(chave_acesso).strip()
    doc = (
        DocumentoSefaz.query.filter(
            DocumentoSefaz.chave_acesso == chave,
            DocumentoSefaz.tipo.in_(TIPOS_DOCUMENTO_XML_COMPLETO),
        )
        .order_by(DocumentoSefaz.id.desc())
        .first()
    )
    if not doc:
        return None
    uid = parse_dados_json(doc.dados_adicionais).get(DA_UPLOAD_ID)
    if not uid:
        return None
    try:
        uid_int = int(uid)
    except (TypeError, ValueError):
        return None
    return db.session.get(Upload, uid_int)
