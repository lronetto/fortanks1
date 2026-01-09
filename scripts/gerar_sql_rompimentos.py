#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para gerar SQL de inserção de rompimentos a partir do arquivo Excel
Gera SQL para as 10 primeiras linhas de dados
"""

import pandas as pd
from datetime import datetime, timedelta
import os
import sys

# Adicionar o diretório raiz ao path para importar modelos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_value_str(row, col_index):
    """Converte valor do Excel para string, retornando None se for NaN ou vazio"""
    try:
        valor = row.iloc[col_index]
        if pd.isna(valor) or valor == '' or valor is None:
            return None
        # Converter para string, removendo espaços
        return str(valor).strip()
    except (IndexError, KeyError):
        return None

def calcular_data_rompimento_28_dias(data_moldagem_dt):
    """Calcula data de rompimento 28 dias após a moldagem. Se cair em domingo, adiciona 1 dia."""
    data_rompimento = data_moldagem_dt + timedelta(days=28)
    # Verificar se é domingo (weekday() retorna 6 para domingo)
    if data_rompimento.weekday() == 6:  # Domingo
        data_rompimento += timedelta(days=1)  # Adiciona 1 dia (vira segunda-feira)
    return data_rompimento

def formatar_data_sql(data_dt):
    """Formata data para SQL MySQL"""
    if data_dt is None:
        return 'NULL'
    return f"'{data_dt.strftime('%Y-%m-%d %H:%M:%S')}'"

def formatar_valor_sql(valor):
    """Formata valor para SQL MySQL"""
    if valor is None or valor == '':
        return 'NULL'
    try:
        # Tentar converter para float
        float_valor = float(valor)
        return str(float_valor)
    except (ValueError, TypeError):
        # Se não for numérico, tratar como string
        valor_str = str(valor).replace("'", "''")  # Escapar aspas simples
        return f"'{valor_str}'"

def gerar_sql_rompimentos():
    """Gera SQL de inserção para as 10 primeiras linhas"""
    
    arquivo_excel = 'migrations/CONTROLE DE ROMPIMENTO DE CORPO DE PROVA.xlsx'
    
    if not os.path.exists(arquivo_excel):
        print(f'Erro: Arquivo não encontrado: {arquivo_excel}')
        return
    
    try:
        # Ler arquivo Excel
        df = pd.read_excel(arquivo_excel)
        
        # Pular as primeiras 4 linhas (começar a partir da linha 5, índice 4)
        df = df.iloc[4:].reset_index(drop=True)
        
        # Limitar às 10 primeiras linhas
        df = df.head(10)
        
        rompimentos = []
        
        for index, row in df.iterrows():
            try:
                numero_serie = get_value_str(row, 1)
                data_moldagem_dt = None
                rompimento5_dt = None
                rompimento8_dt = None
                rompimento9_dt = None
                
                try:
                    data_moldagem_str = get_value_str(row, 2)
                    if data_moldagem_str:
                        data_moldagem_dt = datetime.strptime(data_moldagem_str, '%Y-%m-%d %H:%M:%S')
                    
                    rompimento5_str = get_value_str(row, 5)
                    if rompimento5_str:
                        rompimento5_dt = datetime.strptime(rompimento5_str, '%Y-%m-%d %H:%M:%S')
                    
                    rompimento8_str = get_value_str(row, 8)
                    if rompimento8_str:
                        rompimento8_dt = datetime.strptime(rompimento8_str, '%Y-%m-%d %H:%M:%S')
                    
                    rompimento9_str = get_value_str(row, 9)
                    if rompimento9_str:
                        rompimento9_dt = datetime.strptime(rompimento9_str, '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError) as e:
                    print(f'Erro ao processar linha {index+1}, datas: {str(e)}')
                    continue
                
                resultado10 = get_value_str(row, 10)
                resultado11 = get_value_str(row, 11)
                resultado13 = get_value_str(row, 13)
                resultado17 = get_value_str(row, 17)
                resultado19 = get_value_str(row, 19)
                resultado21 = get_value_str(row, 21)
                resultado25 = get_value_str(row, 25)
                tipo15 = get_value_str(row, 15)
                tipo19 = get_value_str(row, 19)
                tipo24 = get_value_str(row, 24)
                tipo27 = get_value_str(row, 27)
                
                if numero_serie and data_moldagem_dt:
                    if rompimento5_dt:
                        if not rompimento8_dt:
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento5_dt,
                                'resultado': resultado13,
                                'tipo_rompimento': tipo15
                            })
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento5_dt,
                                'resultado': resultado17,
                                'tipo_rompimento': tipo19
                            })
                        elif not rompimento9_dt:
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento5_dt,
                                'resultado': resultado10,
                                'tipo_rompimento': '4'
                            })
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento8_dt,
                                'resultado': resultado13,
                                'tipo_rompimento': tipo15
                            })
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento8_dt,
                                'resultado': resultado17,
                                'tipo_rompimento': tipo19
                            })
                        elif rompimento9_dt:
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento5_dt,
                                'resultado': resultado10,
                                'tipo_rompimento': '4'
                            })
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento8_dt,
                                'resultado': resultado10,
                                'tipo_rompimento': '4'
                            })
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento9_dt,
                                'resultado': resultado13,
                                'tipo_rompimento': tipo15
                            })
                            rompimentos.append({
                                'numero_serie': numero_serie,
                                'data_moldagem': data_moldagem_dt,
                                'data_rompimento': rompimento9_dt,
                                'resultado': resultado17,
                                'tipo_rompimento': tipo19
                            })
                    
                    if resultado21:
                        data_rompimento_28d = calcular_data_rompimento_28_dias(data_moldagem_dt)
                        rompimentos.append({
                            'numero_serie': numero_serie,
                            'data_moldagem': data_moldagem_dt,
                            'data_rompimento': data_rompimento_28d,
                            'resultado': resultado21,
                            'tipo_rompimento': tipo24
                        })
                        rompimentos.append({
                            'numero_serie': numero_serie,
                            'data_moldagem': data_moldagem_dt,
                            'data_rompimento': data_rompimento_28d,
                            'resultado': resultado25,
                            'tipo_rompimento': tipo27
                        })
            except Exception as e:
                print(f'Erro ao processar linha {index+1}: {str(e)}')
                continue
        
        # Gerar SQL
        sql_statements = []
        sql_statements.append("-- SQL gerado automaticamente para inserção de rompimentos")
        sql_statements.append("-- Baseado nas 10 primeiras linhas do arquivo Excel")
        sql_statements.append("")
        sql_statements.append("INSERT INTO ConcretoUsinagensRompimentos")
        sql_statements.append("    (usinagem_id, numero_serie, data_moldagem, data_rompimento, resultado, fator_conversao, idade_cp, tipo_rompimento, observacoes)")
        sql_statements.append("VALUES")
        
        valores_sql = []
        for i, romp in enumerate(rompimentos):
            # Calcular idade_cp
            idade_cp = None
            if romp['data_moldagem'] and romp['data_rompimento']:
                diff_hours = (romp['data_rompimento'] - romp['data_moldagem']).total_seconds() / 3600
                idade_cp = int(diff_hours / 24) if diff_hours >= 24 else int(diff_hours)
            
            valor_sql = f"    (NULL, {formatar_valor_sql(romp['numero_serie'])}, {formatar_data_sql(romp['data_moldagem'])}, {formatar_data_sql(romp['data_rompimento'])}, {formatar_valor_sql(romp['resultado'])}, 1.20, {formatar_valor_sql(idade_cp)}, {formatar_valor_sql(romp['tipo_rompimento'])}, NULL)"
            
            if i < len(rompimentos) - 1:
                valor_sql += ","
            else:
                valor_sql += ";"
            
            valores_sql.append(valor_sql)
        
        sql_statements.extend(valores_sql)
        sql_statements.append("")
        sql_statements.append(f"-- Total de {len(rompimentos)} rompimento(s) gerado(s)")
        
        # Salvar em arquivo
        arquivo_sql = 'migrations/insert_rompimentos_10_linhas.sql'
        with open(arquivo_sql, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sql_statements))
        
        print(f'SQL gerado com sucesso!')
        print(f'Arquivo salvo em: {arquivo_sql}')
        print(f'Total de {len(rompimentos)} rompimento(s) gerado(s)')
        print('\nPrimeiras linhas do SQL:')
        print('\n'.join(sql_statements[:15]))
        if len(sql_statements) > 15:
            print('...')
        
    except Exception as e:
        print(f'Erro ao processar o arquivo Excel: {str(e)}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    gerar_sql_rompimentos()

