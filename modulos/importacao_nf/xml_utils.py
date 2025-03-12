"""
Utilitários para processamento de XML e Base64 para o módulo de importação NF
"""
import base64
import os
import tempfile
import logging
from datetime import datetime

logger = logging.getLogger('importacao_xml')


def decodificar_base64_xml(base64_str):
    """
    Decodifica um XML em Base64

    Args:
        base64_str: String em formato Base64

    Returns:
        dict: Dados processados ou None se falhar
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


def identificar_xml_base64(nfe_data):
    """Identifica se um dicionário contém dados XML em Base64

    Args:
        nfe_data: Dicionário com dados da NF ou string direta de XML potencialmente em Base64

    Returns:
        str: String Base64 ou None
    """
    # Se nfe_data for uma string, retornar diretamente para verificação
    if isinstance(nfe_data, str):
        # Verificar se a string é grande o suficiente para ser Base64 de um XML
        if len(nfe_data) > 100:
            # Verificação adicional para confirmar que parece Base64
            import re
            if re.match(r'^[A-Za-z0-9+/=]+$', nfe_data.strip()):
                return nfe_data
        return None

    # Se não for string nem dicionário, não pode conter Base64
    if not isinstance(nfe_data, dict):
        return None

    # Verificar campos comuns onde APIs podem enviar XML em Base64
    possivel_base64 = None

    if 'xml' in nfe_data and isinstance(nfe_data['xml'], str) and len(nfe_data['xml']) > 100:
        possivel_base64 = nfe_data['xml']
    elif 'xml_content' in nfe_data and isinstance(nfe_data['xml_content'], str) and len(nfe_data['xml_content']) > 100:
        possivel_base64 = nfe_data['xml_content']
    elif 'content' in nfe_data and isinstance(nfe_data['content'], str) and len(nfe_data['content']) > 100:
        possivel_base64 = nfe_data['content']
    elif 'data' in nfe_data and isinstance(nfe_data['data'], str) and len(nfe_data['data']) > 100:
        possivel_base64 = nfe_data['data']

    # Verificação adicional para confirmar que parece Base64
    if possivel_base64:
        import re
        if re.match(r'^[A-Za-z0-9+/=]+$', possivel_base64.strip()):
            return possivel_base64

    return None
