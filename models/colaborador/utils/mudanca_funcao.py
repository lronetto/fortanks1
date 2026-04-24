"""Resolução de função (cargo) vigente a partir de dados_adicionais.mudanca_funcao."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Optional

from ..constants import CHAVE_MUDANCA_FUNCAO, CHAVE_MUDANCA_FUNCAO_LEGACY


def normalizar_id_opcional(valor: Any) -> Optional[int]:
    if valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _parse_data_iso(data_s: str) -> Optional[date]:
    s = (data_s or "").strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0].strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _historico_bruto(dados: dict) -> list[dict]:
    """
    Lista unida de entradas de ``mudanca_funcao`` e do legado ``dados_a``.
    ``mudanca_funcao`` vazio (``[]``) não bloqueia o uso de ``dados_a``.
    """
    out: list[dict] = []
    for key in (CHAVE_MUDANCA_FUNCAO, CHAVE_MUDANCA_FUNCAO_LEGACY):
        raw = dados.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                out.append(item)
    return out


def historico_mudanca_funcao_normalizado(
    dados: dict,
    resolver_nome_funcao: Callable[[str], Optional[int]] | None = None,
) -> list[dict]:
    """
    Lista ``{'data': 'YYYY-MM-DD', 'funcao_id': int}`` a partir de ``mudanca_funcao`` ou legado ``dados_a``.

    ``resolver_nome_funcao`` (opcional): dado o nome textual da função, retorna o id do cargo ou None.
    """
    out: list[dict] = []
    for item in _historico_bruto(dados):
        data_s = (item.get("data") or "").strip() if isinstance(item.get("data"), str) else str(item.get("data") or "").strip()
        fid = normalizar_id_opcional(
            item.get("funcao_id") if item.get("funcao_id") is not None else item.get("cargo_id")
        )
        if not data_s:
            continue
        if fid is None and item.get("funcao") and resolver_nome_funcao is not None:
            nome = (item.get("funcao") or "").strip()
            if nome:
                fid = resolver_nome_funcao(nome)
        if fid is None:
            continue
        out.append({"data": data_s, "funcao_id": fid})
    return out


def funcao_id_vigente_em(
    dados_adicionais: dict,
    referencia: date,
    cargo_id_padrao: Optional[int] = None,
) -> Optional[int]:
    """
    Retorna o id do cargo (função) vigente em ``referencia`` com base na lista
    ``mudanca_funcao`` (ou legado ``dados_a``): entradas ``{data, funcao_id|cargo_id}``.

    Considera válida a última mudança cuja data seja <= ``referencia`` (empate na
    mesma data: prevalece a ordem original no JSON, última ocorrência vence).

    Sem histórico de mudança, lista vazia ou nenhuma entrada com data <= ``referencia``:
    retorna ``cargo_id_padrao`` (``Colaborador.cargo_id``): função vigente *antes* da
    primeira data listada em ``mudanca_funcao`` / ``dados_a``.

    Cada linha do JSON é ``{data, funcao_id|cargo_id}`` (e opcionalmente ``funcao`` para
    resolução de nome): a partir dessa data (inclusive) vale essa função; a última linha
    com ``data <= referencia`` prevalece (empate na mesma data: última na lista após
    ordenação estável).
    """
    itens: list[tuple[date, int, int]] = []
    for idx, item in enumerate(_historico_bruto(dados_adicionais)):
        data_s = item.get("data") or ""
        d = _parse_data_iso(str(data_s) if data_s is not None else "")
        if d is None:
            continue
        fid = normalizar_id_opcional(
            item.get("funcao_id") if item.get("funcao_id") is not None else item.get("cargo_id")
        )
        if fid is None:
            continue
        itens.append((d, fid, idx))

    if not itens:
        return cargo_id_padrao

    itens.sort(key=lambda x: (x[0], x[2]))
    aplicaveis = [(d, fid) for d, fid, _ in itens if d <= referencia]
    if not aplicaveis:
        return cargo_id_padrao
    return aplicaveis[-1][1]
