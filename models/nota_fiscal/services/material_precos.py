"""Serviços de consulta de preços de materiais a partir de notas fiscais."""

from ..entities import NotaFiscal, NotaFiscalItem


def obter_valor_unitario_material(material_id):
    """
    Retorna o último valor unitário conhecido do material a partir dos itens de NF.

    A ordenação considera a data de emissão da nota mais recente.
    Quando não há histórico ou há fator inválido, retorna 0.
    """
    item_nf = (
        NotaFiscalItem.query.filter_by(material_id=material_id)
        .join(NotaFiscal)
        .order_by(NotaFiscal.data_emissao.desc())
        .first()
    )
    if not item_nf:
        return 0

    fator = item_nf.fator_conversao_aplicado or 0
    if fator == 0:
        return 0

    return item_nf.valor_unitario / fator
