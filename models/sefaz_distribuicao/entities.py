"""
Entidades de domínio (dataclasses puras, sem ORM).

XmlBaixado  — um documento devolvido pela SEFAZ/ADN com seu NSU e metadata.
LoteDownload — agregação por tipo (NFe/CTe/NFSe) + cursores finais.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, List, Literal, Optional

TipoDocumento = Literal["nfe", "cte", "nfse"]


@dataclass
class XmlBaixado:
    """Um XML com sua metadata de distribuição."""

    tipo: TipoDocumento
    nsu: str
    xml: str
    schema: str = ""
    chave: Optional[str] = None
    data_emissao: Optional[datetime] = None
    cnpj_emitente: Optional[str] = None
    cnpj_destinatario: Optional[str] = None


@dataclass
class LoteDownload:
    """Resultado da consulta: arrays por tipo + cursores finais por tipo."""

    nfe: List[XmlBaixado] = field(default_factory=list)
    cte: List[XmlBaixado] = field(default_factory=list)
    nfse: List[XmlBaixado] = field(default_factory=list)

    # Maior NSU efetivamente percorrido (= o ultNSU da última página da
    # SEFAZ, antes do filtro de data). Quem persiste deve usar este valor
    # como ponto de partida da próxima execução.
    ultimo_nsu_nfe: str = "0"
    ultimo_nsu_cte: str = "0"

    # NSU mais novo conhecido pela SEFAZ no momento da consulta. Quando
    # `ultimo_nsu_* == max_nsu_*`, não há mais documentos pendentes.
    max_nsu_nfe: str = "0"
    max_nsu_cte: str = "0"

    def __iter__(self) -> Iterator[XmlBaixado]:
        yield from self.nfe
        yield from self.cte
        yield from self.nfse

    @property
    def total(self) -> int:
        return len(self.nfe) + len(self.cte) + len(self.nfse)
