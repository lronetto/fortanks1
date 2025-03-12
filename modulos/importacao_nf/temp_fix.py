import base64
import tempfile
import os
from datetime import datetime


def decodificar_base64_para_xml(base64_str):
    """
    Decodifica uma string base64 para XML

    Args:
        base64_str: String em formato Base64

    Returns:
        tuple: (xml_content, temp_file_path)
    """
    # Remover possíveis espaços ou quebras de linha do base64
    base64_str = base64_str.replace(
        " ", "").replace("\n", "").replace("\r", "")

    # Decodificar o Base64 para bytes
    xml_bytes = base64.b64decode(base64_str)

    # Converter bytes para string
    xml_content = None
    for encoding in ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']:
        try:
            xml_content = xml_bytes.decode(encoding)
            print(f"XML decodificado com sucesso usando {encoding}")
            break
        except UnicodeDecodeError:
            continue

    if not xml_content:
        raise ValueError(
            "Falha ao decodificar XML Base64 com todas as codificações tentadas")

    # Criar um arquivo temporário com o XML decodificado
    temp_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.xml', delete=False, encoding='utf-8')
    temp_file.write(xml_content)
    temp_file_path = temp_file.name
    temp_file.close()

    return xml_content, temp_file_path
