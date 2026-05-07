"""Testes unitários para `models.sefaz_distribuicao.services.cliente_nfe`.

Foca em duas funções críticas que NÃO dependem da rede:

- `_parse_resposta`: extrai docZip da resposta SOAP da SEFAZ.
- `_enriquecer`: preenche chave/CNPJ/dhEmi a partir do XML interno.
- `filtrar_por_data`: filtro local por dhEmi.
"""
from __future__ import annotations

import base64
import gzip
from datetime import date, datetime

import pytest

from models.sefaz_distribuicao.entities import LoteDownload, XmlBaixado
from models.sefaz_distribuicao.services.cliente_nfe import (
    DocumentoXML,
    _enriquecer,
    _parse_resposta,
    filtrar_por_data,
)


# --- Helpers --------------------------------------------------------------

def _gz_b64(xml_str: str) -> str:
    return base64.b64encode(gzip.compress(xml_str.encode("utf-8"))).decode("ascii")


def _envelope_resposta(*, cstat: str, ult_nsu: str, max_nsu: str, doc_zips: list[tuple[str, str, str]]) -> bytes:
    """Monta um envelope SOAP de resposta como o que a SEFAZ devolve.

    Cada `doc_zips` é (NSU, schema, xml_interno).
    """
    docs = "".join(
        f'<docZip NSU="{nsu}" schema="{schema}">{_gz_b64(xml)}</docZip>'
        for nsu, schema, xml in doc_zips
    )
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
        f"<soap:Body>"
        f'<nfeDistDFeInteresseResponse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">'
        f'<retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">'
        f"<tpAmb>1</tpAmb>"
        f"<verAplic>SVRS-1.0</verAplic>"
        f"<cStat>{cstat}</cStat>"
        f"<xMotivo>Teste</xMotivo>"
        f"<dhResp>2026-04-15T10:00:00-03:00</dhResp>"
        f"<ultNSU>{ult_nsu}</ultNSU>"
        f"<maxNSU>{max_nsu}</maxNSU>"
        f"<loteDistDFeInt>{docs}</loteDistDFeInt>"
        f"</retDistDFeInt>"
        f"</nfeDistDFeInteresseResponse>"
        f"</soap:Body>"
        f"</soap:Envelope>"
    ).encode("utf-8")


def _res_nfe(chave: str, cnpj: str, dh_emi: str = "2026-04-10T09:00:00-03:00") -> str:
    """XML mínimo de um resNFe v1.01 (resumo de NFe emitida)."""
    return (
        f'<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">'
        f"<chNFe>{chave}</chNFe>"
        f"<CNPJ>{cnpj}</CNPJ>"
        f"<xNome>Empresa Teste</xNome>"
        f"<IE>123456789</IE>"
        f"<dhEmi>{dh_emi}</dhEmi>"
        f"<tpNF>1</tpNF>"
        f"<vNF>100.00</vNF>"
        f"<digVal>abc</digVal>"
        f"<dhRecbto>2026-04-10T09:05:00-03:00</dhRecbto>"
        f"<cSitNFe>1</cSitNFe>"
        f"</resNFe>"
    )


def _proc_nfe_completa(
    chave: str, cnpj_emit: str, cnpj_dest: str, dh_emi: str = "2026-04-12T14:30:00-03:00"
) -> str:
    """XML mínimo de um procNFe v4.00 (NFe completa, papel destinatário)."""
    return (
        f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
        f'<NFe>'
        f'<infNFe Id="NFe{chave}" versao="4.00">'
        f"<ide><dhEmi>{dh_emi}</dhEmi></ide>"
        f"<emit><CNPJ>{cnpj_emit}</CNPJ><xNome>Emit</xNome></emit>"
        f"<dest><CNPJ>{cnpj_dest}</CNPJ><xNome>Dest</xNome></dest>"
        f"</infNFe>"
        f"</NFe>"
        f"</nfeProc>"
    )


# --- _parse_resposta -----------------------------------------------------

class TestParseResposta:
    def test_138_um_documento_resumo(self):
        xml_resumo = _res_nfe("12345678901234567890123456789012345678901234", "12345678000199")
        envelope = _envelope_resposta(
            cstat="138",
            ult_nsu="000000000000010",
            max_nsu="000000000000010",
            doc_zips=[("000000000000010", "resNFe_v1.01.xsd", xml_resumo)],
        )

        resultado = _parse_resposta(envelope)

        assert resultado.ultimo_nsu == "000000000000010"
        assert resultado.max_nsu == "000000000000010"
        assert len(resultado.documentos) == 1
        doc = resultado.documentos[0]
        assert doc.nsu == "000000000000010"
        assert doc.schema == "resNFe_v1.01.xsd"
        assert "resNFe" in doc.xml

    def test_137_sem_documentos(self):
        envelope = _envelope_resposta(
            cstat="137", ult_nsu="000000000000005", max_nsu="000000000000005", doc_zips=[]
        )
        resultado = _parse_resposta(envelope)
        assert resultado.documentos == []

    def test_656_consumo_indevido_levanta_runtime(self):
        envelope = _envelope_resposta(
            cstat="656", ult_nsu="0", max_nsu="0", doc_zips=[]
        )
        with pytest.raises(RuntimeError, match="Consumo Indevido"):
            _parse_resposta(envelope)

    def test_outro_cstat_levanta_runtime_generico(self):
        envelope = _envelope_resposta(
            cstat="217", ult_nsu="0", max_nsu="0", doc_zips=[]
        )
        with pytest.raises(RuntimeError, match="cStat=217"):
            _parse_resposta(envelope)

    def test_descompacta_gzip_corretamente(self):
        chave = "11111111111111111111111111111111111111111111"
        xml_resumo = _res_nfe(chave, "12345678000199")
        envelope = _envelope_resposta(
            cstat="138",
            ult_nsu="000000000000020",
            max_nsu="000000000000020",
            doc_zips=[("000000000000020", "resNFe_v1.01.xsd", xml_resumo)],
        )
        resultado = _parse_resposta(envelope)
        assert chave in resultado.documentos[0].xml


# --- _enriquecer ---------------------------------------------------------

class TestEnriquecer:
    def test_resumo_extrai_chave_cnpj_e_data(self):
        chave = "12345678901234567890123456789012345678901234"
        doc = DocumentoXML(
            nsu="000000000000010",
            schema="resNFe_v1.01.xsd",
            xml=_res_nfe(chave, "12345678000199", "2026-04-10T09:00:00-03:00"),
        )

        enriquecido = _enriquecer(doc)

        assert enriquecido.chave == chave
        assert enriquecido.cnpj_emitente == "12345678000199"
        assert enriquecido.data_emissao == datetime.fromisoformat(
            "2026-04-10T09:00:00-03:00"
        )

    def test_nfe_completa_extrai_emitente_e_destinatario(self):
        chave = "99999999999999999999999999999999999999999999"
        doc = DocumentoXML(
            nsu="000000000000020",
            schema="procNFe_v4.00.xsd",
            xml=_proc_nfe_completa(chave, "11111111000111", "22222222000122"),
        )

        enriquecido = _enriquecer(doc)

        assert enriquecido.chave == chave
        assert enriquecido.cnpj_emitente == "11111111000111"
        assert enriquecido.cnpj_destinatario == "22222222000122"

    def test_xml_invalido_nao_explode(self):
        doc = DocumentoXML(nsu="0", schema="x", xml="<xml não fechado")
        enriquecido = _enriquecer(doc)
        # Não deve levantar; só não preenche os campos.
        assert enriquecido.chave is None


# --- filtrar_por_data ----------------------------------------------------

class TestFiltrarPorData:
    def test_inclui_extremos(self):
        docs = [
            DocumentoXML(nsu="1", schema="x", xml="", data_emissao=datetime(2026, 4, 1, 0, 0)),
            DocumentoXML(nsu="2", schema="x", xml="", data_emissao=datetime(2026, 4, 30, 23, 59)),
        ]
        out = filtrar_por_data(docs, date(2026, 4, 1), date(2026, 4, 30))
        assert {d.nsu for d in out} == {"1", "2"}

    def test_exclui_fora_do_intervalo(self):
        docs = [
            DocumentoXML(nsu="1", schema="x", xml="", data_emissao=datetime(2026, 3, 31, 23, 59)),
            DocumentoXML(nsu="2", schema="x", xml="", data_emissao=datetime(2026, 4, 15, 12, 0)),
            DocumentoXML(nsu="3", schema="x", xml="", data_emissao=datetime(2026, 5, 1, 0, 0)),
        ]
        out = filtrar_por_data(docs, date(2026, 4, 1), date(2026, 4, 30))
        assert [d.nsu for d in out] == ["2"]

    def test_documento_sem_data_e_descartado(self):
        docs = [
            DocumentoXML(nsu="1", schema="x", xml="", data_emissao=None),
            DocumentoXML(nsu="2", schema="x", xml="", data_emissao=datetime(2026, 4, 10)),
        ]
        out = filtrar_por_data(docs, date(2026, 4, 1), date(2026, 4, 30))
        assert [d.nsu for d in out] == ["2"]


# --- Entidades do model -------------------------------------------------

class TestLoteDownload:
    def test_iter_concatena_tipos(self):
        lote = LoteDownload(
            nfe=[XmlBaixado(tipo="nfe", nsu="1", xml="x")],
            cte=[XmlBaixado(tipo="cte", nsu="2", xml="x")],
            nfse=[XmlBaixado(tipo="nfse", nsu="", xml="x")],
        )
        assert [item.nsu for item in lote] == ["1", "2", ""]

    def test_total_soma_listas(self):
        lote = LoteDownload(
            nfe=[XmlBaixado(tipo="nfe", nsu="1", xml="x"), XmlBaixado(tipo="nfe", nsu="2", xml="x")],
            cte=[XmlBaixado(tipo="cte", nsu="3", xml="x")],
        )
        assert lote.total == 3
