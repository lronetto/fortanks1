"""Dados para edição de orçamento (modal e API)."""

from __future__ import annotations

from sqlalchemy import or_

from models.contrato import Contrato
from models.orcamento import Orcamento


def contratos_para_edicao(orcamento: Orcamento) -> list[Contrato]:
    contrato_filtro = Contrato.ativo == True  # noqa: E712
    if orcamento.contrato_id:
        contrato_filtro = or_(Contrato.ativo == True, Contrato.id == orcamento.contrato_id)  # noqa: E712
    return (
        Contrato.query.filter(contrato_filtro).order_by(Contrato.nome.asc()).all()
    )


def outros_orcamentos_para_edicao(orcamento: Orcamento) -> list[Orcamento]:
    outros = (
        Orcamento.query.filter(Orcamento.id != orcamento.id)
        .order_by(Orcamento.id.desc())
        .limit(400)
        .all()
    )
    if orcamento.vinculado_a_orcamento_id:
        ref = Orcamento.query.get(orcamento.vinculado_a_orcamento_id)
        if ref and ref.id not in {o.id for o in outros}:
            outros.insert(0, ref)
    return outros


def payload_modal_edicao_orcamento(orcamento: Orcamento) -> dict:
    contratos = contratos_para_edicao(orcamento)
    outros = outros_orcamentos_para_edicao(orcamento)
    return {
        "id": orcamento.id,
        "nome": orcamento.nome,
        "data": orcamento.data.isoformat() if orcamento.data else None,
        "status": orcamento.status or "",
        "descricao": orcamento.descricao or "",
        "contrato_id": orcamento.contrato_id,
        "vinculado_a_orcamento_id": orcamento.vinculado_a_orcamento_id,
        "contratos": [{"id": c.id, "nome": c.nome} for c in contratos],
        "outros_orcamentos": [{"id": o.id, "nome": o.nome} for o in outros],
    }
