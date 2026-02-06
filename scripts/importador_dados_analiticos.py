"""
Script para importação de dados analíticos financeiros usando Playwright.
Este script permite a extração automatizada de relatórios financeiros de sistemas externos
e sua importação para o banco de dados da aplicação.
"""
import os
import csv
import logging
import tempfile
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
from pathlib import Path
import sys
import re
from unidecode import unidecode
import pandas as pd
import xlrd
import openpyxl

# Adicionar o diretório pai ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configuração de logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Importações do Playwright
try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    logger.error("Playwright não está instalado. Execute: pip install playwright")
    logger.error("E em seguida: playwright install")
    raise

# Importações dos modelos

from models.database import db
from models.dados_analiticos import DadoAnalitico
from models.centro_custo import CentroCusto
from models.plano_conta import PlanoConta
from models.usuario import Usuario
from config.config import Config


# BeautifulSoup para processamento do HTML
from bs4 import BeautifulSoup

class ImportadorDadosAnaliticos:
    """Classe para importação de dados analíticos financeiros."""
    logs = None
    def __init__(self, usuario_id: int = None,logs=None):
        self.logs = logs
        """
        Inicializa o importador de dados analíticos.
        
        Args:
            usuario_id: ID do usuário que está executando a importação
        """
        self.usuario_id = usuario_id
        self.usuario = None
        if usuario_id:
            self.usuario = Usuario.query.get(usuario_id)
        
        # Configurações
        self.url_sistema_externo = Config.URL_SISTEMA_FINANCEIRO if hasattr(Config, 'URL_SISTEMA_FINANCEIRO') else None
        self.login_sistema_externo = Config.LOGIN_SISTEMA_FINANCEIRO if hasattr(Config, 'LOGIN_SISTEMA_FINANCEIRO') else None
        self.senha_sistema_externo = Config.SENHA_SISTEMA_FINANCEIRO if hasattr(Config, 'SENHA_SISTEMA_FINANCEIRO') else None
        
        # Diretório temporário para armazenar arquivos
        self.temp_dir = tempfile.mkdtemp(prefix="fortanks_temp_")
        logger.info(f"Diretório temporário criado: {self.temp_dir}")
    
    async def executar_extracao(self) -> Optional[str]:
        """
        Executa a extração de dados do sistema externo usando Playwright.
        
        Args:
            data_inicio: Data inicial no formato DD/MM/AAAA
            data_fim: Data final no formato DD/MM/AAAA
            
        Returns:
            Caminho para o arquivo extraído ou None em caso de falha
        """
       # if not self.url_sistema_externo:
       #     logger.error("URL do sistema financeiro não configurada")
      #      return None
            
        logger.info(f"Iniciando extração de dados de ")
        
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
                    # Navegar para a página de login
            await page.goto("https://www.sox.com.br/")
            await page.locator("iframe[name=\"login\"]").content_frame.locator(
                "input[name=\"login\"]").fill("leandrofor")
            await page.locator("iframe[name=\"login\"]").content_frame.locator(
                "input[name=\"senha\"]").fill("netto$%")
            await page.locator("iframe[name=\"login\"]").content_frame.get_by_role(
                "button", name="Acessar").click()
            await page.locator("iframe[name=\"menu\"]").content_frame.get_by_text(
                "FINANCEIRO").click()
            await page.locator("iframe[name=\"menu\"]").content_frame.get_by_text(
                "Custo Analítico").click()
            await page.locator("frame[name=\"conteudo\"]").content_frame.get_by_role(
                "link", name="Filtrar").click()
            
            # Aguardar download ou geração do relatório
            download_path = None
            
            async with page.expect_download() as download_info:
                async with page.expect_popup() as page1_info:
                    downloadPromise = page.wait_for_event('download')
                    await page.locator("frame[name=\"conteudo\"]").content_frame.get_by_role(
                        "link", name="Relatório Excel").click()
                    download = await downloadPromise
                    download_path = os.path.join(self.temp_dir, 'base.xls')
                    await download.save_as(download_path)
                    #page.on('download', download=download.path().then(console.log))
                page1 = page1_info.value
                
                #await browser.close()
        
        if download_path:
            self.logs['dados_analiticos']['mensagem'].append(f"Extração de dados concluída com sucesso")
            return download_path
        else:
            self.logs['dados_analiticos']['erro'] = True
            self.logs['dados_analiticos']['erro_mensagem'].append(f"Falha na extração dos dados")
            return None
       
    
    async def processar_arquivo_html(self, arquivo_path: str) -> List[Dict[str, Any]]:
        """
        Processa arquivo HTML extraído e extrai os dados analíticos.
        
        Args:
            arquivo_path: Caminho para o arquivo HTML
            
        Returns:
            Lista de dicionários com os dados extraídos
        """
        logger.info(f"Processando arquivo HTML: {arquivo_path}")
        dados_extraidos = []
        
        try:
            # Tenta abrir o arquivo com diferentes codificações
            codificacoes = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']
            html_content = None
            
            for encoding in codificacoes:
                try:
                    with open(arquivo_path, 'r', encoding=encoding, errors='replace') as file:
                        html_content = file.read()
                    logger.info(f"Arquivo aberto com sucesso usando codificação: {encoding}")
                    break
                except Exception as e:
                    logger.warning(f"Falha ao abrir com codificação {encoding}: {str(e)}")
            
            if html_content is None:
                raise ValueError("Não foi possível abrir o arquivo com nenhuma das codificações tentadas")
            
            # Usar lxml parser que é mais robusto
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Variáveis para armazenar os valores atuais
            centro_custo = ""
            centro_custo_codigo = ""
            plano_conta = ""
            plano_conta_codigo = ""
            dados_linha = {}
            
            # Procurar todas as linhas da tabela
            rows = soup.find_all('tr')
            logger.info(f"Encontradas {len(rows)} linhas para processar")
            
            for row in rows:
                try:
                    # Procurar linhas de centro de custo
                    if 'bgcolor="#efefef"' in str(row) and 'C.Custo' in str(row):
                        cell_text = row.get_text().strip()
                        match = re.search(r'C\.Custo:\s*(\S+)\s*-\s*(.+)', cell_text)
                        if match:
                            centro_custo_codigo = match.group(1).strip()
                            centro_custo = match.group(2).strip()
                    
                    # Procurar linhas de plano de conta
                    elif row.find('td', colspan='3') and '-' in str(row):
                        cell_text = row.get_text().strip()
                        match = re.search(r'(\d+)\s*-\s*(.+)', cell_text)
                        if match:
                            plano_conta_codigo = match.group(1).strip()
                            plano_conta = match.group(2).strip()
                    
                    # Procurar linhas de dados (registros)
                    elif 'bgcolor=""' in str(row):
                        cells = row.find_all('td')
                        if len(cells) >= 11:
                            data_pgto = cells[2].get_text().strip() if len(cells) > 2 else ''
                            documento = cells[3].get_text().strip() if len(cells) > 3 else ''
                            emitente = cells[4].get_text().strip() if len(cells) > 4 else ''
                            db = cells[5].get_text().strip() if len(cells) > 5 else ''
                            historico = cells[6].get_text().strip() if len(cells) > 6 else ''
                            liberado_por = cells[7].get_text().strip() if len(cells) > 7 else ''
                            banco_ag_conta = cells[8].get_text().strip() if len(cells) > 8 else ''
                            cheque = cells[9].get_text().strip() if len(cells) > 9 else ''
                            valor = cells[10].get_text().strip() if len(cells) > 10 else ''
                            pago = cells[11].get_text().strip() if len(cells) > 11 else ''
                            
                            dados_linha = {
                                'centro_custo': centro_custo,
                                'centro_custo_codigo': centro_custo_codigo,
                                'plano_conta': plano_conta,
                                'plano_conta_codigo': plano_conta_codigo,
                                'data_pagamento': data_pgto,
                                'documento': documento,
                                'emitente': emitente,
                                'debito_credito': db,
                                'historico': historico,
                                'liberado_por': liberado_por,
                                'banco': banco_ag_conta,
                                'cheque': cheque,
                                'valor': valor,
                                'pago': pago
                            }
                            dados_extraidos.append(dados_linha)
                except Exception as e:
                    logger.warning(f"Erro ao processar linha: {str(e)}")
                    continue
            
            logger.info(f"Extração concluída. {len(dados_extraidos)} registros encontrados.")
            return dados_extraidos
            
        except Exception as e:
            logger.error(f"Erro ao processar arquivo HTML: {str(e)}", exc_info=True)
            return []
    
    def processar_arquivo_excel(self, arquivo_path: str) -> List[Dict[str, Any]]:
        """
        Processa arquivo Excel (.xls ou .xlsx) e extrai os dados analíticos.
        
        Args:
            arquivo_path: Caminho para o arquivo Excel
            
        Returns:
            Lista de dicionários com os dados extraídos
        """
        logger.info(f"Processando arquivo Excel: {arquivo_path}")
        dados_extraidos = []
        
        try:
            import pandas as pd
            
            # Verificar se pandas está instalado
            if not pd:
                logger.error("Pandas não está instalado. Execute: pip install pandas openpyxl xlrd")
                raise ImportError("Pandas não está instalado")
            
            # Tentar ler o arquivo Excel
            try:
                df = pd.read_excel(arquivo_path, engine='xlrd')
                logger.info(f"Arquivo Excel lido com sucesso usando xlrd")
            except Exception as e1:
                logger.warning(f"Erro ao ler com xlrd: {e1}, tentando com openpyxl")
                try:
                    df = pd.read_excel(arquivo_path, engine='openpyxl')
                    logger.info(f"Arquivo Excel lido com sucesso usando openpyxl")
                except Exception as e2:
                    logger.error(f"Falha ao ler arquivo Excel: {e2}")
                    raise
            
            # Processar os dados do dataframe
            centro_custo = ""
            centro_custo_codigo = ""
            plano_conta = ""
            plano_conta_codigo = ""
            
            # Processar linha por linha para extrair as informações
            for index, row in df.iterrows():
                row_str = str(row)
                
                # Verificar se é linha de centro de custo
                if 'C.Custo' in row_str:
                    for col in df.columns:
                        cell_text = str(row[col])
                        if 'C.Custo' in cell_text:
                            match = re.search(r'C\.Custo:\s*(\S+)\s*-\s*(.+)', cell_text)
                            if match:
                                centro_custo_codigo = match.group(1).strip()
                                centro_custo = match.group(2).strip()
                
                # Verificar se é linha de plano de conta
                elif '-' in row_str and not pd.isna(row.iloc[0]):
                    cell_text = str(row.iloc[0])
                    match = re.search(r'(\d+)\s*-\s*(.+)', cell_text)
                    if match:
                        plano_conta_codigo = match.group(1).strip()
                        plano_conta = match.group(2).strip()
                
                # Verificar se é linha de dados (registros)
                elif len(row) >= 10 and not pd.isna(row.iloc[2]) and not pd.isna(row.iloc[10]):
                    # Extrair dados da linha
                    data_pgto = str(row.iloc[2]) if not pd.isna(row.iloc[2]) else ''
                    documento = str(row.iloc[3]) if not pd.isna(row.iloc[3]) else ''
                    emitente = str(row.iloc[4]) if not pd.isna(row.iloc[4]) else ''
                    db = str(row.iloc[5]) if not pd.isna(row.iloc[5]) else ''
                    historico = str(row.iloc[6]) if not pd.isna(row.iloc[6]) else ''
                    liberado_por = str(row.iloc[7]) if not pd.isna(row.iloc[7]) else ''
                    banco_ag_conta = str(row.iloc[8]) if not pd.isna(row.iloc[8]) else ''
                    cheque = str(row.iloc[9]) if not pd.isna(row.iloc[9]) else ''
                    valor = str(row.iloc[10]) if not pd.isna(row.iloc[10]) else '0'
                    pago = str(row.iloc[11]) if len(row) > 11 and not pd.isna(row.iloc[11]) else ''
                    
                    dados_linha = {
                        'centro_custo': centro_custo,
                        'centro_custo_codigo': centro_custo_codigo,
                        'plano_conta': plano_conta,
                        'plano_conta_codigo': plano_conta_codigo,
                        'data_pagamento': data_pgto,
                        'documento': documento,
                        'emitente': emitente,
                        'debito_credito': db,
                        'historico': historico,
                        'liberado_por': liberado_por,
                        'banco': banco_ag_conta,
                        'cheque': cheque,
                        'valor': valor,
                        'pago': pago
                    }
                    dados_extraidos.append(dados_linha)
            
            logger.info(f"Extração concluída do Excel. {len(dados_extraidos)} registros encontrados.")
            self.logs['dados_analiticos']['mensagem'].append(f"Extração concluída do Excel. {len(dados_extraidos)} registros encontrados.")
            return dados_extraidos
            
        except Exception as e:
            logger.error(f"Erro ao processar arquivo Excel: {str(e)}", exc_info=True)
            self.logs['dados_analiticos']['erro'] = True
            self.logs['dados_analiticos']['erro_mensagem'].append(f"Erro ao processar arquivo Excel: {str(e)}")
            return []
    
    def importar_dados(self, dados_extraidos: List[Dict[str, Any]]) -> int:
        """
        Importa os dados extraídos para o banco de dados.
        
        Args:
            dados_extraidos: Lista de dicionários com os dados a serem importados
            
        Returns:
            Número de registros importados
        """
        logger.info(f"Iniciando importação de {len(dados_extraidos)} registros para o banco de dados")
        self.logs['dados_analiticos']['mensagem'].append(f"Iniciando importação de {len(dados_extraidos)} registros para o banco de dados")
        contador = 0
        

        try:
            DadoAnalitico.query.delete()
            for dados in dados_extraidos:
                # Buscar ou criar centro de custo
                centro_custo = None
                codigo_cc = dados.get('centro_custo_codigo')
                nome_cc = dados.get('centro_custo')
                
                if codigo_cc:
                    centro_custo = CentroCusto.query.filter_by(codigo=codigo_cc).first()
                
                if not centro_custo and nome_cc:
                    centro_custo = CentroCusto.query.filter_by(nome=nome_cc).first()
                    
                    if not centro_custo:
                        # Criar novo centro de custo
                        centro_custo = CentroCusto(
                            codigo=codigo_cc ,
                            nome=nome_cc,
                            descricao=f"Importado automaticamente em {datetime.now().strftime('%d/%m/%Y')}",
                            ativo=True
                        )
                        db.session.add(centro_custo)
                        db.session.flush()  # Obter ID sem commitar
                        logger.info(f"Novo centro de custo criado: {nome_cc}")
                        print(f"Novo centro de custo criado: {nome_cc}")
                
                # Buscar ou criar plano de conta
                plano_conta = None
                nome_pc = dados.get('plano_conta')
                
                if nome_pc:
                    plano_conta = PlanoConta.query.filter_by(codigo=dados.get('plano_conta_codigo')).first()
                    
                    if not plano_conta:
                        # Criar novo plano de conta
                        plano_conta = PlanoConta(
                            codigo=dados.get('plano_conta_codigo'),
                            descricao=nome_pc,
                            ativo=True
                        )
                        db.session.add(plano_conta)
                        db.session.flush()  # Obter ID sem commitar
                        logger.info(f"Novo plano de conta criado: {nome_pc}")
                        print(f"Novo plano de conta criado: {nome_pc}")

                # Criar registro de dado analítico
                data_pagamento = dados.get('data_pagamento')
                if isinstance(data_pagamento, str):
                    try:
                        data_pagamento = datetime.strptime(data_pagamento, '%d/%m/%Y')
                    except ValueError:
                        logger.warning(f"Formato de data inválido: {data_pagamento}")
                        continue
                
                valor = dados.get('valor', 0).replace('R$', '').replace('.', '').replace(',', '.')
                if isinstance(valor, str):
                    try:
                        valor = float(valor)
                    except ValueError:
                        logger.warning(f"Valor não numérico: {valor}")
                        valor = 0
                
                # Verificar se já existe este registro para evitar duplicação
                documento = dados.get('documento', '')
                emitente = unidecode(dados.get('emitente', ''))
                historico = unidecode(dados.get('historico', ''))

                existe = DadoAnalitico.query.filter_by(
                    centro_custo_id=centro_custo.id if centro_custo else None,
                    plano_conta_id=plano_conta.id if plano_conta else None,

                    documento=documento,
                    emitente=emitente,
                    data_pagamento=data_pagamento,
                    valor=valor,
                    historico=historico,
                    cheque=dados.get('cheque', ''),
                ).first()
                
                if existe:
                    #print(f'existe: {existe}')
                    #print(f"Registro já existe: {documento} - {emitente} - {data_pagamento}")
                    logger.debug(f"Registro já existe: {documento} - {emitente} - {data_pagamento}")
                    continue
                
                novo_dado = DadoAnalitico(
                    centro_custo_id=centro_custo.id if centro_custo else None,
                    plano_conta_id=plano_conta.id if plano_conta else None,
                    data_pagamento=data_pagamento,
                    documento=documento,
                    emitente=emitente,
                    debito_credito=unidecode(dados.get('debito_credito', '')), 
                    historico=historico,
                    liberado_por=unidecode(dados.get('liberado_por', '')),
                    banco=unidecode(dados.get('banco', '')),
                    cheque=dados.get('cheque', ''),
                    valor=valor,
                    pago=dados.get('pago', '') == 'Sim',
                    importado_por=self.usuario_id,
                    importado_em=datetime.now()
                )
                with db.session.no_autoflush:
                    db.session.add(novo_dado)
                contador += 1
                
                # Commit a cada 100 registros para não sobrecarregar a memória
                if contador % 500 == 0:
                    db.session.commit()
                    logger.info(f"Progresso: {contador} registros importados")
                    print(f"Progresso: {contador} registros importados")
            
            # Commit final
            db.session.commit()
            logger.info(f"Importação concluída. {contador} registros importados com sucesso.")
            self.logs['dados_analiticos']['mensagem'].append(f"Importação concluída. {contador} registros importados com sucesso.")
            return contador
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao importar dados: {str(e)}", exc_info=True)
            self.logs['dados_analiticos']['erro'] = True
            self.logs['dados_analiticos']['erro_mensagem'].append(f"Erro ao importar dados: {str(e)}")
            return 0
    
    def processar_arquivo_csv(self, arquivo_path: str) -> List[Dict[str, Any]]:
        """
        Processa arquivo CSV extraído e extrai os dados analíticos.
        
        Args:
            arquivo_path: Caminho para o arquivo CSV
            
        Returns:
            Lista de dicionários com os dados extraídos
        """
        logger.info(f"Processando arquivo CSV: {arquivo_path}")
        dados_extraidos = []
        
        try:
            with open(arquivo_path, 'r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                
                for row in reader:
                    dados_linha = {}
                    
                    # Mapear colunas do CSV para os campos do modelo
                    mapeamento = {
                        'centro de custo': 'centro_custo',
                        'centro de custo código': 'centro_custo_codigo',
                        'plano de conta': 'plano_conta',
                        'Data Pgto': 'data_pagamento',
                        'Documento': 'documento',
                        'Emiten': 'emitente',
                        'D/B': 'debito_credito',
                        'Histórico': 'historico',
                        'Liberado Por': 'liberado_por',
                        'Banco / Agência / Conta': 'banco',
                        'Cheque': 'cheque',
                        'Valor (R$)': 'valor',
                        'Pago': 'pago'
                    }
                    
                    for coluna_csv, campo_modelo in mapeamento.items():
                        if coluna_csv in row:
                            valor = row[coluna_csv].strip()
                            
                            # Processar valores específicos
                            if campo_modelo == 'data_pagamento' and valor:
                                try:
                                    # Tentar converter para datetime
                                    if '/' in valor:
                                        dia, mes, ano = valor.split('/')
                                        valor = f"{ano}-{mes}-{dia}"
                                    elif '-' in valor:
                                        ano, mes, dia = valor.split('-')
                                        valor = f"{ano}-{mes}-{dia}"
                                except Exception as e:
                                    logger.warning(f"Erro ao converter data: {valor}, erro: {str(e)}")
                            
                            elif campo_modelo == 'valor' and valor:
                                # Limpar formatação de moeda
                                valor = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
                                try:
                                    valor = float(valor)
                                except ValueError:
                                    logger.warning(f"Valor não numérico: {valor}")
                                    valor = 0.0
                            
                            dados_linha[campo_modelo] = valor
                    
                    # Adicionar à lista se tiver dados relevantes
                    if dados_linha.get('centro_custo') and dados_linha.get('valor'):
                        dados_extraidos.append(dados_linha)
            
            logger.info(f"Extração CSV concluída. {len(dados_extraidos)} registros encontrados.")
            return dados_extraidos
            
        except Exception as e:
            logger.error(f"Erro ao processar arquivo CSV: {str(e)}", exc_info=True)
            return []
    
    def limpar_arquivos_temporarios(self):
        """Remove arquivos temporários criados durante a importação."""
        try:
            for arquivo in os.listdir(self.temp_dir):
                arquivo_path = os.path.join(self.temp_dir, arquivo)
                if os.path.isfile(arquivo_path):
                    os.unlink(arquivo_path)
            
            os.rmdir(self.temp_dir)
            logger.info(f"Diretório temporário removido: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Erro ao limpar arquivos temporários: {str(e)}")

# Funções para usar fora da classe

async def executar_importacao_async(usuario_id: int,logs=None):
    """
    Executa a importação de dados de forma assíncrona.
    
    Args:
        usuario_id: ID do usuário que está realizando a importação
        
    Returns:
        Dicionário com resultados da importação
    """
    importador = ImportadorDadosAnaliticos(usuario_id, logs)
    
    try:
        # Extrair dados
        arquivo = await importador.executar_extracao()
        
        if not arquivo:
            return {
                "sucesso": False,
                "mensagem": "Falha na extração dos dados",
                "registros_importados": 0
            }
        
        # Processar o arquivo
        if arquivo.endswith('.html'):
            dados = await importador.processar_arquivo_html(arquivo)
        elif arquivo.endswith('.xls') or arquivo.endswith('.xlsx'):
            # Assumindo que arquivos XLS são na verdade HTML
            dados = await importador.processar_arquivo_html(arquivo)
        elif arquivo.endswith('.csv'):
            dados = importador.processar_arquivo_csv(arquivo)
        else:
            return {
                "sucesso": False,
                "mensagem": f"Formato de arquivo não suportado: {os.path.basename(arquivo)}",
                "registros_importados": 0
            }
        
        # Importar dados
        if not dados:
            return {
                "sucesso": False,
                "mensagem": "Nenhum dado encontrado para importar",
                "registros_importados": 0
            }
        
        registros_importados = importador.importar_dados(dados)
        
        return {
            "sucesso": True,
            "mensagem": f"{registros_importados} registros importados com sucesso",
            "registros": registros_importados
        }
    except Exception as e:
        logger.error(f"Erro durante importação: {str(e)}", exc_info=True)
        return {
            "sucesso": False,
            "mensagem": f"Erro durante importação: {str(e)}",
            "registros_importados": 0
        }
    finally:
        importador.limpar_arquivos_temporarios()

async def importar_arquivo_local(caminho_arquivo: str, usuario_id: int = None) -> Dict[str, Any]:
    """
    Importa dados de um arquivo local.
    
    Args:
        caminho_arquivo: Caminho completo para o arquivo
        usuario_id: ID do usuário que está executando a importação
        
    Returns:
        Dicionário com resultados da importação
    """
    logger.info(f"Iniciando importação do arquivo local: {caminho_arquivo}")
    
    if not os.path.exists(caminho_arquivo):
        logger.error(f"Arquivo não encontrado: {caminho_arquivo}")
        return {
            'sucesso': False,
            'mensagem': f"Arquivo não encontrado: {caminho_arquivo}",
            'registros': 0
        }
    
    try:
        importador = ImportadorDadosAnaliticos(usuario_id)
        
        # Detectar extensão do arquivo
        _, extensao = os.path.splitext(caminho_arquivo)
        extensao = extensao.lower()
        
        # Processar o arquivo de acordo com sua extensão
        if extensao in ['.xls', '.xlsx']:
            logger.info(f"Processando arquivo Excel: {caminho_arquivo}")
            dados_extraidos = importador.processar_arquivo_excel(caminho_arquivo)
        elif extensao == '.html' or extensao == '.htm':
            logger.info(f"Processando arquivo HTML: {caminho_arquivo}")
            dados_extraidos = await importador.processar_arquivo_html(caminho_arquivo)
        elif extensao == '.csv':
            logger.info(f"Processando arquivo CSV: {caminho_arquivo}")
            dados_extraidos = importador.processar_arquivo_csv(caminho_arquivo)
        else:
            logger.error(f"Formato de arquivo não suportado: {extensao}")
            return {
                'sucesso': False,
                'mensagem': f"Formato de arquivo não suportado: {extensao}",
                'registros': 0
            }
        
        if not dados_extraidos:
            logger.warning("Nenhum dado foi extraído do arquivo.")
            return {
                'sucesso': False,
                'mensagem': "Nenhum dado foi extraído do arquivo.",
                'registros': 0
            }
        
        # Importar dados extraídos para o banco
        registros_importados = importador.importar_dados(dados_extraidos)
        
        # Limpar arquivos temporários
        importador.limpar_arquivos_temporarios()
        
        logger.info(f"Importação concluída com sucesso. {registros_importados} registros importados.")
        return {
            'sucesso': True,
            'mensagem': f"Importação concluída com sucesso. {registros_importados} registros importados.",
            'registros': registros_importados
        }
        
    except Exception as e:
        logger.error(f"Erro durante a importação: {str(e)}", exc_info=True)
        return {
            'sucesso': False,
            'mensagem': f"Erro durante a importação: {str(e)}",
            'registros': 0
        }

async def importar_dados_extraidos(arquivo_csv: str = 'dados_extraidos.csv', usuario_id: int = None) -> Dict[str, Any]:
    """
    Função utilitária para importar os dados do CSV já extraído.
    
    Args:
        arquivo_csv: Caminho para o arquivo CSV (padrão: dados_extraidos.csv)
        usuario_id: ID do usuário que está executando a importação
        
    Returns:
        Resultados da importação
    """
    caminho_absoluto = os.path.abspath(arquivo_csv)
    return await importar_arquivo_local(caminho_absoluto, usuario_id)

if __name__ == "__main__":
    # Configurar logging para execução como script
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Se for executado diretamente, importar o CSV existente
    resultado = importar_dados_extraidos()
    print(f"Resultado da importação: {resultado['mensagem']}") 