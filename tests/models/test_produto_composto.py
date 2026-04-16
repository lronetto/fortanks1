"""Testes unitários para models.produto_composto."""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import models.produto_composto as produto_module
from models.estoque import Estoque
from models.material import Materiais
from models.produto_composto import ProdutoComposto, ProdutoCompostoItem
from utils.utils import normalizar_para_data


class _SessaoFake:
    def __init__(self):
        self.adicionados = []
        self.removidos = []
        self.flushes = 0
        self.commits = 0
        self._next_id = 1000

    def add(self, obj):
        self.adicionados.append(obj)

    def delete(self, obj):
        self.removidos.append(obj)

    def flush(self):
        self.flushes += 1
        for obj in self.adicionados:
            if hasattr(obj, "id") and getattr(obj, "id", None) in (None, 0):
                obj.id = self._next_id
                self._next_id += 1

    def commit(self):
        self.commits += 1


class _QueryEstoqueFake:
    def __init__(self, itens):
        self.itens = itens
        self.filtro_recebido = None

    def filter(self, filtro):
        self.filtro_recebido = filtro
        return self

    def all(self):
        return self.itens


class _IdColunaFake:
    def in_(self, valores):
        return valores


def _componente_material(
    *,
    componente_id=1,
    estoque_id=1,
    quantidade=Decimal("2"),
    produto_id=10,
    nome_material="Cimento",
    dados_adicionais=None,
):
    estoque = Estoque()
    estoque.id = estoque_id
    estoque.tipo_item = "material"
    estoque.material = Materiais(nome=nome_material)
    estoque.produto_composto = None
    estoque.ProdComp_id = None

    componente = ProdutoCompostoItem()
    componente.id = componente_id
    componente.estoque_id = estoque_id
    componente.quantidade = Decimal(str(quantidade))
    componente.estoque = estoque
    componente.produto_id = produto_id
    componente.dados_adicionais = dados_adicionais
    return componente


def _componente_produto_composto(
    *,
    componente_id=1,
    estoque_id=20,
    quantidade=Decimal("1"),
    produto_id=10,
    prodcomp_id=99,
    produto_composto=None,
):
    estoque = Estoque()
    estoque.id = estoque_id
    estoque.tipo_item = "produto_composto"
    estoque.material = None
    estoque.produto_composto = produto_composto
    estoque.ProdComp_id = prodcomp_id

    componente = ProdutoCompostoItem()
    componente.id = componente_id
    componente.estoque_id = estoque_id
    componente.quantidade = Decimal(str(quantidade))
    componente.estoque = estoque
    componente.produto_id = produto_id
    componente.dados_adicionais = None
    return componente


def test_normalizar_para_data_cobre_entradas_comuns():
    assert normalizar_para_data(date(2026, 4, 15)) == date(2026, 4, 15)
    assert normalizar_para_data(datetime(2026, 4, 15, 12, 0, 0)) == date(2026, 4, 15)
    assert normalizar_para_data("2026-04-15") == date(2026, 4, 15)
    assert normalizar_para_data("15/04/2026", default=date(2020, 1, 1)) == date(2020, 1, 1)


def test_adicionar_item_atualiza_componente_existente():
    produto = ProdutoComposto()
    produto.id = 10
    existente = ProdutoCompostoItem()
    existente.id = 77
    existente.estoque_id = 1
    existente.quantidade = Decimal("1.5")
    produto.componentes = [existente]

    retorno = produto.adicionar_item(SimpleNamespace(id=1), Decimal("4.25"))

    assert retorno is existente
    assert existente.quantidade == Decimal("4.25")


def test_adicionar_item_novo_sem_id_realiza_flush_e_persiste(monkeypatch):
    sessao = _SessaoFake()
    monkeypatch.setattr(produto_module.db, "session", sessao)

    produto = ProdutoComposto()
    produto.id = None
    produto.componentes = []

    novo = produto.adicionar_item(SimpleNamespace(id=88), Decimal("3.0"))

    assert produto.id is not None
    assert novo in produto.componentes
    assert novo.produto_id == produto.id
    assert novo.estoque_id == 88
    assert sessao.flushes == 2
    assert sessao.commits == 0


def test_remover_item_remove_quando_encontra():
    produto = ProdutoComposto()
    c1 = ProdutoCompostoItem()
    c1.estoque_id = 1
    c2 = ProdutoCompostoItem()
    c2.estoque_id = 2
    produto.componentes = [c1, c2]

    assert produto.remover_item(2) is True
    assert produto.componentes == [c1]


def test_remover_item_retorna_false_quando_nao_existe():
    produto = ProdutoComposto()
    c1 = ProdutoCompostoItem()
    c1.estoque_id = 1
    produto.componentes = [c1]

    assert produto.remover_item(999) is False


def test_calcular_itens_necessarios_agrupa_por_estoque():
    produto = ProdutoComposto()
    estoque_a = Estoque()
    estoque_a.id = 10
    estoque_b = Estoque()
    estoque_b.id = 20
    c1 = ProdutoCompostoItem()
    c1.estoque_id = 10
    c1.quantidade = Decimal("1.5")
    c1.estoque = estoque_a
    c2 = ProdutoCompostoItem()
    c2.estoque_id = 10
    c2.quantidade = Decimal("2.5")
    c2.estoque = estoque_a
    c3 = ProdutoCompostoItem()
    c3.estoque_id = 20
    c3.quantidade = Decimal("1")
    c3.estoque = estoque_b
    produto.componentes = [
        c1,
        c2,
        c3,
    ]

    itens = produto.calcular_itens_necessarios(quantidade=2)

    assert itens[10]["quantidade"] == Decimal("8.0")
    assert itens[10]["estoque"] is estoque_a
    assert itens[20]["quantidade"] == Decimal("2")


def test_verificar_disponibilidade_estoque_marca_disponivel(monkeypatch):
    produto = ProdutoComposto()
    produto.componentes = []

    def _fake_calculo(_quantidade):
        return {
            1: {"estoque": "A", "quantidade": Decimal("3")},
            2: {"estoque": "B", "quantidade": Decimal("7")},
        }

    produto.calcular_itens_necessarios = _fake_calculo
    query = _QueryEstoqueFake(
        [
            SimpleNamespace(id=1, quantidade=Decimal("5")),
            SimpleNamespace(id=2, quantidade=Decimal("2")),
        ]
    )
    estoque_fake = type(
        "EstoqueFake",
        (),
        {
            "id": _IdColunaFake(),
            "query": query,
        },
    )
    monkeypatch.setattr(produto_module, "Estoque", estoque_fake)

    disponibilidade = produto.verificar_disponibilidade_estoque(quantidade=1)

    assert disponibilidade[0]["disponivel"] is True
    assert disponibilidade[0]["quantidade_estoque"] == Decimal("5")
    assert disponibilidade[1]["disponivel"] is False
    assert disponibilidade[1]["quantidade_estoque"] == Decimal("2")
    assert query.filtro_recebido is not None


def test_save_produto_persiste_produto_componentes_e_commit(monkeypatch):
    sessao = _SessaoFake()
    monkeypatch.setattr(produto_module.db, "session", sessao)

    produto = ProdutoComposto()
    produto.id = None
    c1 = ProdutoCompostoItem()
    c1.produto_id = None
    c2 = ProdutoCompostoItem()
    c2.produto_id = 77
    produto.componentes = [c1, c2]

    retorno = produto.save()

    assert retorno is produto
    assert produto.id is not None
    assert c1.produto_id == produto.id
    assert sessao.commits == 1
    assert len(sessao.adicionados) >= 3


def test_delete_produto_chama_delete_e_commit(monkeypatch):
    sessao = _SessaoFake()
    monkeypatch.setattr(produto_module.db, "session", sessao)
    produto = ProdutoComposto()

    retorno = produto.delete()

    assert retorno is produto
    assert sessao.removidos == [produto]
    assert sessao.commits == 1


def test_repr_e_valor_total():
    produto = ProdutoComposto()
    produto.id = 11
    produto.nome = "Traço A"
    c1 = ProdutoCompostoItem()
    c2 = ProdutoCompostoItem()
    c1.get_valor_total = lambda: Decimal("2.5")
    c2.get_valor_total = lambda: Decimal("7.5")
    produto.componentes = [c1, c2]

    assert repr(produto) == "<ProdutoComposto 11 - Traço A>"
    assert produto.get_valor_total() == Decimal("10.0")


def test_produzir_agrega_materiais_necessarios():
    produto = ProdutoComposto()
    produto.id = 1
    produto.nome = "Produto A"
    comp = _componente_material(
        componente_id=10,
        estoque_id=5,
        quantidade=Decimal("2"),
        produto_id=1,
        nome_material="Areia",
    )
    produto.componentes = [comp]

    materiais_necessarios = {}
    produto.produzir(
        quantidade=3,
        data_movimento="2026-04-15",
        log=False,
        materiais_necessarios=materiais_necessarios,
    )

    assert 5 in materiais_necessarios
    assert materiais_necessarios[5]["quantidade"] == Decimal("6")
    assert materiais_necessarios[5]["produto_id"] == 1
    assert materiais_necessarios[5]["componentes"] == [comp]


def test_produzir_ignora_componente_fora_da_janela_de_data():
    produto = ProdutoComposto()
    produto.id = 1
    produto.nome = "Produto A"
    comp = _componente_material(
        componente_id=10,
        estoque_id=5,
        quantidade=Decimal("2"),
        produto_id=1,
        nome_material="Areia",
        dados_adicionais='{"data_inicio":"2026-05-01"}',
    )
    produto.componentes = [comp]
    materiais_necessarios = {}

    produto.produzir(
        quantidade=1,
        data_movimento="2026-04-15",
        log=False,
        materiais_necessarios=materiais_necessarios,
    )

    assert materiais_necessarios == {}


def test_produzir_nao_reprocessa_produto_ja_processado():
    produto = ProdutoComposto()
    produto.id = 1
    produto.nome = "Produto A"
    produto.componentes = [_componente_material(estoque_id=10, quantidade=Decimal("2"), produto_id=1)]
    materiais_necessarios = {}
    ja_processados = {1}

    produto.produzir(
        quantidade=2,
        log=False,
        produtos_processados=ja_processados,
        materiais_necessarios=materiais_necessarios,
    )

    assert materiais_necessarios == {}
    assert ja_processados == {1}


def test_produzir_processa_produto_composto_aninhado_com_fallback_query():
    produto_pai = ProdutoComposto()
    produto_pai.id = 1
    produto_pai.nome = "Pai"

    produto_filho = ProdutoComposto()
    produto_filho.id = 99
    produto_filho.nome = "Filho"
    produto_filho.componentes = [
        _componente_material(
            componente_id=500,
            estoque_id=33,
            quantidade=Decimal("4"),
            produto_id=99,
            nome_material="Brita",
        )
    ]

    componente_filho = _componente_produto_composto(
        componente_id=300,
        estoque_id=20,
        quantidade=Decimal("2"),
        produto_id=1,
        prodcomp_id=99,
        produto_composto=produto_filho,
    )
    produto_pai.componentes = [componente_filho]

    materiais_necessarios = {}
    produto_pai.produzir(
        quantidade=3,
        data_movimento=date(2026, 4, 15),
        log=False,
        materiais_necessarios=materiais_necessarios,
    )

    assert 33 in materiais_necessarios
    assert materiais_necessarios[33]["quantidade"] == Decimal("24")


def test_produzir_traco_true_pula_filho_marcado_como_traco():
    produto_pai = ProdutoComposto()
    produto_pai.id = 1
    produto_pai.nome = "Pai"

    filho_traco = ProdutoComposto()
    filho_traco.id = 44
    filho_traco.nome = "Filho traço"
    filho_traco.traco = True
    filho_traco.componentes = [
        _componente_material(
            componente_id=2,
            estoque_id=8,
            quantidade=Decimal("1"),
            produto_id=44,
            nome_material="Aditivo",
        )
    ]

    componente = _componente_produto_composto(
        componente_id=1,
        estoque_id=7,
        quantidade=Decimal("3"),
        produto_id=1,
        prodcomp_id=44,
        produto_composto=filho_traco,
    )
    produto_pai.componentes = [componente]
    materiais_necessarios = {}

    produto_pai.produzir(
        quantidade=2,
        traco=True,
        log=False,
        materiais_necessarios=materiais_necessarios,
    )

    assert materiais_necessarios == {}


def test_item_repr_getters_e_salvar(monkeypatch):
    sessao = _SessaoFake()
    monkeypatch.setattr(produto_module.db, "session", sessao)
    monkeypatch.setattr(
        Estoque,
        "get_valor_unitario",
        lambda _self: Decimal("12.4"),
    )

    item = ProdutoCompostoItem()
    item.id = 12
    item.produto_id = 20
    item.estoque_id = 30
    item.quantidade = Decimal("2.5")
    estoque = Estoque()
    estoque.id = 30
    estoque.material = Materiais(nome="Cimento")
    item.estoque = estoque

    assert "Cimento" in repr(item)
    assert item.get_valor_unitario() == Decimal("12.4")
    assert item.get_valor_total() == Decimal("31.0")
    assert item.salvar() is item
    assert sessao.adicionados == [item]
    assert sessao.commits == 1
