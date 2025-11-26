"""
Script para ler a aba 'cadastro' do arquivo inspecao.xlsx
"""
import os
import sys
import pandas as pd
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Adicionar o diretório pai ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask
from config.config import Config
from models.database import db
from models.nota_fiscal import NotaFiscal, CNPJS_MATRIZ

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
    xlsx_path = os.path.join(base_dir, 'inspecao.xlsx')
    
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
                
                if tipo_tanque and tipo_tanque in ['REATOR 1', 'REATOR 2', 'REATOR 3', 'REATOR 4', 'REATOR 5', 'REATOR 6', 'REATOR 7', 'REATOR 8', 'REATOR 9', 'REATOR 10','REATOR 11','REATOR 12']:
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
                peca['nome'] = str(nome_part1) + '-' + str(nome_part2)
                peca['numero_sequencial'] = row.iloc[7] if len(row) > 7 and pd.notna(row.iloc[7]) else None
                
                numerotanque_raw = tipo_tanque if tipo_tanque else None
                numerotanque_str = str(numerotanque_raw).strip() if numerotanque_raw else 'TANQUE 3'
                try:
                    numerotanque = numerotanque_str.split(' ')[1].strip()
                except:
                    numerotanque = '3'
                peca['numero_tanque'] = int(numerotanque)
                data_raw = row.iloc[1] if len(row) > 1 and pd.notna(row.iloc[1]) else None
                peca['data_concretagem'] = data_raw.strftime('%d/%m/%Y') if data_raw and hasattr(data_raw, 'strftime') else None
                
                peca['tipo'] = row.iloc[9] if len(row) > 9 and pd.notna(row.iloc[9]) else None
                peca['qualidade']['pista'] = row.iloc[18] if len(row) > 18 and pd.notna(row.iloc[18]) else None
                peca['qualidade']['acabamento'] = row.iloc[17] if len(row) > 17 and pd.notna(row.iloc[17]) else None
                chapa_valor = row.iloc[16] if len(row) > 16 and pd.notna(row.iloc[16]) else None
                peca['qualidade']['chapa'] = '' if chapa_valor == 'NÃO TEM CHAPA' else (chapa_valor or '')
                peca['qualidade']['transporte']['data_transporte'] = row.iloc[11] if len(row) > 12 and pd.notna(row.iloc[11]) else None
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

                peca['qualidade']['transporte']['placa_carreta'] = row.iloc[14] if len(row) > 14 and pd.notna(row.iloc[14]) else None
                # Só atualiza transportadora se não foi definida pelo CTE
                if not peca['qualidade']['transporte'].get('transportadora'):
                    peca['qualidade']['transporte']['transportadora'] = row.iloc[15] if len(row) > 15 and pd.notna(row.iloc[15]) else None
                pecas.append(peca)
                log['total_pecas'] += 1
            print(f"Total de peças: {log['total_pecas']}")
            print(f"Total de peças ignoradas: {log['ignoradas']}")
            print(f"Linhas ignoradas: {log['linhas_ignoradas']}")
            print(f"Peças: {pecas}")
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

