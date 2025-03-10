# modulo_importacao_nf/app.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
import requests
import json
from datetime import datetime, timedelta
import os
from mysql.connector import Error
import tempfile
import zipfile
import shutil
import xml.etree.ElementTree as ET
from werkzeug.utils import secure_filename
import logging

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
    """
    logger.debug(f"Processando arquivo XML: {file_path}")
    try:
        # Método alternativo de extração - usando regex para garantir compatibilidade máxima
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            xml_content = f.read()

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
            'xml': xml_content,
            'observacoes': f"Importado via XML em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        }

        # Extrair chave de acesso
        import re
        chave_match = re.search(r'Id="NFe([0-9]{44})"', xml_content)
        if chave_match:
            nfe_data['access_key'] = chave_match.group(1)
        else:
            logger.warning(
                f"Não foi possível extrair a chave de acesso do arquivo {file_path}")
            return None

        # Extrair número da NF
        num_match = re.search(r'<nNF>(\d+)</nNF>', xml_content)
        if num_match:
            nfe_data['number'] = num_match.group(1)

        # Extrair data de emissão
        date_match = re.search(r'<dhEmi>(.*?)</dhEmi>', xml_content)
        if not date_match:
            date_match = re.search(r'<dEmi>(.*?)</dEmi>', xml_content)

        if date_match:
            date_str = date_match.group(1)
            try:
                if 'T' in date_str:
                    # Formato com timezone: 2023-01-01T14:30:00-03:00
                    nfe_data['emission_date'] = datetime.fromisoformat(
                        date_str.replace('T', ' ').split('-03:00')[0])
                else:
                    # Formato antigo: AAAA-MM-DD
                    nfe_data['emission_date'] = datetime.strptime(
                        date_str, '%Y-%m-%d')
            except Exception as e:
                logger.warning(f"Erro ao converter data de emissão: {e}")
                nfe_data['emission_date'] = datetime.now()

        # Extrair valor total
        value_match = re.search(r'<vNF>(.*?)</vNF>', xml_content)
        if value_match:
            try:
                nfe_data['value'] = float(
                    value_match.group(1).replace(',', '.'))
            except:
                logger.warning(f"Erro ao converter valor total para float")

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
        else:
            # Tentar CPF se não encontrou CNPJ
            cpf_dest_match = re.search(
                r'<dest>.*?<CPF>(.*?)</CPF>.*?<xNome>(.*?)</xNome>', xml_content, re.DOTALL)
            if cpf_dest_match:
                nfe_data['cnpj_receiver'] = cpf_dest_match.group(1)
                nfe_data['receiver_name'] = cpf_dest_match.group(2)

        # Extrair itens
        itens = []
        # Padrão para encontrar blocos de produtos
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
                try:
                    item['quantity'] = float(
                        qty_match.group(1).replace(',', '.'))
                except:
                    item['quantity'] = 1

            # Valor unitário
            val_match = re.search(r'<vUnCom>(.*?)</vUnCom>', prod_content)
            if val_match:
                try:
                    item['unit_value'] = float(
                        val_match.group(1).replace(',', '.'))
                except:
                    item['unit_value'] = 0

            # Valor total do item
            total_match = re.search(r'<vProd>(.*?)</vProd>', prod_content)
            if total_match:
                try:
                    item['total_value'] = float(
                        total_match.group(1).replace(',', '.'))
                except:
                    item['total_value'] = 0

            # Adicionar item à lista, se tiver pelo menos código e descrição
            if 'code' in item and 'description' in item:
                itens.append(item)

        # Adicionar itens ao dicionário de retorno
        nfe_data['items'] = itens
        # print(nfe_data)
        return nfe_data

    except Exception as e:
        logger.error(
            f"Erro ao processar arquivo XML {file_path}: {str(e)}", exc_info=True)
        return None


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


# Atualizar a função processar_e_salvar_nfe para incluir o número da nota fiscal:

def processar_e_salvar_nfe(nfe_data):
    connection = get_db_connection()
    if not connection:
        return False

    try:
        cursor = connection.cursor(dictionary=True)

        # Extrair informações relevantes da NFe
        chave_acesso = nfe_data.get('access_key')
        numero_nf = nfe_data.get('number', '')  # Campo adicionado
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

            nfe_id = resultado['id']

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
        return True
    except Exception as e:
        logger.error(f"Erro ao processar NFe: {e}")
        connection.rollback()
        return False
    finally:
        if connection and hasattr(connection, 'is_connected') and connection.is_connected():
            cursor.close()
            connection.close()
# Rota principal - dashboard de importação


@mod_importacao_nf.route('/')
def index():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    # Obter estatísticas de importação
    connection = get_db_connection()
    estatisticas = {
        'total_importadas': 0,
        'total_hoje': 0,
        'valor_total': 0,
        'fornecedores_unicos': 0
    }

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Total de notas importadas
            cursor.execute("SELECT COUNT(*) as total FROM nf_notas")
            resultado = cursor.fetchone()
            estatisticas['total_importadas'] = resultado['total'] if resultado else 0

            # Notas importadas hoje
            cursor.execute(
                "SELECT COUNT(*) as total FROM nf_notas WHERE DATE(data_importacao) = CURDATE()")
            resultado = cursor.fetchone()
            estatisticas['total_hoje'] = resultado['total'] if resultado else 0

            # Valor total das notas
            cursor.execute("SELECT SUM(valor_total) as total FROM nf_notas")
            resultado = cursor.fetchone()
            estatisticas['valor_total'] = resultado['total'] if resultado and resultado['total'] else 0

            # Fornecedores únicos
            cursor.execute(
                "SELECT COUNT(DISTINCT cnpj_emitente) as total FROM nf_notas")
            resultado = cursor.fetchone()
            estatisticas['fornecedores_unicos'] = resultado['total'] if resultado else 0

            cursor.close()
        except Error as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
        finally:
            connection.close()

    return render_template('importacao_nf/index.html', estatisticas=estatisticas)

# Rota para importar notas fiscais via API


@mod_importacao_nf.route('/importar', methods=['GET', 'POST'])
def importar():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

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

    return render_template('importacao_nf/importar.html')

# Rota para importar por upload de XML


@mod_importacao_nf.route('/importar_xml', methods=['GET', 'POST'])
def importar_xml():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if request.method == 'POST':
        logger.info("Recebida requisição POST para importar_xml")

        # Verificar se há arquivos enviados
        if 'files[]' not in request.files:
            logger.warning("Nenhum arquivo encontrado no request.files")
            flash('Nenhum arquivo selecionado', 'warning')
            return redirect(request.url)

        files = request.files.getlist('files[]')

        if not files or files[0].filename == '':
            logger.warning(
                "Lista de arquivos vazia ou primeiro arquivo sem nome")
            flash('Nenhum arquivo selecionado', 'warning')
            return redirect(request.url)

        logger.info(f"Recebidos {len(files)} arquivos para processamento")

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
                    else:
                        total_erros += 1

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
                                else:
                                    total_erros += 1
                    except Exception as e:
                        logger.error(
                            f"Erro ao processar ZIP {file.filename}: {str(e)}", exc_info=True)
                        total_erros += 1
                else:
                    logger.warning(
                        f"Tipo de arquivo não suportado: {file.filename}")
                    total_erros += 1

            # Mostrar resultado da importação
            flash(
                f'Importação concluída: {total_processados} arquivo(s) processado(s), {total_novos} novo(s), {total_atualizados} atualizado(s), {total_erros} erro(s)', 'success')

        except Exception as e:
            logger.error(
                f"Erro durante o processamento dos arquivos: {str(e)}", exc_info=True)
            flash(f'Erro durante a importação: {str(e)}', 'danger')

        finally:
            # Limpar arquivos temporários
            logger.info(f"Removendo diretório temporário: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)

    return render_template('importacao_nf/importar_xml.html')

# Rota para buscar notas fiscais


@mod_importacao_nf.route('/buscar', methods=['GET', 'POST'])
def buscar():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

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

    return render_template('importacao_nf/buscar.html',
                           resultados=resultados,
                           termo_busca=termo_busca,
                           tipo_busca=tipo_busca,
                           data_inicio=data_inicio,
                           data_fim=data_fim)
# Rota para visualizar detalhes da nota fiscal


@mod_importacao_nf.route('/visualizar/<int:nf_id>')
def visualizar(nf_id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

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
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

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
                    # Inserir a solicitação
                    cursor.execute("""
                        INSERT INTO solicitacoes 
                        (justificativa, solicitante_id, centro_custo_id, status, data_solicitacao, nf_id)
                        VALUES (%s, %s, %s, %s, NOW(), %s)
                    """, (justificativa, session['id_usuario'], centro_custo_id, 'pendente', nf_id))

                    solicitacao_id = cursor.lastrowid

                    # Inserir itens selecionados
                    for item_id in itens_selecionados:
                        cursor.execute(
                            "SELECT * FROM nf_itens WHERE id = %s", (item_id,))
                        item = cursor.fetchone()

                        if item:
                            # Verificar se o material já existe
                            cursor.execute("""
                                SELECT id FROM materiais 
                                WHERE codigo = %s OR (nome = %s AND categoria = 'Importado NF')
                            """, (item['codigo'], item['descricao']))

                            material = cursor.fetchone()

                            if not material:
                                # Criar o material se não existir
                                cursor.execute("""
                                    INSERT INTO materiais (codigo, nome, descricao, categoria)
                                    VALUES (%s, %s, %s, %s)
                                """, (item['codigo'], item['descricao'], f"Importado da NF {nota['chave_acesso']}", 'Importado NF'))

                                material_id = cursor.lastrowid
                            else:
                                material_id = material['id']

                            # Inserir o item na solicitação
                            cursor.execute("""
                                INSERT INTO itens_solicitacao 
                                (solicitacao_id, material_id, quantidade, observacao, valor_unitario)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (solicitacao_id, material_id, item['quantidade'],
                                  f"Item importado da NF {nota['chave_acesso']}", item['valor_unitario']))

                    connection.commit()
                    flash('Solicitação criada com sucesso!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Preencha todos os campos obrigatórios', 'warning')

            # Buscar centros de custo para o formulário
            cursor.execute(
                "SELECT * FROM centros_custo WHERE ativo = TRUE ORDER BY codigo")
            centros_custo = cursor.fetchall()

            cursor.close()
        except Error as e:
            logger.error(f"Erro ao processar solicitação: {e}")
            flash(f'Erro ao processar solicitação: {str(e)}', 'danger')
            connection.rollback()
        finally:
            connection.close()

    if not nota:
        flash('Nota fiscal não encontrada', 'warning')
        return redirect(url_for('importacao_nf.buscar'))

    return render_template('importacao_nf/solicitar.html',
                           nota=nota,
                           itens=itens,
                           centros_custo=centros_custo if 'centros_custo' in locals() else [])

# Rotas para API interna


# Atualize a rota api_notas_recentes no arquivo modulo_importacao_nf/app.py:

@mod_importacao_nf.route('/api/notas_recentes')
def api_notas_recentes():
    if 'logado' not in session:
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
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    return render_template('importacao_nf/relatorios.html')

# Rota para API de dados para relatórios


@mod_importacao_nf.route('/api/dados_relatorio')
def api_dados_relatorio():
    if 'logado' not in session:
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
