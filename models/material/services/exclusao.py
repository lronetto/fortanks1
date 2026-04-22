"""
Validação de vínculos e fluxo de exclusão de materiais.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from sqlalchemy import text

from models.database import db
from models.epi import Epi
from models.estoque import Estoque
from models.nota_fiscal import NotaFiscalItem
from models.orcamento import ItemOrcamento, Orcamento
from models.unidade import UnidadesConversao

if TYPE_CHECKING:
    from ..entities.materiais import Materiais

logger = logging.getLogger(__name__)


def mensagem_vinculos_impedem_exclusao(bloqueios: List[str]) -> str:
    return (
        "Este material não pode ser excluído pois está vinculado a: " + ", ".join(bloqueios)
    )


def coletar_bloqueios_exclusao(material: "Materiais") -> List[str]:
    """Lista descrições legíveis dos vínculos que impedem a exclusão."""
    bloqueios: List[str] = []

    try:
        result = db.session.execute(
            text("SELECT COUNT(*) FROM materiais_grupos WHERE material_id = :material_id"),
            {"material_id": material.id},
        ).scalar()
        if result and result > 0:
            bloqueios.append(f"{result} grupo(s) de material")
    except Exception as e:
        logger.warning("Erro ao verificar grupos de material: %s", e)
        try:
            if hasattr(material, "grupos") and material.grupos:
                count = len(material.grupos)
                if count > 0:
                    bloqueios.append(f"{count} grupo(s) de material")
        except Exception:
            pass

    try:
        if hasattr(material, "solicitacoes_itens") and material.solicitacoes_itens:
            count = len(material.solicitacoes_itens)
            if count > 0:
                bloqueios.append(f"{count} solicitação(ões)")
    except Exception:
        pass

    try:
        itens_nf = NotaFiscalItem.query.filter_by(material_id=material.id).count()
        if itens_nf > 0:
            bloqueios.append(f"{itens_nf} item(ns) de nota fiscal")
    except Exception:
        pass

    try:
        estoques = Estoque.query.filter_by(material_id=material.id).count()
        if estoques > 0:
            bloqueios.append(f"{estoques} registro(s) de estoque")
    except Exception:
        pass

    try:
        orcamentos = (
            db.session.query(Orcamento.id)
            .join(ItemOrcamento, ItemOrcamento.orcamento_id == Orcamento.id)
            .filter(ItemOrcamento.material_id == material.id)
            .distinct()
            .count()
        )
        if orcamentos > 0:
            bloqueios.append(f"{orcamentos} orçamento(s)")
    except Exception:
        pass

    try:
        itens_orcamento = ItemOrcamento.query.filter_by(material_id=material.id).count()
        if itens_orcamento > 0:
            bloqueios.append(f"{itens_orcamento} item(ns) de orçamento")
    except Exception:
        pass

    try:
        epis = Epi.query.filter_by(material_id=material.id).count()
        if epis > 0:
            bloqueios.append(f"{epis} epi(s)")
    except Exception:
        pass

    try:
        conversoes = UnidadesConversao.query.filter_by(material_id=material.id).count()
        if conversoes > 0:
            bloqueios.append(f"{conversoes} conversão(ões)")
    except Exception:
        pass

    return bloqueios


def excluir_material_validando_vinculos(material: "Materiais") -> str:
    """
    Exclui o material após validar vínculos.

    Retorna mensagem de sucesso para flash.
    Levanta ``ValueError`` se houver vínculos (mensagem já formatada para o usuário).
    Persistência: delega ao ``delete()`` da entidade (commit incluído).
    """
    bloqueios = coletar_bloqueios_exclusao(material)
    if bloqueios:
        raise ValueError(mensagem_vinculos_impedem_exclusao(bloqueios))

    nome = material.nome
    material.delete()
    return f'Material "{nome}" excluído com sucesso!'
