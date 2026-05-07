"""
Persistência simples do último NSU consumido por (CNPJ, tipo).

A SEFAZ exige que chamadas subsequentes ao Distribuição DF-e usem o
`ultNSU` retornado pela chamada anterior — caso contrário aplica
bloqueio temporário (cStat=656, "Consumo Indevido", 1 hora).

Este módulo grava e lê esse valor em arquivos texto simples no diretório
do usuário (default: ``~/.fortanks/sefaz_nsu/``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

Tipo = Literal["nfe", "cte"]
DEFAULT_DIR = Path.home() / ".fortanks" / "sefaz_nsu"


def _arquivo(diretorio: Path, cnpj: str, tipo: Tipo) -> Path:
    return diretorio / f"{cnpj}_{tipo}.nsu"


def ler(cnpj: str, tipo: Tipo, diretorio: Optional[Path] = None) -> str:
    """Retorna o NSU persistido (ou '0' se não houver)."""
    diretorio = diretorio or DEFAULT_DIR
    path = _arquivo(diretorio, cnpj, tipo)
    if not path.exists():
        return "0"
    valor = path.read_text(encoding="utf-8").strip()
    return valor or "0"


def gravar(cnpj: str, tipo: Tipo, ult_nsu: str, diretorio: Optional[Path] = None) -> None:
    """Grava o NSU. Cria o diretório se não existir."""
    diretorio = diretorio or DEFAULT_DIR
    diretorio.mkdir(parents=True, exist_ok=True)
    _arquivo(diretorio, cnpj, tipo).write_text(str(ult_nsu), encoding="utf-8")


def resetar(cnpj: str, tipo: Tipo, diretorio: Optional[Path] = None) -> None:
    """Apaga o checkpoint para forçar uma reconsulta a partir de NSU=0."""
    diretorio = diretorio or DEFAULT_DIR
    path = _arquivo(diretorio, cnpj, tipo)
    if path.exists():
        path.unlink()
