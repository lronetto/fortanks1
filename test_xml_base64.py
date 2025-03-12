"""
Teste simples para verificar o processamento de XML em Base64

Instruções:
1. Copie este arquivo para o diretório raiz do seu projeto
2. Execute: python test_xml_base64.py
3. Verifique os resultados no console

NOTA: Este teste não modifica o banco de dados, apenas simula o processamento.
"""

import base64
import os
import tempfile
import logging
import sys
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('test_xml_base64')

# Exemplo simples de XML de NFe para teste
XML_EXEMPLO = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe xmlns="http://www.portalfiscal.inf.br/nfe">
    <infNFe Id="NFe12345678901234567890123456789012345678901234" versao="4.00">
      <ide>
        <cUF>35</cUF>
        <cNF>12345678</cNF>
        <natOp>Venda de Mercadoria</natOp>
        <mod>55</mod>
        <serie>1</serie>
        <nNF>123456</nNF>
        <dhEmi>2023-08-25T10:30:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>12345678901234</CNPJ>
        <xNome>EMPRESA TESTE LTDA</xNome>
      </emit>
      <dest>
        <CNPJ>98765432109876</CNPJ>
        <xNome>CLIENTE TESTE S/A</xNome>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>PROD001</cProd>
          <xProd>Produto Teste 1</xProd>
          <qCom>10.0000</qCom>
          <vUnCom>100.0000</vUnCom>
          <vProd>1000.00</vProd>
        </prod>
      </det>
      <det nItem="2">
        <prod>
          <cProd>PROD002</cProd>
          <xProd>Produto Teste 2</xProd>
          <qCom>5.0000</qCom>
          <vUnCom>200.0000</vUnCom>
          <vProd>1000.00</vProd>
        </prod>
      </det>
      <total>
        <ICMSTot>
          <vNF>2000.00</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
</nfeProc>
"""


def process_xml_file(file_path):
    """
    Versão simplificada da função que processa o XML
    Apenas para simular o comportamento da função real
    """
    logger.info(f"Processando arquivo XML: {file_path}")

    try:
        # Ler o arquivo XML
        with open(file_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()

        # Extrair informações do XML (versão simplificada)
        import re

        # Dados da NF
        nfe_data = {
            'access_key': None,
            'number': None,
            'emission_date': None,
            'value': 0.0,
            'cnpj_sender': '',
            'sender_name': '',
            'cnpj_receiver': '',
            'receiver_name': '',
            'items': [],
            'xml': xml_content
        }

        # Extrair chave de acesso
        chave_match = re.search(r'Id="NFe([0-9]{44})"', xml_content)
        if chave_match:
            nfe_data['access_key'] = chave_match.group(1)

        # Extrair número da NF
        num_match = re.search(r'<nNF>(\d+)</nNF>', xml_content)
        if num_match:
            nfe_data['number'] = num_match.group(1)

        # Extrair data de emissão
        date_match = re.search(r'<dhEmi>(.*?)</dhEmi>', xml_content)
        if date_match:
            date_str = date_match.group(1)
            if 'T' in date_str:
                nfe_data['emission_date'] = datetime.fromisoformat(
                    date_str.replace('T', ' ').split('-03:00')[0])

        # Extrair valor total
        value_match = re.search(r'<vNF>(.*?)</vNF>', xml_content)
        if value_match:
            nfe_data['value'] = float(value_match.group(1))

        # Extrair CNPJ e nome do emitente
        cnpj_emit_match = re.search(
            r'<emit>.*?<CNPJ>(.*?)</CNPJ>.*?<xNome>(.*?)</xNome>', xml_content, re.DOTALL)
        if cnpj_emit_match:
            nfe_data['cnpj_sender'] = cnpj_emit_match.group(1)
            nfe_data['sender_name'] = cnpj_emit_match.group(2)

        # Extrair CNPJ e nome do destinatário
        cnpj_dest_match = re.search(
            r'<dest>.*?<CNPJ>(.*?)</CNPJ>.*?<xNome>(.*?)</xNome>', xml_content, re.DOTALL)
        if cnpj_dest_match:
            nfe_data['cnpj_receiver'] = cnpj_dest_match.group(1)
            nfe_data['receiver_name'] = cnpj_dest_match.group(2)

        # Extrair itens
        det_pattern = r'<det[^>]*>.*?<prod>(.*?)</prod>.*?</det>'
        det_matches = re.finditer(det_pattern, xml_content, re.DOTALL)

        for det_match in det_matches:
            prod_content = det_match.group(1)
            item = {}

            # Código do produto
            code_match = re.search(r'<cProd>(.*?)</cProd>', prod_content)
            if code_match:
                item['code'] = code_match.group(1)

            # Descrição do produto
            desc_match = re.search(r'<xProd>(.*?)</xProd>', prod_content)
            if desc_match:
                item['description'] = desc_match.group(1)

            # Quantidade
            qty_match = re.search(r'<qCom>(.*?)</qCom>', prod_content)
            if qty_match:
                item['quantity'] = float(qty_match.group(1).replace(',', '.'))

            # Valor unitário
            val_match = re.search(r'<vUnCom>(.*?)</vUnCom>', prod_content)
            if val_match:
                item['unit_value'] = float(
                    val_match.group(1).replace(',', '.'))

            # Valor total do item
            total_match = re.search(r'<vProd>(.*?)</vProd>', prod_content)
            if total_match:
                item['total_value'] = float(
                    total_match.group(1).replace(',', '.'))

            nfe_data['items'].append(item)

        return nfe_data

    except Exception as e:
        logger.error(f"Erro ao processar XML: {str(e)}")
        return None


def decodificar_base64_xml(base64_str):
    """
    Decodifica um XML em Base64
    """
    try:
        # Remover espaços e quebras de linha
        base64_str = base64_str.replace(
            " ", "").replace("\n", "").replace("\r", "")

        # Decodificar Base64
        xml_bytes = base64.b64decode(base64_str)

        # Tentar diferentes codificações
        xml_content = None
        for encoding in ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']:
            try:
                xml_content = xml_bytes.decode(encoding)
                logger.info(f"XML decodificado com sucesso usando {encoding}")
                break
            except UnicodeDecodeError:
                continue

        if not xml_content:
            logger.error(
                "Falha ao decodificar XML Base64 com todas as codificações tentadas")
            return None

        # Salvar em arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.xml', delete=False, encoding='utf-8')
        temp_file.write(xml_content)
        temp_file_path = temp_file.name
        temp_file.close()

        logger.info(
            f"XML Base64 salvo em arquivo temporário: {temp_file_path}")

        return {
            'xml_content': xml_content,
            'temp_file_path': temp_file_path
        }
    except Exception as e:
        logger.error(f"Erro ao decodificar XML Base64: {str(e)}")
        return None


def processar_e_salvar_nfe_simulado(nfe_data):
    """
    Versão de simulação da função processar_e_salvar_nfe
    Apenas para testar o processamento sem modificar o banco
    """
    logger.info("Iniciando simulação de processamento de NFe")

    try:
        # Verificar se os dados podem estar em Base64
        xml_base64 = None
        processed_xml = False

        # Verificar em diferentes campos onde o XML pode estar
        if 'xml' in nfe_data and isinstance(nfe_data['xml'], str) and len(nfe_data['xml']) > 100:
            xml_base64 = nfe_data['xml']
            logger.info("Encontrado possível XML em campo 'xml'")
        elif 'content' in nfe_data and isinstance(nfe_data['content'], str) and len(nfe_data['content']) > 100:
            xml_base64 = nfe_data['content']
            logger.info("Encontrado possível XML em campo 'content'")
        elif 'data' in nfe_data and isinstance(nfe_data['data'], str) and len(nfe_data['data']) > 100:
            xml_base64 = nfe_data['data']
            logger.info("Encontrado possível XML em campo 'data'")

        # Tentar decodificar Base64
        if xml_base64:
            # Verificar se parece ser Base64 (apenas caracteres válidos de Base64)
            import re
            if re.match(r'^[A-Za-z0-9+/=]+$', xml_base64.replace(" ", "").replace("\n", "")):
                logger.info(
                    "Detectado conteúdo que parece ser Base64, tentando decodificar")

                # Decodificar Base64
                decoded_data = decodificar_base64_xml(xml_base64)

                if decoded_data:
                    # Processar o XML usando a função simulada
                    try:
                        processed_nfe = process_xml_file(
                            decoded_data['temp_file_path'])

                        # Remover arquivo temporário
                        os.unlink(decoded_data['temp_file_path'])

                        # Se processou com sucesso, usar esses dados
                        if processed_nfe and processed_nfe.get('access_key'):
                            nfe_data = processed_nfe
                            nfe_data['xml'] = decoded_data['xml_content']
                            processed_xml = True
                            logger.info(
                                f"XML Base64 processado com sucesso: {processed_nfe.get('access_key')}")
                    except Exception as e:
                        logger.error(
                            f"Erro ao processar arquivo XML temporário: {str(e)}")

        # Exibir os dados processados
        logger.info("Resultado do processamento:")
        logger.info(f"Chave de Acesso: {nfe_data.get('access_key')}")
        logger.info(f"Número NF: {nfe_data.get('number')}")
        logger.info(f"Data Emissão: {nfe_data.get('emission_date')}")
        logger.info(f"Valor Total: {nfe_data.get('value')}")
        logger.info(
            f"Emitente: {nfe_data.get('sender_name')} ({nfe_data.get('cnpj_sender')})")
        logger.info(
            f"Destinatário: {nfe_data.get('receiver_name')} ({nfe_data.get('cnpj_receiver')})")
        logger.info(f"Itens: {len(nfe_data.get('items', []))}")

        for i, item in enumerate(nfe_data.get('items', []), 1):
            logger.info(f"  Item {i}:")
            logger.info(f"    Código: {item.get('code')}")
            logger.info(f"    Descrição: {item.get('description')}")
            logger.info(f"    Quantidade: {item.get('quantity')}")
            logger.info(f"    Valor Unitário: {item.get('unit_value')}")
            logger.info(f"    Valor Total: {item.get('total_value')}")

        return True
    except Exception as e:
        logger.error(f"Erro no processamento da NFe: {str(e)}")
        return False


def executar_teste():
    """
    Função principal de teste
    """
    logger.info("=== INICIANDO TESTE DE PROCESSAMENTO DE XML BASE64 ===")

    # Codificar o XML de exemplo em Base64
    xml_base64 = base64.b64encode(XML_EXEMPLO.encode('utf-8')).decode('utf-8')

    # Criar dados de teste
    nfe_data = {
        'data': xml_base64  # Usando o campo 'data' para testar
    }

    # Processar a NFe
    result = processar_e_salvar_nfe_simulado(nfe_data)

    if result:
        logger.info("=== TESTE CONCLUÍDO COM SUCESSO ===")
    else:
        logger.error("=== TESTE FALHOU ===")


if __name__ == "__main__":
    executar_teste()
