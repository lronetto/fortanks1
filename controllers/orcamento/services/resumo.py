"""Service de resumo financeiro do orçamento."""

from __future__ import annotations

from decimal import Decimal

from models.database import db
from models.orcamento import ItemOrcamento
from models.orcamento.constants import (
    GRUPOS_FABRICACAO,
    GRUPOS_MONTAGEM,
    PADROES_DESC_ITEM_FABRICACAO,
    PADROES_DESC_ITEM_MONTAGEM,
)
from utils.formatting import formatar_moeda


def _normalizar_texto(texto: str | None) -> str:
    return (texto or "").strip().casefold()


def calcular_resumo_valores_orcamento(orcamento_id: int) -> dict:
    grupos_fabricacao = [_normalizar_texto(g) for g in GRUPOS_FABRICACAO if (g or "").strip()]
    grupos_montagem = [_normalizar_texto(g) for g in GRUPOS_MONTAGEM if (g or "").strip()]
    padroes_desc_fabricacao = [_normalizar_texto(p) for p in PADROES_DESC_ITEM_FABRICACAO if (p or "").strip()]
    padroes_desc_montagem = [_normalizar_texto(p) for p in PADROES_DESC_ITEM_MONTAGEM if (p or "").strip()]

    valor_fabricacao = Decimal("0.00")
    valor_montagem = Decimal("0.00")
    valor_total = Decimal("0.00")

    itens = (
        db.session.query(
            ItemOrcamento.descricao_item,
            ItemOrcamento.grupo,
            ItemOrcamento.quantidade,
            ItemOrcamento.valor,
        )
        .filter(ItemOrcamento.orcamento_id == orcamento_id)
        .all()
    )

    for item in itens:
        quantidade = item.quantidade or Decimal("0.00")
        valor = item.valor or Decimal("0.00")
        subtotal = quantidade * valor
        valor_total += subtotal

        desc_norm = _normalizar_texto(item.descricao_item)
        grupo_norm = _normalizar_texto(item.grupo)

        fab_por_desc = any(p in desc_norm for p in padroes_desc_fabricacao)
        mont_por_desc = any(p in desc_norm for p in padroes_desc_montagem)

        if fab_por_desc and mont_por_desc:
            valor_fabricacao += subtotal
        elif fab_por_desc:
            valor_fabricacao += subtotal
        elif mont_por_desc:
            valor_montagem += subtotal
        else:
            if any(grupo_cfg in grupo_norm for grupo_cfg in grupos_fabricacao):
                valor_fabricacao += subtotal
            if any(grupo_cfg in grupo_norm for grupo_cfg in grupos_montagem):
                valor_montagem += subtotal

    return {
        "valor_fabricacao": float(valor_fabricacao),
        "valor_montagem": float(valor_montagem),
        "valor_total": float(valor_total),
        "valor_fabricacao_fmt": formatar_moeda(valor_fabricacao),
        "valor_montagem_fmt": formatar_moeda(valor_montagem),
        "valor_total_fmt": formatar_moeda(valor_total),
        "grupos_fabricacao": GRUPOS_FABRICACAO,
        "grupos_montagem": GRUPOS_MONTAGEM,
        "padroes_desc_fabricacao": PADROES_DESC_ITEM_FABRICACAO,
        "padroes_desc_montagem": PADROES_DESC_ITEM_MONTAGEM,
    }
