# modulo_importacao_nf/xml_processor.py
import xml.etree.ElementTree as ET
from datetime import datetime
import base64
import os
import tempfile
import shutil
from defusedxml.ElementTree import parse


@staticmethod
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
        print(nfe_data)
        return nfe_data

    except Exception as e:
        logger.error(
            f"Erro ao processar arquivo XML {file_path}: {str(e)}", exc_info=True)
        return None


@staticmethod
def extract_zip(zip_file, extract_dir):
    """
    Extrai arquivos ZIP contendo XMLs de NF-e

    Args:
        zip_file: Arquivo ZIP enviado
        extract_dir: Diretório para extração

    Returns:
        list: Lista de caminhos dos arquivos XML extraídos
    """
    import zipfile

    xml_files = []

    try:
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            # Listar todos os arquivos no ZIP
            file_list = zip_ref.namelist()

            # Extrair apenas arquivos XML
            for file_name in file_list:
                if file_name.lower().endswith('.xml'):
                    zip_ref.extract(file_name, extract_dir)
                    xml_files.append(os.path.join(extract_dir, file_name))

    except Exception as e:
        print(f"Erro ao extrair arquivo ZIP: {str(e)}")

    return xml_files


@staticmethod
def process_upload(files, temp_dir=None):
    """
    Processa múltiplos arquivos enviados (XML ou ZIP)

    Args:
        files: Lista de arquivos enviados
        temp_dir: Diretório temporário opcional

    Returns:
        list: Lista de dados de NF-e extraídos dos arquivos
    """
    nfe_data_list = []

    # Criar diretório temporário se não fornecido
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()

    try:
        for uploaded_file in files:
            file_path = os.path.join(temp_dir, uploaded_file.filename)

            # Salvar o arquivo enviado
            uploaded_file.save(file_path)

            # Verificar se é um arquivo ZIP
            if file_path.lower().endswith('.zip'):
                # Extrair e processar arquivos XML do ZIP
                xml_files = extract_zip(file_path, temp_dir)

                for xml_file in xml_files:
                    nfe_data = process_xml_file(xml_file)
                    if nfe_data:
                        nfe_data_list.append(nfe_data)

            # Verificar se é um arquivo XML
            elif file_path.lower().endswith('.xml'):
                nfe_data = process_xml_file(file_path)
                if nfe_data:
                    nfe_data_list.append(nfe_data)

    finally:
        # Limpar arquivos temporários
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    return nfe_data_list
