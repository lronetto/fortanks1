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

# Configuração de logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('integracao_erp.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('integracao_erp')

# Configuração do Blueprint
mod_integracao_erp = Blueprint('integracao_erp', __name__,
                               template_folder='templates',
                               static_folder='static')

# Função para conectar ao banco de dados


def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'sistema_solicitacoes'),
            user=os.environ.get('DB_USER', 'root'),
            password=os.environ.get('DB_PASSWORD', 'sua_senha')
        )
        return connection
    except Error as e:
        logger.error(f"Erro ao conectar ao MySQL: {e}")
        return None

# Função para baixar arquivos do ERP via Playwright


async def download_xls_from_erp(credenciais):
    """
    Faz login no ERP e baixa os arquivos XLS necessários

    Args:
        credenciais (dict): Dicionário com credenciais de acesso ao ERP

    Returns:
        str: Caminho para o arquivo baixado ou None em caso de erro
    """
    temp_dir = tempfile.mkdtemp()
    downloaded_file = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
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
            # time.sleep(10)

            async with page.expect_download() as download_info:
                async with page.expect_popup() as page1_info:
                    downloadPromise = page.wait_for_event('download')
                    await page.locator("frame[name=\"conteudo\"]").content_frame.get_by_role(
                        "link", name="Relatório Excel").click()
                    download = await downloadPromise
                    await download.save_as('base.xls')
                    # page.on('download', download=> download.path().then(console.log))
                page1 = page1_info.value
            download = download_info.value

            return downloaded_file

    except Exception as e:
        logger.error(f"Erro ao baixar arquivo do ERP: {str(e)}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
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
        tuple: (sucesso, mensagem)
    """
    if not dados:
        return False, "Nenhum dado para importar"

    connection = get_db_connection()
    if not connection:
        return False, "Erro de conexão com o banco de dados"

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

        return True, f"{records_insert} registros importados com sucesso"

    except Exception as e:
        connection.rollback()
        cursor.close()
        connection.close()
        logger.error(f"Erro ao salvar dados no banco: {str(e)}")
        return False, f"Erro ao salvar dados: {str(e)}"

# Rota principal - dashboard de integração


@mod_integracao_erp.route('/')
def index():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    # Obter estatísticas
    connection = get_db_connection()
    estatisticas = {
        'total_transacoes': 0,
        'total_hoje': 0,
        'valor_total': 0,
        'centro_custos': 0
    }

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Total de transações
            cursor.execute("SELECT COUNT(*) as total FROM erp_transacoes")
            resultado = cursor.fetchone()
            estatisticas['total_transacoes'] = resultado['total'] if resultado else 0

            # Transações importadas hoje
            cursor.execute(
                "SELECT COUNT(*) as total FROM erp_transacoes WHERE DATE(importado_em) = CURDATE()")
            resultado = cursor.fetchone()
            estatisticas['total_hoje'] = resultado['total'] if resultado else 0

            # Valor total
            cursor.execute("SELECT SUM(valor) as total FROM erp_transacoes")
            resultado = cursor.fetchone()
            estatisticas['valor_total'] = resultado['total'] if resultado and resultado['total'] else 0

            # Centros de custo
            cursor.execute(
                "SELECT COUNT(DISTINCT centro_custo) as total FROM erp_transacoes")
            resultado = cursor.fetchone()
            estatisticas['centro_custos'] = resultado['total'] if resultado else 0

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {str(e)}")
        finally:
            connection.close()

    return render_template('integracao_erp/index.html', estatisticas=estatisticas)

# Rota para importação manual


@mod_integracao_erp.route('/importar_manual', methods=['GET', 'POST'])
def importar_manual():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

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
            # Criar diretório temporário
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, "arquivo_importacao.xls")

            # Salvar o arquivo
            arquivo.save(file_path)

            # Processar o arquivo
            dados = extrair_dados_xls(file_path)

            # Salvar os dados no banco
            sucesso, mensagem = salvar_dados_no_banco(dados)

            # Limpar arquivos temporários
            shutil.rmtree(temp_dir)

            if sucesso:
                flash(mensagem, 'success')
            else:
                flash(mensagem, 'danger')

        except Exception as e:
            flash(f'Erro durante a importação: {str(e)}', 'danger')

    return render_template('integracao_erp/importar_manual.html')

# Rota para importação automática


@mod_integracao_erp.route('/importar_automatico', methods=['GET', 'POST'])
def importar_automatico():
    if 'logado' not in session or session['cargo'] != 'admin':
        flash('Acesso restrito para administradores', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        # Obter credenciais do formulário
        credenciais = {
            'url_login': request.form.get('url_login'),
            'usuario': request.form.get('usuario'),
            'senha': request.form.get('senha'),
            'url_relatorio': request.form.get('url_relatorio'),
            'tipo_relatorio': request.form.get('tipo_relatorio'),
            'periodo': request.form.get('periodo')
        }

        # Verificar se todos os campos foram preenchidos
        if not all([credenciais['url_login'], credenciais['usuario'], credenciais['senha'], credenciais['url_relatorio']]):
            flash('Todos os campos são obrigatórios', 'warning')
            return redirect(request.url)

        try:
            # Baixar o arquivo do ERP
            arquivo_path = download_xls_from_erp(credenciais)

            if not arquivo_path:
                flash('Não foi possível baixar o arquivo do ERP', 'danger')
                return redirect(request.url)

            # Processar o arquivo
            dados = extrair_dados_xls(arquivo_path)

            # Salvar os dados no banco
            sucesso, mensagem = salvar_dados_no_banco(dados)

            # Limpar arquivos temporários
            if os.path.exists(os.path.dirname(arquivo_path)):
                shutil.rmtree(os.path.dirname(arquivo_path))

            if sucesso:
                flash(mensagem, 'success')
            else:
                flash(mensagem, 'danger')

        except Exception as e:
            flash(f'Erro durante a importação automática: {str(e)}', 'danger')

    return render_template('integracao_erp/importar_automatico.html')

# Rota para listar as transações


@mod_integracao_erp.route('/transacoes', methods=['GET'])
def listar_transacoes():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    # Parâmetros de filtro
    filtro_centro_custo = request.args.get('centro_custo', '')
    filtro_categoria = request.args.get('categoria', '')
    filtro_emitente = request.args.get('emitente', '')
    filtro_data_inicio = request.args.get('data_inicio', '')
    filtro_data_fim = request.args.get('data_fim', '')

    connection = get_db_connection()
    transacoes = []
    centros_custo = []
    categorias = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Obter lista de centros de custo para o filtro
            cursor.execute(
                "SELECT DISTINCT centro_custo FROM erp_transacoes ORDER BY centro_custo")
            centros_custo = [row['centro_custo'] for row in cursor.fetchall()]

            # Obter lista de categorias para o filtro
            cursor.execute(
                "SELECT DISTINCT categoria FROM erp_transacoes WHERE categoria IS NOT NULL ORDER BY categoria")
            categorias = [row['categoria'] for row in cursor.fetchall()]

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
            cursor.execute(query, params)
            transacoes = cursor.fetchall()

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao listar transações: {str(e)}")
            flash(f'Erro ao carregar transações: {str(e)}', 'danger')
        finally:
            connection.close()

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
def visualizar_transacao(id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    connection = get_db_connection()
    transacao = None

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar transação pelo ID
            cursor.execute("SELECT * FROM erp_transacoes WHERE id = %s", (id,))
            transacao = cursor.fetchone()

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao buscar transação: {str(e)}")
            flash(f'Erro ao carregar transação: {str(e)}', 'danger')
        finally:
            connection.close()

    if not transacao:
        flash('Transação não encontrada', 'warning')
        return redirect(url_for('integracao_erp.listar_transacoes'))

    return render_template('integracao_erp/visualizar_transacao.html', transacao=transacao)

# Rota para relatórios analíticos


@mod_integracao_erp.route('/relatorios')
def relatorios():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    return render_template('integracao_erp/relatorios.html')

# API para dados do relatório por centro de custo


@mod_integracao_erp.route('/api/dados_centro_custo')
def api_dados_centro_custo():
    if 'logado' not in session:
        return jsonify({'error': 'Não autorizado', 'data': []}), 401

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Erro de conexão com o banco de dados', 'data': []}), 500

    try:
        cursor = connection.cursor(dictionary=True)

        # Dados por centro de custo
        cursor.execute("""
            SELECT 
                centro_custo as rotulo,
                COUNT(*) as total_transacoes,
                SUM(valor) as valor_total
            FROM erp_transacoes
            GROUP BY centro_custo
            ORDER BY valor_total DESC
            LIMIT 10
        """)

        dados = cursor.fetchall()

        # Converter valores para float para serialização JSON
        for item in dados:
            if 'valor_total' in item and hasattr(item['valor_total'], 'as_integer_ratio'):
                item['valor_total'] = float(item['valor_total'])

        cursor.close()
        connection.close()

        return jsonify({'data': dados})
    except Exception as e:
        logger.error(f"Erro ao buscar dados por centro de custo: {e}")
        if connection:
            connection.close()
        return jsonify({'error': str(e), 'data': []}), 500

# API para dados do relatório por categoria


@mod_integracao_erp.route('/api/dados_categoria')
def api_dados_categoria():
    if 'logado' not in session:
        return jsonify({'error': 'Não autorizado', 'data': []}), 401

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Erro de conexão com o banco de dados', 'data': []}), 500

    try:
        cursor = connection.cursor(dictionary=True)

        # Dados por categoria
        cursor.execute("""
            SELECT 
                IFNULL(categoria, 'Sem categoria') as rotulo,
                COUNT(*) as total_transacoes,
                SUM(valor) as valor_total
            FROM erp_transacoes
            GROUP BY categoria
            ORDER BY valor_total DESC
            LIMIT 10
        """)

        dados = cursor.fetchall()

        # Converter valores para float para serialização JSON
        for item in dados:
            if 'valor_total' in item and hasattr(item['valor_total'], 'as_integer_ratio'):
                item['valor_total'] = float(item['valor_total'])

        cursor.close()
        connection.close()

        return jsonify({'data': dados})
    except Exception as e:
        logger.error(f"Erro ao buscar dados por categoria: {e}")
        if connection:
            connection.close()
        return jsonify({'error': str(e), 'data': []}), 500

# Configuração inicial do módulo


def init_app(app):
    # Registrar o blueprint
    app.register_blueprint(mod_integracao_erp, url_prefix='/integracao_erp')

    # Adicionar item ao menu principal
    @app.context_processor
    def inject_menu_data():
        menu_items = []
        if 'logado' in session:
            menu_items = [
                {'name': 'Dashboard', 'url': url_for(
                    'dashboard'), 'icon': 'fas fa-tachometer-alt'},
                {'name': 'Solicitações', 'url': url_for(
                    'dashboard'), 'icon': 'fas fa-clipboard-list'},
                {'name': 'Notas Fiscais', 'url': url_for(
                    'importacao_nf.index'), 'icon': 'fas fa-file-invoice'},
                {'name': 'Integração ERP', 'url': url_for(
                    'integracao_erp.index'), 'icon': 'fas fa-sync'},
                {'name': 'Relatórios', 'url': url_for(
                    'relatorios'), 'icon': 'fas fa-chart-bar'},
            ]
        return {'menu_items': menu_items}

    return app
