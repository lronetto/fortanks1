"""Testes unitários abrangentes para models.material."""

from datetime import datetime
from types import SimpleNamespace

import models.material as material_module
from models.material import Material, Materiais, MateriaisGrupos
from models.unidade import Unidades
from models.usuario import Usuario


class _SessaoFake:
    def __init__(self):
        self.adicionados = []
        self.removidos = []
        self.commits = 0

    def add(self, obj):
        self.adicionados.append(obj)

    def delete(self, obj):
        self.removidos.append(obj)

    def commit(self):
        self.commits += 1


class _QueryChainFake:
    def __init__(self, retorno_all=None, retorno_first=None):
        self.retorno_all = retorno_all if retorno_all is not None else []
        self.retorno_first = retorno_first
        self.kwargs_filter = None
        self.order_by_recebido = None

    def filter_by(self, **kwargs):
        self.kwargs_filter = kwargs
        return self

    def order_by(self, campo):
        self.order_by_recebido = campo
        return self

    def all(self):
        return self.retorno_all

    def first(self):
        return self.retorno_first


def test_alias_material_aponta_para_materiais():
    assert Material is Materiais


def test_material_to_dict_retorna_campos_esperados():
    material = Materiais()
    material.id = 10
    material.nome = "Areia"
    material.descricao = "Areia média"
    material.unidade_id = 3
    material.unidade_obj = Unidades(nome="m3")

    assert material.to_dict() == {
        "id": 10,
        "nome": "Areia",
        "descricao": "Areia média",
        "unidade": "m3",
        "unidade_id": 3,
    }


def test_material_data_criacao_retorna_criado_em():
    material = Materiais()
    material.criado_em = datetime(2026, 4, 15, 10, 30, 0)

    assert material.data_criacao == datetime(2026, 4, 15, 10, 30, 0)


def test_imagem_upload_id_retorna_none_para_dados_invalidos():
    material = Materiais()
    material.dados_adicionais = "json-invalido"

    assert material.imagem_upload_id is None


def test_imagem_upload_id_retorna_int_quando_valido():
    material = Materiais()
    material.dados_adicionais = '{"imagem_upload_id": "123"}'

    assert material.imagem_upload_id == 123


def test_repr_exibe_codigo_ou_sem_codigo():
    material_sem_codigo = Materiais()
    material_sem_codigo.id = 1
    material_sem_codigo.nome = "Cimento"
    material_sem_codigo.codigo = None

    material_com_codigo = Materiais()
    material_com_codigo.id = 2
    material_com_codigo.nome = "Brita"
    material_com_codigo.codigo = "MAT-01"

    assert repr(material_sem_codigo) == "<Material 1 - Cimento>"
    assert repr(material_com_codigo) == "<Material 2 - Brita>"


def test_get_unidade_nome_prioriza_unidade_obj():
    material = Materiais()
    material.unidade = "UN"
    material.unidade_obj = Unidades(nome="KG")

    assert material.get_unidade_nome() == "KG"


def test_get_unidade_nome_fallback_para_unidade():
    material = Materiais()
    material.unidade = "UN"
    material.unidade_obj = None

    assert material.get_unidade_nome() == "UN"


def test_tem_conversoes_retorna_false_sem_unidade_definida():
    material = Materiais()
    material.unidade = None
    material.unidade_id = None
    material.conversoes_unidade = [1, 2]

    assert material.tem_conversoes() is False


def test_tem_conversoes_retorna_true_quando_tem_lista_de_conversao():
    material = Materiais()
    material.unidade = "UN"
    material.unidade_id = None
    material.conversoes_unidade = [object()]

    assert material.tem_conversoes() is True


def test_get_valor_unitario_delega_para_servico(monkeypatch):
    material = Materiais()
    material.id = 321

    def _obter_valor_unitario_material(material_id):
        assert material_id == 321
        return 12.34

    monkeypatch.setattr(
        "models.nota_fiscal.services.material_precos.obter_valor_unitario_material",
        _obter_valor_unitario_material,
    )

    assert material.get_valor_unitario() == 12.34


def test_calcular_quantidade_sem_formula_retorna_um():
    material = Materiais()
    material.formula_calculo = None

    valor = material.calcular_quantidade(
        quantidade_total=3,
        placas_normais=2,
        placas_fecho=1,
        quantidade_bainhas=0,
    )

    assert valor == 1.0


def test_calcular_quantidade_com_formula_valida():
    material = Materiais()
    material.formula_calculo = "quantidade_total + placas_normais + placas_fecho + quantidade_bainhas"

    valor = material.calcular_quantidade(
        quantidade_total=2,
        placas_normais=3,
        placas_fecho=4,
        quantidade_bainhas=1,
    )

    assert valor == 10.0


def test_calcular_quantidade_com_formula_invalida_retorna_um():
    material = Materiais()
    material.id = 99
    material.formula_calculo = "quantidade_total + ("

    valor = material.calcular_quantidade(
        quantidade_total=2,
        placas_normais=3,
        placas_fecho=4,
        quantidade_bainhas=1,
    )

    assert valor == 1.0


def test_save_material_chama_add_e_commit(monkeypatch):
    material = Materiais()
    sessao_fake = _SessaoFake()
    monkeypatch.setattr(material_module.db, "session", sessao_fake)

    material.save()

    assert sessao_fake.adicionados == [material]
    assert sessao_fake.commits == 1


def test_delete_material_chama_delete_e_commit(monkeypatch):
    material = Materiais()
    sessao_fake = _SessaoFake()
    monkeypatch.setattr(material_module.db, "session", sessao_fake)

    material.delete()

    assert sessao_fake.removidos == [material]
    assert sessao_fake.commits == 1


def test_materiais_grupos_repr():
    grupo = MateriaisGrupos()
    grupo.id = 7
    grupo.codigo = "GRP-7"
    grupo.nome = "Insumos"

    assert repr(grupo) == "<MaterialGrupo GRP-7 - Insumos>"


def test_materiais_grupos_to_dict():
    grupo = MateriaisGrupos()
    grupo.id = 1
    grupo.nome = "Grupo A"
    grupo.descricao = "Teste"
    grupo.codigo = "A"
    grupo.ativo = True
    grupo.cor = "#ffffff"
    grupo.icone = "fas fa-boxes"
    grupo.criado_em = datetime(2026, 4, 1, 8, 0, 0)
    grupo.atualizado_em = datetime(2026, 4, 2, 9, 0, 0)
    grupo.criado_por = Usuario(
        nome="Admin",
        email="admin@example.com",
        senha="x",
        departamento_id=1,
        cargo_id=1,
    )
    grupo.materiais = [Materiais(ativo=True, nome="M1"), Materiais(ativo=False, nome="M2")]

    resultado = grupo.to_dict()

    assert resultado["id"] == 1
    assert resultado["nome"] == "Grupo A"
    assert resultado["criado_por"] == "Admin"
    assert resultado["total_materiais"] == 2
    assert resultado["criado_em"] == "2026-04-01T08:00:00"
    assert resultado["atualizado_em"] == "2026-04-02T09:00:00"


def test_save_grupo_chama_add_e_commit(monkeypatch):
    grupo = MateriaisGrupos()
    sessao_fake = _SessaoFake()
    monkeypatch.setattr(material_module.db, "session", sessao_fake)

    grupo.save()

    assert sessao_fake.adicionados == [grupo]
    assert sessao_fake.commits == 1


def test_delete_grupo_limpa_materiais_e_persiste(monkeypatch):
    grupo = MateriaisGrupos()
    grupo.materiais = [Materiais(nome="M1"), Materiais(nome="M2")]
    sessao_fake = _SessaoFake()
    monkeypatch.setattr(material_module.db, "session", sessao_fake)

    grupo.delete()

    assert grupo.materiais == []
    assert sessao_fake.removidos == [grupo]
    assert sessao_fake.commits == 1


def test_adicionar_material_evita_duplicata(monkeypatch):
    grupo = MateriaisGrupos()
    material = Materiais(nome="M1")
    grupo.materiais = [material]
    sessao_fake = _SessaoFake()
    monkeypatch.setattr(material_module.db, "session", sessao_fake)

    retorno = grupo.adicionar_material(material)

    assert retorno is False
    assert sessao_fake.commits == 0


def test_adicionar_material_novo_persiste(monkeypatch):
    grupo = MateriaisGrupos()
    material = Materiais(nome="M1")
    grupo.materiais = []
    sessao_fake = _SessaoFake()
    monkeypatch.setattr(material_module.db, "session", sessao_fake)

    retorno = grupo.adicionar_material(material)

    assert retorno is True
    assert material in grupo.materiais
    assert sessao_fake.commits == 1


def test_remover_material_existente_persiste(monkeypatch):
    grupo = MateriaisGrupos()
    material = Materiais(nome="M1")
    grupo.materiais = [material]
    sessao_fake = _SessaoFake()
    monkeypatch.setattr(material_module.db, "session", sessao_fake)

    grupo.remover_material(material)

    assert material not in grupo.materiais
    assert sessao_fake.commits == 1


def test_get_materiais_ativos_filtra_lista():
    grupo = MateriaisGrupos()
    ativo = Materiais(nome="Ativo", ativo=True)
    inativo = Materiais(nome="Inativo", ativo=False)
    grupo.materiais = [ativo, inativo]

    assert grupo.get_materiais_ativos() == [ativo]


def test_propriedades_total_materiais():
    grupo = MateriaisGrupos()
    grupo.materiais = [Materiais(nome="Ativo", ativo=True), Materiais(nome="Inativo", ativo=False)]

    assert grupo.total_materiais == 2
    assert grupo.total_materiais_ativos == 1
