"""
Funções auxiliares compartilhadas entre usinagens e rompimentos
"""
import pandas as pd
from datetime import datetime, timedelta
import re
from PyPDF2 import PdfReader, PdfWriter
import io
import logging
import json
from decimal import Decimal
from pdf2image import convert_from_bytes
from pyzbar.pyzbar import decode
import sys

def formatarMoeda(valor):
    """Formata valor como moeda brasileira"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def normalizar_data_str(s):
    """Normaliza string de data removendo espaços extras"""
    # Remover múltiplos espaços e normalizar
    s = re.sub(r'\s+', ' ', s.strip())
    return s


def get_value_datetime(row, col_index):
    """Converte valor do Excel para datetime, preservando horas"""
    
    try:
        valor = row.iloc[col_index]
        if pd.isna(valor) or valor == '' or valor is None:
            return None
        
        # Se já for datetime do pandas, converter diretamente (preserva horas)
        if isinstance(valor, pd.Timestamp):
            # Converter preservando horas, minutos e segundos
            # Usar replace para evitar aviso de nanossegundos
            py_dt = valor.to_pydatetime()
            
            return py_dt
        
        # Se for datetime do Python, retornar como está
        if isinstance(valor, datetime):
           
            return valor
        
        # Se for número (serial do Excel), converter usando cálculo manual
        # O Excel armazena datas como números seriais desde 1899-12-30
        # A parte decimal representa as horas (0.5 = meio-dia, 0.25 = 6h, etc)
        if isinstance(valor, (int, float)) and not pd.isna(valor):
            try:
                # Primeiro tentar usar openpyxl que já faz a conversão correta
                try:
                    from openpyxl.utils.datetime import from_excel
                    dt = from_excel(valor)
                    if isinstance(dt, datetime):
                        
                        return dt
                    elif isinstance(dt, pd.Timestamp):
                        
                        return dt.to_pydatetime()
                except (ImportError, Exception):
                    pass
                
                # Método alternativo: calcular manualmente a partir do número serial
                # Excel: base é 1899-12-30 (dia 0), então dia 1 = 1899-12-31
                base_date = datetime(1899, 12, 30)
                days = int(valor)
                fraction = valor - days
                
                # Adicionar dias
                dt = base_date + timedelta(days=days)
                
                # Adicionar fração do dia (horas, minutos, segundos)
                if fraction > 0:
                    total_seconds = int(fraction * 86400)  # 86400 segundos em um dia
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    dt = dt.replace(hour=hours, minute=minutes, second=seconds)
                
               
                return dt
            except Exception as e:
                # Última tentativa: usar pd.to_datetime (pode perder precisão de horas)
                try:
                    dt = pd.to_datetime(valor, unit='d', origin='1899-12-30')
                    if pd.notna(dt):
                       
                        return dt.to_pydatetime()
                except:
                    pass
        
        # Converter para string para processar
        valor_str = str(valor).strip()
        if not valor_str or valor_str.lower() == 'nan' or valor_str.lower() == 'nat':
            return None
        
        valor_str = normalizar_data_str(valor_str)
        
        # Tentar diferentes formatos de data/hora, priorizando os que têm hora
        # Incluir formatos com ano de 2 dígitos (formato comum do Excel)
        date_formats = [
            '%d/%m/%y %H:%M',         # 26/6/25 7:50 (formato do Excel mostrado)
            '%d/%m/%y %H:%M:%S',      # 26/6/25 7:50:00
            '%d/%m/%Y %H:%M',         # 26/06/2025 7:50
            '%d/%m/%Y %H:%M:%S',      # 26/06/2025 7:50:00
            '%Y-%m-%d %H:%M:%S',      # 2025-06-26 17:00:00
            '%Y-%m-%d %H:%M',         # 2025-06-26 17:00
            '%Y-%m-%dT%H:%M:%S',      # ISO format com hora
            '%Y-%m-%dT%H:%M',         # ISO format com hora (sem segundos)
            '%d/%m/%y',                # 26/6/25 (apenas data)
            '%Y-%m-%d',                # Apenas data (sem hora)
            '%d/%m/%Y',                # Apenas data (sem hora)
        ]
        
        # Tentar formatos com hora primeiro
        for fmt in date_formats[:8]:  # Primeiros 8 formatos têm hora
            try:
                dt = datetime.strptime(valor_str, fmt)
                
                return dt
            except ValueError:
                continue
        
        # Se nenhum formato com hora funcionou, tentar formatos sem hora
        for fmt in date_formats[8:]:
            try:
                dt = datetime.strptime(valor_str, fmt)
                
                # Se não tinha hora, manter como está (meia-noite)
                return dt
            except ValueError:
                continue
        
        # Última tentativa: usar pd.to_datetime com dayfirst=True para datas DD/MM
        # Isso é mais flexível e pode detectar formatos variados
        try:
            dt = pd.to_datetime(valor_str, errors='coerce', dayfirst=True)
            if pd.notna(dt):
                # Converter para datetime do Python, preservando horas e minutos
                py_dt = dt.to_pydatetime()
                
                return py_dt
        except:
            pass
        
        return None
    except (IndexError, KeyError, Exception) as e:
        print(f'Erro ao converter datetime col_index {col_index}: {str(e)}, valor: {valor}')
        return None


def is_date_string(valor_str):
    """Verifica se a string parece ser uma data"""
    if not valor_str:
        return False
    # Se for Timestamp do pandas, é uma data
    if isinstance(valor_str, pd.Timestamp) or isinstance(valor_str, datetime):
        return True
    # Verificar padrões comuns de data
    date_patterns = ['%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M']
    for pattern in date_patterns:
        try:
            datetime.strptime(str(valor_str), pattern)
            return True
        except:
            continue
    return False


def format_float(value):
    """Formata float para string com duas casas decimais e separador de milhar"""
    return "{:,.2f}".format(value).replace('.', ',')

def get_value_str(row, col_index, default=None):
    """Converte valor do Excel para string, retornando None se for NaN ou vazio"""
    try:
        valor = row.iloc[col_index]
        if pd.isna(valor) or valor == '' or valor is None:
            return default
        return str(valor).strip().replace('.0', '')
    except (IndexError, KeyError):
        return default


def calcular_data_rompimento_28_dias(data_moldagem_dt):
    """Calcula data de rompimento 28 dias após a moldagem. Se cair em domingo, adiciona 1 dia."""
    data_rompimento = data_moldagem_dt + timedelta(days=28)
    # Verificar se é domingo (weekday() retorna 6 para domingo)
    if data_rompimento.weekday() == 6:  # Domingo
        data_rompimento += timedelta(days=1)  # Adiciona 1 dia (vira segunda-feira)
    return data_rompimento

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
    except Exception:
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

