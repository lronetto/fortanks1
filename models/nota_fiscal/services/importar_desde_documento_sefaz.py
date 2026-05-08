"""
Promove `DocumentoSefaz` (NFe/CTe completos) para `NotaFiscal`.

Considera pendentes os registros cujo `dados_adicionais` não tem a chave
`inserido` ou tem `inserido: null`. Após importação bem-sucedida, grava
`inserido: 1` no JSON do documento SEFAZ.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Optional

from sqlalchemy import case, func, or_, true

from models.database import db
from models.documento_sefaz import DocumentoSefaz
from models.documento_sefaz.constants import DA_INSERIDO, DA_UPLOAD_ID
from models.upload import Upload
from models.nota_fiscal.entities import NotaFiscal
from utils.utils import parse_dados_json, set_dados_json_item

logger = logging.getLogger(__name__)

_TIPOS_NOTA_FISCAL = ("nfe", "cte")
_JSON_PATH_INSERIDO = f"$.{DA_INSERIDO}"


def _sql_documento_sem_inserido():
    """
    Predicado: `dados_adicionais.inserido` inexistente ou JSON null — em SQL.

    Evita JSON_EXTRACT em texto vazio (MySQL invalida JSON) usando CASE.
    """
    col = DocumentoSefaz.dados_adicionais
    texto_invalido = or_(col.is_(None), col == "")
    nome = db.engine.dialect.name

    if nome in ("mysql", "mariadb") or nome.startswith("mysql"):
        return case(
            (texto_invalido, true()),
            else_=func.json_extract(col, _JSON_PATH_INSERIDO).is_(None),
        )

    if nome == "postgresql":
        from sqlalchemy import cast as sa_cast
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy.sql import literal_column

        j = sa_cast(col, JSONB)
        json_nulo = literal_column("'null'::jsonb")
        return case(
            (texto_invalido, true()),
            else_=or_(~j.has_key(DA_INSERIDO), j[DA_INSERIDO] == json_nulo),
        )

    return case(
        (texto_invalido, true()),
        else_=func.json_extract(col, _JSON_PATH_INSERIDO).is_(None),
    )


def _logs_tem_erro(logs: Any) -> bool:
    if not isinstance(logs, dict):
        return True
    err = logs.get("erro")
    if err is None:
        return False
    if isinstance(err, list):
        return len(err) > 0
    if isinstance(err, str):
        return bool(err.strip())
    return True


def executar_importacao_desde_documento_sefaz(
    *,
    limite: Optional[int] = None,
) -> dict:
    """
    Importa XMLs de `DocumentoSefaz` (tipos `nfe` e `cte`) ainda não marcados
    com `dados_adicionais.inserido`, persiste via `NotaFiscal` e marca
    `inserido = 1` quando houver registro em nota fiscal e nenhum erro de
    processamento nos `logs`.

    Args:
        limite: opcional — máximo de documentos **pendentes** tentados nesta
            execução (sem limite processa todos os pendentes).

    Returns:
        dict com chaves: processados, marcados_inserido, erros (lista).
        (Registros com `inserido` já preenchido ficam de fora via filtro SQL.)
    """
    q = (
        DocumentoSefaz.query.filter(DocumentoSefaz.tipo.in_(_TIPOS_NOTA_FISCAL))
        .filter(_sql_documento_sem_inserido())
        .order_by(DocumentoSefaz.id.asc())
    )

    resumo = {
        "processados": 0,
        "marcados_inserido": 0,
        "erros": [],
    }

    tentativas = 0
    for doc in q.yield_per(200):
        if limite is not None and tentativas >= limite:
            break
        tentativas += 1

        da = parse_dados_json(doc.dados_adicionais)
        upload_id = da.get(DA_UPLOAD_ID)
        if not upload_id:
            resumo["erros"].append(f"doc id={doc.id}: sem upload_id em dados_adicionais")
            continue

        upload = db.session.get(Upload, upload_id)
        if not upload:
            resumo["erros"].append(f"doc id={doc.id}: Upload id={upload_id} não encontrado")
            continue

        blob = upload.get_blob()
        if not blob:
            resumo["erros"].append(f"doc id={doc.id}: blob vazio (upload {upload_id})")
            continue

        resumo["processados"] += 1
        try:
            xml_b64 = base64.b64encode(blob).decode("ascii")
            nf = NotaFiscal(xml_data=xml_b64)
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            logger.exception("importar desde DocumentoSefaz id=%s: %s", doc.id, exc)
            resumo["erros"].append(f"doc id={doc.id}: {exc}")
            continue

        if getattr(nf, "id", None) and not _logs_tem_erro(getattr(nf, "logs", {})):
            doc.dados_adicionais = set_dados_json_item(
                doc.dados_adicionais, DA_INSERIDO, 1
            )
            db.session.add(doc)
            db.session.commit()
            resumo["marcados_inserido"] += 1
        else:
            db.session.rollback()
            cid = getattr(nf, "chave_acesso", None)
            resumo["erros"].append(
                f"doc id={doc.id} chave={cid}: falha ao persistir ou logs com erro: "
                f"{getattr(nf, 'logs', {})}"
            )

    return resumo
