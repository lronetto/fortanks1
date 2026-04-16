"""Testes unitários para models.nota_fiscal.services.material_precos."""

from decimal import Decimal
from types import SimpleNamespace

from models.nota_fiscal.services import material_precos


class _ColunaDataEmissaoFake:
    def desc(self):
        return "DATA_EMISSAO_DESC"


class _NotaFiscalFake:
    data_emissao = _ColunaDataEmissaoFake()


class _QueryFake:
    def __init__(self, item_retorno):
        self.item_retorno = item_retorno
        self.material_id_recebido = None

    def filter_by(self, **kwargs):
        self.material_id_recebido = kwargs.get("material_id")
        return self

    def join(self, _modelo):
        return self

    def order_by(self, _criterio):
        return self

    def first(self):
        return self.item_retorno


def test_obter_valor_unitario_material_retorna_zero_sem_historico(monkeypatch):
    query_fake = _QueryFake(item_retorno=None)
    nota_fiscal_item_fake = SimpleNamespace(query=query_fake)

    monkeypatch.setattr(material_precos, "NotaFiscal", _NotaFiscalFake)
    monkeypatch.setattr(material_precos, "NotaFiscalItem", nota_fiscal_item_fake)

    valor = material_precos.obter_valor_unitario_material(99)

    assert query_fake.material_id_recebido == 99
    assert valor == 0


def test_obter_valor_unitario_material_retorna_zero_quando_fator_invalido(monkeypatch):
    item_fake = SimpleNamespace(
        valor_unitario=Decimal("10.00"),
        fator_conversao_aplicado=0,
    )
    query_fake = _QueryFake(item_retorno=item_fake)
    nota_fiscal_item_fake = SimpleNamespace(query=query_fake)

    monkeypatch.setattr(material_precos, "NotaFiscal", _NotaFiscalFake)
    monkeypatch.setattr(material_precos, "NotaFiscalItem", nota_fiscal_item_fake)

    valor = material_precos.obter_valor_unitario_material(7)

    assert valor == 0


def test_obter_valor_unitario_material_retorna_valor_convertido(monkeypatch):
    item_fake = SimpleNamespace(
        valor_unitario=Decimal("15.00"),
        fator_conversao_aplicado=3,
    )
    query_fake = _QueryFake(item_retorno=item_fake)
    nota_fiscal_item_fake = SimpleNamespace(query=query_fake)

    monkeypatch.setattr(material_precos, "NotaFiscal", _NotaFiscalFake)
    monkeypatch.setattr(material_precos, "NotaFiscalItem", nota_fiscal_item_fake)

    valor = material_precos.obter_valor_unitario_material(123)

    assert valor == Decimal("5.00")
