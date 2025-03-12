# modulo_integracao_erp/app.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
import os
import tempfile
import shutil
import logging
from datetime import datetime
import re
from bs4 import BeautifulSoup
from playwright.async_api import Playwright, async_playwright, expect
import asyncio
import mysql.connector
from mysql.connector import Error

# Importações das funções centralizadas
from utils.db import get_db_connection, execute_query, get_single_result, insert_data, update_data
from utils.auth import login_obrigatorio, admin_obrigatorio, verificar_login_api, get_user_id
from utils.crypto import decrypt_password

# Configuração de logging centralizada
log_dir = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'integracao_erp.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Criar o Blueprint com um nome único
mod_integracao_erp = Blueprint(
    'integracao_erp', __name__, url_prefix='/integracao_erp')

# Função para conectar ao banco de dados


# Função para baixar arquivos do ERP via Playwright


async def download_erp_report(credentials):
    """
    Faz login no ERP SOX e baixa o relatório de Custo Analítico

    Args:
        credentials (dict): Dicionário com credenciais e configurações
            - username: Nome de usuário
            - password: Senha
            - periodo: Período do relatório (opcional)
            - output_path: Caminho para salvar o arquivo (opcional)
            - headless: Se True, executa navegador sem interface (opcional)

    Returns:
        str: Caminho para o arquivo baixado ou None em caso de erro
    """
    try:
        output_path = credentials.get('output_path', 'base.xls')

        async with async_playwright() as p:
            # Iniciar o navegador (com modo headless configurável)
            browser = await p.chromium.launch(
                headless=False
            )

            # Configurar a página com timeout adequado
            page = await browser.new_page(
                viewport={'width': 1280, 'height': 800}
            )

            # Acessar página de login
            await page.goto("https://www.sox.com.br/")

            # Login com credenciais
            login_frame = page.locator("iframe[name=\"login\"]").content_frame
            await login_frame.locator("input[name=\"login\"]").fill(
                credentials.get('username', 'leandrofor'))
            await login_frame.locator("input[name=\"senha\"]").fill(
                credentials.get('password', 'netto$%'))
            await login_frame.get_by_role("button", name="Acessar").click()

            # Acessar menu Financeiro > Custo Analítico
            menu_frame = page.locator("iframe[name=\"menu\"]").content_frame
            await menu_frame.get_by_text("FINANCEIRO").click()
            await menu_frame.get_by_text("Custo Analítico").click()

            # Filtrar e baixar relatório em Excel
            content_frame = await page.locator("frame[name=\"conteudo\"]").content_frame
            await content_frame.get_by_role("link", name="Filtrar").click()

            # Configurar período do relatório, se fornecido
            if credentials.get('periodo'):
                # Adicionar lógica para selecionar período específico
                # Esta parte depende da interface específica do ERP
                pass

            # Esperar pelo download
            download_promise = page.wait_for_event('download')
            await content_frame.get_by_role("link", name="Relatório Excel").click()
            download = await download_promise

            # Salvar o arquivo
            await download.save_as(output_path)

            # Fechar o navegador
            await browser.close()

            return output_path

    except Exception as e:
        logger.error(f"Erro na automação do ERP: {str(e)}", exc_info=True)
        return None

# Função para extrair dados do arquivo XLS (formato HTML)


def extrair_dados_xls(arquivo_path):
    """
    Extrai dados do arquivo XLS em formato HTML

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
                    valor_text = re.sub(r'[^\d.,]', '', valor_text).replace(
                        '.', '').replace(',', '.')

                    if valor_text.strip() and float(valor_text) > 0:
                        registros += 1

                        # Coletar dados
                        data = cell_texts[indices['data_pagamento']] if indices['data_pagamento'] < len(
                            cell_texts) else ""
                        documento = cell_texts[indices['documento']] if indices['documento'] < len(
                            cell_texts) else ""
                        emitente = cell_texts[indices['emitente']] if indices['emitente'] < len(
                            cell_texts) else ""
                        historico = cell_texts[indices['historico']] if indices['historico'] < len(
                            cell_texts) else ""
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

        logger.info(
            f"Processamento concluído: {registros} registros extraídos")
        return dados

    except Exception as e:
        logger.error(f"Erro ao extrair dados do arquivo: {str(e)}")
        return dados

# Função para salvar os dados no banco de dados


def salvar_dados_no_banco(dados):
    """
    Salva os dados extraídos no banco de dados

    Args:
        dados (list): Lista de dicionários com os dados a serem salvos

    Returns:
        tuple: (sucesso, mensagem, contador)
    """
    if not dados:
        return False, "Nenhum dado para importar", 0

    connection = get_db_connection()
    if not connection:
        return False, "Erro de conexão com o banco de dados", 0

    try:
        cursor = connection.cursor()

        # Criar tabela se não existir
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS erp_transacoes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                centro_custo VARCHAR(20) NOT NULL,
                categoria VARCHAR(20),
                data_pagamento VARCHAR(50),
                documento VARCHAR(100),
                emitente VARCHAR(255),
                historico TEXT,
                valor DECIMAL(15,2) NOT NULL,
                data_processamento DATETIME NOT NULL,
                importado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Inserir os dados
        records_insert = 0
        for registro in dados:
            try:
                cursor.execute("""
                    INSERT INTO erp_transacoes (
                        centro_custo, categoria, data_pagamento, documento, 
                        emitente, historico, valor, data_processamento
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    registro['centro_custo'],
                    registro['categoria'],
                    registro['data_pagamento'],
                    registro['documento'],
                    registro['emitente'],
                    registro['historico'],
                    registro['valor'],
                    registro['data_processamento']
                ))
                records_insert += 1
            except Exception as e:
                logger.error(f"Erro ao inserir registro: {str(e)}")

        connection.commit()
        cursor.close()
        connection.close()

        return True, f"{records_insert} registros importados com sucesso", records_insert

    except Exception as e:
        connection.rollback()
        cursor.close()
        connection.close()
        logger.error(f"Erro ao salvar dados no banco: {str(e)}")
        return False, f"Erro ao salvar dados: {str(e)}", 0

# Funções auxiliares para gerenciar importação


def registrar_importacao_iniciada(usuario_id):
    """Registra o início de uma importação no banco de dados"""
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO erp_importacoes 
            (usuario_id, tipo, data_inicio, status)
            VALUES (%s, 'AUTOMATICA', NOW(), 'ERRO')
        """, [usuario_id])
        importacao_id = cursor.lastrowid
        connection.commit()
        return importacao_id
    except Exception as e:
        logger.error(f"Erro ao registrar importação: {e}")
        return None
    finally:
        if connection:
            connection.close()


def registrar_importacao_finalizada(importacao_id, status, mensagem, total_registros=0, valor_total=0):
    """Atualiza o registro de importação com o resultado"""
    if not importacao_id:
        return

    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE erp_importacoes 
            SET status = %s, 
                mensagem = %s,
                total_registros = %s,
                valor_total = %s,
                data_fim = NOW()
            WHERE id = %s
        """, [status, mensagem, total_registros, valor_total, importacao_id])
        connection.commit()
    except Exception as e:
        logger.error(f"Erro ao finalizar importação: {e}")
    finally:
        if connection:
            connection.close()


def limpar_arquivos_temporarios(arquivo_path):
    """Remove arquivos e diretórios temporários"""
    try:
        if os.path.exists(arquivo_path):
            temp_dir = os.path.dirname(arquivo_path)
            if os.path.exists(arquivo_path):
                os.remove(arquivo_path)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    except Exception as e:
        logger.error(f"Erro ao limpar arquivos temporários: {e}")

# Rota principal - dashboard de integração


@mod_integracao_erp.route('/')
@login_obrigatorio
def index():
    # Obter estatísticas
    estatisticas = {
        'total_transacoes': 0,
        'total_hoje': 0,
        'valor_total': 0,
        'centro_custos': 0
    }

    try:
        # Total de transações
        result = get_single_result(
            "SELECT COUNT(*) as total FROM erp_transacoes")
        if result:
            estatisticas['total_transacoes'] = result['total']

        # Transações importadas hoje
        result = get_single_result(
            "SELECT COUNT(*) as total FROM erp_transacoes WHERE DATE(importado_em) = CURDATE()")
        if result:
            estatisticas['total_hoje'] = result['total']

        # Valor total
        result = get_single_result(
            "SELECT SUM(valor) as total FROM erp_transacoes")
        if result and result['total']:
            estatisticas['valor_total'] = result['total']

        # Centros de custo
        result = get_single_result(
            "SELECT COUNT(DISTINCT centro_custo) as total FROM erp_transacoes")
        if result:
            estatisticas['centro_custos'] = result['total']
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {str(e)}")

    return render_template('integracao_erp/index.html', estatisticas=estatisticas)

# Rota para importação manual


@mod_integracao_erp.route('/importar_manual', methods=['GET', 'POST'])
@login_obrigatorio
def importar_manual():
    if request.method == 'POST':
        # Verificar se foi enviado um arquivo
        if 'arquivo_xls' not in request.files:
            flash('Nenhum arquivo selecionado', 'warning')
            return redirect(request.url)

        arquivo = request.files['arquivo_xls']

        if arquivo.filename == '':
            flash('Nenhum arquivo selecionado', 'warning')
            return redirect(request.url)

        # Verificar extensão do arquivo
        if not arquivo.filename.lower().endswith('.xls'):
            flash('Apenas arquivos .xls são permitidos', 'warning')
            return redirect(request.url)

        try:
            # Registrar início da importação
            importacao_id = registrar_importacao_iniciada(get_user_id())

            # Criar diretório temporário
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, "arquivo_importacao.xls")

            # Salvar o arquivo
            arquivo.save(file_path)

            # Processar o arquivo
            dados = extrair_dados_xls(file_path)

            # Salvar os dados no banco
            sucesso, mensagem, records_insert = salvar_dados_no_banco(dados)

            # Atualizar registro de importação
            status = 'SUCESSO' if sucesso else 'ERRO'
            valor_total = sum(d['valor'] for d in dados) if dados else 0
            registrar_importacao_finalizada(
                importacao_id, status, mensagem, len(dados), valor_total)

            # Limpar arquivos temporários
            limpar_arquivos_temporarios(file_path)

            if sucesso:
                flash(mensagem, 'success')
            else:
                flash(mensagem, 'danger')

        except Exception as e:
            flash(f'Erro durante a importação: {str(e)}', 'danger')
            if 'importacao_id' in locals():
                registrar_importacao_finalizada(importacao_id, 'ERRO', str(e))

    return render_template('integracao_erp/importar_manual.html')

# Rota para importação automática


@mod_integracao_erp.route('/importar_automatico', methods=['GET', 'POST'])
@admin_obrigatorio
async def importar_automatico():
    if request.method == 'POST':
        # Obter credenciais do formulário
        credentials = {
            'username': request.form.get('usuario'),
            'password': request.form.get('senha'),
            'headless': request.form.get('modo_headless') == 'on',
            'periodo': request.form.get('periodo', 'atual'),
            'output_path': os.path.join(tempfile.mkdtemp(), 'relatorio_erp.xls')
        }

        try:
            # Registrar início da importação
            importacao_id = registrar_importacao_iniciada(get_user_id())

            # Baixar o arquivo do ERP
            arquivo_path = await download_erp_report(credentials)

            if not arquivo_path:
                flash('Não foi possível baixar o arquivo do ERP', 'danger')
                registrar_importacao_finalizada(
                    importacao_id, 'ERRO', 'Falha no download do arquivo')
                return redirect(request.url)

            # Processar o arquivo
            dados = extrair_dados_xls(arquivo_path)

            # Salvar os dados no banco
            sucesso, mensagem, records_insert = salvar_dados_no_banco(dados)

            # Atualizar registro de importação
            status = 'SUCESSO' if sucesso else 'ERRO'
            valor_total = sum(d['valor'] for d in dados) if dados else 0
            registrar_importacao_finalizada(
                importacao_id, status, mensagem, len(dados), valor_total)

            # Limpar arquivos temporários
            limpar_arquivos_temporarios(arquivo_path)

            if sucesso:
                flash(
                    f'Importação automática concluída: {mensagem}', 'success')
            else:
                flash(f'Erro durante a importação: {mensagem}', 'danger')

        except Exception as e:
            flash(f'Erro durante a importação automática: {str(e)}', 'danger')
            if 'importacao_id' in locals():
                registrar_importacao_finalizada(importacao_id, 'ERRO', str(e))

    return render_template('integracao_erp/importar_automatico.html')

# Rota para listar as transações


@mod_integracao_erp.route('/transacoes', methods=['GET'])
@login_obrigatorio
def listar_transacoes():
    # Parâmetros de filtro
    filtro_centro_custo = request.args.get('centro_custo', '')
    filtro_categoria = request.args.get('categoria', '')
    filtro_emitente = request.args.get('emitente', '')
    filtro_data_inicio = request.args.get('data_inicio', '')
    filtro_data_fim = request.args.get('data_fim', '')

    transacoes = []
    centros_custo = []
    categorias = []

    try:
        # Obter lista de centros de custo para o filtro
        centros_custo_results = execute_query(
            "SELECT DISTINCT centro_custo FROM erp_transacoes ORDER BY centro_custo")
        if centros_custo_results:
            centros_custo = [row['centro_custo']
                             for row in centros_custo_results]

        # Obter lista de categorias para o filtro
        categorias_results = execute_query(
            "SELECT DISTINCT categoria FROM erp_transacoes WHERE categoria IS NOT NULL ORDER BY categoria")
        if categorias_results:
            categorias = [row['categoria'] for row in categorias_results]

        # Construir a consulta SQL com filtros
        query = """
            SELECT * FROM erp_transacoes 
            WHERE 1=1
        """
        params = []

        if filtro_centro_custo:
            query += " AND centro_custo = %s"
            params.append(filtro_centro_custo)

        if filtro_categoria:
            query += " AND categoria = %s"
            params.append(filtro_categoria)

        if filtro_emitente:
            query += " AND emitente LIKE %s"
            params.append(f'%{filtro_emitente}%')

        if filtro_data_inicio:
            query += " AND data_pagamento >= %s"
            params.append(filtro_data_inicio)

        if filtro_data_fim:
            query += " AND data_pagamento <= %s"
            params.append(filtro_data_fim)

        query += " ORDER BY data_pagamento DESC LIMIT 1000"

        # Executar a consulta
        transacoes = execute_query(query, params)
        if transacoes is None:
            transacoes = []
    except Exception as e:
        logger.error(f"Erro ao listar transações: {str(e)}")
        flash(f'Erro ao carregar transações: {str(e)}', 'danger')

    return render_template('integracao_erp/transacoes.html',
                           transacoes=transacoes,
                           centros_custo=centros_custo,
                           categorias=categorias,
                           filtros={
                               'centro_custo': filtro_centro_custo,
                               'categoria': filtro_categoria,
                               'emitente': filtro_emitente,
                               'data_inicio': filtro_data_inicio,
                               'data_fim': filtro_data_fim
                           })

# Rota para visualizar detalhes de uma transação


@mod_integracao_erp.route('/transacoes/<int:id>')
@login_obrigatorio
def visualizar_transacao(id):
    transacao = get_single_result(
        "SELECT * FROM erp_transacoes WHERE id = %s", (id,))

    if not transacao:
        flash('Transação não encontrada', 'warning')
        return redirect(url_for('integracao_erp.listar_transacoes'))

    return render_template('integracao_erp/visualizar_transacao.html', transacao=transacao)

# Rota para relatórios analíticos


@mod_integracao_erp.route('/relatorios')
@login_obrigatorio
def relatorios():
    return render_template('integracao_erp/relatorios.html')

# API para dados do relatório por centro de custo


@mod_integracao_erp.route('/api/dados_centro_custo')
def api_dados_centro_custo():
    logado, resposta = verificar_login_api()
    if not logado:
        return resposta

    try:
        # Dados por centro de custo
        dados = execute_query("""
            SELECT 
                centro_custo as rotulo,
                COUNT(*) as total_transacoes,
                SUM(valor) as valor_total
            FROM erp_transacoes
            GROUP BY centro_custo
            ORDER BY valor_total DESC
            LIMIT 10
        """)

        # Converter valores para float para serialização JSON
        if dados:
            for item in dados:
                if 'valor_total' in item and hasattr(item['valor_total'], 'as_integer_ratio'):
                    item['valor_total'] = float(item['valor_total'])

        return jsonify({'data': dados or []})
    except Exception as e:
        logger.error(f"Erro ao buscar dados por centro de custo: {e}")
        return jsonify({'error': str(e), 'data': []}), 500

# API para dados do relatório por categoria


@mod_integracao_erp.route('/api/dados_categoria')
def api_dados_categoria():
    logado, resposta = verificar_login_api()
    if not logado:
        return resposta

    try:
        # Dados por categoria
        dados = execute_query("""
            SELECT 
                IFNULL(categoria, 'Sem categoria') as rotulo,
                COUNT(*) as total_transacoes,
                SUM(valor) as valor_total
            FROM erp_transacoes
            GROUP BY categoria
            ORDER BY valor_total DESC
            LIMIT 10
        """)

        # Converter valores para float para serialização JSON
        if dados:
            for item in dados:
                if 'valor_total' in item and hasattr(item['valor_total'], 'as_integer_ratio'):
                    item['valor_total'] = float(item['valor_total'])

        return jsonify({'data': dados or []})
    except Exception as e:
        logger.error(f"Erro ao buscar dados por categoria: {e}")
        return jsonify({'error': str(e), 'data': []}), 500

# API para listar histórico de importações


@mod_integracao_erp.route('/api/importacoes')
def api_importacoes():
    logado, resposta = verificar_login_api()
    if not logado:
        return resposta

    try:
        # Obter histórico de importações
        dados = execute_query("""
            SELECT i.*, u.nome as usuario_nome 
            FROM erp_importacoes i
            LEFT JOIN usuarios u ON i.usuario_id = u.id
            ORDER BY i.data_inicio DESC
            LIMIT 10
        """)

        # Converter valores para tipos apropriados para serialização JSON
        if dados:
            for item in dados:
                if 'data_inicio' in item and item['data_inicio']:
                    item['data_inicio'] = item['data_inicio'].strftime(
                        '%Y-%m-%d %H:%M:%S')
                if 'data_fim' in item and item['data_fim']:
                    item['data_fim'] = item['data_fim'].strftime(
                        '%Y-%m-%d %H:%M:%S')
                if 'valor_total' in item and hasattr(item['valor_total'], 'as_integer_ratio'):
                    item['valor_total'] = float(item['valor_total'])

        return jsonify({'data': dados or []})
    except Exception as e:
        logger.error(f"Erro ao buscar histórico de importações: {e}")
        return jsonify({'error': str(e), 'data': []}), 500

# Rota para importação programada


@mod_integracao_erp.route('/importar_programado', methods=['GET', 'POST'])
@login_obrigatorio
def importar_programado():
    # Buscar a última importação
    ultima_importacao = None

    try:
        # Buscar o último registro de importação
        resultado = get_single_result("""
            SELECT i.*, u.nome as usuario_nome 
            FROM erp_importacoes i
            LEFT JOIN usuarios u ON i.usuario_id = u.id
            ORDER BY i.data_inicio DESC
            LIMIT 1
        """)

        if resultado:
            # Formatar data para exibição
            if resultado['data_inicio']:
                resultado['data_inicio'] = resultado['data_inicio'].strftime(
                    '%d/%m/%Y %H:%M')
            if resultado['data_fim']:
                resultado['data_fim'] = resultado['data_fim'].strftime(
                    '%d/%m/%Y %H:%M')

            ultima_importacao = resultado
    except Exception as e:
        logger.error(f"Erro ao buscar última importação: {e}")

    return render_template('integracao_erp/importar_programado.html', ultima_importacao=ultima_importacao)

# Nova rota para executar a importação programada


@mod_integracao_erp.route('/executar_importacao_programada', methods=['POST'])
@login_obrigatorio
def executar_importacao_programada():
    usuario_id = get_user_id()

    try:
        # Buscar configuração ativa para o usuário
        config = get_single_result("""
            SELECT c.*, cr.usuario, cr.senha_encriptada
            FROM erp_configuracoes c
            JOIN erp_credenciais cr ON c.id = cr.configuracao_id
            WHERE c.criado_por = %s AND c.ativo = 1
            LIMIT 1
        """, [usuario_id])

        if not config:
            flash(
                'Não foram encontradas credenciais salvas para importação automática', 'warning')
            return redirect(url_for('integracao_erp.importar_programado'))

        # Decriptografar a senha usando a função centralizada
        senha_descriptografada = decrypt_password(config['senha_encriptada'])

        # Configurar credenciais
        credentials = {
            'username': config['usuario'],
            'password': senha_descriptografada,
            'headless': True,  # Sempre executar em modo headless
            'periodo': config['periodo'],
            'output_path': os.path.join(tempfile.mkdtemp(), 'relatorio_erp.xls'),
            'url_login': config['url_login'],
            'url_relatorio': config['url_relatorio'],
        }

        # Executar em um thread separado ou usar asyncio.run
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        output_path = loop.run_until_complete(download_erp_report(credentials))
        loop.close()

        if not output_path or not os.path.exists(output_path):
            flash('Falha ao baixar relatório do ERP', 'danger')
            logger.error("Falha ao baixar relatório do ERP")
            return redirect(url_for('integracao_erp.importar_programado'))

        # Processar o arquivo
        dados = extrair_dados_xls(output_path)

        if not dados:
            flash('Nenhum dado encontrado no relatório', 'warning')
            return redirect(url_for('integracao_erp.importar_programado'))

        # Contagem de registros processados
        registros_processados = len(dados)
        resultado = salvar_dados_no_banco(dados)
        registros_inseridos = resultado[2] if isinstance(
            resultado, tuple) and len(resultado) > 2 else 0

        # Registrar a importação
        importacao_id = insert_data('erp_importacoes', {
            'configuracao_id': config['id'],
            'usuario_id': usuario_id,
            'data_importacao': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'total_registros': registros_processados,
            'registros_processados': registros_inseridos,
            'status': 'concluido',
            'arquivo': output_path,
        })

        flash(
            f'Importação concluída com sucesso! {registros_inseridos} de {registros_processados} registros processados.', 'success')

        # Limpar o arquivo temporário
        try:
            os.remove(output_path)
            os.rmdir(os.path.dirname(output_path))
        except Exception as e:
            logger.warning(f"Erro ao remover arquivo temporário: {str(e)}")

        return redirect(url_for('integracao_erp.visualizar_importacao', importacao_id=importacao_id))

    except Exception as e:
        logger.error(
            f"Erro ao executar importação programada: {str(e)}", exc_info=True)
        flash(f'Erro ao executar importação programada: {str(e)}', 'danger')
        return redirect(url_for('integracao_erp.importar_programado'))

# Função para descriptografar senha (implemente de acordo com seu sistema)


# Configuração inicial do módulo


def init_app(app):
    """
    Função para inicializar o módulo com a aplicação Flask
    """
    # Não registramos o Blueprint aqui, pois ele será registrado no app principal

    @app.context_processor
    def inject_menu_data():
        return {
            'modulo_integracao_erp': True
        }

    # Configurar rotas específicas do módulo que precisam ser registradas diretamente no app
    @app.route('/integracao_erp/executar_importacao_automatica', methods=['POST'])
    async def executar_importacao_automatica():
        # Utilizando a função centralizada para verificar autenticação
        if 'usuario_id' not in session:
            return jsonify({'success': False, 'message': 'Não autorizado. Faça login para continuar.'}), 401

        if session.get('cargo') != 'admin':
            return jsonify({'success': False, 'message': 'Acesso negado. Permissão de administrador necessária.'}), 403

        credentials = {
            'username': request.form.get('usuario'),
            'password': request.form.get('senha'),
            'headless': request.form.get('modo_headless') == 'on',
            'periodo': request.form.get('periodo', 'atual'),
            'output_path': os.path.join(tempfile.mkdtemp(), 'relatorio_erp.xls')
        }

        importacao_id = registrar_importacao_iniciada(get_user_id())

        try:
            # Função assíncrona para executar a importação em background
            async def execute_import():
                try:
                    # Baixar arquivo do ERP
                    logger.info("Iniciando download do relatório do ERP...")
                    arquivo_path = await download_erp_report(credentials)

                    if not arquivo_path or not os.path.exists(arquivo_path):
                        logger.error("Falha ao baixar o arquivo")
                        registrar_importacao_finalizada(
                            importacao_id, 'ERRO', 'Falha no download do arquivo')
                        return

                    logger.info(f"Arquivo baixado: {arquivo_path}")

                    # Processar o arquivo
                    dados = extrair_dados_xls(arquivo_path)

                    if not dados:
                        logger.warning("Nenhum dado encontrado no arquivo")
                        registrar_importacao_finalizada(
                            importacao_id, 'ERRO', 'Nenhum dado encontrado no arquivo')
                        return

                    # Salvar no banco
                    sucesso, mensagem, records_insert = salvar_dados_no_banco(
                        dados)

                    # Atualizar registro
                    status = 'SUCESSO' if sucesso else 'ERRO'
                    valor_total = sum(d['valor']
                                      for d in dados) if dados else 0
                    registrar_importacao_finalizada(
                        importacao_id, status, mensagem, len(dados), valor_total)

                    # Limpar arquivos
                    limpar_arquivos_temporarios(arquivo_path)

                    logger.info(f"Importação programada concluída: {mensagem}")

                except Exception as e:
                    logger.error(
                        f"Erro na execução da importação: {str(e)}", exc_info=True)
                    registrar_importacao_finalizada(
                        importacao_id, 'ERRO', str(e))

            # Iniciar a tarefa em background
            asyncio.create_task(execute_import())

            return jsonify({
                'success': True,
                'message': 'Importação iniciada em segundo plano',
                'importacao_id': importacao_id
            })

        except Exception as e:
            logger.error(f"Erro ao iniciar importação: {str(e)}")
            registrar_importacao_finalizada(importacao_id, 'ERRO', str(e))
            return jsonify({'success': False, 'message': str(e)}), 500

    return app
