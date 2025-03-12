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

# Configurar logger
log_dir = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'importacao_xml.log')

logger = logging.getLogger('importacao_xml')
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Adicionar console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

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
        success = False

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                    xml_content = f.read()

                # Verificar se parece um XML válido
                if not xml_content or not ('<' in xml_content and '>' in xml_content):
                    logger.warning(
                        f"Arquivo não parece ser um XML válido com codificação {encoding}")
                    continue

                # Tentar construir a árvore XML
                try:
                    # Remover caracteres inválidos que podem atrapalhar o parsing
                    xml_content = ''.join(char for char in xml_content if ord(
                        char) < 128 or ord(char) > 159)

                    # Tentar parse com ElementTree
                    tree = ET.fromstring(xml_content)
                    success = True
                    logger.info(
                        f"XML parseado com sucesso usando codificação {encoding}")
                    break

                except Exception as e:
                    logger.warning(
                        f"Erro no parsing XML com codificação {encoding}: {str(e)}")
                    continue

            except Exception as e:
                logger.warning(
                    f"Falha ao ler arquivo com codificação {encoding}: {str(e)}")
                continue

        # Se não conseguiu ler o arquivo com nenhuma codificação
        if not xml_content:
            logger.error(f"Não foi possível ler o arquivo XML: {file_path}")
            return None

        # Salvar o conteúdo XML no objeto de retorno
        nfe_data['xml'] = xml_content

        # Verificar se conseguimos fazer o parse do XML
        if not success:
            logger.warning(
                "Não foi possível fazer o parse do XML com ElementTree, tentando com abordagem alternativa")
            # Criar uma árvore com um parser mais permissivo
            try:
                import lxml.etree as LET
                tree = LET.fromstring(xml_content.encode('utf-8'))
                success = True
                logger.info("XML parseado com sucesso usando lxml")
            except ImportError:
                logger.warning(
                    "lxml não está instalado, pulando esta tentativa")
            except Exception as e:
                logger.warning(f"Erro ao usar lxml para parsing: {str(e)}")

        # Se conseguimos um parser válido, tentar extrair os dados
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
                    item['total_value'] = item['quantity']*item['unit_value']

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

        # Se não conseguimos extrair a chave de acesso, tentar com regex de forma mais agressiva
        if nfe_data['access_key'] is None and xml_content:
            logger.info(
                "Chave de acesso não encontrada com ElementTree, tentando com regex")

            # Extrair chave de acesso com regex - padrões ampliados
            import re
            chave_patterns = [
                r'Id="NFe([0-9]{44})"',
                r'Id=["\']NFe([0-9]{44})["\']',
                r'chNFe>([0-9]{44})<',
                r'<chNFe>([0-9]{44})</chNFe>',
                r'chave="([0-9]{44})"',
                r'chave=["\']([0-9]{44})["\']',
                r'Chave de acesso: ([0-9]{44})',
                r'chave>([0-9]{44})<',
                r'chnfe>([0-9]{44})<',
                r'chave.{0,20}([0-9]{44})',
                r'<infNFe.*?Id="NFe([0-9]{44})"',
                r'<NFe.*?Id="NFe([0-9]{44})"',
                r'["\']NFe([0-9]{44})["\']',
                # Último recurso: qualquer sequência de 44 dígitos
                r'([0-9]{44})'
            ]

            for pattern in chave_patterns:
                chave_match = re.search(pattern, xml_content, re.IGNORECASE)
                if chave_match:
                    chave_candidata = chave_match.group(1)
                    # Verificar se é realmente uma chave de acesso (44 dígitos)
                    if len(chave_candidata) == 44 and chave_candidata.isdigit():
                        nfe_data['access_key'] = chave_candidata
                        logger.info(
                            f"Chave de acesso encontrada com regex: {nfe_data['access_key']}")
                        break

            # Se ainda não encontrou, buscar 44 dígitos em sequência como último recurso
            if nfe_data['access_key'] is None:
                all_numbers = re.findall(r'\d+', xml_content)
                for num in all_numbers:
                    if len(num) == 44:
                        nfe_data['access_key'] = num
                        logger.info(
                            f"Chave de acesso encontrada como sequência de 44 dígitos: {num}")
                        break

            if nfe_data['access_key'] is None:
                # Temos um problema sério, depurar o conteúdo XML
                debug_xml_content(xml_content, file_path)
                logger.error(
                    f"Não foi possível extrair a chave de acesso do arquivo {file_path}")
                return None

        # Se não temos número da NF, tentar com regex
        if not nfe_data['number']:
            import re
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
            import re
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
            import re
            value_patterns = [
                r'<vNF>(.*?)</vNF>',
                r'vNF>(.*?)<',
                r'Valor Total: ([\d.,]+)',
                r'total>([\d.,]+)<'
            ]

            for pattern in value_patterns:
                value_match = re.search(pattern, xml_content, re.IGNORECASE)
                if value_match:
                    try:
                        nfe_data['value'] = float(value_match.group(
                            1).replace('.', '').replace(',', '.'))
                        break
                    except:
                        continue

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

        # Tentar salvar informações de debug
        if 'xml_content' in locals() and xml_content:
            debug_xml_content(xml_content, file_path)

            # Último recurso: tentar extrair pelo menos a chave de acesso
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


def debug_xml_content(xml_content, file_path, salvar_debug=True):
    """Função para depurar conteúdo XML problemático"""
    logger.error(f"Conteúdo XML inválido ou não reconhecido em {file_path}")

    # Verificar tamanho do conteúdo
    content_size = len(xml_content) if xml_content else 0
    logger.error(f"Tamanho do conteúdo XML: {content_size} bytes")

    # Exibir primeiros 200 caracteres para depuração
    if xml_content and len(xml_content) > 0:
        logger.error(f"Primeiros 200 caracteres: {xml_content[:200]}")
    else:
        logger.error("Conteúdo XML está vazio")

    # Salvar conteúdo para análise posterior
    if salvar_debug and xml_content:
        debug_file = os.path.join(os.path.dirname(file_path), 'debug_xml.txt')
        try:
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(f"XML original de {file_path}:\n\n")
                f.write(xml_content)
            logger.info(f"Conteúdo XML salvo para debug em {debug_file}")
        except Exception as e:
            logger.error(f"Não foi possível salvar arquivo de debug: {str(e)}")

    return False


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
    connection = get_db_connection()
    if not connection:
        logger.error("Não foi possível conectar ao banco de dados")
        return 'erro'

    try:
        logger.info("Iniciando processamento de NFe")
        cursor = connection.cursor(dictionary=True)

        # 1. Tratamento inicial dos dados
        # Se nfe_data for uma string (conteúdo XML direto), transformar em dicionário
        if isinstance(nfe_data, str):
            # Tratar como XML direto
            logger.info("Recebido conteúdo XML direto, processando")
            xml_content = nfe_data

            # Verificar se o conteúdo parece ser XML
            if not xml_content or not ('<' in xml_content[:100]):
                logger.error("Conteúdo não parece ser XML válido")
                logger.debug(f"Primeiros 100 caracteres: {xml_content[:100]}")
                return 'erro'

            try:
                # Salvar em arquivo temporário
                temp_file = tempfile.NamedTemporaryFile(
                    mode='w', suffix='.xml', delete=False, encoding='utf-8')
                temp_file.write(xml_content)
                temp_file_path = temp_file.name
                temp_file.close()

                # Processar XML para extrair dados
                processed_nfe = process_xml_file(temp_file_path)

                # Remover arquivo temporário
                try:
                    os.unlink(temp_file_path)
                except:
                    pass

                if not processed_nfe:
                    logger.error("Falha ao processar o XML")
                    return 'erro'

                # Adicionar o conteúdo original ao dicionário processado
                processed_nfe['xml'] = xml_content
                nfe_data = processed_nfe
            except Exception as e:
                logger.error(f"Erro ao processar XML: {str(e)}")
                return 'erro'

        elif not isinstance(nfe_data, dict):
            logger.error(
                f"Dados NFe inválidos, não é um dicionário ou string: {type(nfe_data)}")
            return 'erro'

        # 2. Verificar se temos os dados mínimos necessários
        if not isinstance(nfe_data, dict):
            logger.error(
                "Dados NFe inválidos após processamento, não é um dicionário")
            return 'erro'

        chave_acesso = nfe_data.get('access_key')
        if not chave_acesso:
            logger.error("Chave de acesso não encontrada nos dados")
            return 'erro'

        # 3. Extração de dados para persistência
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

        # 4. Persistência no banco de dados
        # Verificar se a NFe já existe no banco
        cursor.execute(
            "SELECT id FROM nf_notas WHERE chave_acesso = %s", (chave_acesso,))
        resultado = cursor.fetchone()

        if resultado:
            # Atualizar NFe existente
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
                'Atualizado em ' + datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                chave_acesso
            ))

            nfe_id = resultado['id']

            # Remover itens antigos
            cursor.execute("DELETE FROM nf_itens WHERE nf_id = %s", (nfe_id,))

            logger.info(f"NFe {chave_acesso} atualizada com sucesso")

            # 5. Processamento de itens
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
            return 'atualizado'
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
                'Importado em ' + datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            ))

            # Obter o ID da NFe inserida
            nfe_id = cursor.lastrowid

            logger.info(f"NFe {chave_acesso} inserida com sucesso")

            # 5. Processamento de itens
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
        return 'novo'
    except Exception as e:
        logger.error(f"Erro ao processar NFe: {str(e)}", exc_info=True)
        if connection:
            connection.rollback()
        return 'erro'
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
        return redirect(url_for('login'))

    # Verificar token CSRF para requisições POST
    if request.method == 'POST':
        logger.info(f"Método: {request.method}")
        logger.info(f"Headers: {request.headers}")
        logger.info(f"Form: {request.form}")
        logger.info(f"Files: {request.files}")

        if 'files[]' not in request.files:
            flash('Nenhum arquivo selecionado', 'danger')
            return redirect(request.url)

        files = request.files.getlist('files[]')

        if not files or all(file.filename == '' for file in files):
            flash('Nenhum arquivo selecionado', 'danger')
            return redirect(request.url)

        # Criar diretório temporário para processar os arquivos
        temp_dir = tempfile.mkdtemp()
        try:
            processados = 0
            novos = 0
            atualizados = 0
            erros = 0

            # Reduzir o tamanho do lote para processar menos arquivos por vez
            # e evitar o erro "Request Entity Too Large"
            lote_size = 3  # Reduzido de 5 para 3 arquivos por vez

            # Dividir os arquivos em lotes menores para processamento
            for i in range(0, len(files), lote_size):
                lote_atual = files[i:i+lote_size]
                logger.info(
                    f"Processando lote {i//lote_size + 1} de {(len(files) + lote_size - 1)//lote_size}")

                for file in lote_atual:
                    if file.filename == '':
                        continue

                    filename = secure_filename(file.filename)
                    file_path = os.path.join(temp_dir, filename)

                    try:
                        # Salvar o arquivo em disco para processamento
                        file.save(file_path)
                        logger.info(f"Arquivo salvo: {file_path}")

                        # Verificar o tamanho do arquivo
                        file_size = os.path.getsize(file_path)
                        logger.info(
                            f"Tamanho do arquivo {filename}: {file_size/1024:.2f} KB")

                        # Processar arquivo com base na extensão
                        if filename.lower().endswith('.xml'):
                            # Processar arquivo XML individualmente
                            resultado = processar_arquivo_xml(file_path)
                            processados += 1
                            if resultado == 'novo':
                                novos += 1
                                logger.info(
                                    f"Arquivo {filename} processado como NOVO")
                            elif resultado == 'atualizado':
                                atualizados += 1
                                logger.info(
                                    f"Arquivo {filename} processado como ATUALIZADO")
                            else:
                                erros += 1
                                logger.warning(
                                    f"Erro ao processar arquivo {filename}")

                        elif filename.lower().endswith('.zip'):
                            # Processar arquivo ZIP (extrai XMLs internos)
                            # Primeiro verificar o tamanho do ZIP
                            if file_size > 20 * 1024 * 1024:  # 20 MB
                                logger.warning(
                                    f"Arquivo ZIP muito grande: {file_size/1024/1024:.2f} MB. Processando em modo otimizado")
                                # Para arquivos muito grandes, usar método otimizado
                                zip_resultados = processar_arquivo_zip_otimizado(
                                    file_path, temp_dir)
                            else:
                                # Para arquivos menores, usar método padrão
                                zip_resultados = processar_arquivo_zip(
                                    file_path, temp_dir)

                            processados += zip_resultados['processados']
                            novos += zip_resultados['novos']
                            atualizados += zip_resultados['atualizados']
                            erros += zip_resultados['erros']
                            logger.info(
                                f"ZIP {filename} processado: {zip_resultados['processados']} arquivos")

                        else:
                            flash(
                                f'Tipo de arquivo não suportado: {filename}', 'warning')
                            logger.warning(
                                f"Tipo de arquivo não suportado: {filename}")
                            continue

                    except Exception as e:
                        logger.error(
                            f"Erro ao processar arquivo {filename}: {str(e)}", exc_info=True)
                        erros += 1
                        flash(
                            f'Erro ao processar {filename}: {str(e)}', 'danger')

                # Liberar memória entre lotes
                import gc
                gc.collect()

            # Resultado final
            mensagem = f'Processamento concluído: {processados} arquivos processados ({novos} novos, {atualizados} atualizados, {erros} erros)'
            logger.info(mensagem)
            flash(mensagem, 'success' if erros == 0 else 'warning')

        except Exception as e:
            logger.error(
                f"Erro durante o processamento de arquivos: {str(e)}", exc_info=True)
            flash(
                f'Erro durante o processamento de arquivos: {str(e)}', 'danger')
        finally:
            # Limpar diretório temporário
            shutil.rmtree(temp_dir, ignore_errors=True)

        return redirect(url_for('importacao_nf.importar_xml'))

    return render_template('importacao_nf/importar_xml.html')


def processar_arquivo_xml(file_path):
    """Processa um único arquivo XML e salva no banco de dados."""
    try:
        # Verificar se o arquivo existe
        if not os.path.exists(file_path):
            logger.error(f"Arquivo não encontrado: {file_path}")
            return 'erro'

        # Verificar o tamanho do arquivo
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            logger.error(f"Arquivo vazio: {file_path}")
            return 'erro'

        logger.debug(
            f"Processando arquivo XML: {file_path} (Tamanho: {file_size} bytes)")

        # Tentar diferentes codificações
        xml_content = None
        encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                    xml_content = f.read()

                # Verificação básica se o conteúdo parece ser XML
                if xml_content and ('<' in xml_content[:100]):
                    logger.debug(
                        f"Arquivo lido com sucesso usando codificação {encoding}")
                    break
                else:
                    xml_content = None
            except Exception as e:
                logger.warning(
                    f"Falha ao ler com codificação {encoding}: {str(e)}")
                continue

        # Se não conseguiu ler o arquivo com nenhuma codificação
        if not xml_content:
            logger.error(
                f"Não foi possível ler o arquivo como texto: {file_path}")
            # Tentar ler como binário em último caso
            try:
                with open(file_path, 'rb') as f:
                    binary_content = f.read()
                    # Tentar decodificar manualmente
                    for enc in encodings:
                        try:
                            xml_content = binary_content.decode(enc)
                            if '<' in xml_content[:100]:
                                logger.debug(
                                    f"Arquivo decodificado como binário usando {enc}")
                                break
                        except:
                            pass
            except Exception as e:
                logger.error(f"Falha também ao ler como binário: {str(e)}")

            if not xml_content:
                logger.error(f"Conteúdo não é XML válido: {file_path}")
                # Mostrar primeiros bytes para diagnóstico
                try:
                    with open(file_path, 'rb') as f:
                        first_bytes = f.read(100)
                    logger.error(f"Primeiros bytes: {first_bytes}")
                except:
                    pass
                return 'erro'

        # Log para diagnóstico
        logger.debug(f"Primeiros 100 caracteres do XML: {xml_content[:100]}")

        # Processar o conteúdo XML com a função existente
        resultado = processar_e_salvar_nfe(xml_content)
        return resultado

    except Exception as e:
        logger.error(
            f"Erro ao processar arquivo XML {file_path}: {str(e)}", exc_info=True)
        return 'erro'


def processar_arquivo_zip(zip_path, temp_dir):
    """Extrai e processa os arquivos XML de um arquivo ZIP."""
    resultados = {
        'processados': 0,
        'novos': 0,
        'atualizados': 0,
        'erros': 0
    }

    try:
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Extrai apenas arquivos XML
            for item in zip_ref.infolist():
                if item.filename.lower().endswith('.xml'):
                    zip_ref.extract(item, extract_dir)

                    # Processar cada arquivo XML extraído
                    xml_path = os.path.join(extract_dir, item.filename)
                    try:
                        resultado = processar_arquivo_xml(xml_path)
                        resultados['processados'] += 1

                        if resultado == 'novo':
                            resultados['novos'] += 1
                        elif resultado == 'atualizado':
                            resultados['atualizados'] += 1
                        else:
                            resultados['erros'] += 1

                    except Exception as e:
                        logger.error(
                            f"Erro ao processar XML extraído {xml_path}: {str(e)}")
                        resultados['erros'] += 1

        return resultados
    except Exception as e:
        logger.error(f"Erro ao processar arquivo ZIP {zip_path}: {str(e)}")
        return resultados


def processar_arquivo_zip_otimizado(zip_path, temp_dir):
    """
    Versão otimizada para extrair e processar XMLs de arquivos ZIP muito grandes
    Faz a extração e processamento de forma mais eficiente para grandes volumes
    """
    resultados = {
        'processados': 0,
        'novos': 0,
        'atualizados': 0,
        'erros': 0
    }

    try:
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)

        # Extrair apenas arquivos XML do ZIP
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Identificar apenas os arquivos XML dentro do ZIP
            xml_files = [item for item in zip_ref.infolist()
                         if item.filename.lower().endswith('.xml')]

            logger.info(
                f"Encontrados {len(xml_files)} arquivos XML no arquivo ZIP")

            # Processar em lotes menores para evitar consumo excessivo de memória
            batch_size = 10
            for i in range(0, len(xml_files), batch_size):
                current_batch = xml_files[i:i+batch_size]
                logger.info(
                    f"Processando lote {i//batch_size + 1} de {(len(xml_files) + batch_size - 1)//batch_size}")

                # Extrair e processar cada arquivo XML do lote atual
                for item in current_batch:
                    if item.filename.lower().endswith('.xml'):
                        # Extrair apenas este arquivo
                        zip_ref.extract(item, extract_dir)

                        # Caminho completo do arquivo extraído
                        xml_path = os.path.join(extract_dir, item.filename)

                        try:
                            # Processar o XML
                            resultado = processar_arquivo_xml(xml_path)
                            resultados['processados'] += 1

                            if resultado == 'novo':
                                resultados['novos'] += 1
                            elif resultado == 'atualizado':
                                resultados['atualizados'] += 1
                            else:
                                resultados['erros'] += 1

                            # Remover o arquivo após processamento para economizar espaço
                            try:
                                os.remove(xml_path)
                            except:
                                pass

                        except Exception as e:
                            logger.error(
                                f"Erro ao processar XML extraído {xml_path}: {str(e)}", exc_info=True)
                            resultados['erros'] += 1

                            # Liberar memória entre lotes
                            import gc
                            gc.collect()

        return resultados
    except Exception as e:
        logger.error(
            f"Erro ao processar arquivo ZIP {zip_path}: {str(e)}", exc_info=True)
        resultados['erros'] += 1
        return resultados

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
                    "SELECT * FROM nf_itens WHERE nf_id = %s", (nf_id,)
                )
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
                    "SELECT * FROM nf_itens WHERE nf_id = %s", (nf_id,)
                )
                itens = cursor.fetchall()

            # Se for uma requisição POST, criar a solicitação
            if request.method == 'POST' and nota and itens:
                justificativa = request.form.get('justificativa', '')
                centro_custo_id = request.form.get(
                    'centro_custo_id', '')
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
