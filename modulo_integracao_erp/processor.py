# modulo_integracao_erp/processor.py
"""
Processador de arquivos XLS em formato HTML do ERP
"""

import os
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup

# Configuração de logging
logger = logging.getLogger('integracao_erp.processor')

def extrair_dados_xls(arquivo_path):
    """
    Extrai dados de um arquivo XLS em formato HTML
    
    Args:
        arquivo_path (str): Caminho para o arquivo XLS
    
    Returns:
        list: Lista de dicionários com os dados extraídos
    """
    dados = []
    
    try:
        logger.info(f"Processando arquivo: {arquivo_path}")
        
        # Ler o conteúdo do arquivo HTML
        with open(arquivo_path, 'r', encoding='utf-8', errors='ignore') as file:
            html_content = file.read()
        
        # Substituir entidades HTML comuns
        html_content = html_content.replace('&nbsp;', ' ')
        
        # Parsear o HTML usando BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Data de processamento
        data_processamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Encontrar tabelas no HTML
        tabelas = soup.find_all('table')
        
        if not tabelas:
            logger.warning("Nenhuma tabela encontrada no arquivo")
            return dados
        
        # Encontrar a tabela principal (geralmente a maior)
        tabela_principal = max(tabelas, key=lambda t: len(t.find_all('tr')))
        
        # Variáveis para rastrear
        centro_custo_atual = None
        categoria_atual = None
        
        # Índices das colunas
        indices = {
            'data_pagamento': 2,
            'documento': 3,
            'emitente': 4,
            'historico': 6,
            'valor': 10
        }
        
        # Processar linhas
        rows = tabela_principal.find_all('tr')
        registros = 0
        
        for row in rows:
            cells = row.find_all('td')
            if not cells:
                continue
            
            cell_texts = [c.text.strip() for c in cells]
            
            # Centro de custo (formato: XXXX-XX)
            if len(cell_texts) > 0 and "C.Custo:" in cell_texts[0]:
                codigo_match = re.search(r'(\d{4}-\d{2})', cell_texts[0])
                if codigo_match:
                    centro_custo_atual = codigo_match.group(1)
                continue
            
            # Categoria (extrair apenas o número)
            if len(cell_texts) > 1 and cell_texts[1] and not cell_texts[1].isspace():
                categoria_match = re.search(r'^(\d+)', cell_texts[1].strip())
                if categoria_match:
                    categoria_atual = categoria_match.group(1)
                continue
            
            # Processar linhas com valores
            try:
                if len(cell_texts) > indices['valor']:
                    valor_text = cell_texts[indices['valor']]
                    # Limpar texto de valor
                    valor_text = re.sub(r'[^\d.,]', '', valor_text).replace('.', '').replace(',', '.')
                    
                    if valor_text.strip() and float(valor_text) > 0:
                        registros += 1
                        
                        # Coletar dados
                        data = cell_texts[indices['data_pagamento']] if indices['data_pagamento'] < len(cell_texts) else ""
                        documento = cell_texts[indices['documento']] if indices['documento'] < len(cell_texts) else ""
                        emitente = cell_texts[indices['emitente']] if indices['emitente'] < len(cell_texts) else ""
                        historico = cell_texts[indices['historico']] if indices['historico'] < len(cell_texts) else ""
                        valor = float(valor_text)
                        
                        # Adicionar registro à lista
                        registro = {
                            'centro_custo': centro_custo_atual,
                            'categoria': categoria_atual,
                            'data_pagamento': data,
                            'documento': documento,
                            'emitente': emitente,
                            'historico': historico,
                            'valor': valor,
                            'data_processamento': data_processamento
                        }
                        dados.append(registro)
                        
                        # Mostrar progresso
                        if registros % 100 == 0:
                            logger.info(f"{registros} registros processados")
            except Exception as e:
                logger.error(f"Erro ao processar linha: {str(e)}")
                continue
        
        logger.info(f"Processamento concluído: {registros} registros extraídos")
        return dados
    
    except Exception as e:
        logger.error(f"Erro ao extrair dados do arquivo: {str(e)}", exc_info=True)
        return dados

def processar_arquivo_batch(arquivo_path, callback=None):
    """
    Processa um arquivo em lotes para evitar sobrecarga de memória
    
    Args:
        arquivo_path (str): Caminho para o arquivo
        callback (function): Função de callback para processar cada lote
        
    Returns:
        dict: Resultado do processamento com estatísticas
    """
    resultado = {
        'sucesso': False,
        'registros_processados': 0,
        'registros_com_erro': 0,
        'valor_total': 0,
        'mensagem': ''
    }
    
    try:
        # Extrair todos os dados (poderia ser em lotes para arquivos muito grandes)
        dados = extrair_dados_xls(arquivo_path)
        
        if not dados:
            resultado['mensagem'] = "Nenhum dado encontrado no arquivo"
            return resultado
        
        # Processar os dados
        if callback:
            # Tamanho do lote
            tamanho_lote = 1000
            
            # Dividir em lotes
            for i in range(0, len(dados), tamanho_lote):
                lote = dados[i:i + tamanho_lote]
                
                # Chamar o callback para cada lote
                sucesso, processados, erros, mensagem = callback(lote)
                
                # Atualizar estatísticas
                resultado['registros_processados'] += processados
                resultado['registros_com_erro'] += erros
                
                # Calcular valor total
                for registro in lote:
                    resultado['valor_total'] += registro['valor']
                
                # Se houver erro crítico, interromper
                if not sucesso:
                    resultado['mensagem'] = mensagem
                    return resultado
            
            resultado['sucesso'] = True
            resultado['mensagem'] = f"Processamento concluído: {resultado['registros_processados']} registros processados, {resultado['registros_com_erro']} com erro"
        else:
            # Se não houver callback, apenas contar os registros
            resultado['registros_processados'] = len(dados)
            for registro in dados:
                resultado['valor_total'] += registro['valor']
            
            resultado['sucesso'] = True
            resultado['mensagem'] = f"Dados extraídos: {resultado['registros_processados']} registros encontrados"
        
        return resultado
    
    except Exception as e:
        logger.error(f"Erro ao processar arquivo em lotes: {str(e)}", exc_info=True)
        resultado['mensagem'] = f"Erro durante o processamento: {str(e)}"
        return resultado
