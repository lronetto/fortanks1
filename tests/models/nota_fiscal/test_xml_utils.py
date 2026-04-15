"""Testes unitários para models.nota_fiscal.xml_utils (Fase C)."""
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

from models.nota_fiscal.xml_utils import _parse_nfe_data_emissao_xml, get_xml_text


class TestParseNfeDataEmissaoXml:
    def test_iso_com_timezone_preserva_hora(self):
        dt = _parse_nfe_data_emissao_xml("2026-04-01T09:53:00-03:00")
        assert dt.year == 2026 and dt.month == 4 and dt.day == 1
        assert dt.hour == 9 and dt.minute == 53 and dt.second == 0
        assert dt.tzinfo is None

    def test_apenas_data_sem_timezone(self):
        dt = _parse_nfe_data_emissao_xml("2026-04-01")
        assert dt == datetime(2026, 4, 1, 0, 0, 0)

    def test_string_vazia_levanta_valuerror(self):
        with pytest.raises(ValueError, match="emissão vazia"):
            _parse_nfe_data_emissao_xml("")

    def test_apenas_espacos_levanta_valuerror(self):
        with pytest.raises(ValueError, match="emissão vazia"):
            _parse_nfe_data_emissao_xml("   ")


class TestGetXmlText:
    def test_elemento_none_retorna_none(self):
        assert get_xml_text(None, ".//x", {}) is None

    def test_encontra_texto_por_xpath(self):
        root = ET.fromstring("<root><child>valor</child></root>")
        assert get_xml_text(root, ".//child", {}) == "valor"

    def test_caminho_inexistente_retorna_none(self):
        root = ET.fromstring("<root/>")
        assert get_xml_text(root, ".//missing", {}) is None


def test_fixture_nfe_minima_get_xml_text_ns():
    """Trecho mínimo com prefixo nfe (como em NF-e real) para validar find + namespace."""
    xml = """
    <nfe:NFe xmlns:nfe="http://www.portalfiscal.inf.br/nfe">
      <nfe:infNFe>
        <nfe:ide>
          <nfe:nNF>98765</nfe:nNF>
        </nfe:ide>
      </nfe:infNFe>
    </nfe:NFe>
    """
    root = ET.fromstring(xml.strip())
    ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
    n = get_xml_text(root, ".//nfe:nNF", ns)
    assert n == "98765"
