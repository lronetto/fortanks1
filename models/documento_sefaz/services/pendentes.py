"""
Persistência em disco de XmlBaixado aguardando ingestão no DB/MinIO.

Padrão write-ahead-log: o XML baixado da SEFAZ é gravado em
`.tmp/sefaz/pendentes/<tipo>_<nsu>.xml` antes de tentar persistir.
Em caso de falha (DB ou MinIO), o arquivo permanece e a próxima
execução do `processar_sefaz` o re-processa antes de chamar a SEFAZ.

Cada XML tem um sidecar `.meta.json` com os metadados que não estão
no XML em si (`schema`, `tipo` original, `cnpj_*`, `data_emissao`).

Estrutura:
    .tmp/sefaz/pendentes/
        nfe_000000000027770.xml
        nfe_000000000027770.meta.json
        cte_000000000005500.xml
        cte_000000000005500.meta.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from models.sefaz_distribuicao import XmlBaixado

logger = logging.getLogger(__name__)

PASTA_DEFAULT = Path(".tmp") / "sefaz" / "pendentes"


def _base_filename(xml_baixado: XmlBaixado) -> str:
    """Nome base estável: `<tipo>_<nsu>` (sem extensão)."""
    nsu = xml_baixado.nsu or "sem-nsu"
    tipo = xml_baixado.tipo or "?"
    return f"{tipo}_{nsu}"


def salvar(xml_baixado: XmlBaixado, *, pasta: Path = PASTA_DEFAULT) -> Path:
    """
    Grava o XmlBaixado em disco. Idempotente: se já existir, sobrescreve.
    Retorna o caminho do `.xml`.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    base = _base_filename(xml_baixado)
    xml_path = pasta / f"{base}.xml"
    meta_path = pasta / f"{base}.meta.json"

    xml_path.write_text(xml_baixado.xml, encoding="utf-8")
    meta = {
        "tipo": xml_baixado.tipo,
        "nsu": xml_baixado.nsu,
        "schema": xml_baixado.schema,
        "chave": xml_baixado.chave,
        "data_emissao": (
            xml_baixado.data_emissao.isoformat() if xml_baixado.data_emissao else None
        ),
        "cnpj_emitente": xml_baixado.cnpj_emitente,
        "cnpj_destinatario": xml_baixado.cnpj_destinatario,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return xml_path


def remover(xml_baixado: XmlBaixado, *, pasta: Path = PASTA_DEFAULT) -> bool:
    """Remove os arquivos `.xml` e `.meta.json`. Devolve True se algo foi apagado."""
    base = _base_filename(xml_baixado)
    apagou = False
    for sufixo in (".xml", ".meta.json"):
        p = pasta / f"{base}{sufixo}"
        if p.exists():
            try:
                p.unlink()
                apagou = True
            except OSError as exc:
                logger.warning("Falha removendo pendente %s: %s", p, exc)
    return apagou


def listar(pasta: Path = PASTA_DEFAULT) -> Iterator[XmlBaixado]:
    """
    Itera os XmlBaixado pendentes na pasta. Ignora silenciosamente
    arquivos malformados (sem .xml correspondente, JSON inválido, etc.)
    com warning no log.
    """
    if not pasta.is_dir():
        return
    for meta_path in sorted(pasta.glob("*.meta.json")):
        base = meta_path.name[: -len(".meta.json")]
        xml_path = pasta / f"{base}.xml"
        if not xml_path.is_file():
            logger.warning("Pendente sem .xml correspondente: %s", meta_path)
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            xml_str = xml_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha lendo pendente %s: %s", meta_path, exc)
            continue
        yield XmlBaixado(
            tipo=meta.get("tipo") or "nfe",
            nsu=meta.get("nsu") or "",
            xml=xml_str,
            schema=meta.get("schema") or "",
            chave=meta.get("chave"),
            data_emissao=_parse_iso(meta.get("data_emissao")),
            cnpj_emitente=meta.get("cnpj_emitente"),
            cnpj_destinatario=meta.get("cnpj_destinatario"),
        )


def contar(pasta: Path = PASTA_DEFAULT) -> int:
    """Retorna a quantidade de pendentes (conta arquivos .meta.json)."""
    if not pasta.is_dir():
        return 0
    return sum(1 for _ in pasta.glob("*.meta.json"))


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None
