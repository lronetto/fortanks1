"""
Script para ler a aba 'cadastro' do arquivo inspecao.xlsx
"""
import os
import sys
import pandas as pd
from dotenv import load_dotenv
import re
import datetime

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Adicionar o diretório pai ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from flask import Flask
from config.config import Config
from models.database import db
from models.nota_fiscal import NotaFiscal, CNPJS_MATRIZ
from models.peca import Peca
import json

# Inicializa o app Flask e o contexto
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)


def main():
    # Garante saída UTF-8 no console do Windows
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    # Caminho do arquivo
    base_dir = os.path.dirname(__file__)
    xlsx_path = os.path.join(base_dir, 'INSPEÇÃO DE PISTA -  NEREDA - PRIMARIO.xlsx')
    
    if not os.path.exists(xlsx_path):
        print(f"Arquivo não encontrado: {xlsx_path}")
        return
    
    try:
        # Ler o arquivo Excel na aba ' CADASTRO' (com espaço no início)
        print(f"Lendo arquivo: {xlsx_path}")
        print(f"Aba:  CADASTRO")
        print("-" * 80)
        
        # Tentar ler com pandas
        try:
            df = pd.read_excel(xlsx_path, sheet_name=' CADASTRO', engine='openpyxl')
            print(f"Arquivo lido com sucesso!")
            print(f"Total de linhas: {len(df)}")
            print(f"Total de colunas: {len(df.columns)}")
            print("\nColunas encontradas:")
            for i, col in enumerate(df.columns, 1):
                print(f"  {i}. {col}")
            
            print("\n" + "=" * 80)
            print("Primeiras 10 linhas:")
            print("=" * 80)
            print(df.head(10).to_string())
            
            print("\n" + "=" * 80)
            print("Informações do DataFrame:")
            print("=" * 80)
            print(df.info())
            
            print("\n" + "=" * 80)
            print("Estatísticas descritivas:")
            print("=" * 80)
            print(df.describe())
            pecas = []
            log = {
                'total_pecas': 0,
                'ignoradas': 0,
                'linhas_ignoradas': []
            }
            def serialize_value(value):
                if isinstance(value, (pd.Timestamp, datetime.datetime, datetime.date)):
                    return value.strftime('%Y-%m-%d')
                return value

            def serialize_nested(data):
                if isinstance(data, dict):
                    return {k: serialize_nested(v) for k, v in data.items()}
                if isinstance(data, list):
                    return [serialize_nested(item) for item in data]
                return serialize_value(data)

            for index, row in df.iterrows():
                peca = {
                    'tanque_id': None,
                    'nome': None,
                    'numero_sequencial': None,
                    'numero_tanque': None,
                    'data_concretagem': None,
                    'tipo': None,
                    'qualidade': {
                        'acabamento': None,
                        'chapa': None,
                        'pista': None,
                        'transporte':{
                            'data_transporte': None,
                            'nota': None,
                            'cte': None,
                            'placa_carreta': None,
                            'transportadora': None,
                        }
                    },
                }
                # Usa iloc para acessar por posição (evita warnings de depreciação)
                tipo_tanque_raw = row.iloc[4] if len(row) > 4 else None
                tipo_tanque = str(tipo_tanque_raw).strip() if pd.notna(tipo_tanque_raw) else None
                
                if tipo_tanque and tipo_tanque in ['REATOR 1', 'REATOR 2', 'REATOR 3', 'REATOR 4', 'REATOR 5', 'REATOR 6', 'REATOR 7', 'REATOR 8', 'REATOR 9', 'REATOR 10','REATOR 11','REATOR 12','NEREDA']:
                    peca['tanque_id'] = 1
                elif tipo_tanque and tipo_tanque in ['PRIMARIO 1', 'PRIMARIO 2', 'PRIMARIO 3']:
                    peca['tanque_id'] = 4
                elif tipo_tanque and tipo_tanque in ['TANQUE AERADOR 1','TANQUE AERADOR 2','TANQUE AERADOR']:
                    peca['tanque_id'] = 2
                
                if peca['tanque_id'] is None:
                    log['ignoradas'] += 1
                    log['linhas_ignoradas'].append(index)
                    continue

                # Trata valores nan do pandas
                nome_part1 = row.iloc[5] if len(row) > 5 and pd.notna(row.iloc[5]) else ''
                nome_part2 = row.iloc[7] if len(row) > 7 and pd.notna(row.iloc[7]) else ''
                seq_match = re.search(r'\d+', str(nome_part2)) if nome_part2 != '' else None
                seq_formatado = seq_match.group(0).zfill(2) if seq_match else (str(nome_part2).strip() if nome_part2 != '' else '')
                peca['nome'] = f"{str(nome_part1).strip()}-{seq_formatado}"
                peca['numero_sequencial'] = seq_formatado if seq_formatado else (str(nome_part2).strip() if nome_part2 != '' else None)
                
                numerotanque_raw = tipo_tanque if tipo_tanque else None
                numerotanque_str = str(numerotanque_raw).strip() if numerotanque_raw else ''
                numero_tanque = None
                if numerotanque_str:
                    match = re.search(r'(\d+)', numerotanque_str)
                    if match:
                        numero_tanque = int(match.group(1))
                peca['numero_tanque'] = numero_tanque if numero_tanque is not None else 3
                data_raw = row.iloc[1] if len(row) > 1 and pd.notna(row.iloc[1]) else None
                # Converte para datetime object ou None para salvar no MySQL
                if data_raw and hasattr(data_raw, 'strftime'):
                    peca['data_concretagem'] = data_raw
                elif data_raw and isinstance(data_raw, str):
                    # Tenta parsear string no formato DD/MM/YYYY
                    try:
                        peca['data_concretagem'] = datetime.datetime.strptime(data_raw, '%d/%m/%Y')
                    except:
                        peca['data_concretagem'] = None
                else:
                    peca['data_concretagem'] = None
                
                peca['tipo'] = row.iloc[9] if len(row) > 9 and pd.notna(row.iloc[9]) else None
                peca['qualidade']['pista'] = row.iloc[18] if len(row) > 18 and pd.notna(row.iloc[18]) else None
                peca['qualidade']['acabamento'] = row.iloc[17] if len(row) > 17 and pd.notna(row.iloc[17]) else None
                chapa_valor = row.iloc[16] if len(row) > 16 and pd.notna(row.iloc[16]) else None
                peca['qualidade']['chapa'] = '' if chapa_valor == 'NÃO TEM CHAPA' else (chapa_valor or '')
                # Trata data_transporte - converte para datetime ou string formatada
                data_transporte_raw = row.iloc[20] if len(row) > 20 and pd.notna(row.iloc[20]) else None
                if data_transporte_raw and hasattr(data_transporte_raw, 'strftime'):
                    peca['qualidade']['transporte']['data_transporte'] = data_transporte_raw.strftime('%Y-%m-%d')
                elif data_transporte_raw and isinstance(data_transporte_raw, str):
                    # Tenta parsear string no formato DD/MM/YYYY
                    try:
                        dt = datetime.datetime.strptime(data_transporte_raw, '%d/%m/%Y')
                        peca['qualidade']['transporte']['data_transporte'] = dt.strftime('%Y-%m-%d')
                    except:
                        peca['qualidade']['transporte']['data_transporte'] = data_transporte_raw
                else:
                    peca['qualidade']['transporte']['data_transporte'] = None
                # Trata nan do pandas antes de usar na query
                nota_raw = row.iloc[22] if len(row) > 23 else None
                if pd.notna(nota_raw):
                    peca['qualidade']['transporte']['nota'] = int(nota_raw) if isinstance(nota_raw, (int, float)) else nota_raw
                else:
                    peca['qualidade']['transporte']['nota'] = None

                # Só busca nota se tiver um valor válido
                nota = None
                if peca['qualidade']['transporte']['nota'] is not None and pd.notna(peca['qualidade']['transporte']['nota']) and type(peca['qualidade']['transporte']['nota']) == str:
                    nota = NotaFiscal.query.filter(NotaFiscal.numero_nf==int(peca['qualidade']['transporte']['nota']),NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ)).first()
                if nota:
                    print(f"Nota encontrada: {nota.numero_nf}")
                    cte = NotaFiscal.query.filter(NotaFiscal.dados_adicionais.like(f'%chave_nf:{nota.chave_acesso}%')).first()
                    if cte:
                        peca['qualidade']['transporte']['cte'] = cte.numero_nf
                        peca['qualidade']['transporte']['transportadora'] = cte.nome_emitente

                peca['qualidade']['transporte']['placa_carreta'] = row.iloc[21] if len(row) > 21 and pd.notna(row.iloc[21]) else None
                # Só atualiza transportadora se não foi definida pelo CTE

                pecas.append(peca)
                log['total_pecas'] += 1
            print(f"Total de peças: {log['total_pecas']}")
            print(f"Total de peças ignoradas: {log['ignoradas']}")
            print(f"Linhas ignoradas: {log['linhas_ignoradas']}")
            #print(f"Peças: {pecas}")
            for peca in pecas:
                peca_existe = Peca.query.filter(Peca.nome==peca['nome'], 
                                                Peca.numero_sequencial==peca['numero_sequencial'], 
                                                Peca.tanque_id==peca['tanque_id']).first()
                if not peca_existe:
                    print(f"Peça não encontrada: {peca['nome']} {peca['numero_sequencial']} {peca['tanque_id']}")
                    qualidade_serializada = json.dumps(serialize_nested(peca['qualidade']), ensure_ascii=False)
                    peca_dict = Peca(
                        tanque_id=peca['tanque_id'],
                        nome=peca['nome'],
                        numero_sequencial=peca['numero_sequencial'],
                        numero_tanque=peca['numero_tanque'],
                        data_concretagem=peca['data_concretagem'],
                        tipo=peca['tipo'],
                        qualidade=qualidade_serializada
                    )
                    peca_dict.save()
                else:
                    print(f"Peça já existe: {peca['nome']} {peca['numero_sequencial']} {peca['tanque_id']}")
                    peca_existe.qualidade = json.dumps(serialize_nested(peca['qualidade']), ensure_ascii=False)
                    peca_existe.data_concretagem = peca['data_concretagem']
                    peca_existe.tipo = peca['tipo']
                    peca_existe.numero_tanque = peca['numero_tanque']
                    peca_existe.save()
                    print(f"Peça atualizada: {peca['nome']} {peca['numero_sequencial']} {peca['tanque_id']}")
                
        except Exception as e:
            print(f"Erro ao ler com pandas: {e}")
            
    except Exception as e:
        print(f"Erro ao processar o arquivo: {e}")
        import traceback
        traceback.print_exc()
        return

if __name__ == '__main__':
    print('ler_inspecao_cadastro')
    with app.app_context():
        main()

