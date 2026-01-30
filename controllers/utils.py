"""
Funções auxiliares compartilhadas entre usinagens e rompimentos
"""
import pandas as pd
from datetime import datetime, timedelta
import re


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