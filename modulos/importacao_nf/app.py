# modulo_importacao_nf/app.py
from modulos.importacao_nf.xml_utils import decodificar_base64_xml, identificar_xml_base64
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
import requests
import json
from datetime import datetime, timedelta
import os
from mysql.connector import Error
import mysql
import tempfile
import zipfile
import shutil
import xml.etree.ElementTree as ET
from werkzeug.utils import secure_filename
import logging
from flask_wtf import FlaskForm
import base64

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('importacao_xml.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('importacao_xml')

# Configuração do Blueprint
mod_importacao_nf = Blueprint('importacao_nf', __name__,
                              template_folder='templates',
                              static_folder='static')

# Configurações da API Arquivei
ARQUIVEI_API_ID = os.environ.get('ARQUIVEI_API_ID', 'seu_api_id')
ARQUIVEI_API_KEY = os.environ.get('ARQUIVEI_API_KEY', 'sua_api_key')
ARQUIVEI_API_ENDPOINT = 'https://api.arquivei.com.br/v1/nfe/received'

# Importar o módulo xml_utils

# Função para conectar ao banco de dados


def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'sistema_solicitacoes'),
            user=os.environ.get('DB_USER', 'root'),
            password=os.environ.get('DB_PASSWORD', 'sua_senha')
        )
        return connection
    except Error as e:
        logger.error(f"Erro ao conectar ao MySQL: {e}")
        return None

# Função para buscar NFes da API Arquivei


def process_xml_file(file_path):
    """
    Processa um arquivo XML de NF-e e extrai os dados relevantes
    Usa uma abordagem híbrida combinando ElementTree e regex para máxima compatibilidade
    """
    logger.debug(f"Processando arquivo XML: {file_path}")

    # Criar um objeto básico para a nota fiscal
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
        'xml': '',
        'observacoes': f"Importado via XML em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    }

    # Abordagem 1: Tentar com parser XML nativo
    try:
        tree = None
        xml_content = None

        # Tentar diferentes codificações
        encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                    xml_content = f.read()

                # Tentar construir a árvore XML
                try:
                    # Remover caracteres inválidos que podem atrapalhar o parsing
                    xml_content = ''.join(char for char in xml_content if ord(
                        char) < 128 or ord(char) > 159)

                except Exception as e:
                    logger.warning(
                        f"Erro no parsing XML com codificação {encoding}: {str(e)}")
                    continue

            except Exception as e:
                logger.warning(
                    f"Falha ao ler arquivo com codificação {encoding}: {str(e)}")
                continue

        # Salvar o conteúdo XML no objeto de retorno
        nfe_data['xml'] = xml_content

        # Tentar extrair dados com ElementTree se o parsing for bem-sucedido
        if tree is not None:
            # Registrar namespaces comuns em NFe
            namespaces = {
                'nfe': 'http://www.portalfiscal.inf.br/nfe',
                '': 'http://www.portalfiscal.inf.br/nfe'
            }

            # Função auxiliar para buscar elemento com suporte a namespace
            def find_element(root, path):
                # Tentar busca direta
                element = root.find(path)
                if element is not None:
                    return element

                # Tentar com namespace
                for prefix, uri in namespaces.items():
                    ns_path = path
                    if prefix:
                        ns_path = path.replace('/', f'/{prefix}:')
                        ns_path = f'.//{prefix}:{path.lstrip("./")}'

                    element = root.find(ns_path, namespaces=namespaces)
                    if element is not None:
                        return element

                # Busca mais flexível usando //
                return root.find(f'.//{path.split("/")[-1]}')

            # Extrair chave de acesso
            ide = find_element(tree, './/infNFe')
            if ide is not None and 'Id' in ide.attrib:
                id_value = ide.attrib['Id']
                if id_value.startswith('NFe'):
                    # Remover 'NFe' do início
                    nfe_data['access_key'] = id_value[3:]

            # Extrair número da NF
            num_nf = find_element(tree, './/nNF')
            if num_nf is not None and num_nf.text:
                nfe_data['number'] = num_nf.text.strip()

            # Extrair data de emissão
            dh_emi = find_element(tree, './/dhEmi')
            if dh_emi is None:
                dh_emi = find_element(tree, './/dEmi')

            if dh_emi is not None and dh_emi.text:
                date_str = dh_emi.text.strip()
                try:
                    if 'T' in date_str:
                        # Formato com timezone: 2023-01-01T14:30:00-03:00
                        clean_date = date_str.replace('T', ' ')
                        if '-03:00' in clean_date:
                            clean_date = clean_date.split('-03:00')[0]
                        nfe_data['emission_date'] = datetime.fromisoformat(
                            clean_date)
                    else:
                        # Formato antigo: AAAA-MM-DD
                        nfe_data['emission_date'] = datetime.strptime(
                            date_str, '%Y-%m-%d')
                except Exception as e:
                    logger.warning(f"Erro ao converter data de emissão: {e}")
                    nfe_data['emission_date'] = datetime.now()
            else:
                nfe_data['emission_date'] = datetime.now()

            # Extrair valor total
            v_nf = find_element(tree, './/vNF')
            if v_nf is not None and v_nf.text:
                try:
                    nfe_data['value'] = float(v_nf.text.replace(',', '.'))
                except Exception as e:
                    logger.warning(f"Erro ao converter valor total: {e}")

            # Extrair informações do emitente
            emit = find_element(tree, './/emit')
            if emit is not None:
                cnpj_emit = find_element(emit, 'CNPJ')
                if cnpj_emit is not None and cnpj_emit.text:
                    nfe_data['cnpj_sender'] = cnpj_emit.text.strip()

                nome_emit = find_element(emit, 'xNome')
                if nome_emit is not None and nome_emit.text:
                    nfe_data['sender_name'] = nome_emit.text.strip()

            # Extrair informações do destinatário
            dest = find_element(tree, './/dest')
            if dest is not None:
                cnpj_dest = find_element(dest, 'CNPJ')
                if cnpj_dest is not None and cnpj_dest.text:
                    nfe_data['cnpj_receiver'] = cnpj_dest.text.strip()
                else:
                    # Tentar CPF se não encontrou CNPJ
                    cpf_dest = find_element(dest, 'CPF')
                    if cpf_dest is not None and cpf_dest.text:
                        nfe_data['cnpj_receiver'] = cpf_dest.text.strip()

                nome_dest = find_element(dest, 'xNome')
                if nome_dest is not None and nome_dest.text:
                    nfe_data['receiver_name'] = nome_dest.text.strip()

            # Extrair itens
            itens = []
            det_nodes = tree.findall('.//det')

            if not det_nodes:
                # Tentar busca alternativa para itens
                det_nodes = []
                for item in tree.findall('.//*'):
                    if item.tag.endswith('det'):
                        det_nodes.append(item)

            for i, det in enumerate(det_nodes, 1):
                item = {}

                # Buscar elemento prod dentro de det
                prod = find_element(det, 'prod')
                if prod is not None:
                    # Código do produto
                    c_prod = find_element(prod, 'cProd')
                    if c_prod is not None and c_prod.text:
                        item['code'] = c_prod.text.strip()
                    else:
                        item['code'] = f"ITEM{i}"

                    # Descrição do produto
                    x_prod = find_element(prod, 'xProd')
                    if x_prod is not None and x_prod.text:
                        item['description'] = x_prod.text.strip()
                    else:
                        item['description'] = f"Item {i}"

                    # Quantidade
                    q_com = find_element(prod, 'qCom')
                    if q_com is not None and q_com.text:
                        try:
                            item['quantity'] = float(
                                q_com.text.replace(',', '.'))
                        except:
                            item['quantity'] = 1
                    else:
                        item['quantity'] = 1

                    # Valor unitário
                    v_un_com = find_element(prod, 'vUnCom')
                    if v_un_com is not None and v_un_com.text:
                        try:
                            item['unit_value'] = float(
                                v_un_com.text.replace(',', '.'))
                        except:
                            item['unit_value'] = 0
                    else:
                        item['unit_value'] = 0

                    # Valor total do item
                    v_prod = find_element(prod, 'vProd')
                    if v_prod is not None and v_prod.text:
                        try:
                            item['total_value'] = float(
                                v_prod.text.replace(',', '.'))
                        except:
                            # Calcular valor total se não conseguir extrair
                            item['total_value'] = item['quantity'] * \
                                item['unit_value']
                    else:
                        # Calcular valor total se não conseguir extrair
                        item['total_value'] = item['quantity'] * \
                            item['unit_value']

                    # Adicionar item à lista
                    itens.append(item)
                else:
                    # Tentar extrair informações diretamente do det
                    item = {
                        'code': f"ITEM{i}",
                        'description': f"Item {i}",
                        'quantity': 1,
                        'unit_value': 0,
                        'total_value': 0
                    }

                    # Tentar extrair campos diretamente
                    for field in ['cProd', 'xProd', 'qCom', 'vUnCom', 'vProd']:
                        elem = find_element(det, f'.//{field}')
                        if elem is not None and elem.text:
                            if field == 'cProd':
                                item['code'] = elem.text.strip()
                            elif field == 'xProd':
                                item['description'] = elem.text.strip()
                            elif field == 'qCom':
                                try:
                                    item['quantity'] = float(
                                        elem.text.replace(',', '.'))
                                except:
                                    pass
                            elif field == 'vUnCom':
                                try:
                                    item['unit_value'] = float(
                                        elem.text.replace(',', '.'))
                                except:
                                    pass
                            elif field == 'vProd':
                                try:
                                    item['total_value'] = float(
                                        elem.text.replace(',', '.'))
                                except:
                                    # Calcular valor total
                                    item['total_value'] = item['quantity'] * \
                                        item['unit_value']

                    # Adicionar item à lista
                    itens.append(item)

            # Adicionar itens ao dicionário de retorno
            nfe_data['items'] = itens

        # Verificar se conseguimos extrair pelo menos a chave de acesso
        # Caso contrário, recorrer ao método de regex
        if nfe_data['access_key'] is None and xml_content:
            logger.info(
                "Chave de acesso não encontrada com ElementTree, tentando com regex")

            # Extrair chave de acesso com regex
            import re
            chave_patterns = [
                r'Id="NFe([0-9]{44})"',
                r'chNFe>([0-9]{44})<',
                r'<chNFe>([0-9]{44})</chNFe>',
                r'chave="([0-9]{44})"',
                r'Chave de acesso: ([0-9]{44})',
                r'chave>([0-9]{44})<',
                r'chnfe>([0-9]{44})<'
            ]

            for pattern in chave_patterns:
                chave_match = re.search(pattern, xml_content, re.IGNORECASE)
                if chave_match:
                    nfe_data['access_key'] = chave_match.group(1)
                    logger.info(
                        f"Chave de acesso encontrada com regex: {nfe_data['access_key']}")
                    break

            if nfe_data['access_key'] is None:
                logger.error(
                    f"Não foi possível extrair a chave de acesso do arquivo {file_path}")
                return None

            # Se não temos número da NF, tentar com regex
            if not nfe_data['number']:
                num_patterns = [
                    r'<nNF>(\d+)</nNF>',
                    r'nNF>(\d+)<',
                    r'Número: (\d+)',
                    r'numero>(\d+)<',
                    r'num>(\d+)<'
                ]

                for pattern in num_patterns:
                    num_match = re.search(pattern, xml_content, re.IGNORECASE)
                    if num_match:
                        nfe_data['number'] = num_match.group(1)
                        break

            # Se não temos data de emissão, tentar com regex
            if not nfe_data['emission_date']:
                date_patterns = [
                    r'<dhEmi>(.*?)</dhEmi>',
                    r'<dEmi>(.*?)</dEmi>',
                    r'dhEmi>(.*?)<',
                    r'dEmi>(.*?)<',
                    r'Data de emissão: (\d{2}/\d{2}/\d{4})',
                    r'data>(\d{2}/\d{2}/\d{4})<'
                ]

                for pattern in date_patterns:
                    date_match = re.search(pattern, xml_content, re.IGNORECASE)
                    if date_match:
                        date_str = date_match.group(1)
                        try:
                            if 'T' in date_str:
                                # Formato com timezone: 2023-01-01T14:30:00-03:00
                                clean_date = date_str.replace('T', ' ')
                                if '-03:00' in clean_date:
                                    clean_date = clean_date.split('-03:00')[0]
                                nfe_data['emission_date'] = datetime.fromisoformat(
                                    clean_date)
                            elif '/' in date_str:
                                # Formato DD/MM/YYYY
                                nfe_data['emission_date'] = datetime.strptime(
                                    date_str, '%d/%m/%Y')
                            else:
                                # Formato antigo: AAAA-MM-DD
                                nfe_data['emission_date'] = datetime.strptime(
                                    date_str, '%Y-%m-%d')
                            break
                        except Exception as e:
                            logger.warning(
                                f"Regex: Erro ao converter data de emissão: {e}")
                            continue

            # Se ainda não temos data de emissão, usar data atual
            if not nfe_data['emission_date']:
                nfe_data['emission_date'] = datetime.now()
                logger.warning(
                    f"Data de emissão não encontrada, usando data atual")

            # Se não temos valor total, tentar com regex
            if nfe_data['value'] == 0:
                value_patterns = [
                    r'<vNF>(.*?)</vNF>',
                    r'vNF>(.*?)<',
                    r'Valor Total: ([\d.,]+)',
                    r'total>([\d.,]+)<'
                ]

                for pattern in value_patterns:
                    value_match = re.search(
                        pattern, xml_content, re.IGNORECASE)
                    if value_match:
                        try:
                            nfe_data['value'] = float(value_match.group(
                                1).replace('.', '').replace(',', '.'))
                            break
                        except:
                            continue

            # Se não temos dados do emitente, tentar com regex
            if not nfe_data['cnpj_sender'] or not nfe_data['sender_name']:
                # CNPJ do emitente
                cnpj_patterns = [
                    r'<emit>.*?<CNPJ>(.*?)</CNPJ>',
                    r'emit>.*?CNPJ>(.*?)<',
                    r'Emitente:.*?CNPJ: (\d{14})',
                    r'emit.*?cnpj>(\d{14})<'
                ]

                for pattern in cnpj_patterns:
                    cnpj_match = re.search(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE)
                    if cnpj_match:
                        nfe_data['cnpj_sender'] = cnpj_match.group(1)
                        break

                # Nome do emitente
                name_patterns = [
                    r'<emit>.*?<xNome>(.*?)</xNome>',
                    r'emit>.*?xNome>(.*?)<',
                    r'Emitente:.*?Nome: (.*?)[<\n]',
                    r'emit.*?nome>(.*?)<'
                ]

                for pattern in name_patterns:
                    name_match = re.search(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE)
                    if name_match:
                        nfe_data['sender_name'] = name_match.group(1)
                        break

            # Se não temos dados do destinatário, tentar com regex
            if not nfe_data['cnpj_receiver'] or not nfe_data['receiver_name']:
                # CNPJ do destinatário
                cnpj_patterns = [
                    r'<dest>.*?<CNPJ>(.*?)</CNPJ>',
                    r'dest>.*?CNPJ>(.*?)<',
                    r'Destinatário:.*?CNPJ: (\d{14})',
                    r'dest.*?cnpj>(\d{14})<'
                ]

                for pattern in cnpj_patterns:
                    cnpj_match = re.search(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE)
                    if cnpj_match:
                        nfe_data['cnpj_receiver'] = cnpj_match.group(1)
                        break

                if not nfe_data['cnpj_receiver']:
                    # Tentar CPF se não encontrou CNPJ
                    cpf_patterns = [
                        r'<dest>.*?<CPF>(.*?)</CPF>',
                        r'dest>.*?CPF>(.*?)<',
                        r'Destinatário:.*?CPF: (\d{11})',
                        r'dest.*?cpf>(\d{11})<'
                    ]

                    for pattern in cpf_patterns:
                        cpf_match = re.search(
                            pattern, xml_content, re.DOTALL | re.IGNORECASE)
                        if cpf_match:
                            nfe_data['cnpj_receiver'] = cpf_match.group(1)
                            break

                # Nome do destinatário
                name_patterns = [
                    r'<dest>.*?<xNome>(.*?)</xNome>',
                    r'dest>.*?xNome>(.*?)<',
                    r'Destinatário:.*?Nome: (.*?)[<\n]',
                    r'dest.*?nome>(.*?)<'
                ]

                for pattern in name_patterns:
                    name_match = re.search(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE)
                    if name_match:
                        nfe_data['receiver_name'] = name_match.group(1)
                        break

            # Se não temos itens, tentar extrair com regex
            if not nfe_data['items']:
                logger.info("Tentando extrair itens com regex")
                itens = []

                # Vários padrões para encontrar blocos de produtos
                det_patterns = [
                    r'<det[^>]*>.*?<prod>(.*?)</prod>.*?</det>',
                    r'det .*?prod>(.*?)</prod',
                    r'<item>.*?</item>',
                    r'<produto>.*?</produto>'
                ]

                for pattern in det_patterns:
                    det_matches = list(re.finditer(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE))
                    if det_matches:
                        for i, det_match in enumerate(det_matches, 1):
                            prod_content = det_match.group(1)
                            item = {}

                            # Código do produto
                            code_match = re.search(
                                r'<cProd>(.*?)</cProd>|cProd>(.*?)<', prod_content, re.IGNORECASE)
                            if code_match:
                                item['code'] = code_match.group(
                                    1) if code_match.group(1) else code_match.group(2)
                            else:
                                item['code'] = f"ITEM{i}"

                            # Descrição do produto
                            desc_match = re.search(
                                r'<xProd>(.*?)</xProd>|xProd>(.*?)<', prod_content, re.IGNORECASE)
                            if desc_match:
                                item['description'] = desc_match.group(
                                    1) if desc_match.group(1) else desc_match.group(2)
                            else:
                                item['description'] = f"Item {i}"

                            # Quantidade
                            qty_match = re.search(
                                r'<qCom>(.*?)</qCom>|qCom>(.*?)<', prod_content, re.IGNORECASE)
                            if qty_match:
                                try:
                                    value = qty_match.group(1) if qty_match.group(
                                        1) else qty_match.group(2)
                                    item['quantity'] = float(
                                        value.replace(',', '.'))
                                except:
                                    item['quantity'] = 1
                            else:
                                item['quantity'] = 1

                            # Valor unitário
                            val_match = re.search(
                                r'<vUnCom>(.*?)</vUnCom>|vUnCom>(.*?)<', prod_content, re.IGNORECASE)
                            if val_match:
                                try:
                                    value = val_match.group(1) if val_match.group(
                                        1) else val_match.group(2)
                                    item['unit_value'] = float(
                                        value.replace(',', '.'))
                                except:
                                    item['unit_value'] = 0
                            else:
                                item['unit_value'] = 0

                            # Valor total do item
                            total_match = re.search(
                                r'<vProd>(.*?)</vProd>|vProd>(.*?)<', prod_content, re.IGNORECASE)
                            if total_match:
                                try:
                                    value = total_match.group(1) if total_match.group(
                                        1) else total_match.group(2)
                                    item['total_value'] = float(
                                        value.replace(',', '.'))
                                except:
                                    # Calcular valor total
                                    item['total_value'] = item['quantity'] * \
                                        item['unit_value']
                            else:
                                # Calcular valor total
                                item['total_value'] = item['quantity'] * \
                                    item['unit_value']

                            # Adicionar item à lista
                            itens.append(item)

                        # Se encontrou itens, sair do loop
                        if itens:
                            break

                # Adicionar itens ao dicionário de retorno
                nfe_data['items'] = itens

        # Verificar se conseguimos extrair pelo menos a chave de acesso
        # Caso contrário, recorrer ao método de regex
        if nfe_data['access_key'] is None and xml_content:
            logger.info(
                "Chave de acesso não encontrada com ElementTree, tentando com regex")

            # Extrair chave de acesso com regex
            import re
            chave_patterns = [
                r'Id="NFe([0-9]{44})"',
                r'chNFe>([0-9]{44})<',
                r'<chNFe>([0-9]{44})</chNFe>',
                r'chave="([0-9]{44})"',
                r'Chave de acesso: ([0-9]{44})',
                r'chave>([0-9]{44})<',
                r'chnfe>([0-9]{44})<'
            ]

            for pattern in chave_patterns:
                chave_match = re.search(pattern, xml_content, re.IGNORECASE)
                if chave_match:
                    nfe_data['access_key'] = chave_match.group(1)
                    logger.info(
                        f"Chave de acesso encontrada com regex: {nfe_data['access_key']}")
                    break

            if nfe_data['access_key'] is None:
                logger.error(
                    f"Não foi possível extrair a chave de acesso do arquivo {file_path}")
                return None

            # Se não temos número da NF, tentar com regex
            if not nfe_data['number']:
                num_patterns = [
                    r'<nNF>(\d+)</nNF>',
                    r'nNF>(\d+)<',
                    r'Número: (\d+)',
                    r'numero>(\d+)<',
                    r'num>(\d+)<'
                ]

                for pattern in num_patterns:
                    num_match = re.search(pattern, xml_content, re.IGNORECASE)
                    if num_match:
                        nfe_data['number'] = num_match.group(1)
                        break

            # Se não temos data de emissão, tentar com regex
            if not nfe_data['emission_date']:
                date_patterns = [
                    r'<dhEmi>(.*?)</dhEmi>',
                    r'<dEmi>(.*?)</dEmi>',
                    r'dhEmi>(.*?)<',
                    r'dEmi>(.*?)<',
                    r'Data de emissão: (\d{2}/\d{2}/\d{4})',
                    r'data>(\d{2}/\d{2}/\d{4})<'
                ]

                for pattern in date_patterns:
                    date_match = re.search(pattern, xml_content, re.IGNORECASE)
                    if date_match:
                        date_str = date_match.group(1)
                        try:
                            if 'T' in date_str:
                                # Formato com timezone: 2023-01-01T14:30:00-03:00
                                clean_date = date_str.replace('T', ' ')
                                if '-03:00' in clean_date:
                                    clean_date = clean_date.split('-03:00')[0]
                                nfe_data['emission_date'] = datetime.fromisoformat(
                                    clean_date)
                            elif '/' in date_str:
                                # Formato DD/MM/YYYY
                                nfe_data['emission_date'] = datetime.strptime(
                                    date_str, '%d/%m/%Y')
                            else:
                                # Formato antigo: AAAA-MM-DD
                                nfe_data['emission_date'] = datetime.strptime(
                                    date_str, '%Y-%m-%d')
                            break
                        except Exception as e:
                            logger.warning(
                                f"Regex: Erro ao converter data de emissão: {e}")
                            continue

            # Se ainda não temos data de emissão, usar data atual
            if not nfe_data['emission_date']:
                nfe_data['emission_date'] = datetime.now()
                logger.warning(
                    f"Data de emissão não encontrada, usando data atual")

            # Se não temos valor total, tentar com regex
            if nfe_data['value'] == 0:
                value_patterns = [
                    r'<vNF>(.*?)</vNF>',
                    r'vNF>(.*?)<',
                    r'Valor Total: ([\d.,]+)',
                    r'total>([\d.,]+)<'
                ]

                for pattern in value_patterns:
                    value_match = re.search(
                        pattern, xml_content, re.IGNORECASE)
                    if value_match:
                        try:
                            nfe_data['value'] = float(value_match.group(
                                1).replace('.', '').replace(',', '.'))
                            break
                        except:
                            continue

            # Se não temos dados do emitente, tentar com regex
            if not nfe_data['cnpj_sender'] or not nfe_data['sender_name']:
                # CNPJ do emitente
                cnpj_patterns = [
                    r'<emit>.*?<CNPJ>(.*?)</CNPJ>',
                    r'emit>.*?CNPJ>(.*?)<',
                    r'Emitente:.*?CNPJ: (\d{14})',
                    r'emit.*?cnpj>(\d{14})<'
                ]

                for pattern in cnpj_patterns:
                    cnpj_match = re.search(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE)
                    if cnpj_match:
                        nfe_data['cnpj_sender'] = cnpj_match.group(1)
                        break

                # Nome do emitente
                name_patterns = [
                    r'<emit>.*?<xNome>(.*?)</xNome>',
                    r'emit>.*?xNome>(.*?)<',
                    r'Emitente:.*?Nome: (.*?)[<\n]',
                    r'emit.*?nome>(.*?)<'
                ]

                for pattern in name_patterns:
                    name_match = re.search(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE)
                    if name_match:
                        nfe_data['sender_name'] = name_match.group(1)
                        break

            # Se não temos dados do destinatário, tentar com regex
            if not nfe_data['cnpj_receiver'] or not nfe_data['receiver_name']:
                # CNPJ do destinatário
                cnpj_patterns = [
                    r'<dest>.*?<CNPJ>(.*?)</CNPJ>',
                    r'dest>.*?CNPJ>(.*?)<',
                    r'Destinatário:.*?CNPJ: (\d{14})',
                    r'dest.*?cnpj>(\d{14})<'
                ]

                for pattern in cnpj_patterns:
                    cnpj_match = re.search(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE)
                    if cnpj_match:
                        nfe_data['cnpj_receiver'] = cnpj_match.group(1)
                        break

                if not nfe_data['cnpj_receiver']:
                    # Tentar CPF se não encontrou CNPJ
                    cpf_patterns = [
                        r'<dest>.*?<CPF>(.*?)</CPF>',
                        r'dest>.*?CPF>(.*?)<',
                        r'Destinatário:.*?CPF: (\d{11})',
                        r'dest.*?cpf>(\d{11})<'
                    ]

                    for pattern in cpf_patterns:
                        cpf_match = re.search(
                            pattern, xml_content, re.DOTALL | re.IGNORECASE)
                        if cpf_match:
                            nfe_data['cnpj_receiver'] = cpf_match.group(1)
                            break

                # Nome do destinatário
                name_patterns = [
                    r'<dest>.*?<xNome>(.*?)</xNome>',
                    r'dest>.*?xNome>(.*?)<',
                    r'Destinatário:.*?Nome: (.*?)[<\n]',
                    r'dest.*?nome>(.*?)<'
                ]

                for pattern in name_patterns:
                    name_match = re.search(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE)
                    if name_match:
                        nfe_data['receiver_name'] = name_match.group(1)
                        break

            # Se não temos itens, tentar extrair com regex
            if not nfe_data['items']:
                logger.info("Tentando extrair itens com regex")
                itens = []

                # Vários padrões para encontrar blocos de produtos
                det_patterns = [
                    r'<det[^>]*>.*?<prod>(.*?)</prod>.*?</det>',
                    r'det .*?prod>(.*?)</prod',
                    r'<item>.*?</item>',
                    r'<produto>.*?</produto>'
                ]

                for pattern in det_patterns:
                    det_matches = list(re.finditer(
                        pattern, xml_content, re.DOTALL | re.IGNORECASE))
                    if det_matches:
                        for i, det_match in enumerate(det_matches, 1):
                            prod_content = det_match.group(1)
                            item = {}

                            # Código do produto
                            code_match = re.search(
                                r'<cProd>(.*?)</cProd>|cProd>(.*?)<', prod_content, re.IGNORECASE)
                            if code_match:
                                item['code'] = code_match.group(
                                    1) if code_match.group(1) else code_match.group(2)
                            else:
                                item['code'] = f"ITEM{i}"

                            # Descrição do produto
                            desc_match = re.search(
                                r'<xProd>(.*?)</xProd>|xProd>(.*?)<', prod_content, re.IGNORECASE)
                            if desc_match:
                                item['description'] = desc_match.group(
                                    1) if desc_match.group(1) else desc_match.group(2)
                            else:
                                item['description'] = f"Item {i}"

                            # Quantidade
                            qty_match = re.search(
                                r'<qCom>(.*?)</qCom>|qCom>(.*?)<', prod_content, re.IGNORECASE)
                            if qty_match:
                                try:
                                    value = qty_match.group(1) if qty_match.group(
                                        1) else qty_match.group(2)
                                    item['quantity'] = float(
                                        value.replace(',', '.'))
                                except:
                                    item['quantity'] = 1
                            else:
                                item['quantity'] = 1

                            # Valor unitário
                            val_match = re.search(
                                r'<vUnCom>(.*?)</vUnCom>|vUnCom>(.*?)<', prod_content, re.IGNORECASE)
                            if val_match:
                                try:
                                    value = val_match.group(1) if val_match.group(
                                        1) else val_match.group(2)
                                    item['unit_value'] = float(
                                        value.replace(',', '.'))
                                except:
                                    item['unit_value'] = 0
                            else:
                                item['unit_value'] = 0

                            # Valor total do item
                            total_match = re.search(
                                r'<vProd>(.*?)</vProd>|vProd>(.*?)<', prod_content, re.IGNORECASE)
                            if total_match:
                                try:
                                    value = total_match.group(1) if total_match.group(
                                        1) else total_match.group(2)
                                    item['total_value'] = float(
                                        value.replace(',', '.'))
                                except:
                                    # Calcular valor total
                                    item['total_value'] = item['quantity'] * \
                                        item['unit_value']
                            else:
                                # Calcular valor total
                                item['total_value'] = item['quantity'] * \
                                    item['unit_value']

                            # Adicionar item à lista
                            itens.append(item)

                        # Se encontrou itens, sair do loop
                        if itens:
                            break

                # Adicionar itens ao dicionário de retorno
                nfe_data['items'] = itens

        # Se não encontrou itens, adicionar item genérico
        if not nfe_data['items'] and nfe_data['access_key']:
            logger.warning(
                f"Nenhum item encontrado, adicionando item genérico para a NFe {nfe_data['access_key']}")
            nfe_data['items'] = [{
                'code': 'GENERICO',
                'description': f"Nota Fiscal {nfe_data['access_key']}",
                'quantity': 1,
                'unit_value': nfe_data['value'],
                'total_value': nfe_data['value']
            }]

    except Exception as e:
        logger.error(
            f"Erro ao processar arquivo XML {file_path}: {str(e)}", exc_info=True)
        # Se temos o conteúdo XML mas houve erro no processamento, tente extrair pelo menos a chave de acesso
        if 'xml_content' in locals() and xml_content:
            import re
            chave_match = re.search(r'Id="NFe([0-9]{44})"', xml_content)
            if chave_match:
                nfe_data['access_key'] = chave_match.group(1)
                logger.info(
                    f"Conseguiu extrair apenas a chave de acesso após erro: {nfe_data['access_key']}")

                # Adicionar um item genérico
                nfe_data['items'] = [{
                    'code': 'ERRO_PROC',
                    'description': f"Erro no processamento: {str(e)}",
                    'quantity': 1,
                    'unit_value': 0,
                    'total_value': 0
                }]

                # Retornar dados parciais
                return nfe_data

        return None

    # Verificação final: se não temos a chave de acesso, não podemos proceder
    if not nfe_data['access_key']:
        logger.error(
            f"Não foi possível extrair a chave de acesso do arquivo {file_path}")
        return None

    # Log do sucesso da operação
    num_itens = len(nfe_data['items'])
    logger.info(
        f"XML processado com sucesso: {nfe_data['access_key']}, {num_itens} itens encontrados")

    return nfe_data


def buscar_nfes_arquivei(dias_atras=30, cnpj=None):
    try:
        # Calcular data inicial (30 dias atrás por padrão)
        data_inicial = (datetime.now() -
                        timedelta(days=dias_atras)).strftime('%Y-%m-%d')

        # Parâmetros da requisição
        params = {
            'start_date': data_inicial,
            'limit': 50  # Limite de NFes a serem retornadas
        }

        # Adicionar CNPJ aos parâmetros se fornecido
        if cnpj:
            cnpj_formatado = ''.join(filter(str.isdigit, cnpj))
            params['cnpj'] = cnpj_formatado

        # Cabeçalhos da requisição
        headers = {
            'Content-Type': 'application/json',
            'X-API-ID': ARQUIVEI_API_ID,
            'X-API-KEY': ARQUIVEI_API_KEY
        }

        # Fazer a requisição
        response = requests.get(ARQUIVEI_API_ENDPOINT,
                                headers=headers, params=params)

        # Verificar se a requisição foi bem-sucedida
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(
                f"Erro ao buscar NFes: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exceção ao buscar NFes: {str(e)}")
        return None


# Função para salvar NFe no banco de dados


def save_nfe_to_db(nfe_data):
    """
    Salva os dados da NFe no banco de dados
    Retorna True se for uma nova NFe, False se for uma atualização
    """
    is_new = True
    connection = get_db_connection()

    if not connection:
        logger.error("Falha ao conectar ao banco de dados")
        return False

    try:
        cursor = connection.cursor(dictionary=True)

        # Verificar se a nota já existe
        cursor.execute("SELECT id FROM nf_notas WHERE chave_acesso = %s",
                       (nfe_data.get('access_key'),))
        nota_existente = cursor.fetchone()

        if nota_existente:
            # Atualizar nota existente
            is_new = False
            nota_id = nota_existente['id']

            cursor.execute("""
                UPDATE nf_notas SET
                data_emissao = %s,
                valor_total = %s,
                cnpj_emitente = %s,
                nome_emitente = %s,
                cnpj_destinatario = %s,
                nome_destinatario = %s,
                status_processamento = 'atualizado',
                data_atualizacao = NOW(),
                observacoes = %s
                WHERE id = %s
            """, (
                nfe_data.get('emission_date'),
                nfe_data.get('value', 0),
                nfe_data.get('cnpj_sender', ''),
                nfe_data.get('sender_name', ''),
                nfe_data.get('cnpj_receiver', ''),
                nfe_data.get('receiver_name', ''),
                nfe_data.get('observacoes', ''),
                nota_id
            ))

            # Remover itens antigos
            cursor.execute("DELETE FROM nf_itens WHERE nf_id = %s", (nota_id,))
        else:
            # Inserir nova nota
            cursor.execute("""
                INSERT INTO nf_notas (
                    chave_acesso, numero_nf, data_emissao, valor_total, cnpj_emitente,
                    nome_emitente, cnpj_destinatario, nome_destinatario, status_processamento, data_importacao, observacoes
                ) VALUES (%s, %s, %s,%s,%s, %s, %s, %s, %s, NOW(), %s)
            """, (
                nfe_data.get('access_key', ''),
                nfe_data.get('number'),
                nfe_data.get('emission_date'),
                nfe_data.get('value', 0),
                nfe_data.get('cnpj_sender', ''),
                nfe_data.get('sender_name', ''),
                nfe_data.get('cnpj_receiver', ''),
                nfe_data.get('receiver_name', ''),
                'importado',
                nfe_data.get('observacoes', '')
            ))

            nota_id = cursor.lastrowid

        # Inserir itens
        for item in nfe_data.get('items', []):
            cursor.execute("""
                INSERT INTO nf_itens (
                    nf_id, codigo, descricao, quantidade,
                    valor_unitario, valor_total
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                nota_id,
                item.get('code', ''),
                item.get('description', ''),
                item.get('quantity', 0),
                item.get('unit_value', 0),
                item.get('total_value', 0)
            ))

        connection.commit()
        logger.info(f"NFe {nfe_data.get('access_key')} salva com sucesso")
        return is_new

    except Exception as e:
        connection.rollback()
        logger.error(f"Erro ao salvar NFe no banco: {str(e)}", exc_info=True)
        return False

    finally:
        cursor.close()
        connection.close()

# Função para processar e salvar NFe no banco de dados (para API Arquivei)


def processar_e_salvar_nfe(nfe_data):
    """
    Processa e salva os dados de NFe recebidos da API Arquivei no banco de dados
    Retorna True se a operação foi bem-sucedida, False caso contrário
    """
    connection = get_db_connection()
    if not connection:
        return False

    try:
        logger.info("Iniciando processamento de NFe da API Arquivei")
        cursor = connection.cursor(dictionary=True)

        # Verificar se os dados contêm XML em Base64
        xml_base64 = identificar_xml_base64(nfe_data)

        # Se identificamos um possível XML em Base64, tentar decodificar e processar
        if xml_base64:
            logger.info(
                "Detectado possível XML em Base64, tentando decodificar")
            try:
                # Decodificar o XML Base64
                decoded_data = decodificar_base64_xml(xml_base64)

                if decoded_data:
                    # Processar o XML usando a função existente
                    temp_file_path = decoded_data['temp_file_path']
                    processed_nfe = process_xml_file(temp_file_path)

                    # Remover o arquivo temporário
                    os.unlink(temp_file_path)

                    # Se o processamento foi bem-sucedido, usar esses dados
                    if processed_nfe and processed_nfe.get('access_key'):
                        logger.info(
                            f"XML Base64 processado com sucesso: {processed_nfe.get('access_key')}")
                        nfe_data = processed_nfe

                        # Guardar o XML decodificado
                        nfe_data['xml'] = decoded_data['xml_content']
            except Exception as e:
                logger.warning(f"Erro ao processar XML Base64: {str(e)}")

        # Extrair informações relevantes da NFe
        chave_acesso = nfe_data.get('access_key')
        numero_nf = nfe_data.get('number', '')
        data_emissao = nfe_data.get('emission_date')

        # Verificar se data_emissao está presente
        if data_emissao is None:
            # Usar a data atual como fallback
            data_emissao = datetime.now()
            logger.warning(
                f"Data de emissão ausente para NFe {chave_acesso}, usando data atual como fallback")

        valor_total = nfe_data.get('value', 0)
        cnpj_emitente = nfe_data.get('cnpj_sender', '')
        nome_emitente = nfe_data.get('sender_name', '')
        cnpj_destinatario = nfe_data.get('cnpj_receiver', '')
        nome_destinatario = nfe_data.get('receiver_name', '')
        xml_data = nfe_data.get('xml', '')

        # Verificar se a chave de acesso está presente
        if not chave_acesso:
            logger.error("Chave de acesso ausente, impossível importar NFe")
            return False

        # Verificar se a NFe já existe no banco
        cursor.execute(
            "SELECT id FROM nf_notas WHERE chave_acesso = %s", (chave_acesso,))
        resultado = cursor.fetchone()

        if resultado:
            # Atualizar NFe existente
            nfe_id = resultado['id']

            cursor.execute("""
                UPDATE nf_notas SET
                numero_nf = %s,
                data_emissao = %s,
                valor_total = %s,
                cnpj_emitente = %s,
                nome_emitente = %s,
                cnpj_destinatario = %s,
                nome_destinatario = %s,
                status_processamento = 'atualizado',
                data_atualizacao = NOW(),
                observacoes = %s
                WHERE chave_acesso = %s
            """, (
                numero_nf,
                data_emissao,
                valor_total,
                cnpj_emitente,
                nome_emitente,
                cnpj_destinatario,
                nome_destinatario,
                'Atualizado via API Arquivei em ' + datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                chave_acesso
            ))

            # Remover itens antigos
            cursor.execute("DELETE FROM nf_itens WHERE nf_id = %s", (nfe_id,))
        else:
            # Inserir nova NFe
            cursor.execute("""
                INSERT INTO nf_notas (
                    chave_acesso, numero_nf, data_emissao, valor_total, cnpj_emitente,
                    nome_emitente, cnpj_destinatario, nome_destinatario,
                    xml_data, status_processamento, data_importacao, observacoes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
            """, (
                chave_acesso,
                numero_nf,
                data_emissao,
                valor_total,
                cnpj_emitente,
                nome_emitente,
                cnpj_destinatario,
                nome_destinatario,
                xml_data,
                'importado',
                'Importado via API Arquivei em ' + datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            ))

            # Obter o ID da NFe inserida
            nfe_id = cursor.lastrowid

        # Processar itens da NFe
        itens = nfe_data.get('items', [])
        for item in itens:
            codigo = item.get('code', '')
            descricao = item.get('description', '')
            quantidade = item.get('quantity', 0)
            valor_unitario = item.get('unit_value', 0)
            valor_total_item = item.get('total_value', 0)

            cursor.execute("""
                INSERT INTO nf_itens (
                    nf_id, codigo, descricao, quantidade,
                    valor_unitario, valor_total
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (nfe_id, codigo, descricao, quantidade,
                  valor_unitario, valor_total_item))

        connection.commit()
        logger.info(f"NFe {chave_acesso} salva com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro ao processar NFe: {str(e)}", exc_info=True)
        if connection:
            connection.rollback()
        return False
    finally:
        if connection and hasattr(connection, 'is_connected') and connection.is_connected():
            cursor.close()
            connection.close()

# Rota principal - dashboard de importação


@mod_importacao_nf.route('/')
def index():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    # Inicializar estatísticas
    estatisticas = {
        'total_notas': 0,
        'notas_hoje': 0,
        'valor_total': 0,
        'fornecedores': 0
    }

    # Inicializar dados dos gráficos
    labels_dias = []
    dados_dias = []
    dados_status = [0, 0, 0]  # [Sucesso, Erro, Pendente]

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Total de notas importadas
            cursor.execute("SELECT COUNT(*) as total FROM nf_notas")
            result = cursor.fetchone()
            estatisticas['total_notas'] = result['total'] if result else 0

            # Total de notas importadas hoje
            cursor.execute(
                "SELECT COUNT(*) as total FROM nf_notas WHERE DATE(data_importacao) = CURDATE()")
            result = cursor.fetchone()
            estatisticas['notas_hoje'] = result['total'] if result else 0

            # Valor total das notas
            cursor.execute(
                "SELECT COALESCE(SUM(valor_total), 0) as total FROM nf_notas")
            result = cursor.fetchone()
            estatisticas['valor_total'] = float(
                result['total']) if result else 0

            # Total de fornecedores únicos
            cursor.execute(
                "SELECT COUNT(DISTINCT cnpj_emitente) as total FROM nf_notas")
            result = cursor.fetchone()
            estatisticas['fornecedores'] = result['total'] if result else 0

            # Dados para o gráfico de importações por dia
            cursor.execute("""
                SELECT DATE(data_importacao) as data, COUNT(*) as total
                FROM nf_notas
                WHERE data_importacao >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY DATE(data_importacao)
                ORDER BY data
            """)
            for row in cursor.fetchall():
                labels_dias.append(row['data'].strftime('%d/%m'))
                dados_dias.append(row['total'])

            # Dados para o gráfico de status
            cursor.execute("""
                SELECT status_processamento as status, COUNT(*) as total
                FROM nf_notas
                GROUP BY status_processamento
            """)
            for row in cursor.fetchall():
                if row['status'] == 'SUCESSO':
                    dados_status[0] = row['total']
                elif row['status'] == 'ERRO':
                    dados_status[1] = row['total']
                else:
                    dados_status[2] = row['total']

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao buscar estatísticas: {e}")
        finally:
            connection.close()

    return render_template('importacao_nf/index.html',
                           estatisticas=estatisticas,
                           labels_dias=labels_dias,
                           dados_dias=dados_dias,
                           dados_status=dados_status)

# Rota para importar notas fiscais via API


@mod_importacao_nf.route('/importar', methods=['GET', 'POST'])
def importar():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    # Criar uma instância de formulário vazio para obter o token CSRF
    form = FlaskForm()

    if request.method == 'POST':
        dias = int(request.form.get('dias', 30))
        cnpj = request.form.get('cnpj', '')

        # Buscar notas fiscais
        resultado = buscar_nfes_arquivei(
            dias_atras=dias, cnpj=cnpj if cnpj else None)

        if resultado and 'data' in resultado:
            notas = resultado['data']
            total_importadas = 0

            for nfe in notas:
                if processar_e_salvar_nfe(nfe):
                    total_importadas += 1

            flash(
                f'Importação concluída. {total_importadas} nota(s) fiscal(is) importada(s).', 'success')
        else:
            flash(
                'Erro ao importar notas fiscais. Verifique os logs para mais detalhes.', 'danger')

    # Renderizar template para ambos GET e POST
    return render_template('importacao_nf/importar.html', form=form)

# Rota para importar por upload de XML


@mod_importacao_nf.route('/importar_xml', methods=['GET', 'POST'])
def importar_xml():
    if 'usuario_id' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('login'))

    # Criar uma instância de formulário vazio para obter o token CSRF
    form = FlaskForm()

    if request.method == 'POST':
        logger.info("Recebida requisição POST para importar_xml")
        logger.info(f"Headers: {request.headers}")
        logger.info(f"Form data: {request.form}")
        logger.info(f"Files: {list(request.files.keys())}")

        # Verificar se há arquivos enviados
        if 'file' not in request.files and 'files[]' not in request.files:
            logger.warning("Nenhum arquivo encontrado no request.files")
            return jsonify({"error": "Nenhum arquivo selecionado"}), 400

        # Obter arquivos (pode ser um único 'file' ou múltiplos 'files[]')
        if 'file' in request.files:
            files = [request.files['file']]
            logger.info("Usando campo 'file' para upload")
        else:
            files = request.files.getlist('files[]')
            logger.info(
                f"Usando campo 'files[]' para upload, contém {len(files)} arquivos")

        if not files or files[0].filename == '':
            logger.warning(
                "Lista de arquivos vazia ou primeiro arquivo sem nome")
            return jsonify({"error": "Nenhum arquivo válido selecionado"}), 400

        logger.info(f"Recebidos {len(files)} arquivos para processamento")

        # Verificar conteúdo do primeiro arquivo
        if len(files) > 0:
            logger.info(
                f"Primeiro arquivo: {files[0].filename}, tipo: {files[0].content_type}")

        # Contador para estatísticas
        total_processados = 0
        total_novos = 0
        total_atualizados = 0
        total_erros = 0

        # Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Criado diretório temporário: {temp_dir}")

        try:
            # Processar cada arquivo
            for file in files:
                if not file or not file.filename:
                    continue

                logger.info(f"Processando arquivo: {file.filename}")

                # Salvar o arquivo no diretório temporário
                file_path = os.path.join(
                    temp_dir, secure_filename(file.filename))
                file.save(file_path)
                logger.debug(f"Arquivo salvo em: {file_path}")

                # Verificar tipo de arquivo
                if file.filename.lower().endswith('.xml'):
                    # Processar arquivo XML
                    nfe_data = process_xml_file(file_path)
                    if nfe_data:
                        total_processados += 1
                        if save_nfe_to_db(nfe_data):
                            total_novos += 1
                        else:
                            total_atualizados += 1
                elif file.filename.lower().endswith('.zip'):
                    # Processar arquivo ZIP
                    try:
                        logger.info(f"Extraindo arquivo ZIP: {file.filename}")
                        with zipfile.ZipFile(file_path, 'r') as zip_ref:
                            # Listar arquivos no ZIP
                            xml_files = [f for f in zip_ref.namelist(
                            ) if f.lower().endswith('.xml')]
                            logger.info(
                                f"Encontrados {len(xml_files)} arquivos XML no ZIP")

                            # Extrair e processar cada XML
                            for xml_file in xml_files:
                                xml_path = os.path.join(
                                    temp_dir, os.path.basename(xml_file))
                                with zip_ref.open(xml_file) as source, open(xml_path, 'wb') as target:
                                    shutil.copyfileobj(source, target)

                                    logger.debug(
                                        f"Processando XML extraído: {xml_path}")
                                    nfe_data = process_xml_file(xml_path)
                                    if nfe_data:
                                        total_processados += 1
                                        if save_nfe_to_db(nfe_data):
                                            total_novos += 1
                                        else:
                                            total_atualizados += 1
                    except Exception as e:
                        logger.error(
                            f"Erro ao processar ZIP {file.filename}: {str(e)}", exc_info=True)
                        total_erros += 1
                else:
                    logger.warning(
                        f"Tipo de arquivo não suportado: {file.filename}")
                    total_erros += 1

            # Mostrar resultado da importação
            resultado = f'Importação concluída: {total_processados} arquivo(s) processado(s), {total_novos} novo(s), {total_atualizados} atualizado(s), {total_erros} erro(s)'
            logger.info(resultado)

            # Adicionar mensagem flash para exibir na página
            if total_erros > 0:
                flash(resultado, 'warning')
            else:
                flash(resultado, 'success')

            # Redirecionar para a mesma página para mostrar o resultado
            return redirect(url_for('importacao_nf.importar_xml'))

        except Exception as e:
            logger.error(
                f"Erro durante o processamento dos arquivos: {str(e)}", exc_info=True)
            flash(f"Erro durante o processamento: {str(e)}", 'danger')
            return redirect(url_for('importacao_nf.importar_xml'))

        finally:
            # Limpar arquivos temporários
            logger.info(f"Removendo diretório temporário: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)

        return render_template('importacao_nf/importar_xml.html', form=form)

    # Rota para buscar notas fiscais


@mod_importacao_nf.route('/buscar', methods=['GET', 'POST'])
def buscar():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    # Criar uma instância de formulário vazio para obter o token CSRF
    form = FlaskForm()

    resultados = []
    termo_busca = ''
    tipo_busca = 'fornecedor'
    data_inicio = ''
    data_fim = ''

    if request.method == 'POST':
        termo_busca = request.form.get('termo', '')
        tipo_busca = request.form.get('tipo', 'fornecedor')
        data_inicio = request.form.get('data_inicio', '')
        data_fim = request.form.get('data_fim', '')

        # Construir a consulta SQL
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)

                # Base da consulta SQL
                base_query = """
                    SELECT n.*, COUNT(i.id) as total_itens
                    FROM nf_notas n
                    LEFT JOIN nf_itens i ON n.id = i.nf_id
                    WHERE 1=1
                """

                params = []

                # Adicionar filtro por termo de busca
                if termo_busca:
                    if tipo_busca == 'fornecedor':
                        base_query += " AND (n.nome_emitente LIKE %s OR n.cnpj_emitente LIKE %s)"
                        params.extend([f'%{termo_busca}%', f'%{termo_busca}%'])
                    elif tipo_busca == 'destinatario':
                        base_query += " AND (n.nome_destinatario LIKE %s OR n.cnpj_destinatario LIKE %s)"
                        params.extend([f'%{termo_busca}%', f'%{termo_busca}%'])
                    elif tipo_busca == 'descricao':
                        base_query += " AND n.id IN (SELECT nf_id FROM nf_itens WHERE descricao LIKE %s)"
                        params.append(f'%{termo_busca}%')
                    else:  # chave
                        base_query += " AND n.chave_acesso LIKE %s"
                        params.append(f'%{termo_busca}%')

                # Adicionar filtro por data de emissão
                if data_inicio:
                    base_query += " AND n.data_emissao >= %s"
                    params.append(data_inicio)

                if data_fim:
                    base_query += " AND n.data_emissao <= %s"
                    params.append(data_fim)

                # Finalizar a consulta
                base_query += " GROUP BY n.id ORDER BY n.data_emissao DESC"

                # Executar a consulta
                cursor.execute(base_query, params)
                resultados = cursor.fetchall()

                # Converter datas para formato mais amigável
                for nota in resultados:
                    if 'data_emissao' in nota and nota['data_emissao']:
                        nota['data_emissao_formatada'] = nota['data_emissao'].strftime(
                            '%d/%m/%Y')

                cursor.close()
            except Exception as e:
                logger.error(f"Erro ao buscar notas fiscais: {e}")
                flash(f'Erro ao buscar notas fiscais: {str(e)}', 'danger')
            finally:
                connection.close()

    # Renderizar template para ambos GET e POST
    return render_template('importacao_nf/buscar.html',
                           resultados=resultados,
                           termo_busca=termo_busca,
                           tipo_busca=tipo_busca,
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           form=form)

    # Rota para visualizar detalhes da nota fiscal


@mod_importacao_nf.route('/visualizar/<int:nf_id>')
def visualizar(nf_id):
    if 'usuario_id' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('login'))

    connection = get_db_connection()
    nota = None
    itens = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar dados da nota fiscal
            cursor.execute("SELECT * FROM nf_notas WHERE id = %s", (nf_id,))
            nota = cursor.fetchone()

            if nota:
                # Buscar itens da nota fiscal
                cursor.execute(
                    "SELECT * FROM nf_itens WHERE nf_id = %s", (nf_id,))
                itens = cursor.fetchall()

            cursor.close()
        except Error as e:
            logger.error(f"Erro ao buscar detalhes da nota fiscal: {e}")
            flash(
                f'Erro ao buscar detalhes da nota fiscal: {str(e)}', 'danger')
        finally:
            connection.close()

    if not nota:
        flash('Nota fiscal não encontrada', 'warning')
        return redirect(url_for('importacao_nf.buscar'))

    return render_template('importacao_nf/visualizar.html', nota=nota, itens=itens)

    # Rota para criar uma solicitação a partir de uma nota fiscal


@mod_importacao_nf.route('/solicitar/<int:nf_id>', methods=['GET', 'POST'])
def solicitar(nf_id):
    if 'usuario_id' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('login'))

    # Criar uma instância de formulário vazio para obter o token CSRF
    form = FlaskForm()

    connection = get_db_connection()
    nota = None
    itens = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar dados da nota fiscal
            cursor.execute("SELECT * FROM nf_notas WHERE id = %s", (nf_id,))
            nota = cursor.fetchone()

            if nota:
                # Buscar itens da nota fiscal
                cursor.execute(
                    "SELECT * FROM nf_itens WHERE nf_id = %s", (nf_id,))
                itens = cursor.fetchall()

                # Se for uma requisição POST, criar a solicitação
                if request.method == 'POST' and nota and itens:
                    justificativa = request.form.get('justificativa', '')
                    centro_custo_id = request.form.get('centro_custo_id', '')
                    itens_selecionados = request.form.getlist('item_id')

                    if justificativa and centro_custo_id and itens_selecionados:
                        # Adicione aqui o restante do código para processar a solicitação
                        pass

                cursor.close()
        except Exception as e:
            logger.error(f"Erro ao processar solicitação: {e}")
            flash(f'Erro ao processar solicitação: {str(e)}', 'danger')
            if connection.is_connected():
                connection.rollback()
        finally:
            if connection.is_connected():
                connection.close()

        if not nota:
            flash('Nota fiscal não encontrada', 'warning')
            return redirect(url_for('importacao_nf.buscar'))

        # Buscar centros de custo para o formulário
        centros_custo = []

        return render_template('importacao_nf/solicitar.html',
                               nota=nota,
                               itens=itens,
                               form=form,
                               centros_custo=centros_custo)

        # Rotas para API interna


@mod_importacao_nf.route('/api/notas_recentes')
def api_notas_recentes():
    if 'usuario_id' not in session:
        return jsonify({'error': 'Não autorizado', 'data': []}), 401

    # Obter parâmetros de filtro de data
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Erro de conexão com o banco de dados', 'data': []}), 500

    try:
        cursor = connection.cursor(dictionary=True)

        # Construir a consulta SQL com filtros de data
        query = """
            SELECT n.id, n.chave_acesso, n.numero_nf, n.data_emissao, n.valor_total,
            n.nome_emitente, n.nome_destinatario, n.status_processamento,
            n.observacoes,
            COUNT(i.id) as total_itens
            FROM nf_notas n
            LEFT JOIN nf_itens i ON n.id = i.nf_id
            WHERE 1=1
        """

        params = []

        # Adicionar filtros de data, se fornecidos
        if data_inicio:
            query += " AND DATE(n.data_emissao) >= %s"
            params.append(data_inicio)

        if data_fim:
            query += " AND DATE(n.data_emissao) <= %s"
            params.append(data_fim)

        # Finalizar a consulta
        query += """
            GROUP BY n.id
            ORDER BY n.data_emissao DESC
            LIMIT 100
        """

        # Executar a consulta
        cursor.execute(query, params)
        notas = cursor.fetchall()

        # Converter objetos datetime para string para permitir serialização em JSON
        for nota in notas:
            if 'data_emissao' in nota and nota['data_emissao'] is not None:
                nota['data_emissao'] = nota['data_emissao'].strftime(
                    '%Y-%m-%d %H:%M:%S')

            # Converter valores Decimal para float
            if 'valor_total' in nota and hasattr(nota['valor_total'], 'as_integer_ratio'):
                # Converter valores Decimal para float
                if 'valor_total' in nota and hasattr(nota['valor_total'], 'as_integer_ratio'):
                    nota['valor_total'] = float(nota['valor_total'])

                    if 'total_itens' in nota and hasattr(nota['total_itens'], 'as_integer_ratio'):
                        nota['total_itens'] = float(nota['total_itens'])

                    cursor.close()
                    connection.close()

                    return jsonify({'data': notas})
    except Exception as e:
        logger.error(f"Erro ao buscar notas recentes: {e}")
        if connection:
            connection.close()
        return jsonify({'error': str(e), 'data': []}), 500


@mod_importacao_nf.route('/relatorios')
def relatorios():
    if 'usuario_id' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('login'))

    return render_template('importacao_nf/relatorios.html')

    # Rota para API de dados para relatórios


@mod_importacao_nf.route('/api/dados_relatorio')
def api_dados_relatorio():
    if 'usuario_id' not in session:
        return jsonify({'error': 'Não autorizado'}), 401

    tipo = request.args.get('tipo', 'mensal')

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Erro de conexão com o banco de dados'}), 500

    try:
        cursor = connection.cursor(dictionary=True)

        if tipo == 'mensal':
            # Dados mensais
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(data_emissao, '%Y-%m') as periodo,
                    COUNT(*) as total_notas,
                    SUM(valor_total) as valor_total
                FROM nf_notas
                WHERE data_emissao >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                GROUP BY DATE_FORMAT(data_emissao, '%Y-%m')
                ORDER BY periodo
            """)
        elif tipo == 'fornecedor':
            # Dados por fornecedor
            cursor.execute("""
                SELECT 
                    nome_emitente as rotulo,
                    COUNT(*) as total_notas,
                    SUM(valor_total) as valor_total
                FROM nf_notas
                GROUP BY nome_emitente
                ORDER BY valor_total DESC
                LIMIT 10
            """)
        else:
            # Dados por status
            cursor.execute("""
                SELECT 
                    status_processamento as rotulo,
                    COUNT(*) as total_notas,
                    SUM(valor_total) as valor_total
                FROM nf_notas
                GROUP BY status_processamento
            """)

        dados = cursor.fetchall()
        cursor.close()

        return jsonify({'data': dados})
    except Error as e:
        logger.error(f"Erro ao buscar dados do relatório: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        connection.close()
