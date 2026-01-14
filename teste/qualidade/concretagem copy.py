"""
Script para importação de dados de concretagem da planilha contl.xlsx

A planilha contém duas abas:
- 'plan de data': contém pista e placas (formato JSON: {placa: x, tanque: y, forma: z})
  O número da forma está no cabeçalho na linha 2
- 'CA': contém alongamentos e bobinas utilizadas
  Formato JSON para cordoalhas: {'alongamentos': {'c-x': y, ...}, 'bobinas': [{n: x, data_fabricacao: y, certificado: z}]}
As duas planilhas são linkadas pela coluna 1 (folha)
"""
import os
import sys
import traceback
import pandas as pd
from dotenv import load_dotenv
import json
import re
from datetime import datetime
from dateutil.parser import parse as parse_date

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Adicionar o diretório pai ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from flask import Flask
from config.config import Config
from models.database import db
from models.concretagem import Concretagem, ConcretagemTanque
from models.peca import Peca
from models.tanque import Tanque

# Inicializa o app Flask e o contexto
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)


def parse_json_field(value):
    """Tenta parsear um campo que pode estar em formato JSON"""
    if pd.isna(value) or value is None:
        return None
    
    if isinstance(value, str):
        # Tenta parsear como JSON
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Se não for JSON válido, tenta extrair dados manualmente
            # Procura por padrões como {placa: x, tanque: y, forma: z}
            return value
    return value


def extrair_placas_do_campo(placas_value, formas_cabecalho):
    """
    Extrai as placas do campo que pode estar em formato JSON ou texto
    Retorna lista de dicionários: [{'placa': x, 'tanque': y, 'forma': z}, ...]
    """
    if pd.isna(placas_value) or placas_value is None:
        return []
    
    placas_list = []
    
    # Se for string, tenta parsear
    if isinstance(placas_value, str):
        # Tenta parsear como JSON primeiro
        try:
            parsed = json.loads(placas_value)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            pass
        
        # Se não for JSON, tenta extrair manualmente
        # Procura por padrões como "placa: x, tanque: y, forma: z"
        # ou múltiplas placas separadas por vírgula ou quebra de linha
        partes = re.split(r'[,;\n]', placas_value)
        for parte in partes:
            parte = parte.strip()
            if not parte:
                continue
            
            # Tenta extrair informações
            placa_match = re.search(r'placa[:\s]+(\d+)', parte, re.IGNORECASE)
            tanque_match = re.search(r'tanque[:\s]+(\d+)', parte, re.IGNORECASE)
            forma_match = re.search(r'forma[:\s]+(\d+)', parte, re.IGNORECASE)
            
            placa = placa_match.group(1) if placa_match else None
            tanque = tanque_match.group(1) if tanque_match else None
            forma = forma_match.group(1) if forma_match else None
            
            if placa:
                placas_list.append({
                    'placa': placa,
                    'tanque': tanque,
                    'forma': forma
                })
    
    return placas_list


def extrair_alongamentos(df_ca_row):
    """
    Extrai alongamentos da linha da planilha CA
    Os alongamentos estão entre as colunas 3 e 24 (índices 3 a 24)
    Retorna dicionário: {"C-1": 338, "C-2": 337, ...}
    """
    alongamentos = {}
    
    # Processar apenas as colunas entre 3 e 24 (índices 3 a 24)
    for col_idx in range(2, min(24, len(df_ca_row))):  # 3 a 24 (inclusive)
        if col_idx >= len(df_ca_row):
            break
        
        valor = df_ca_row.iloc[col_idx] if hasattr(df_ca_row, 'iloc') else df_ca_row[col_idx]
        
        if pd.isna(valor):
            continue
        
        # O número do cabo (C-1, C-2, etc.) é baseado na posição da coluna
        # Coluna 3 = C-1, Coluna 4 = C-2, etc.
        cabo_numero = col_idx - 1  # Coluna 3 -> C-1, Coluna 4 -> C-2, etc.
        chave = f"C-{cabo_numero}"
        
        # Garantir que o valor seja numérico
        try:
            alongamentos[chave] = int(float(valor)) if isinstance(valor, (int, float, str)) else int(valor)
        except (ValueError, TypeError):
            # Se não conseguir converter, tenta extrair número
            num_match = re.search(r'(\d+)', str(valor))
            if num_match:
                alongamentos[chave] = int(num_match.group(1))
    
    return alongamentos


def extrair_bobinas(df_ca_row):
    """
    Extrai bobinas da linha da planilha CA
    As bobinas estão nas colunas:
    - Primeira bobina: colunas 25, 26, 27 (índices 25, 26, 27)
    - Segunda bobina: colunas 28, 29, 30 (índices 28, 29, 30)
    Retorna lista: [{'numero': 1062265533, 'data_fabricacao': '28/02/2025', 'certificado': 81795}, ...]
    """
    bobinas = []
    
    # Primeira bobina: colunas 25, 26, 27
    # Coluna 25: N° BOBINA
    # Coluna 26: DATA FAB.
    # Coluna 27: CERTIFICADO
    bobina1_num = None
    bobina1_data = None
    bobina1_cert = None
    
    if len(df_ca_row) > 24:
        valor = df_ca_row.iloc[24] if hasattr(df_ca_row, 'iloc') else df_ca_row[24]
        if pd.notna(valor):
            try:
                bobina1_num = int(float(str(valor).strip()))
            except (ValueError, TypeError):
                bobina1_num = str(valor).strip()
    
    if len(df_ca_row) > 25:
        valor = df_ca_row.iloc[25] if hasattr(df_ca_row, 'iloc') else df_ca_row[25]
        if pd.notna(valor):
            try:
                if isinstance(valor, (datetime, pd.Timestamp)):
                    bobina1_data = valor.strftime('%d/%m/%Y')
                elif isinstance(valor, str):
                    parsed_date = parse_date(valor)
                    bobina1_data = parsed_date.strftime('%d/%m/%Y')
                else:
                    bobina1_data = str(valor)
            except:
                bobina1_data = str(valor) if valor else None
    
    if len(df_ca_row) > 26:
        valor = df_ca_row.iloc[26] if hasattr(df_ca_row, 'iloc') else df_ca_row[26]
        if pd.notna(valor):
            try:
                bobina1_cert = int(float(str(valor).strip()))
            except (ValueError, TypeError):
                bobina1_cert = str(valor).strip()
    
    # Se encontrou dados da primeira bobina, adiciona
    if bobina1_num:
        bobina = {
            'numero': bobina1_num,
            'data_fabricacao': bobina1_data,
            'certificado': bobina1_cert
        }
        bobinas.append(bobina)
    
    # Segunda bobina: colunas 28, 29, 30
    # Coluna 28: N° BOBINA.1
    # Coluna 29: DATA FAB. .1
    # Coluna 30: CERTIFICADO.1
    bobina2_num = None
    bobina2_data = None
    bobina2_cert = None
    
    if len(df_ca_row) > 27:
        valor = df_ca_row.iloc[27] if hasattr(df_ca_row, 'iloc') else df_ca_row[27]
        if pd.notna(valor):
            try:
                bobina2_num = int(float(str(valor).strip()))
            except (ValueError, TypeError):
                bobina2_num = str(valor).strip()
    
    if len(df_ca_row) > 28:
        valor = df_ca_row.iloc[28] if hasattr(df_ca_row, 'iloc') else df_ca_row[28]
        if pd.notna(valor):
            try:
                if isinstance(valor, (datetime, pd.Timestamp)):
                    bobina2_data = valor.strftime('%d/%m/%Y')
                elif isinstance(valor, str):
                    parsed_date = parse_date(valor)
                    bobina2_data = parsed_date.strftime('%d/%m/%Y')
                else:
                    bobina2_data = str(valor)
            except:
                bobina2_data = str(valor) if valor else None
    
    if len(df_ca_row) > 29:
        valor = df_ca_row.iloc[29] if hasattr(df_ca_row, 'iloc') else df_ca_row[29]
        if pd.notna(valor):
            try:
                bobina2_cert = int(float(str(valor).strip()))
            except (ValueError, TypeError):
                bobina2_cert = str(valor).strip()
    
    # Se encontrou dados da segunda bobina, adiciona
    if bobina2_num:
        bobina = {
            'numero': bobina2_num,
            'data_fabricacao': bobina2_data,
            'certificado': bobina2_cert
        }
        bobinas.append(bobina)
    
    return bobinas


def buscar_peca_por_nome(nome_peca, tanque_id=None):
    """
    Busca uma peça pelo nome no formato "PN-X" ou similar
    """
    if not nome_peca:
        return None
    
    nome_peca_str = str(nome_peca).strip().upper()
    
    if tanque_id:
        # Busca no tanque específico
        # Tenta buscar pelo nome exato
        pecas = Peca.query.filter_by(tanque_id=tanque_id).all()
        for peca in pecas:
            peca_nome_upper = str(peca.nome).upper()
            # Verifica se o nome da peça contém o padrão (PN-001, PN-02, etc.)
            if nome_peca_str in peca_nome_upper or peca_nome_upper in nome_peca_str:
                return peca
            # Também verifica se o número sequencial corresponde
            if nome_peca_str.replace('PN-', '').replace('PN', '') == str(peca.numero_sequencial):
                return peca
    else:
        # Busca em todos os tanques
        pecas = Peca.query.all()
        for peca in pecas:
            peca_nome_upper = str(peca.nome).upper()
            # Verifica se o nome da peça contém o padrão
            if nome_peca_str in peca_nome_upper or peca_nome_upper in nome_peca_str:
                return peca
            # Também verifica se o número sequencial corresponde
            try:
                num_planilha = int(nome_peca_str.replace('PN-', '').replace('PN', '').strip())
                if peca.numero_sequencial == num_planilha:
                    return peca
            except ValueError:
                pass
    
    return None


def buscar_peca_por_placa(placa_num, tanque_id=None):
    """
    Busca uma peça pelo número de placa (mantido para compatibilidade)
    A placa pode estar no nome ou número sequencial da peça
    """
    placa_num_str = str(placa_num).strip()
    
    if tanque_id:
        # Busca no tanque específico
        # Primeiro tenta pelo número sequencial exato
        try:
            peca = Peca.query.filter_by(tanque_id=tanque_id, numero_sequencial=int(placa_num_str)).first()
            if peca:
                return peca
        except ValueError:
            pass
        
        # Depois tenta pelo nome contendo a placa
        pecas = Peca.query.filter_by(tanque_id=tanque_id).all()
        for peca in pecas:
            if placa_num_str in str(peca.nome) or placa_num_str in str(peca.numero_sequencial):
                return peca
    else:
        # Busca em todos os tanques
        # Primeiro tenta pelo número sequencial exato
        try:
            peca = Peca.query.filter_by(numero_sequencial=int(placa_num_str)).first()
            if peca:
                return peca
        except ValueError:
            pass
        
        # Depois tenta pelo nome contendo a placa
        pecas = Peca.query.all()
        for peca in pecas:
            if placa_num_str in str(peca.nome) or placa_num_str in str(peca.numero_sequencial):
                return peca
    
    return None


def buscar_tanque_por_numero(numero_tanque):
    """
    Busca um tanque pelo número
    O número pode estar no campo nome ou numero_tanque das peças
    """
    # Primeiro tenta buscar pelo ID direto
    tanque = Tanque.query.get(numero_tanque)
    if tanque:
        return tanque
    
    # Busca pelo nome contendo o número
    tanques = Tanque.query.filter(Tanque.nome.contains(str(numero_tanque))).all()
    if tanques:
        return tanques[0]
    
    return None


def buscar_tanque_por_descricao(descricao):
    """
    Busca um tanque pela descrição (coluna 34 da planilha)
    """
    if not descricao:
        return None
    
    descricao_str = str(descricao).strip()
    
    # Busca pelo nome contendo a descrição
    tanques = Tanque.query.filter(Tanque.nome.contains(descricao_str)).all()
    if tanques:
        return tanques[0]
    
    # Tenta buscar por partes da descrição
    palavras = descricao_str.split()
    for palavra in palavras:
        if len(palavra) > 2:  # Ignora palavras muito curtas
            tanques = Tanque.query.filter(Tanque.nome.contains(palavra)).all()
            if tanques:
                return tanques[0]
    
    return None


def main():
    # Garante saída UTF-8 no console do Windows
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    # Caminho do arquivo
    base_dir = os.path.dirname(__file__)
    xlsx_path = os.path.join(base_dir, 'contl.xlsx')
    
    if not os.path.exists(xlsx_path):
        print(f"Arquivo não encontrado: {xlsx_path}")
        return
    
    try:
        print(f"Lendo arquivo: {xlsx_path}")
        print("-" * 80)
        
        # Ler a planilha "plan de data"
        df_plan = pd.read_excel(xlsx_path, sheet_name='plan de data', header=None, engine='openpyxl')
        print(f"Planilha 'plan de data' lida: {len(df_plan)} linhas")
        
        # Ler a planilha "CA"
        df_ca = pd.read_excel(xlsx_path, sheet_name='CA', engine='openpyxl')
        print(f"Planilha 'CA' lida: {len(df_ca)} linhas")
        
        # Obter cabeçalho da linha 1 (índice 1) para formas
        # Linha 0 tem números, linha 1 tem "FORMA 1", "FORMA 2", etc.
        formas_cabecalho = {}
        if len(df_plan) > 1:
            linha_cabecalho = df_plan.iloc[1]  # Linha 2 (índice 1)
            for idx, valor in enumerate(linha_cabecalho):
                if pd.notna(valor):
                    valor_str = str(valor).strip().upper()
                    # Procura por "FORMA X" no cabeçalho
                    if 'FORMA' in valor_str:
                        # Extrai o número da forma ou usa o valor da linha 0
                        forma_num = df_plan.iloc[0, idx] if len(df_plan) > 0 and idx < len(df_plan.iloc[0]) else None
                        if pd.notna(forma_num):
                            formas_cabecalho[idx] = str(forma_num).strip()
                        else:
                            # Tenta extrair do texto "FORMA 1", "FORMA 2", etc.
                            match = re.search(r'FORMA\s*(\d+)', valor_str)
                            if match:
                                formas_cabecalho[idx] = match.group(1)
        
        print(f"Formas encontradas no cabeçalho: {formas_cabecalho}")
        
        # Processar cada linha da planilha "plan de data" (começando da linha 2, índice 2)
        # Linha 0: números das formas, Linha 1: cabeçalho, Linha 2+: dados
        log = {
            'total_linhas': 0,
            'concretagens_criadas': 0,
            'concretagens_atualizadas': 0,
            'erros': 0,
            'erros_detalhes': []
        }
        
        # Modo teste: armazenar dados de todas as peças
        pecas_teste = []
        
        # Limitar processamento às primeiras 5 folhas
        limite_folhas = 999999
        folhas_processadas = 0
        
        for idx in range(2, len(df_plan)):  # Começa da linha 3 (índice 2)
            # Parar após processar 5 folhas
            if folhas_processadas >= limite_folhas:
                print(f"\nLimite de {limite_folhas} folhas atingido. Parando processamento.")
                break
            try:
                row_plan = df_plan.iloc[idx]
                
                # Coluna 0 (índice 0) é o número da folha (link com CA)
                folha = row_plan.iloc[0] if len(row_plan) > 0 else None
                if pd.isna(folha):
                    continue
                
                folha = int(folha) if isinstance(folha, (int, float)) else None
                if folha is None:
                    continue
                
                # Incrementar contador de folhas processadas
                folhas_processadas += 1
                log['total_linhas'] += 1
                
                # Coluna 1 (índice 1) é a data
                data_raw = row_plan.iloc[1] if len(row_plan) > 1 else None
                if pd.isna(data_raw):
                    print(f"Linha {idx}: Data não encontrada, pulando...")
                    continue
                
                # Converter data
                if isinstance(data_raw, (datetime, pd.Timestamp)):
                    data_concretagem = data_raw.date()
                elif isinstance(data_raw, str):
                    try:
                        data_concretagem = parse_date(data_raw).date()
                    except:
                        print(f"Linha {idx}: Erro ao parsear data '{data_raw}', pulando...")
                        continue
                else:
                    print(f"Linha {idx}: Formato de data inválido, pulando...")
                    continue
                
                # Procurar pista na coluna 31 (índice 31) - formato PN-002
                pista = None
                if len(row_plan) > 30:
                    pista_valor = row_plan.iloc[30]
                    if pd.notna(pista_valor):
                        pista_str = str(pista_valor).strip()
                        # Extrair número da pista do formato PN-002
                        match = re.search(r'PN-(\d+)', pista_str, re.IGNORECASE)
                        if match:
                            pista = match.group(1)
                        else:
                            # Se não encontrar formato PN-X, usa o valor direto
                            pista = pista_str
                
                if not pista:
                    # Valor padrão
                    pista = '1'
                
                # Coluna 34 (índice 34) contém a descrição do tanque para buscar o ID
                descricao_tanque = None
                tanque_id = None
                if len(row_plan) > 33:
                    descricao_tanque_valor = row_plan.iloc[33]
                    if pd.notna(descricao_tanque_valor):
                        descricao_tanque = str(descricao_tanque_valor).strip()
                        # Buscar tanque pela descrição
                        tanque = buscar_tanque_por_descricao(descricao_tanque)
                        if tanque:
                            tanque_id = tanque.id
                
                # Extrair nomes de peças das colunas 3, 5, 7, 9, etc. (formato PN-X)
                # O número da forma pode começar em 1, 2, 3, etc. dependendo da folha
                placas_data = []
                forma_numero = None  # Será determinado ao encontrar a primeira peça
                forma_idx = 3  # Primeira coluna de forma (índice 3)
                primeira_peca_encontrada = False
                
               
                # Se não encontrou placas na coluna 2, tenta buscar em outras colunas
                if not placas_data:
                    # Procura em colunas ímpares (3, 5, 7, 9, etc.) que podem ser placas
                    for col_idx in range(3, min(30, len(row_plan)), 2):  # Colunas ímpares de 3 a 29
                        valor = row_plan.iloc[col_idx]
                        if pd.notna(valor):
                            valor_str = str(valor).strip()
                            # Se parece com número de placa
                            forma = formas_cabecalho.get(col_idx)
                            placas_data.append({
                                'placa': valor_str,
                                'tanque': tanque_id if tanque_id else None,
                                'forma': forma
                            })
                
                # Buscar dados correspondentes na planilha CA
                df_ca_row = None
                if folha:
                    # Busca linha na planilha CA onde a primeira coluna (folha) corresponde
                    ca_matches = df_ca[df_ca.iloc[:, 0] == folha]
                    if not ca_matches.empty:
                        df_ca_row = ca_matches.iloc[0]
                
                # Extrair alongamentos e bobinas da planilha CA
                alongamentos = {}
                bobinas = []
                if df_ca_row is not None:
                    alongamentos = extrair_alongamentos(df_ca_row)
                    bobinas = extrair_bobinas(df_ca_row)
                
                # Montar JSON de cordoalhas
                cordoalhas_json = {
                    'alongamentos': alongamentos,
                    'bobinas': bobinas
                }
                
                # Montar JSON de peças
                pecas_json = placas_data
               
                concretagem = Concretagem(
                    data_concretagem=data_concretagem,
                    pista=pista,
                    cordoalhas=json.dumps(cordoalhas_json),
                    pecas=json.dumps(pecas_json),
                )
                db.session.add(concretagem)
            except Exception as e:
                print(f"Erro ao processar a linha {idx}: {e}")
                log['erros'] += 1
                log['erros_detalhes'].append(f"Linha {idx}: {str(e)}")
                continue
        db.session.commit()
        print(f"\nProcessamento concluído com {log['concretagens_criadas']} concretagens criadas e {log['concretagens_atualizadas']} atualizadas.")
        print(f"Total de erros: {log['erros']}")

    except Exception as e:
        print(f"Erro ao processar o arquivo: {e}")
        print(traceback.format_exc())
        return


if __name__ == '__main__':
    print('Importação de concretagem da planilha contl.xlsx')
    with app.app_context():
        main()

