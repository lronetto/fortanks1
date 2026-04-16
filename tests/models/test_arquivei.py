"""Testes unitários para models.arquivei."""

import requests

from models.arquivei import Arquivei


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="{}"):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


def test_definir_tipo_por_chave_cte():
    chave_cte = "0" * 20 + "57" + "1" * 22
    arq = Arquivei(chave_acesso=chave_cte)
    assert arq.tipo == "cte"


def test_definir_tipo_por_chave_nfe():
    chave_nfe = "0" * 20 + "55" + "1" * 22
    arq = Arquivei(chave_acesso=chave_nfe)
    assert arq.tipo == "nfe"


def test_definir_tipo_por_chave_nfse_por_tamanho():
    arq = Arquivei(chave_acesso="a" * 32)
    assert arq.tipo == "nfse"


def test_cancelamento_retorna_false_para_tipo_invalido():
    arq = Arquivei(chave_acesso="123", tipo="desconhecido")
    assert arq.cancelamento() is False


def test_cancelamento_retorna_false_quando_request_exception(monkeypatch):
    arq = Arquivei(chave_acesso="0" * 44, tipo="nfe")

    def _raise(*args, **kwargs):
        raise requests.RequestException("falha de rede")

    monkeypatch.setattr("models.arquivei.requests.get", _raise)
    assert arq.cancelamento() is False


def test_cancelamento_nfe_retorna_true_com_evento_110111(monkeypatch):
    arq = Arquivei(chave_acesso="0" * 44, tipo="nfe")
    payload = {"status": {"code": 200}, "data": [{"type": "110111"}]}
    monkeypatch.setattr(
        "models.arquivei.requests.get",
        lambda *args, **kwargs: _FakeResponse(status_code=200, payload=payload, text='{"ok":true}'),
    )
    assert arq.cancelamento() is True


def test_cancelamento_nfse_retorna_true_com_evento_101101(monkeypatch):
    arq = Arquivei(chave_acesso="a" * 32, tipo="nfse")
    payload = {"status": {"code": 200}, "data": [{"type": "101101"}]}
    monkeypatch.setattr(
        "models.arquivei.requests.get",
        lambda *args, **kwargs: _FakeResponse(status_code=200, payload=payload, text='{"ok":true}'),
    )
    assert arq.cancelamento() is True


def test_processar_arquivei_retorna_erro_para_tipo_invalido():
    arq = Arquivei(tipo="xxx")
    arq.data_inicial = "2026-04-01"
    arq.data_final = "2026-04-01"
    retorno = arq.processar_arquivei()
    assert retorno["success"] is False
    assert "Tipo de documento inválido" in retorno["message"]


def test_processar_arquivei_sem_dados_retorna_mensagem(monkeypatch):
    arq = Arquivei(tipo="nfe")
    arq.data_inicial = "2026-04-01"
    arq.data_final = "2026-04-01"
    payload = {"status": {"code": 200}, "data": []}
    monkeypatch.setattr(
        "models.arquivei.requests.get",
        lambda *args, **kwargs: _FakeResponse(status_code=200, payload=payload, text='{"ok":true}'),
    )
    retorno = arq.processar_arquivei()
    assert retorno["success"] is False
    assert "Nenhuma nota fiscal encontrada" in retorno["message"]


def test_processar_arquivei_com_item_retorna_sucesso(monkeypatch):
    arq = Arquivei(tipo="nfe")
    arq.data_inicial = "2026-04-01"
    arq.data_final = "2026-04-02"
    payload = {
        "status": {"code": 200},
        "data": [{"xml": "BASE64XML", "id": "abc", "access_key": "CHAVE123"}],
    }
    monkeypatch.setattr(
        "models.arquivei.requests.get",
        lambda *args, **kwargs: _FakeResponse(status_code=200, payload=payload, text='{"ok":true}'),
    )
    retorno = arq.processar_arquivei()
    assert retorno["success"] is True
    assert retorno["notas_processadas"] == 1
    assert len(arq.datas) == 1
    assert arq.datas[0]["xml"] == "BASE64XML"


def test_get_xml_define_xml_data(monkeypatch):
    arq = Arquivei(chave_acesso="0" * 44, tipo="nfe")
    payload = {"status": {"code": 200}, "data": [{"xml": "XML-BASE64"}]}
    monkeypatch.setattr(
        "models.arquivei.requests.get",
        lambda *args, **kwargs: _FakeResponse(status_code=200, payload=payload, text='{"ok":true}'),
    )
    arq.get_xml()
    assert arq.xml_data == "XML-BASE64"


def test_get_pdf_define_pdf(monkeypatch):
    arq = Arquivei(chave_acesso="0" * 44, tipo="nfe")
    payload = {"status": {"code": 200}, "data": {"encoded_pdf": "PDF-BASE64"}}
    monkeypatch.setattr(
        "models.arquivei.requests.get",
        lambda *args, **kwargs: _FakeResponse(status_code=200, payload=payload, text='{"ok":true}'),
    )
    arq.get_pdf()
    assert arq.pdf == "PDF-BASE64"
