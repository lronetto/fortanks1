#!/usr/bin/env python3
"""
Script para importar dados adicionais de materiais a partir de um arquivo Excel.

O arquivo Excel deve conter:
- Coluna "Alternativo": ID do material (models/material.py)
- Coluna "Cód.Item": Valor a ser salvo no campo dados_adicionais em formato JSON

O script atualiza o campo dados_adicionais do material com o valor da coluna "Cód.Item" em formato JSON.
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path

# Adicionar o diretório raiz ao path para importar os modelos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from models.database import db
from models.material import Materiais
from app import app

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def importar_dados_adicionais(arquivo_excel, sobrescrever=False):
    """
    Importa dados adicionais de materiais a partir de um arquivo Excel.
    
    Args:
        arquivo_excel: Caminho para o arquivo Excel
        sobrescrever: Se True, sobrescreve dados_adicionais existentes. Se False, apenas atualiza se estiver vazio.
    
    Returns:
        dict: Estatísticas da importação
    """
    if not os.path.exists(arquivo_excel):
        logger.error(f"Arquivo não encontrado: {arquivo_excel}")
        return {
            'sucesso': False,
            'erro': f'Arquivo não encontrado: {arquivo_excel}'
        }
    
    try:
        # Ler o arquivo Excel
        logger.info(f"Lendo arquivo Excel: {arquivo_excel}")
        df = pd.read_excel(arquivo_excel)
        
        # Verificar se as colunas necessárias existem
        colunas_necessarias = ['Alternativo', 'Cód.Item']
        colunas_faltando = [col for col in colunas_necessarias if col not in df.columns]
        
        if colunas_faltando:
            logger.error(f"Colunas obrigatórias não encontradas: {', '.join(colunas_faltando)}")
            logger.info(f"Colunas disponíveis no arquivo: {', '.join(df.columns.tolist())}")
            return {
                'sucesso': False,
                'erro': f'Colunas obrigatórias não encontradas: {", ".join(colunas_faltando)}'
            }
        
        # Estatísticas
        total_linhas = len(df)
        atualizados = 0
        ignorados = 0
        erros = 0
        erros_detalhes = []
        
        logger.info(f"Processando {total_linhas} linhas...")
        
        # Processar cada linha
        for index, row in df.iterrows():
            try:
                # Obter o ID do material (coluna Alternativo)
                material_id = row['Alternativo']
                
                # Verificar se o ID é válido
                if pd.isna(material_id) or material_id == '':
                    logger.warning(f"Linha {index + 2}: ID do material (Alternativo) está vazio, ignorando...")
                    ignorados += 1
                    continue
                
                # Converter para inteiro
                try:
                    material_id = int(float(material_id))
                except (ValueError, TypeError):
                    logger.warning(f"Linha {index + 2}: ID do material inválido: {material_id}, ignorando...")
                    ignorados += 1
                    continue
                
                # Obter o código do item (coluna Cód.Item)
                cod_item = row['Cód.Item']
                
                # Verificar se o código do item é válido
                if pd.isna(cod_item) or cod_item == '':
                    logger.warning(f"Linha {index + 2}: Cód.Item está vazio para material ID {material_id}, ignorando...")
                    ignorados += 1
                    continue
                
                # Converter para string
                cod_item = str(cod_item).strip()
                
                # Buscar o material no banco de dados
                material = Materiais.query.get(material_id)
                
                if not material:
                    logger.warning(f"Linha {index + 2}: Material com ID {material_id} não encontrado, ignorando...")
                    ignorados += 1
                    continue
                
                # Preparar o JSON com o código do item
                dados_json = {
                    'cod_mega': cod_item
                }
                
                # Verificar se já existe dados_adicionais
                dados_existentes = None
                if material.dados_adicionais:
                    try:
                        dados_existentes = json.loads(material.dados_adicionais)
                    except json.JSONDecodeError:
                        logger.warning(f"Linha {index + 2}: Material ID {material_id} tem dados_adicionais inválidos, será sobrescrito")
                        dados_existentes = None
                
                # Decidir se atualiza ou não
                if dados_existentes and not sobrescrever:
                    logger.info(f"Linha {index + 2}: Material ID {material_id} ({material.nome}) já possui dados_adicionais, ignorando (use --sobrescrever para sobrescrever)")
                    ignorados += 1
                    continue
                
                # Atualizar ou mesclar dados
                if dados_existentes and sobrescrever:
                    # Mesclar com dados existentes
                    dados_existentes.update(dados_json)
                    dados_json = dados_existentes
                
                # Salvar no banco de dados
                material.dados_adicionais = json.dumps(dados_json, ensure_ascii=False)
                db.session.commit()
                
                logger.info(f"Linha {index + 2}: Material ID {material_id} ({material.nome}) atualizado com sucesso. Cód.Item: {cod_item}")
                atualizados += 1
                
            except Exception as e:
                logger.error(f"Linha {index + 2}: Erro ao processar linha: {str(e)}")
                erros += 1
                erros_detalhes.append({
                    'linha': index + 2,
                    'erro': str(e)
                })
                continue
        
        # Resumo
        logger.info("=" * 60)
        logger.info("RESUMO DA IMPORTAÇÃO")
        logger.info("=" * 60)
        logger.info(f"Total de linhas processadas: {total_linhas}")
        logger.info(f"Materiais atualizados: {atualizados}")
        logger.info(f"Linhas ignoradas: {ignorados}")
        logger.info(f"Erros: {erros}")
        
        if erros_detalhes:
            logger.info("\nDetalhes dos erros:")
            for erro in erros_detalhes:
                logger.info(f"  Linha {erro['linha']}: {erro['erro']}")
        
        return {
            'sucesso': True,
            'total_linhas': total_linhas,
            'atualizados': atualizados,
            'ignorados': ignorados,
            'erros': erros,
            'erros_detalhes': erros_detalhes
        }
        
    except Exception as e:
        logger.error(f"Erro ao processar arquivo Excel: {str(e)}")
        return {
            'sucesso': False,
            'erro': str(e)
        }


def main():
    """
    Função principal do script
    """
    
    
    # Usar a aplicação Flask para ter acesso ao banco de dados
    with app.app_context():
        resultado = importar_dados_adicionais('20260114T134721.932-Gd_Produtos.xlsx')
        
        if not resultado['sucesso']:
            logger.error(f"Importação falhou: {resultado.get('erro', 'Erro desconhecido')}")
            sys.exit(1)
        else:
            logger.info("Importação concluída com sucesso!")
            sys.exit(0)


if __name__ == '__main__':
    main()
