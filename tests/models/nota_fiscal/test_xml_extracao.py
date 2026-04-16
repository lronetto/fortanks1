"""Testes unitários para models.nota_fiscal.parsing.xml_extracao."""

import base64
from datetime import datetime
from decimal import Decimal

from models.nota_fiscal.parsing.xml_extracao import (
    extrair_dados_xml_cte,
    extrair_dados_xml_nfe,
    extrair_dados_xml_nfse,
)


def _xml_para_b64(xml: str) -> str:
    return base64.b64encode(xml.encode("utf-8")).decode("utf-8")


class TestExtrairDadosXmlNfe:
    def test_nfe_valida_retorna_campos_basicos_e_itens(self):
        xml = """
        <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
          <NFe>
            <infNFe Id="NFe12345678901234567890123456789012345678901234">
              <ide>
                <nNF>321</nNF>
                <tpNF>1</tpNF>
                <dhEmi>2026-04-05T13:20:00-03:00</dhEmi>
              </ide>
              <emit>
                <CNPJ>11222333000144</CNPJ>
                <xNome>Fornecedor XPTO</xNome>
                <enderEmit><UF>SP</UF></enderEmit>
              </emit>
              <dest>
                <CPF>12345678900</CPF>
                <xNome>Cliente Final</xNome>
              </dest>
              <det nItem="1">
                <prod>
                  <cProd>ABC-1</cProd>
                  <xProd>Produto A</xProd>
                  <qCom>2.0000</qCom>
                  <vUnCom>10.50</vUnCom>
                  <vProd>21.00</vProd>
                  <NCM>84715010</NCM>
                  <CFOP>5102</CFOP>
                  <uCom>UN</uCom>
                </prod>
                <imposto>
                  <ICMS><ICMS60><CST>60</CST></ICMS60></ICMS>
                  <IPI><IPITrib><CST>50</CST></IPITrib></IPI>
                  <PIS><PISAliq><CST>01</CST></PISAliq></PIS>
                  <COFINS><COFINSAliq><CST>01</CST></COFINSAliq></COFINS>
                </imposto>
              </det>
              <total>
                <ICMSTot>
                  <vNF>21.00</vNF>
                  <vIPI>0.00</vIPI>
                  <vPIS>0.00</vPIS>
                  <vCOFINS>0.00</vCOFINS>
                  <vICMS>0.00</vICMS>
                </ICMSTot>
              </total>
            </infNFe>
          </NFe>
        </nfeProc>
        """
        chave, dados = extrair_dados_xml_nfe(_xml_para_b64(xml))

        assert chave == "12345678901234567890123456789012345678901234"
        assert dados["numero"] == "321"
        assert dados["tipo"] == "1"
        assert dados["cnpj_emitente"] == "11222333000144"
        assert dados["cnpj_destinatario"] == "12345678900"
        assert dados["valor_total"] == Decimal("21.00")
        assert dados["data_emissao"] == datetime(2026, 4, 5, 13, 20, 0)
        assert len(dados["itens"]) == 1
        assert dados["itens"][0]["codigo"] == "ABC-1"
        assert dados["itens"][0]["descricao"] == "Produto A"

    def test_nfe_sem_data_emissao_retorna_dados_none(self):
        xml = """
        <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
          <NFe>
            <infNFe Id="NFe999">
              <ide><nNF>1</nNF><tpNF>1</tpNF></ide>
              <emit><CNPJ>1</CNPJ><xNome>A</xNome></emit>
              <dest><CNPJ>2</CNPJ><xNome>B</xNome></dest>
              <total><ICMSTot><vNF>1.00</vNF></ICMSTot></total>
            </infNFe>
          </NFe>
        </nfeProc>
        """
        chave, dados = extrair_dados_xml_nfe(_xml_para_b64(xml))

        assert chave == "999"
        assert dados is None


class TestExtrairDadosXmlCte:
    def test_cte_valido_retorna_campos_esperados(self):
        xml = """
        <cteProc xmlns="http://www.portalfiscal.inf.br/cte">
          <CTe>
            <infCte Id="CTe35123456789012345678901234567890123456789012">
              <ide>
                <nCT>123</nCT>
                <dhEmi>2026-04-10T08:30:00-03:00</dhEmi>
                <xMunIni>Curitiba</xMunIni>
                <UFIni>PR</UFIni>
                <xMunFim>Sao Paulo</xMunFim>
                <UFFim>SP</UFFim>
              </ide>
              <emit>
                <CNPJ>99887766000155</CNPJ>
                <xNome>Transportadora X</xNome>
              </emit>
              <dest>
                <CNPJ>12312312300019</CNPJ>
                <xNome>Destino Y</xNome>
              </dest>
              <rem>
                <CNPJ>11111111000111</CNPJ>
                <xNome>Remetente Z</xNome>
              </rem>
              <vPrest><vTPrest>345.67</vTPrest></vPrest>
              <infCTeNorm>
                <infDoc>
                  <infNFe>
                    <chave>CHAVE-NFE-RELACIONADA</chave>
                  </infNFe>
                </infDoc>
              </infCTeNorm>
            </infCte>
          </CTe>
        </cteProc>
        """
        chave, dados = extrair_dados_xml_cte(_xml_para_b64(xml))

        assert chave == "35123456789012345678901234567890123456789012"
        assert dados["numero_cte"] == "123"
        assert dados["cnpj_emitente"] == "99887766000155"
        assert dados["cnpj_destinatario"] == "12312312300019"
        assert dados["valor_total"] == 345.67
        assert dados["data_emissao"] == datetime(2026, 4, 10, 8, 30, 0)
        assert dados["dados_adicionais"]["chave_nf"] == "CHAVE-NFE-RELACIONADA"

    def test_xml_sem_infcte_retorna_none_none(self):
        xml = "<nfeProc><NFe /></nfeProc>"
        chave, dados = extrair_dados_xml_cte(_xml_para_b64(xml))

        assert chave is None
        assert dados is None


class TestExtrairDadosXmlNfse:
    def test_nfse_formato_lista_nfse_retorna_campos(self):
        xml = """
        <ListaNfse>
          <CompNfse>
            <Nfse>
              <InfNfse Id="NFS12345">
                <Numero>2026</Numero>
                <DataEmissao>2026-04-01</DataEmissao>
                <ValoresNfse>
                  <ValorLiquidoNfse>1500.00</ValorLiquidoNfse>
                </ValoresNfse>
                <PrestadorServico><RazaoSocial>Prestador Servico</RazaoSocial></PrestadorServico>
                <DeclaracaoPrestacaoServico>
                  <InfDeclaracaoPrestacaoServico>
                    <Prestador><CpfCnpj><Cnpj>00111222000133</Cnpj></CpfCnpj></Prestador>
                    <TomadorServico>
                      <IdentificacaoTomador><CpfCnpj><Cnpj>99888777000166</Cnpj></CpfCnpj></IdentificacaoTomador>
                      <RazaoSocial>Tomador Exemplo</RazaoSocial>
                    </TomadorServico>
                  </InfDeclaracaoPrestacaoServico>
                </DeclaracaoPrestacaoServico>
              </InfNfse>
            </Nfse>
          </CompNfse>
        </ListaNfse>
        """
        chave, dados = extrair_dados_xml_nfse(_xml_para_b64(xml))

        assert chave == "12345"
        assert dados["Numero"] == "2026"
        assert dados["cnpj_emitente"] == "00111222000133"
        assert dados["cnpj_destinatario"] == "99888777000166"
        assert dados["valores"]["ValorLiquidoNfse"] == "1500.00"

    def test_nfse_formato_nao_reconhecido_retorna_none_none(self):
        xml = "<root><outroFormato /></root>"
        chave, dados = extrair_dados_xml_nfse(_xml_para_b64(xml))

        assert chave is None
        assert dados is None
