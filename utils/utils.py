"""
Funções auxiliares compartilhadas entre usinagens e rompimentos
"""
from typing import Dict
import pandas as pd
from datetime import datetime, timedelta
from pypdf import PdfReader, PdfWriter
import io
import logging
import json
from decimal import Decimal
from pdf2image import convert_from_bytes
from pyzbar.pyzbar import decode
import sys
from typing import Any, Optional
from utils.normalizar import (
    get_value_datetime,
    is_date_string,
    normalizar_data_str,
    normalizar_para_data,
)
from utils.parser import IntToStr
def formatarMoeda(valor):
    """Formata valor como moeda brasileira"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_float(value):
    """Formata float para string com duas casas decimais e separador de milhar"""
    return "{:,.2f}".format(value).replace('.', ',')


def get_value_str(row, col_index, default=None):
    """Converte valor do Excel para string, retornando None se for NaN ou vazio"""
    try:
        valor = row.iloc[col_index]
        if pd.isna(valor) or valor == '' or valor is None:
            return default
        return IntToStr(valor, default)
    except (IndexError, KeyError):
        return default



def serialize_value(value):
        from datetime import date as date_type
        if isinstance(value, (pd.Timestamp, datetime, date_type)):
            if hasattr(value, 'strftime'):
                return value.strftime('%Y-%m-%d')
            return str(value)
        return value

def serialize_nested(data):
    if isinstance(data, dict):
        return {k: serialize_nested(v) for k, v in data.items()}
    if isinstance(data, list):
        return [serialize_nested(item) for item in data]
    return serialize_value(data)

def separar_pdf_por_paginas(payload, filename):
    """
    Separa um PDF em múltiplos PDFs, um por página.
    Retorna lista de tuplas (payload_pagina, filename_pagina).
    """
    try:
        pdf_reader = PdfReader(io.BytesIO(payload))
        num_paginas = len(pdf_reader.pages)
        
        if num_paginas <= 1:
            return [(payload, filename)]
        
        paginas_separadas = []
        nome_base = filename.replace('.pdf', '')
        
        for i in range(num_paginas):
            pdf_writer = PdfWriter()
            pdf_writer.add_page(pdf_reader.pages[i])
            
            # Cria um novo PDF em memória
            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            output_buffer.seek(0)
            payload_pagina = output_buffer.getvalue()
            
            # Nome do arquivo com número da página
            filename_pagina = f"{nome_base}_pagina_{i+1}.pdf"
            
            paginas_separadas.append((payload_pagina, filename_pagina))
            logging.info(f"Página {i+1}/{num_paginas} separada: {filename_pagina}")
        
        return paginas_separadas
    except Exception as e:
        logging.error(f"Erro ao separar PDF {filename} por páginas: {e}")
        # Em caso de erro, retorna o PDF original
        return [(payload, filename)]

def json_dumps_safe(obj):
    """
    Serializa um objeto para JSON, convertendo objetos datetime e Decimal para formatos serializáveis.
    """
    def default_serializer(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
    
    return json.dumps(obj, default=default_serializer, ensure_ascii=False)

def validar_chave_acesso(chave):
    """
    Valida se uma string é uma chave de acesso válida de nota fiscal.
    Uma chave de acesso válida deve ter 44 caracteres e conter apenas dígitos numéricos.
    Retorna True se válida, False caso contrário.
    """
    if not chave:
        return False
    
    # Remove espaços e caracteres especiais
    chave_limpa = chave.strip()
    
    if len(chave_limpa) == 44:
        tipo_nf = chave_limpa[20:22]
        if tipo_nf not in ['55', '57']:
            return False
        return True
    elif len(chave_limpa) == 50:
        return True
    else:
        return False
    # Verifica se tem exatamente 44 caracteres
    if len(chave_limpa) != 44:
        return False
    
    # Verifica se contém apenas dígitos numéricos
    if not chave_limpa.isdigit():
        return False
    
    # Verifica se o tipo (posições 20:22) é válido (55 para NFE ou 57 para CTE)
    
    
    return True

def extrair_chave_do_pdf(payload: bytes) -> str | None:
    """
    Extrai a chave de acesso da primeira página do PDF (código de barras ou QR).
    Mesma lógica usada em processar_anexo_pdf_pagina.
    """
    if sys.platform == "linux":
        poppler_path = "/usr/bin"
    else:
        poppler_path = None

    try:
        images = convert_from_bytes(payload, 500, poppler_path=poppler_path)
    except Exception as e:
        logging.error(f"Erro ao converter PDF para imagem: {e}")
        return None

    if not images:
        return None

    dec1 = None
    for img in images:
        try:
            decs = decode(img)
        except Exception:
            continue

        if not decs:
            continue

        # Preferir CODE128 (chave direta)
        code128 = [d for d in decs if d.type == "CODE128"]
        if code128:
            dec1 = code128[0].data.decode("utf-8") if code128[0].data else None
            break

        # Senão, tentar QRCODE (pode ser URL)
        qr = [d for d in decs if d.type == "QRCODE"]
        if qr:
            dec1 = qr[0].data.decode("utf-8") if qr[0].data else None
            if dec1 and "https://nfe.fazenda.sp.gov.br/CTeConsulta" in dec1:
                dec1 = dec1.split("=")[1].split("&")[0]
                break
            if dec1 and "https://www.nfse.gov.br/ConsultaPublica" in dec1:
                dec1 = dec1.split("&")[1].split("=")[1]
                break
            # Pode ser a chave em texto
            break

        if dec1:
            break

    if not dec1:
        return None
    if not validar_chave_acesso(dec1):
        return None
    return dec1

def parse_dados_json(text: Optional[str]) -> Dict[str, Any]:
    if not text or not str(text).strip():
        return {}
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}

def parse_dados_json_int(text: Optional[str],item: str) -> int | None:
    d = parse_dados_json(text)
    return int(d.get(item, None)) if d.get(item, None) else None

def set_dados_json_item(text: Optional[str],item: str, value: Any) -> str:
    d = parse_dados_json(text)
    d[item] = value
    return dump_dados_json(d)
def dump_dados_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)