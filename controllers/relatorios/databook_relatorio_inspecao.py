import logging
from time import time
from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required
from openpyxl.worksheet.page import PageMargins
from models import tanque
from models.concreto import ConcretoConcretagens, ConcretoConcretagensTanques
from models.contrato import Contrato
from models.tanque import Tanques, TanquesPecas, TanquesGrupos
from models.database import db
from sqlalchemy import or_, and_
from datetime import datetime, timedelta
import os
import io
import shutil
import tempfile
import zipfile
import openpyxl
from openpyxl import load_workbook
import json
import subprocess
import platform
import time

# Tentar importar odfpy para suporte a ODS
try:
    from odf.opendocument import load, OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell
    from odf.text import P
    ODFPY_AVAILABLE = True
except ImportError:
    ODFPY_AVAILABLE = False
    print('odfpy não está instalado. Para processar ODS diretamente, instale: pip install odfpy')



# Funções auxiliares para gerenciar pasta temporária do projeto
def _obter_pasta_temp_projeto():
    """
    Obtém ou cria a pasta temporária exclusiva do projeto.
    Retorna o caminho da pasta temporária.
    """
    # Obter diretório base do projeto (onde está o arquivo atual)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    temp_dir = os.path.join(base_dir, 'temp', 'databook_inspecao')
    
    # Criar pasta se não existir
    os.makedirs(temp_dir, exist_ok=True)
    
    return temp_dir

def _deve_manter_arquivos_temp():
    """
    Verifica se deve manter os arquivos temporários ou deletá-los.
    Por padrão, mantém os arquivos (True).
    """
    manter_temp = os.getenv('MANTER_ARQUIVOS_TEMP', 'true').lower()
    return manter_temp in ('true', '1', 'yes', 'sim')

def _criar_arquivo_temp_projeto(suffix='', prefix='temp_'):
    """
    Cria um arquivo temporário na pasta do projeto.
    
    Args:
        suffix: Sufixo do arquivo (ex: '.xlsx', '.pdf')
        prefix: Prefixo do arquivo (padrão: 'temp_')
    
    Returns:
        Caminho do arquivo temporário criado
    """
    temp_dir = _obter_pasta_temp_projeto()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filename = f'{prefix}{timestamp}{suffix}'
    filepath = os.path.join(temp_dir, filename)
    
    # Criar arquivo vazio
    open(filepath, 'a').close()
    
    return filepath

def _criar_diretorio_temp_projeto(prefix='temp_dir_'):
    """
    Cria um diretório temporário na pasta do projeto.
    
    Args:
        prefix: Prefixo do diretório (padrão: 'temp_dir_')
    
    Returns:
        Caminho do diretório temporário criado
    """
    temp_dir = _obter_pasta_temp_projeto()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    dirname = f'{prefix}{timestamp}'
    dirpath = os.path.join(temp_dir, dirname)
    
    # Criar diretório
    os.makedirs(dirpath, exist_ok=True)
    
    return dirpath

def _limpar_arquivo_temp(filepath):
    """
    Remove um arquivo temporário se a configuração permitir.
    
    Args:
        filepath: Caminho do arquivo a ser removido
    """
    if not _deve_manter_arquivos_temp():
        try:
            if os.path.isfile(filepath):
                os.unlink(filepath)
            elif os.path.isdir(filepath):
                shutil.rmtree(filepath)
        except Exception as e:
            print(f'Erro ao limpar arquivo temporário {filepath}: {str(e)}')

def _limpar_diretorio_temp(dirpath):
    """
    Remove um diretório temporário se a configuração permitir.
    
    Args:
        dirpath: Caminho do diretório a ser removido
    """
    if not _deve_manter_arquivos_temp():
        try:
            if os.path.exists(dirpath) and os.path.isdir(dirpath):
                shutil.rmtree(dirpath)
        except Exception as e:
            print(f'Erro ao limpar diretório temporário {dirpath}: {str(e)}')


databook_inspecao_bp = Blueprint('databook_inspecao', __name__, url_prefix='/relatorios/databook/inspecao')

@databook_inspecao_bp.route('/')
@login_required
def index():
    """
    Página principal do relatório de inspeção (DataBook)
    """
    # Buscar contratos ativos para o filtro
    contratos = Contrato.query.filter_by(ativo=True).order_by(Contrato.nome).all()
    
    # Buscar grupos de tanques para o filtro
    grupos = TanquesGrupos.query.order_by(TanquesGrupos.nome).all()
    
    # Buscar tanques para o filtro (inicialmente todos)
    tanques = Tanques.query.order_by(Tanques.nome).all()
    
    # Obter filtros da requisição
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_id = request.args.get('tanque_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    
    # Se houver contrato selecionado, filtrar tanques
    if contrato_id:
        tanques = Tanques.query.filter_by(contrato_id=contrato_id).order_by(Tanques.nome).all()
    
    return render_template('relatorios/databook/inspecao/index.html', 
                         contratos=contratos,
                         grupos=grupos,
                         tanques=tanques,
                         contrato_id=contrato_id,
                         tanque_id=tanque_id,
                         grupo_id=grupo_id,
                         data_inicio=data_inicio,
                         data_fim=data_fim)

@databook_inspecao_bp.route('/api/dados')
@login_required
def api_dados():
    """
    API para retornar dados do relatório em JSON (para DataTable)
    Agrupa por data_concretagem e pista
    """
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_id = request.args.get('tanque_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    
    # Converter datas se fornecidas
    data_inicio = None
    data_fim = None
    if data_inicio_str:
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        except ValueError:
            data_inicio = None
    
    if data_fim_str:
        try:
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        except ValueError:
            data_fim = None
    
    # Construir query base - buscar de ConcretoConcretagens
    query = db.session.query(ConcretoConcretagens)
    
    # Aplicar filtros de data (filtrar por data_concretagem)
    if data_inicio:
        query = query.filter(ConcretoConcretagens.data_concretagem >= data_inicio)
    
    if data_fim:
        query = query.filter(ConcretoConcretagens.data_concretagem <= data_fim)
    
    # Executar query e ordenar por data e pista
    concretagens = query.order_by(
        ConcretoConcretagens.data_concretagem.desc(),
        ConcretoConcretagens.pista.asc()
    ).all()
    
    # Agrupar dados por data_concretagem e pista
    grupos = {}
    grupos_tanques = {}  # Armazenar todos os tanques únicos por grupo
    grupos_concretagens = {}  # Armazenar IDs de concretagens por grupo
    
    for concretagem in concretagens:
        # Criar chave única para agrupamento (data + pista)
        chave = (concretagem.data_concretagem, concretagem.pista)
        
        # Extrair IDs de tanques do JSON
        tanque_ids = extrair_tanque_ids_do_json(concretagem.pecas)
        
        # Aplicar filtros de tanque se especificado
        if tanque_id and tanque_id not in tanque_ids:
            continue
        
        # Aplicar filtro de grupo se especificado
        if grupo_id:
            grupo = TanquesGrupos.query.get(grupo_id)
            if grupo and grupo.tanques:
                tanque_ids_grupo = [t.id for t in grupo.tanques]
                # Verificar se algum tanque do grupo está presente
                if not any(tid in tanque_ids for tid in tanque_ids_grupo):
                    continue
        
        # Inicializar lista de tanques do grupo se não existir
        if chave not in grupos_tanques:
            grupos_tanques[chave] = set()
            grupos_concretagens[chave] = []
        
        # Adicionar IDs de tanques ao grupo
        grupos_tanques[chave].update(tanque_ids)
        # Adicionar ID da concretagem ao grupo
        grupos_concretagens[chave].append(concretagem.id)
    
    # Processar cada grupo para buscar informações dos tanques
    for chave, tanque_ids_set in grupos_tanques.items():
        data_concretagem, pista = chave
        
        # Buscar informações dos tanques usando a função comum
        tanques_info = []
        if tanque_ids_set:
            tanques = buscar_tanques_com_filtros(
                tanque_ids=tanque_ids_set,
                tanque_id=None,  # Não filtrar por tanque específico na api_dados
                contrato_id=contrato_id,
                grupo_id=grupo_id
            )
            
            for tanque in tanques:
                tanques_info.append({
                    'id': tanque.id,
                    'nome': tanque.nome,
                    'contrato_nome': tanque.contrato.nome if tanque.contrato else None,
                    'contrato_id': tanque.contrato_id if tanque.contrato else None
                })
        
        # Se filtro de contrato ou grupo foi aplicado e não encontrou tanques, pular
        if (contrato_id or grupo_id) and not tanques_info:
            continue
        
        # Contar total de concretagens neste grupo (mesma data e pista)
        total_concretagens_grupo = len(grupos_concretagens[chave])
        
        # Usar o primeiro ID de concretagem do grupo para exportação
        concretagem_id_grupo = grupos_concretagens[chave][0] if grupos_concretagens[chave] else None
        
        # Obter projeto_id do primeiro tanque (se houver)
        projeto_id_grupo = tanques_info[0]['contrato_id'] if tanques_info and tanques_info[0].get('contrato_id') else None
        
        # Criar estrutura de dados do grupo
        grupos[chave] = {
            'concretagem_id': concretagem_id_grupo,
            'projeto_id': projeto_id_grupo,
            'data_concretagem': data_concretagem.strftime('%d/%m/%Y') if data_concretagem else 'N/A',
            'data_concretagem_raw': data_concretagem.isoformat() if data_concretagem else None,
            'pista': pista,
            'tanque_nome': ', '.join([t['nome'] for t in tanques_info]) if tanques_info else 'N/A',
            'projeto_nome': tanques_info[0]['contrato_nome'] if tanques_info and tanques_info[0].get('contrato_nome') else 'N/A',
            'total_concretagens': total_concretagens_grupo
        }
    
    # Preparar dados finais (apenas grupos únicos)
    dados = []
    # Ordenar grupos, tratando None adequadamente
    for chave in sorted(grupos.keys(), key=lambda x: (
        x[0] if x[0] is not None else datetime.min.date(),
        x[1] if x[1] is not None else ''
    ), reverse=True):
        dados.append(grupos[chave])
    
    return jsonify({
        'data': dados,
        'recordsTotal': len(dados),
        'recordsFiltered': len(dados)
    })

# Endpoints api_tanques e api_grupos foram movidos para databook_api_controller.py
# para evitar duplicação de código

def extrair_tanque_ids_do_json(pecas_json_str):
    """
    Extrai os IDs únicos de tanques do JSON da coluna pecas.
    
    Formato esperado do JSON:
    [
        {"placa": "PN-02", "tanque": 1, "forma": "4"},
        {"placa": "PN-03", "tanque": 1, "forma": "6"},
        ...
    ]
    
    Args:
        pecas_json_str: String JSON ou objeto JSON já parseado
    
    Returns:
        Set de IDs de tanques únicos
    """
    tanque_ids = set()
    try:
        if not pecas_json_str:
            return tanque_ids
        
        pecas_data = json.loads(pecas_json_str) if isinstance(pecas_json_str, str) else pecas_json_str
        
        # Se for uma lista de objetos (formato padrão)
        if isinstance(pecas_data, list):
            for item in pecas_data:
                if isinstance(item, dict):
                    # Extrair ID do tanque (chave: "tanque")
                    tanque_id = item.get('tanque')
                    if tanque_id:
                        tanque_ids.add(int(tanque_id))
        # Se for um objeto com uma lista de peças
        elif isinstance(pecas_data, dict):
            if 'pecas' in pecas_data and isinstance(pecas_data['pecas'], list):
                for item in pecas_data['pecas']:
                    if isinstance(item, dict):
                        tanque_id = item.get('tanque')
                        if tanque_id:
                            tanque_ids.add(int(tanque_id))
            # Ou se os tanques estão diretamente no objeto
            elif 'tanque_id' in pecas_data:
                tanque_ids.add(int(pecas_data['tanque_id']))
    except (json.JSONDecodeError, TypeError, ValueError, KeyError) as e:
        print(f"Erro ao processar JSON de pecas: {e}")
    
    return tanque_ids

def buscar_tanques_com_filtros(tanque_ids, tanque_id=None, contrato_id=None, grupo_id=None):
    """
    Função auxiliar para buscar tanques aplicando filtros
    
    Args:
        tanque_ids: Lista ou set de IDs de tanques para filtrar
        tanque_id: ID específico do tanque para filtrar (opcional)
        contrato_id: ID do contrato/projeto para filtrar (opcional)
        grupo_id: ID do grupo de tanques para filtrar (opcional)
    
    Returns:
        Lista de objetos Tanques que atendem aos filtros
    """
    if not tanque_ids:
        return []
    
    # Converter para lista se for set
    tanque_ids_list = list(tanque_ids) if isinstance(tanque_ids, set) else tanque_ids
    
    # Iniciar query
    tanques_query = Tanques.query.filter(Tanques.id.in_(tanque_ids_list))
    
    # Aplicar filtro de tanque específico se especificado
    if tanque_id:
        tanques_query = tanques_query.filter(Tanques.id == tanque_id)
    
    # Aplicar filtro de contrato/projeto se especificado
    if contrato_id is not None:
        tanques_query = tanques_query.filter(Tanques.contrato_id == contrato_id)
    
    # Aplicar filtro de grupo se especificado
    if grupo_id:
        grupo = TanquesGrupos.query.get(grupo_id)
        if grupo and grupo.tanques:
            tanque_ids_grupo = [t.id for t in grupo.tanques]
            tanques_query = tanques_query.filter(Tanques.id.in_(tanque_ids_grupo))
    
    return tanques_query.all()

def buscar_peca_por_tanque_e_nome(tanque_id, nome_peca, tanque_id_filtro=None, grupo_id=None):
    """
    Função auxiliar para buscar uma peça por tanque e nome aplicando filtros
    
    Args:
        tanque_id: ID do tanque da peça
        nome_peca: Nome da peça
        tanque_id_filtro: ID do tanque para filtrar (opcional)
        grupo_id: ID do grupo de tanques para filtrar (opcional)
    
    Returns:
        Objeto TanquesPecas ou None se não encontrado
    """
    peca_query = TanquesPecas.query.filter(
        TanquesPecas.tanque_id == tanque_id,
        TanquesPecas.nome == nome_peca
    )
    
    # Aplicar filtro de tanque se especificado
    if tanque_id_filtro:
        peca_query = peca_query.filter(TanquesPecas.tanque_id == tanque_id_filtro)
    
    # Aplicar filtro de grupo se especificado
    if grupo_id:
        grupo = TanquesGrupos.query.get(grupo_id)
        if grupo and grupo.tanques:
            tanque_ids_grupo = [t.id for t in grupo.tanques]
            peca_query = peca_query.filter(TanquesPecas.tanque_id.in_(tanque_ids_grupo))
    
    return peca_query.first()

def _converter_excel_para_pdf(excel_path, pdf_path=None):
    """
    Converte arquivo Excel/ODS para PDF usando LibreOffice em modo headless.
    Aceita tanto arquivos XLSX quanto ODS - gera PDF diretamente do ODS quando disponível.
    
    Args:
        excel_path: Caminho do arquivo Excel (XLSX) ou ODS
        pdf_path: Caminho de saída do PDF (opcional)
    
    Returns:
        Caminho do arquivo PDF gerado ou None em caso de erro
    """
    return _converter_excel_para_pdf_libreoffice(excel_path, pdf_path)

def _converter_excel_para_pdf_libreoffice(excel_path, pdf_path=None):
    """
    Converte arquivo Excel/ODS para PDF usando LibreOffice em modo headless.
    Funciona tanto no Windows quanto no Linux.
    Aceita tanto arquivos XLSX quanto ODS - gera PDF diretamente do ODS quando disponível.
    
    Args:
        excel_path: Caminho do arquivo Excel (XLSX) ou ODS
        pdf_path: Caminho de saída do PDF (opcional, se None, usa mesmo nome do arquivo)
    
    Returns:
        Caminho do arquivo PDF gerado ou None em caso de erro
    """
    try:
        if not excel_path or not os.path.exists(excel_path):
            print(f'[_converter_excel_para_pdf_libreoffice] Arquivo não encontrado: {excel_path}')
            return None
        
        # Determinar caminho do PDF de saída
        if pdf_path is None:
            pdf_path = excel_path.replace('.xlsx', '.pdf').replace('.xls', '.pdf').replace('.ods', '.pdf')
        
        # Obter diretório de saída
        output_dir = os.path.dirname(pdf_path)
        if not output_dir:
            output_dir = os.path.dirname(excel_path)
        
        # Criar diretório se não existir
        os.makedirs(output_dir, exist_ok=True)
        
        # Detectar sistema operacional e comando do LibreOffice
        sistema = platform.system().lower()
        
        if sistema == 'windows':
            # Windows - tentar diferentes caminhos comuns do LibreOffice
            possiveis_caminhos = [
                r'C:\Program Files\LibreOffice\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
                r'C:\Program Files\LibreOffice 7\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice 7\program\soffice.exe',
            ]
            
            # Verificar se existe variável de ambiente
            libreoffice_env = os.getenv('LIBREOFFICE_PATH')
            if libreoffice_env:
                possiveis_caminhos.insert(0, libreoffice_env)
            
            soffice_cmd = None
            for caminho in possiveis_caminhos:
                if os.path.exists(caminho):
                    soffice_cmd = caminho
                    break
            
            if not soffice_cmd:
                print('[_converter_excel_para_pdf_libreoffice] LibreOffice não encontrado no Windows')
                print('[_converter_excel_para_pdf_libreoffice] Configure a variável LIBREOFFICE_PATH ou instale o LibreOffice')
                return None
        else:
            # Linux/Unix - usar comando do sistema
            soffice_cmd = None
            
            # Verificar variável de ambiente primeiro
            libreoffice_env = os.getenv('LIBREOFFICE_PATH')
            if libreoffice_env and os.path.exists(libreoffice_env):
                soffice_cmd = libreoffice_env
                logging.info(f'[_converter_excel_para_pdf_libreoffice] Usando LIBREOFFICE_PATH: {soffice_cmd}')
            else:
                # Tentar encontrar o executável real do LibreOffice (não o wrapper script)
                # O wrapper /usr/bin/soffice pode ter problemas com PATH
                import glob
                import re
                
                # Primeiro, tentar encontrar o executável real diretamente
                possiveis_caminhos = []
                
                # Buscar em /usr/lib e /usr/lib64
                for lib_dir in ['/usr/lib', '/usr/lib64', '/usr/local/lib']:
                    # Tentar diferentes versões do LibreOffice
                    for version in ['', '7', '8', '6', '5']:
                        path = f'{lib_dir}/libreoffice{version}/program/soffice'
                        if os.path.exists(path):
                            possiveis_caminhos.append(path)
                
                # Buscar em /opt
                opt_paths = glob.glob('/opt/libreoffice*/program/soffice')
                possiveis_caminhos.extend(opt_paths)
                
                # Verificar cada caminho
                for caminho in possiveis_caminhos:
                    if os.path.exists(caminho) and os.access(caminho, os.X_OK):
                        # Verificar se é um executável real (ELF binary)
                        try:
                            with open(caminho, 'rb') as f:
                                header = f.read(4)
                                if header.startswith(b'\x7fELF'):  # ELF binary
                                    soffice_cmd = caminho
                                    logging.info(f'[_converter_excel_para_pdf_libreoffice] Encontrado executável real: {soffice_cmd}')
                                    break
                        except Exception as e:
                            logging.debug(f'[_converter_excel_para_pdf_libreoffice] Erro ao verificar {caminho}: {str(e)}')
                            continue
                
                # Se não encontrou o executável real, tentar extrair do wrapper
                if not soffice_cmd:
                    # Tentar encontrar usando shutil.which (pode retornar o wrapper)
                    wrapper_path = shutil.which('soffice')
                    if wrapper_path:
                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Encontrado wrapper no PATH: {wrapper_path}')
                        # Tentar encontrar o executável real através do wrapper
                        try:
                            with open(wrapper_path, 'r') as f:
                                script_content = f.read()
                                # Procurar por padrões comuns no script
                                # Padrão 1: /usr/lib/libreoffice/program/soffice
                                # Padrão 2: /usr/lib64/libreoffice/program/soffice
                                # Padrão 3: variáveis como INSTALL_DIR
                                patterns = [
                                    r'(/usr/lib[^/\s]*/libreoffice[^/\s]*/program/soffice)',
                                    r'(/usr/lib64[^/\s]*/libreoffice[^/\s]*/program/soffice)',
                                    r'INSTALL_DIR[=:]\s*["\']?([^"\'\s]+)',
                                    r'exec\s+["\']?([^"\'\s]+/soffice)',
                                ]
                                
                                for pattern in patterns:
                                    matches = re.findall(pattern, script_content)
                                    for match in matches:
                                        if isinstance(match, tuple):
                                            match = match[0] if match else None
                                        if match and os.path.exists(match) and os.access(match, os.X_OK):
                                            # Verificar se é ELF
                                            try:
                                                with open(match, 'rb') as f:
                                                    header = f.read(4)
                                                    if header.startswith(b'\x7fELF'):
                                                        soffice_cmd = match
                                                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Executável real encontrado via wrapper: {soffice_cmd}')
                                                        break
                                            except:
                                                continue
                                    if soffice_cmd:
                                        break
                        except Exception as e:
                            logging.warning(f'[_converter_excel_para_pdf_libreoffice] Não foi possível encontrar executável real via wrapper: {str(e)}')
                
                # Se ainda não encontrou, NÃO usar o wrapper - retornar erro
                if not soffice_cmd:
                    logging.error('[_converter_excel_para_pdf_libreoffice] Executável real do LibreOffice não encontrado')
                    logging.error('[_converter_excel_para_pdf_libreoffice] Tentou buscar em: /usr/lib/libreoffice/program/soffice, /usr/lib64/libreoffice/program/soffice, /opt/libreoffice*/program/soffice')
                    logging.error('[_converter_excel_para_pdf_libreoffice] Configure a variável LIBREOFFICE_PATH com o caminho completo do executável')
                    logging.error('[_converter_excel_para_pdf_libreoffice] Exemplo: export LIBREOFFICE_PATH=/usr/lib/libreoffice/program/soffice')
                    return None
        
        # Comando para converter Excel/ODS para PDF
        # --headless: modo sem interface gráfica
        # Aceita tanto XLSX quanto ODS - gera PDF diretamente do formato original
        # --convert-to pdf: converter para PDF
        # --outdir: diretório de saída
        cmd = [
            soffice_cmd,
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            excel_path
        ]
        
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Executando: {" ".join(cmd)}')
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Arquivo de entrada: {excel_path}')
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Diretório de saída: {output_dir}')
        
        try:
            # Configurar PATH mínimo necessário para o LibreOffice funcionar
            # O wrapper script precisa de comandos básicos do sistema
            env = os.environ.copy()
            # Garantir que comandos básicos estejam no PATH
            basic_paths = ['/usr/bin', '/bin', '/usr/local/bin']
            current_path = env.get('PATH', '')
            # Adicionar caminhos básicos se não estiverem presentes
            for path in basic_paths:
                if path not in current_path:
                    env['PATH'] = f"{path}:{env.get('PATH', '')}"
            
            # Executar conversão com PATH configurado
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # Timeout de 2 minutos
                check=False,
                env=env
            )
            
            if result.returncode != 0:
                logging.error(f'[_converter_excel_para_pdf_libreoffice] Erro ao converter (código {result.returncode})')
                logging.error(f'[_converter_excel_para_pdf_libreoffice] stdout: {result.stdout}')
                logging.error(f'[_converter_excel_para_pdf_libreoffice] stderr: {result.stderr}')
                return None
            else:
                logging.info(f'[_converter_excel_para_pdf_libreoffice] Comando executado com sucesso')
                if result.stdout:
                    print(f'[_converter_excel_para_pdf_libreoffice] stdout: {result.stdout}')
        except subprocess.TimeoutExpired:
            print('[_converter_excel_para_pdf_libreoffice] Timeout ao converter Excel para PDF')
            return None
        except Exception as e:
            print(f'[_converter_excel_para_pdf_libreoffice] Exceção ao executar comando: {str(e)}')
            import traceback
            print(traceback.format_exc())
            return None
        
        # O LibreOffice gera o PDF com o mesmo nome do arquivo Excel
        excel_basename = os.path.basename(excel_path)
        pdf_basename = excel_basename.replace('.xlsx', '.pdf').replace('.xls', '.pdf').replace('.ods', '.pdf')
        generated_pdf_path = os.path.join(output_dir, pdf_basename)
        
        print(f'[_converter_excel_para_pdf_libreoffice] Caminho esperado do PDF: {generated_pdf_path}')
        
        # Aguardar um pouco para garantir que o arquivo foi criado
        max_tentativas = 10
        tentativa = 0
        while tentativa < max_tentativas:
            if os.path.exists(generated_pdf_path):
                # Verificar se o arquivo não está sendo escrito (tamanho estável)
                tamanho_anterior = os.path.getsize(generated_pdf_path)
                time.sleep(0.5)
                tamanho_atual = os.path.getsize(generated_pdf_path)
                if tamanho_anterior == tamanho_atual and tamanho_atual > 0:
                    print(f'[_converter_excel_para_pdf_libreoffice] PDF gerado com sucesso: {generated_pdf_path} (tamanho: {tamanho_atual} bytes)')
                    return generated_pdf_path
                elif tamanho_anterior == tamanho_atual and tamanho_atual == 0:
                    print(f'[_converter_excel_para_pdf_libreoffice] PDF gerado mas está vazio: {generated_pdf_path}')
                    # Continuar tentando por mais um pouco
            else:
                print(f'[_converter_excel_para_pdf_libreoffice] Tentativa {tentativa + 1}/{max_tentativas}: PDF ainda não existe')
            tentativa += 1
            time.sleep(0.5)
        
        # Verificar se o arquivo existe mas está vazio
        if os.path.exists(generated_pdf_path):
            tamanho = os.path.getsize(generated_pdf_path)
            if tamanho == 0:
                print(f'[_converter_excel_para_pdf_libreoffice] PDF foi criado mas está vazio: {generated_pdf_path}')
                return None
        
        # Listar arquivos no diretório de saída para debug
        try:
            arquivos_no_dir = os.listdir(output_dir)
            print(f'[_converter_excel_para_pdf_libreoffice] Arquivos no diretório de saída: {arquivos_no_dir}')
            # Verificar se há algum PDF no diretório
            pdfs_no_dir = [f for f in arquivos_no_dir if f.endswith('.pdf')]
            if pdfs_no_dir:
                print(f'[_converter_excel_para_pdf_libreoffice] PDFs encontrados no diretório: {pdfs_no_dir}')
        except Exception as e:
            print(f'[_converter_excel_para_pdf_libreoffice] Erro ao listar diretório: {str(e)}')
        
        print(f'[_converter_excel_para_pdf_libreoffice] PDF não foi gerado após {max_tentativas} tentativas')
        print(f'[_converter_excel_para_pdf_libreoffice] Caminho esperado: {generated_pdf_path}')
        return None
        
    except subprocess.TimeoutExpired:
        print('[_converter_excel_para_pdf_libreoffice] Timeout ao converter Excel para PDF')
        return None
    except Exception as e:
        print(f'[_converter_excel_para_pdf_libreoffice] Erro ao converter Excel para PDF: {str(e)}')
        import traceback
        print(traceback.format_exc())
        return None

def _converter_ods_para_xlsx_libreoffice(ods_path, xlsx_path=None):
    """
    Converte arquivo ODS para XLSX usando LibreOffice em modo headless.
    Funciona tanto no Windows quanto no Linux.
    
    Args:
        ods_path: Caminho do arquivo ODS
        xlsx_path: Caminho de saída do XLSX (opcional, se None, usa mesmo nome do ODS)
    
    Returns:
        Caminho do arquivo XLSX gerado ou None em caso de erro
    """
    try:
        if not ods_path or not os.path.exists(ods_path):
            print(f'[_converter_ods_para_xlsx_libreoffice] Arquivo ODS não encontrado: {ods_path}')
            return None
        
        # Determinar caminho do XLSX de saída
        if xlsx_path is None:
            xlsx_path = ods_path.replace('.ods', '.xlsx')
        
        # Obter diretório de saída
        output_dir = os.path.dirname(xlsx_path)
        if not output_dir:
            output_dir = os.path.dirname(ods_path)
        
        # Criar diretório se não existir
        os.makedirs(output_dir, exist_ok=True)
        
        # Detectar sistema operacional e comando do LibreOffice
        sistema = platform.system().lower()
        print(f'[_converter_ods_para_xlsx_libreoffice] Sistema operacional: {sistema}')
        
        if sistema == 'windows':
            possiveis_caminhos = [
                r'C:\Program Files\LibreOffice\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
                r'C:\Program Files\LibreOffice 7\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice 7\program\soffice.exe',
            ]
            
            libreoffice_env = os.getenv('LIBREOFFICE_PATH')
            if libreoffice_env:
                possiveis_caminhos.insert(0, libreoffice_env)
            
            soffice_cmd = None
            for caminho in possiveis_caminhos:
                if os.path.exists(caminho):
                    soffice_cmd = caminho
                    break
            
            if not soffice_cmd:
                print('[_converter_ods_para_xlsx_libreoffice] LibreOffice não encontrado no Windows')
                return None
        else:
            # Linux/Unix - usar comando do sistema
            soffice_cmd = None
            
            # Verificar variável de ambiente primeiro
            libreoffice_env = os.getenv('LIBREOFFICE_PATH')
            if libreoffice_env and os.path.exists(libreoffice_env):
                soffice_cmd = libreoffice_env
                print(f'[_converter_ods_para_xlsx_libreoffice] Usando LIBREOFFICE_PATH: {soffice_cmd}')
            else:
                # Tentar encontrar o executável real do LibreOffice (não o wrapper script)
                import glob
                import re
                
                # Primeiro, tentar encontrar o executável real diretamente
                possiveis_caminhos = []
                
                # Buscar em /usr/lib e /usr/lib64
                for lib_dir in ['/usr/lib', '/usr/lib64', '/usr/local/lib']:
                    # Tentar diferentes versões do LibreOffice
                    for version in ['', '7', '8', '6', '5']:
                        path = f'{lib_dir}/libreoffice{version}/program/soffice'
                        if os.path.exists(path):
                            possiveis_caminhos.append(path)
                
                # Buscar em /opt
                opt_paths = glob.glob('/opt/libreoffice*/program/soffice')
                possiveis_caminhos.extend(opt_paths)
                
                # Verificar cada caminho
                for caminho in possiveis_caminhos:
                    if os.path.exists(caminho) and os.access(caminho, os.X_OK):
                        # Verificar se é um executável real (ELF binary)
                        try:
                            with open(caminho, 'rb') as f:
                                header = f.read(4)
                                if header.startswith(b'\x7fELF'):  # ELF binary
                                    soffice_cmd = caminho
                                    print(f'[_converter_ods_para_xlsx_libreoffice] Encontrado executável real: {soffice_cmd}')
                                    break
                        except Exception as e:
                            print(f'[_converter_ods_para_xlsx_libreoffice] Erro ao verificar {caminho}: {str(e)}')
                            continue
                
                # Se não encontrou o executável real, tentar extrair do wrapper
                if not soffice_cmd:
                    # Tentar encontrar usando shutil.which (pode retornar o wrapper)
                    wrapper_path = shutil.which('soffice')
                    if wrapper_path:
                        print(f'[_converter_ods_para_xlsx_libreoffice] Encontrado wrapper no PATH: {wrapper_path}')
                        # Tentar encontrar o executável real através do wrapper
                        try:
                            with open(wrapper_path, 'r') as f:
                                script_content = f.read()
                                # Procurar por padrões comuns no script
                                patterns = [
                                    r'(/usr/lib[^/\s]*/libreoffice[^/\s]*/program/soffice)',
                                    r'(/usr/lib64[^/\s]*/libreoffice[^/\s]*/program/soffice)',
                                    r'INSTALL_DIR[=:]\s*["\']?([^"\'\s]+)',
                                    r'exec\s+["\']?([^"\'\s]+/soffice)',
                                ]
                                
                                for pattern in patterns:
                                    matches = re.findall(pattern, script_content)
                                    for match in matches:
                                        if isinstance(match, tuple):
                                            match = match[0] if match else None
                                        if match and os.path.exists(match) and os.access(match, os.X_OK):
                                            # Verificar se é ELF
                                            try:
                                                with open(match, 'rb') as f:
                                                    header = f.read(4)
                                                    if header.startswith(b'\x7fELF'):
                                                        soffice_cmd = match
                                                        print(f'[_converter_ods_para_xlsx_libreoffice] Executável real encontrado via wrapper: {soffice_cmd}')
                                                        break
                                            except:
                                                continue
                                    if soffice_cmd:
                                        break
                        except Exception as e:
                            print(f'[_converter_ods_para_xlsx_libreoffice] Não foi possível encontrar executável real via wrapper: {str(e)}')
                
                # Se ainda não encontrou, NÃO usar o wrapper - retornar erro
                if not soffice_cmd:
                    print('[_converter_ods_para_xlsx_libreoffice] Executável real do LibreOffice não encontrado')
                    print('[_converter_ods_para_xlsx_libreoffice] Tentou buscar em: /usr/lib/libreoffice/program/soffice, /usr/lib64/libreoffice/program/soffice, /opt/libreoffice*/program/soffice')
                    print('[_converter_ods_para_xlsx_libreoffice] Configure a variável LIBREOFFICE_PATH com o caminho completo do executável')
                    print('[_converter_ods_para_xlsx_libreoffice] Exemplo: export LIBREOFFICE_PATH=/usr/lib/libreoffice/program/soffice')
                    return None
        
        cmd = [
            soffice_cmd,
            '--headless',
            '--convert-to', 'xlsx',
            '--outdir', output_dir,
            ods_path
        ]
        
        print(f'[_converter_ods_para_xlsx_libreoffice] Executando: {" ".join(cmd)}')
        print(f'[_converter_ods_para_xlsx_libreoffice] Arquivo ODS: {ods_path}')
        print(f'[_converter_ods_para_xlsx_libreoffice] Diretório de saída: {output_dir}')
        
        try:
            # Configurar PATH mínimo necessário para o LibreOffice funcionar
            env = os.environ.copy()
            basic_paths = ['/usr/bin', '/bin', '/usr/local/bin']
            current_path = env.get('PATH', '')
            for path in basic_paths:
                if path not in current_path:
                    env['PATH'] = f"{path}:{env.get('PATH', '')}"
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=env
            )
            
            if result.returncode != 0:
                print(f'[_converter_ods_para_xlsx_libreoffice] Erro ao converter (código {result.returncode})')
                print(f'[_converter_ods_para_xlsx_libreoffice] stdout: {result.stdout}')
                print(f'[_converter_ods_para_xlsx_libreoffice] stderr: {result.stderr}')
                return None
            else:
                print(f'[_converter_ods_para_xlsx_libreoffice] Comando executado com sucesso')
                if result.stdout:
                    print(f'[_converter_ods_para_xlsx_libreoffice] stdout: {result.stdout}')
        except subprocess.TimeoutExpired:
            print('[_converter_ods_para_xlsx_libreoffice] Timeout ao converter ODS para XLSX')
            return None
        except Exception as e:
            print(f'[_converter_ods_para_xlsx_libreoffice] Exceção ao executar comando: {str(e)}')
            import traceback
            print(traceback.format_exc())
            return None
        
        ods_basename = os.path.basename(ods_path)
        xlsx_basename = ods_basename.replace('.ods', '.xlsx')
        generated_xlsx_path = os.path.join(output_dir, xlsx_basename)
        
        max_tentativas = 10
        tentativa = 0
        while tentativa < max_tentativas:
            if os.path.exists(generated_xlsx_path):
                tamanho_anterior = os.path.getsize(generated_xlsx_path)
                time.sleep(0.5)
                tamanho_atual = os.path.getsize(generated_xlsx_path)
                if tamanho_anterior == tamanho_atual:
                    if generated_xlsx_path != xlsx_path:
                        shutil.move(generated_xlsx_path, xlsx_path)
                    print(f'[_converter_ods_para_xlsx_libreoffice] XLSX gerado com sucesso: {xlsx_path}')
                    return xlsx_path
            tentativa += 1
            time.sleep(0.5)
        
        print(f'[_converter_ods_para_xlsx_libreoffice] XLSX não foi gerado após {max_tentativas} tentativas')
        return None
        
    except subprocess.TimeoutExpired:
        print('[_converter_ods_para_xlsx_libreoffice] Timeout ao converter ODS para XLSX')
        return None
    except Exception as e:
        print(f'[_converter_ods_para_xlsx_libreoffice] Erro ao converter ODS para XLSX: {str(e)}')
        import traceback
        print(traceback.format_exc())
        return None

def _processar_ods_template_inspecao(ods_path, concretagem_id, concretagem, contrato, tanque_id, projeto_id, grupo_id):
    """
    Processa um arquivo ODS diretamente, substituindo placeholders pelos dados.
    
    Args:
        ods_path: Caminho do arquivo ODS
        concretagem_id: ID da concretagem
        concretagem: Objeto concretagem
        contrato: Objeto contrato
        tanque_id: ID do tanque (opcional)
        projeto_id: ID do projeto (opcional)
        grupo_id: ID do grupo (opcional)
    """
    if not ODFPY_AVAILABLE:
        raise ImportError('odfpy não está disponível. Instale com: pip install odfpy')
    
    try:
        # Carregar o documento ODS
        doc = load(ods_path)
        
        # Obter todas as tabelas (planilhas)
        tables = doc.getElementsByType(Table)
        
        # Preparar dados para substituição
        pecas = None
        
        # Buscar primeira peça válida para usar no processamento de alongamentos
        peca_tanque_global = None
        if concretagem.pecas:
            pecas = json.loads(concretagem.pecas) if isinstance(concretagem.pecas, str) else concretagem.pecas
            if pecas and isinstance(pecas, list):
                for peca in pecas:
                    if isinstance(peca, dict) and peca.get('tanque') is not None and peca.get('placa'):
                        peca_tanque_global = buscar_peca_por_tanque_e_nome(
                            tanque_id=peca['tanque'],
                            nome_peca=peca['placa'],
                            tanque_id_filtro=tanque_id,
                            grupo_id=grupo_id
                        )
                        if peca_tanque_global:
                            break
        
        for table in tables:
            # Iterar sobre todas as linhas
            rows = table.getElementsByType(TableRow)
            for row_idx, row in enumerate(rows):
                if row_idx == 77:  # Pular linha 77 como no código original
                    continue
                
                # Iterar sobre todas as células
                cells = row.getElementsByType(TableCell)
                for cell_idx, cell in enumerate(cells):
                    if cell_idx == 42:  # Pular coluna 42 como no código original
                        continue
                    
                    # Obter o texto da célula
                    original_text = ''
                    paragraphs = cell.getElementsByType(P)
                    
                    # Coletar texto de todos os parágrafos
                    if paragraphs:
                        for para in paragraphs:
                            para_text = ''
                            for node in para.childNodes:
                                if hasattr(node, 'data'):
                                    para_text += str(node.data)
                                elif hasattr(node, 'nodeValue'):
                                    para_text += str(node.nodeValue)
                            if para_text:
                                original_text += para_text
                    
                    # Se não encontrou texto em parágrafos, tentar obter diretamente
                    if not original_text:
                        for node in cell.childNodes:
                            if hasattr(node, 'data'):
                                original_text += str(node.data)
                            elif hasattr(node, 'nodeValue'):
                                original_text += str(node.nodeValue)
                    
                    # Processar apenas células com texto no formato de placeholder (1 a 5 caracteres)
                    if original_text and len(original_text.strip()) > 0 and 1 < len(original_text) <= 5:
                        new_value = original_text
                        
                        # Variáveis locais para esta célula
                        series_local = ""
                        peca_tanque_local = peca_tanque_global
                        
                        # Substituir placeholders básicos
                        new_value = new_value.replace('{1}', str(concretagem_id))
                        
                        cliente_nome = 'N/A'
                        if contrato and contrato.cliente_direto:
                            cliente_nome = contrato.cliente_direto.nome
                        new_value = new_value.replace('{2}', str(cliente_nome))
                        new_value = new_value.replace('{3}', str(contrato.nome if contrato else 'N/A'))
                        new_value = new_value.replace('{4}', str(concretagem.data_concretagem.strftime('%d/%m/%Y')))
                        
                        # Processar tanques
                        if concretagem.pecas and pecas:
                            tanques_ids_json = extrair_tanque_ids_do_json(concretagem.pecas)
                            if tanques_ids_json:
                                tanques = buscar_tanques_com_filtros(
                                    tanque_ids=tanques_ids_json,
                                    tanque_id=tanque_id,
                                    contrato_id=projeto_id,
                                    grupo_id=grupo_id
                                )
                                
                                tanques_nomes = {tanque.id: tanque.nome for tanque in tanques}
                                
                                if tanque_id is None:
                                    nomes_tanques = []
                                    for tid in sorted([t for t in tanques_ids_json if t is not None]):
                                        if tid in tanques_nomes:
                                            nomes_tanques.append(tanques_nomes[tid])
                                    if nomes_tanques:
                                        new_value = new_value.replace('{5}', ', '.join(nomes_tanques))
                                else:
                                    if tanque_id in tanques_nomes:
                                        new_value = new_value.replace('{5}', str(tanques_nomes[tanque_id]))
                                
                                if tanques:
                                    new_value = new_value.replace('{6}', str(tanques[0].sistema if tanques[0].sistema else ''))
                                else:
                                    new_value = new_value.replace('{6}', '')
                                
                                new_value = new_value.replace('{7}', str(concretagem.pista if concretagem.pista else ''))
                                
                                # Processar formas
                                formas = [1,2,3,4,5,6,7,8,9,10,11,12]
                                for forma in formas:
                                    count = 0
                                    for peca in pecas:
                                        if isinstance(peca, dict) and 'forma' in peca and peca['forma'] is not None:
                                            try:
                                                forma_peca = None
                                                if isinstance(peca['forma'], str):
                                                    try:
                                                        forma_peca = int(peca['forma'])
                                                    except (ValueError, TypeError):
                                                        continue
                                                elif isinstance(peca['forma'], int):
                                                    forma_peca = peca['forma']
                                                else:
                                                    continue
                                                
                                                if forma_peca is not None and forma_peca == forma:
                                                    if peca.get('tanque') is not None and peca.get('placa'):
                                                        peca_tanque = buscar_peca_por_tanque_e_nome(
                                                            tanque_id=peca['tanque'],
                                                            nome_peca=peca['placa'],
                                                            tanque_id_filtro=tanque_id,
                                                            grupo_id=grupo_id
                                                        )
                                                        
                                                        if peca_tanque:
                                                            peca_tanque_local = peca_tanque
                                                            qualidade = json.loads(peca_tanque.qualidade) if isinstance(peca_tanque.qualidade, str) else peca_tanque.qualidade
                                                            if qualidade and 'series' in qualidade:
                                                                for serie in qualidade['series']:
                                                                    if str(serie) not in series_local:
                                                                        series_local += str(serie) + ', '
                                                            
                                                            new_value = new_value.replace(f'{{{7+forma}}}', str(forma))
                                                            new_value = new_value.replace(f'{{{19+forma}}}', str(peca['placa']))
                                                            new_value = new_value.replace(f'{{{31+forma}}}', str(peca_tanque.tipo if peca_tanque.tipo else ''))
                                                            
                                                            if peca_tanque.tipo == 'PF':
                                                                tipo_painel = 'FECHO'
                                                            elif peca_tanque.tipo in ['PN','P']:
                                                                tipo_painel = 'NORMAL'
                                                            else:
                                                                tipo_painel = 'ESPECIAL'
                                                            new_value = new_value.replace(f'{{{43+forma}}}', str(tipo_painel))
                                                            count += 1
                                            except (ValueError, TypeError):
                                                continue
                                    
                                    if count == 0:
                                        new_value = new_value.replace(f'{{{7+forma}}}', '')
                                        new_value = new_value.replace(f'{{{19+forma}}}', '')
                                        new_value = new_value.replace(f'{{{31+forma}}}', '')
                                        new_value = new_value.replace(f'{{{43+forma}}}', '')
                                
                                # Séries
                                if series_local:
                                    series_str = ', '.join(str(serie) for serie in sorted(series_local.split(', ')) if serie)
                                    new_value = new_value.replace('{120}', series_str)
                                else:
                                    new_value = new_value.replace('{120}', '')
                        
                        # Processar bobinas
                        if concretagem.cordoalhas:
                            cordoalhas = json.loads(concretagem.cordoalhas) if isinstance(concretagem.cordoalhas, str) else concretagem.cordoalhas
                            if cordoalhas and isinstance(cordoalhas, dict) and 'bobinas' in cordoalhas and cordoalhas['bobinas']:
                                bobinas = cordoalhas['bobinas']
                                if len(bobinas) > 0 and bobinas[0]:
                                    bobina1 = bobinas[0]
                                    new_value = new_value.replace('{56}', str(bobina1.get('numero', '')))
                                    new_value = new_value.replace('{57}', str(bobina1.get('data_fabricacao', '')))
                                    new_value = new_value.replace('{60}', str(bobina1.get('certificado', '')))
                                else:
                                    new_value = new_value.replace('{56}', '')
                                    new_value = new_value.replace('{57}', '')
                                    new_value = new_value.replace('{60}', '')
                                
                                if len(bobinas) > 1 and bobinas[1]:
                                    bobina2 = bobinas[1]
                                    new_value = new_value.replace('{58}', str(bobina2.get('numero', '')))
                                    new_value = new_value.replace('{59}', str(bobina2.get('data_fabricacao', '')))
                                    new_value = new_value.replace('{61}', str(bobina2.get('certificado', '')))
                                else:
                                    new_value = new_value.replace('{58}', '')
                                    new_value = new_value.replace('{59}', '')
                                    new_value = new_value.replace('{61}', '')
                            else:
                                new_value = new_value.replace('{55}', '')
                                new_value = new_value.replace('{57}', '')
                                new_value = new_value.replace('{58}', '')
                                new_value = new_value.replace('{59}', '')
                                new_value = new_value.replace('{60}', '')
                                new_value = new_value.replace('{61}', '')
                        
                        # Processar alongamentos
                        if concretagem.cordoalhas:
                            cordoalhas_data = json.loads(concretagem.cordoalhas) if isinstance(concretagem.cordoalhas, str) else concretagem.cordoalhas
                            if cordoalhas_data and isinstance(cordoalhas_data, dict) and 'alongamentos' in cordoalhas_data:
                                alongamentos = cordoalhas_data['alongamentos']
                                total_alongamentos = len(alongamentos)
                                
                                if alongamentos and isinstance(alongamentos, dict):
                                    alongamentos_soma = 0
                                    alongamentos_maior = 0
                                    alongamentos_menor = 0
                                    modulo = 198.7
                                    area = 99.7
                                    
                                    if peca_tanque_local and peca_tanque_local.tipo == 'PF':
                                        comprimento = 15000
                                        alongamento_maximo_teorico = 120
                                        alongamento_minimo_teorico = 100
                                    else:
                                        comprimento = 65000
                                        alongamento_maximo_teorico = 356
                                        alongamento_minimo_teorico = 321
                                    
                                    alongamento_soma_maximo_teorico = alongamento_maximo_teorico * total_alongamentos
                                    alongamento_soma_minimo_teorico = alongamento_minimo_teorico * total_alongamentos
                                    
                                    new_value = new_value.replace('{98}', f"{alongamento_minimo_teorico:.2f}")
                                    new_value = new_value.replace('{99}', f"{alongamento_maximo_teorico:.2f}")
                                    new_value = new_value.replace('{115}', f"{alongamento_soma_minimo_teorico:.2f}")
                                    new_value = new_value.replace('{116}', f"{alongamento_soma_maximo_teorico:.2f}")
                                    
                                    alongamentos_fora_da_tolerancia = 0
                                    for chave, valor in alongamentos.items():
                                        alongamentos_soma += valor
                                        if valor > alongamentos_maior:
                                            alongamentos_maior = valor
                                        if valor < alongamentos_menor or alongamentos_menor == 0:
                                            alongamentos_menor = valor
                                        
                                        if valor > alongamento_maximo_teorico or valor < alongamento_minimo_teorico:
                                            new_value = new_value.replace(f'{{{103+alongamentos_fora_da_tolerancia}}}', str(chave.replace('C-', '')))
                                            alongamentos_fora_da_tolerancia += 1
                                        
                                        if chave and valor is not None:
                                            try:
                                                numero = int(chave.replace('C-', ''))
                                                placeholder = 62 + numero - 1
                                                new_value = new_value.replace(f'{{{placeholder}}}', str(valor))
                                            except (ValueError, TypeError):
                                                continue
                                    
                                    if alongamentos_fora_da_tolerancia < 12:
                                        for i in range(1, 12 - alongamentos_fora_da_tolerancia):
                                            new_value = new_value.replace(f'{{{102+alongamentos_fora_da_tolerancia+i}}}', '')
                                    
                                    for i in range(total_alongamentos + 1, 26):
                                        new_value = new_value.replace(f'{{{62+i}}}', '')
                                    
                                    if total_alongamentos > 16:
                                        new_value = new_value.replace('{122}', 'C-17')
                                        for i in range(17, total_alongamentos + 1):
                                            chave = f'C-{i}'
                                            placeholder = 79 + (i - 17)
                                            if chave in alongamentos:
                                                valor = alongamentos[chave]
                                                new_value = new_value.replace(f'{{{placeholder+9}}}', chave)
                                                new_value = new_value.replace(f'{{{placeholder}}}', str(valor))
                                            else:
                                                new_value = new_value.replace(f'{{{placeholder+9}}}', '')
                                        new_value = new_value.replace('{122}', '')
                                        for i in range(1, 11):
                                            if i > 1:
                                                new_value = new_value.replace(f'{{{i+86}}}', '')
                                            new_value = new_value.replace(f'{{{i+77}}}', '')
                                    
                                    # Somatório
                                    new_value = new_value.replace('{97}', str(alongamentos_soma))
                                    
                                    # Alongamentos individuais maior e menor
                                    if peca_tanque_local and peca_tanque_local.tipo == 'PF':
                                        if 100 < alongamentos_soma < 120:
                                            new_value = new_value.replace('{101}', 'X')
                                            new_value = new_value.replace('{102}', '')
                                        else:
                                            new_value = new_value.replace('{101}', '')
                                            new_value = new_value.replace('{102}', 'X')
                                    elif peca_tanque_local and peca_tanque_local.tipo != 'PF':
                                        if 321 < alongamentos_soma < 356:
                                            new_value = new_value.replace('{101}', 'X')
                                            new_value = new_value.replace('{102}', '')
                                        else:
                                            new_value = new_value.replace('{101}', '')
                                            new_value = new_value.replace('{102}', '')
                        
                        # Atualizar o texto da célula
                        if new_value != original_text:
                            # Limpar todos os parágrafos existentes
                            paragraphs_to_remove = cell.getElementsByType(P)
                            for para in paragraphs_to_remove:
                                cell.removeChild(para)
                            
                            # Criar novo parágrafo com o texto atualizado
                            new_para = P()
                            new_para.addText(new_value)
                            cell.addElement(new_para)
        
        # Salvar o documento modificado
        doc.save(ods_path)
        print(f'[_processar_ods_template_inspecao] ODS processado com sucesso: {ods_path}')
        
    except Exception as e:
        print(f'[_processar_ods_template_inspecao] Erro ao processar ODS: {str(e)}')
        import traceback
        print(traceback.format_exc())
        raise

def _gerar_excel_temp(concretagem_id,tanque_id=None,projeto_id=None,grupo_id=None):
    """
    Função auxiliar que gera o Excel e retorna o caminho do arquivo temporário
    Retorna o caminho do arquivo temporário ou None em caso de erro
    """
    temp_file_path = None
    temp_ods_path = None
    try:
       
        
        # Buscar a concretagem pelo ID
        query = ConcretoConcretagens.query.filter(
            ConcretoConcretagens.id == concretagem_id
        )
        concretagem = query.first()

        if not concretagem:
            print(f'Concretagem com ID {concretagem_id} não encontrada')
            return None

        contrato = None
        if projeto_id is not None:
            # Buscar informações do contrato/projeto
            contrato = Contrato.query.filter(Contrato.id == projeto_id).first()
        
      

        
        # Caminho do arquivo template - tentar ODS primeiro, depois XLSX
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates_excel'
        )
        
        template_ods = os.path.join(templates_dir, 'RELATORIO_INSPECAO.ods')
        template_xlsx = os.path.join(templates_dir, 'RELATORIO_INSPECAO.xlsx')
        
        template_path = None
        usar_ods = False
        temp_ods_path = None
        
        # Verificar qual template existe
        if os.path.exists(template_ods):
            template_path = template_ods
            usar_ods = True
            print(f'[_gerar_excel_temp] Usando template ODS')
        elif os.path.exists(template_xlsx):
            template_path = template_xlsx
            print(f'[_gerar_excel_temp] Usando template XLSX')
        else:
            print(f'Template RELATORIO_INSPECAO não encontrado (nem .ods nem .xlsx)')
            return None
        
        # Se for ODS e odfpy estiver disponível, processar diretamente
        if usar_ods and ODFPY_AVAILABLE:
            # Criar cópia do ODS e processar diretamente
            temp_file_path = _criar_arquivo_temp_projeto(suffix='.ods', prefix='excel_')
            shutil.copy2(template_path, temp_file_path)
            
            # Processar ODS diretamente
            _processar_ods_template_inspecao(
                temp_file_path,
                concretagem_id,
                concretagem,
                contrato,
                tanque_id,
                projeto_id,
                grupo_id
            )
            
            # Retornar o arquivo ODS processado
            return temp_file_path
        
        # Se for ODS mas odfpy não estiver disponível, converter para XLSX
        elif usar_ods and not ODFPY_AVAILABLE:
            print(f'[_gerar_excel_temp] odfpy não disponível, convertendo ODS para XLSX')
            temp_file_path = _criar_arquivo_temp_projeto(suffix='.xlsx', prefix='excel_')
            temp_ods_path = _criar_arquivo_temp_projeto(suffix='.ods', prefix='template_')
            shutil.copy2(template_path, temp_ods_path)
            
            # Converter ODS para XLSX usando LibreOffice
            template_xlsx_convertido = _converter_ods_para_xlsx_libreoffice(temp_ods_path, temp_file_path)
            if not template_xlsx_convertido:
                print(f'[_gerar_excel_temp] Erro ao converter ODS para XLSX')
                return None
        else:
            # Se for XLSX, apenas copiar
            temp_file_path = _criar_arquivo_temp_projeto(suffix='.xlsx', prefix='excel_')
            shutil.copy2(template_path, temp_file_path)
        
        # Carregar o arquivo Excel base (XLSX)
        wb = load_workbook(temp_file_path, data_only=False, keep_vba=False, read_only=False)
       
        # Processar apenas células com texto, preservando imagens e outros objetos
        for sheet in wb.worksheets:
            for index, row in enumerate(sheet.iter_rows()):
                if index == 77:
                    continue
                for index_cell, cell in enumerate(row):
                    if index_cell == 42:
                        continue
                    # Processar apenas células que contêm texto (string) e não estão vazias
                    if cell.value is not None and isinstance(cell.value, str) and len(cell.value.strip()) > 0 and  1<len(cell.value)<=5:
                        # Criar uma cópia do valor original para evitar problemas
                        original_value = str(cell.value)
                        new_value = original_value
                    
                        # Registro
                        new_value = new_value.replace('{1}', str(concretagem_id))

                        # Cliente
                        cliente_nome = 'N/A'
                        if contrato and contrato.cliente_direto:
                            cliente_nome = contrato.cliente_direto.nome
                        new_value = new_value.replace('{2}', str(cliente_nome))

                        #Obra
                        new_value = new_value.replace('{3}', str(contrato.nome if contrato else 'N/A'))

                        # Data de fabricação
                        new_value = new_value.replace('{4}', str(concretagem.data_concretagem.strftime('%d/%m/%Y')))

                        # Processar tanques do JSON
                        if concretagem.pecas:
                            pecas = json.loads(concretagem.pecas) if isinstance(concretagem.pecas, str) else concretagem.pecas
                            series=""
                            # Extrair todos os IDs únicos de tanques do JSON usando a função comum
                            tanques_ids_json = extrair_tanque_ids_do_json(concretagem.pecas)
                                
                               

                            
                            if tanques_ids_json:
                                # Buscar informações dos tanques usando a função comum
                                tanques = buscar_tanques_com_filtros(
                                    tanque_ids=tanques_ids_json,
                                    tanque_id=tanque_id,
                                    contrato_id=projeto_id,
                                    grupo_id=grupo_id
                                )
                                
                                tanques_nomes = {tanque.id: tanque.nome for tanque in tanques}
                                
                                # Se tanque_id for None, listar todos os tanques únicos
                                if tanque_id is None:
                                    # Listar todos os tanques encontrados no JSON (filtrar None antes de ordenar)
                                    nomes_tanques = []
                                    for tid in sorted([t for t in tanques_ids_json if t is not None]):
                                        if tid in tanques_nomes:
                                            nomes_tanques.append(tanques_nomes[tid])
                                    
                                    if nomes_tanques:
                                        new_value = new_value.replace('{5}', ', '.join(nomes_tanques))
                                else:
                                    # Se tanque_id foi especificado, mostrar apenas aquele tanque
                                    if tanque_id in tanques_nomes:
                                        new_value = new_value.replace('{5}', str(tanques_nomes[tanque_id]))
                                
                                #sistema (verificar se há tanques antes de acessar)
                                if tanques:
                                    new_value = new_value.replace('{6}', str(tanques[0].sistema if tanques[0].sistema else ''))
                                else:
                                    new_value = new_value.replace('{6}', '')
                                
                                #mesa
                                new_value = new_value.replace('{7}', str(concretagem.pista if concretagem.pista else ''))
                                
                                formas = [1,2,3,4,5,6,7,8,9,10,11,12]
                                for forma in formas:
                                    count = 0
                                    for peca in pecas:
                                        if isinstance(peca, dict) and 'forma' in peca and peca['forma'] is not None:
                                            try:
                                                # Converter forma para int se for string
                                                forma_peca = None
                                                if isinstance(peca['forma'], str):
                                                    try:
                                                        forma_peca = int(peca['forma'])
                                                    except (ValueError, TypeError):
                                                        continue
                                                elif isinstance(peca['forma'], int):
                                                    forma_peca = peca['forma']
                                                else:
                                                    continue
                                                
                                                # Verificar se forma_peca não é None antes de comparar
                                                if forma_peca is not None and forma_peca == forma:
                                                    # Verificar se tanque e placa existem
                                                    if peca.get('tanque') is not None and peca.get('placa'):
                                                        # Buscar peça usando a função comum
                                                        peca_tanque = buscar_peca_por_tanque_e_nome(
                                                            tanque_id=peca['tanque'],
                                                            nome_peca=peca['placa'],
                                                            tanque_id_filtro=tanque_id,
                                                            grupo_id=grupo_id
                                                        )
                                                        
                                                        if peca_tanque:
                                                            # Buscar séries da qualidade
                                                            qualidade = json.loads(peca_tanque.qualidade) if isinstance(peca_tanque.qualidade, str) else peca_tanque.qualidade
                                                            if qualidade and 'series' in qualidade:
                                                                for serie in qualidade['series']:
                                                                    if serie not in series:
                                                                        series += str(serie) + ', '
                                                            
                                                            #formas
                                                            new_value = new_value.replace(f'{{{7+forma}}}', str(forma))
                                                            #nomes
                                                            new_value = new_value.replace(f'{{{19+forma}}}', str(peca['placa']))
                                                            #tipo
                                                            new_value = new_value.replace(f'{{{31+forma}}}', str(peca_tanque.tipo if peca_tanque.tipo else ''))
                                                            #tipo painel
                                                            if peca_tanque.tipo == 'PF':
                                                                tipo_painel = 'FECHO'
                                                            elif peca_tanque.tipo in ['PN','P']:
                                                                tipo_painel = 'NORMAL'
                                                            else:
                                                                tipo_painel = 'ESPECIAL'
                                                            #tipo painel
                                                            new_value = new_value.replace(f'{{{43+forma}}}', str(tipo_painel))
                                                            count += 1
                                            except (ValueError, TypeError) as e:
                                                # Se não conseguir converter ou comparar, pular esta peça
                                                continue
                                    
                                    if count == 0:
                                        new_value = new_value.replace(f'{{{7+forma}}}', '')
                                        new_value = new_value.replace(f'{{{19+forma}}}', '')
                                        new_value = new_value.replace(f'{{{31+forma}}}', '')
                                        new_value = new_value.replace(f'{{{43+forma}}}', '')
                            
                            # Preencher campo de séries após processar todas as peças
                            if series:
                                series_str = ', '.join(str(serie) for serie in sorted(series))
                                new_value = new_value.replace('{120}', series_str)
                            else:
                                new_value = new_value.replace('{120}', '')
                                
                        #bobinas
                        if concretagem.cordoalhas:
                            cordoalhas = json.loads(concretagem.cordoalhas) if isinstance(concretagem.cordoalhas, str) else concretagem.cordoalhas
                            if cordoalhas and isinstance(cordoalhas, dict) and 'bobinas' in cordoalhas and cordoalhas['bobinas']:
                                bobinas = cordoalhas['bobinas']
                                #bobina 1
                                if len(bobinas) > 0 and bobinas[0]:
                                    bobina1 = bobinas[0]
                                    new_value = new_value.replace('{56}', str(bobina1.get('numero', '')))
                                    new_value = new_value.replace('{57}', str(bobina1.get('data_fabricacao', '')))
                                    new_value = new_value.replace('{60}', str(bobina1.get('certificado', '')))
                                else:
                                    new_value = new_value.replace('{56}', '')
                                    new_value = new_value.replace('{57}', '')
                                    new_value = new_value.replace('{60}', '')
                                
                                #bobina 2
                                if len(bobinas) > 1 and bobinas[1]:
                                    bobina2 = bobinas[1]
                                    new_value = new_value.replace('{58}', str(bobina2.get('numero', '')))
                                    new_value = new_value.replace('{59}', str(bobina2.get('data_fabricacao', '')))
                                    new_value = new_value.replace('{61}', str(bobina2.get('certificado', '')))
                                else:   
                                    new_value = new_value.replace('{58}', '')
                                    new_value = new_value.replace('{59}', '')
                                    new_value = new_value.replace('{61}', '')
                            else:
                                # Limpar campos de bobinas se não houver dados
                                new_value = new_value.replace('{55}', '')
                                new_value = new_value.replace('{57}', '')
                                new_value = new_value.replace('{58}', '')
                                new_value = new_value.replace('{59}', '')
                                new_value = new_value.replace('{60}', '')
                                new_value = new_value.replace('{61}', '')
                        
                        #alongamentos
                        if concretagem.cordoalhas:
                            cordoalhas_data = json.loads(concretagem.cordoalhas) if isinstance(concretagem.cordoalhas, str) else concretagem.cordoalhas
                            if cordoalhas_data and isinstance(cordoalhas_data, dict) and 'alongamentos' in cordoalhas_data:
                                alongamentos = cordoalhas_data['alongamentos']
                                total_alongamentos = len(alongamentos)
    
                                if alongamentos and isinstance(alongamentos, dict):
                                    # Iterar sobre os alongamentos (formato: {"C-1": 339, "C-2": 339, ...})
                                    alongamentos_soma = 0
                                    alongamentos_maior = 0
                                    alongamentos_menor = 0
                                    modulo = 198.7
                                    area = 99.7
                                    if peca_tanque and peca_tanque.tipo == 'PF':
                                        comprimento = 15000
                                    else:
                                        comprimento = 65000

                                    forca = 139.4
                                    alongamento_teorico = (forca * comprimento) / (modulo * area)

                                    if peca_tanque and peca_tanque.tipo == 'PF':
                                        alongamento_maximo_teorico = 120#alongamento_teorico * 1.05
                                        alongamento_minimo_teorico = 100#alongamento_teorico * 0.95
                                    else:
                                        alongamento_maximo_teorico = 356#alongamento_teorico * 1.05
                                        alongamento_minimo_teorico = 321#alongamento_teorico * 0.95
                                    alongamento_soma_maximo_teorico = alongamento_maximo_teorico*total_alongamentos#alongamento_soma_teorico * 1.03
                                    alongamento_soma_minimo_teorico = alongamento_minimo_teorico*total_alongamentos#alongamento_soma_teorico * 0.97

                                    new_value = new_value.replace('{98}', f"{alongamento_minimo_teorico:.2f}")
                                    new_value = new_value.replace('{99}', f"{alongamento_maximo_teorico:.2f}")
                                    new_value = new_value.replace('{115}', f"{alongamento_soma_minimo_teorico:.2f}")
                                    new_value = new_value.replace('{116}', f"{alongamento_soma_maximo_teorico:.2f}")
                                    alongamentos_fora_da_tolerancia = 0
                                    for chave, valor in alongamentos.items():
                                        alongamentos_soma += valor
                                        if valor > alongamentos_maior:
                                            alongamentos_maior = valor
                                        if valor < alongamentos_menor:
                                            alongamentos_menor = valor

                                        if valor > alongamento_maximo_teorico or valor < alongamento_minimo_teorico:
                                            new_value = new_value.replace(f'{{{103+alongamentos_fora_da_tolerancia}}}', str(chave.replace('C-', '')))
                                            alongamentos_fora_da_tolerancia += 1
                                        
                                        if chave and valor is not None:
                                            # Extrair o número da chave (ex: "C-1" -> 1)
                                            try:
                                                numero = int(chave.replace('C-', ''))
                                                # Preencher o placeholder correspondente (62 + número - 1, pois começa em C-1)
                                                placeholder = 62 + numero - 1
                                                new_value = new_value.replace(f'{{{placeholder}}}', str(valor))
                                            except (ValueError, TypeError):
                                                continue
                                    if alongamentos_fora_da_tolerancia < 12:
                                        for i in range(1,12-alongamentos_fora_da_tolerancia):
                                            new_value = new_value.replace(f'{{{102+alongamentos_fora_da_tolerancia+i}}}', '')
                                    # Tratar alongamentos além de C-16
                                    total_alongamentos = len(alongamentos)
                                    for i in range(total_alongamentos+1, 26):
                                        new_value = new_value.replace(f'{{{62+i}}}', '')

                                    if total_alongamentos > 16:
                                        new_value = new_value.replace('{122}', 'C-17')
                                        # Preencher C-17 até o último alongamento
                                        for i in range(17 , total_alongamentos + 1):
                                            chave = f'C-{i}'
                                            placeholder = 79 + (i - 17)
                                            if chave in alongamentos:
                                                valor = alongamentos[chave]
                                                
                                                new_value = new_value.replace(f'{{{placeholder+9}}}', chave)
                                                new_value = new_value.replace(f'{{{placeholder}}}', str(valor))
                                            else:
                                                new_value = new_value.replace(f'{{{placeholder+9}}}', '')

                                                                                    
                                        new_value = new_value.replace('{122}', '')
                                        # Limpar placeholders de C-17 até C-26
                                        for i in range(1, 11):
                                            if i>1:
                                                new_value = new_value.replace(f'{{{i+86}}}', '')
                                            new_value = new_value.replace(f'{{{i+77}}}', '')

                        #somatorio
                        new_value = new_value.replace('{97}', str(alongamentos_soma))
                        #alongamentos individuais maior e menor
                        #PF  100 < soma < 120 - ok
                        #PN  321 < soma < 356 - ok
                        if peca_tanque and peca_tanque.tipo == 'PF':
                            if 100 < alongamentos_soma < 120:
                                new_value = new_value.replace('{101}', 'X')
                                new_value = new_value.replace('{102}', '')
                            else:
                                new_value = new_value.replace('{101}', '')
                                new_value = new_value.replace('{102}', 'X')
                        elif peca_tanque and peca_tanque.tipo != 'PF':
                            if 321 < alongamentos_soma < 356:
                                new_value = new_value.replace('{101}', 'X')
                                new_value = new_value.replace('{102}', '')
                            else:
                                new_value = new_value.replace('{101}', '')
                                new_value = new_value.replace('{102}', '')
                    
                        
                        # TODO: Preencher outros campos conforme necessário baseado no template
                        # Por enquanto, apenas preenchemos os campos básicos
                        
                        # Atribuir o valor final à célula apenas uma vez
                        if new_value != original_value:
                            cell.value = new_value

        # Configurar tamanho da página como A4 para todas as planilhas
        for sheet in wb.worksheets:
            # A4 = '9' conforme documentação do openpyxl
            sheet.page_setup.paperSize = 9  # PAPERSIZE_A4
            sheet.page_setup.orientation = 'portrait'  # ORIENTATION_PORTRAIT
            
            # Configurar margens menores (em centímetros, convertido para polegadas)
            # Margens reduzidas: 0.5cm = ~0.2 polegadas
            sheet.page_margins = PageMargins(
                left=0.2,    # 0.5cm
                right=0.2,   # 0.5cm
                top=0.3,     # 0.75cm
                bottom=0.3,  # 0.75cm
                header=0.1,  # 0.25cm
                footer=0.1  # 0.25cm
            )
            
            # Ajustar escala para caber em 1 página de largura
            sheet.page_setup.fitToWidth = 1
            sheet.page_setup.fitToHeight = 1  # 0 = ajustar automaticamente a altura
        
        # Salvar o arquivo temporário
        try:
            wb.save(temp_file_path)
        except Exception as save_error:
            raise Exception(f'Erro ao salvar arquivo Excel: {str(save_error)}')
        finally:
            try:
                wb.close()
            except:
                pass
        
        # Verificar se o arquivo foi salvo corretamente
        if not os.path.exists(temp_file_path):
            return None
        
        file_size = os.path.getsize(temp_file_path)
        if file_size == 0:
            return None
        
        return temp_file_path
    except Exception as e:
        try:
            if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
                _limpar_arquivo_temp(temp_file_path)
            # Limpar arquivo ODS temporário se existir
            if 'temp_ods_path' in locals() and temp_ods_path and os.path.exists(temp_ods_path):
                _limpar_arquivo_temp(temp_ods_path)
        except:
            pass
        print(f'Erro ao gerar Excel: {str(e)}')
        return None
    finally:
        # Limpar arquivo ODS temporário após uso (se configurado)
        if 'temp_ods_path' in locals() and temp_ods_path and os.path.exists(temp_ods_path):
            _limpar_arquivo_temp(temp_ods_path)

@databook_inspecao_bp.route('/exportar-excel')
@login_required
def exportar_excel():
    """
    Exporta dados de uma concretagem específica para Excel usando template base
    """
    try:
        concretagem_id = request.args.get('concretagem_id', type=int)
        tanque_id = request.args.get('tanque_id', type=int) or None
        projeto_id = request.args.get('projeto_id', type=int) or None
        grupo_id = request.args.get('grupo_id', type=int) or None
        if not concretagem_id:
            return jsonify({'error': 'Parâmetro concretagem_id é obrigatório'}), 400
        time_inicio = datetime.now()
        excel_path = _gerar_excel_temp(concretagem_id, tanque_id, projeto_id, grupo_id)
        print(f'Tempo de geração do Excel: {datetime.now() - time_inicio}')
        if not excel_path:
            return jsonify({'error': f'Nenhuma concretagem encontrada para o ID {concretagem_id}'}), 404
        
        try:
            # Ler o arquivo salvo para o buffer
            output = io.BytesIO()
            with open(excel_path, 'rb') as f:
                output.write(f.read())
            output.seek(0)
            
            # Nome do arquivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'relatorio_inspecao_{concretagem_id}_{timestamp}.xlsx'
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )
        finally:
            # Limpar arquivo temporário (se configurado)
            if excel_path and os.path.exists(excel_path):
                _limpar_arquivo_temp(excel_path)
        
    except Exception as e:
        return jsonify({'error': f'Erro ao exportar Excel: {str(e)}'}), 500

@databook_inspecao_bp.route('/exportar-pdf')
@login_required
def exportar_pdf():
    """
    Exporta dados de uma concretagem específica para PDF convertendo do Excel/ODS gerado usando LibreOffice
    """
    excel_path = None
    pdf_temp_path = None
    
    try:
        concretagem_id = request.args.get('concretagem_id', type=int)
        tanque_id = request.args.get('tanque_id', type=int) or None
        projeto_id = request.args.get('projeto_id', type=int) or None
        
        if not concretagem_id:
            return jsonify({'error': 'Parâmetro concretagem_id é obrigatório'}), 400
        
        excel_path = _gerar_excel_temp(concretagem_id, tanque_id, projeto_id)
        
        if not excel_path or not os.path.exists(excel_path):
            return jsonify({'error': f'Nenhuma concretagem encontrada para o ID {concretagem_id}'}), 404
        
        # Verificar se o arquivo é válido
        if not os.path.isfile(excel_path):
            return jsonify({'error': f'Arquivo gerado não é um arquivo válido: {excel_path}'}), 500
        
        # Verificar tamanho do arquivo
        file_size = os.path.getsize(excel_path)
        if file_size == 0:
            return jsonify({'error': f'Arquivo gerado está vazio: {excel_path}'}), 500
        
        print(f'[exportar_pdf] Arquivo gerado: {excel_path}, tamanho: {file_size} bytes')
        
        # Converter Excel/ODS para PDF usando LibreOffice
        # Se o arquivo for ODS processado diretamente, gera PDF direto do ODS sem converter para XLSX
        generated_pdf_path = _converter_excel_para_pdf(excel_path)
        
        if not generated_pdf_path:
            # Verificar se o LibreOffice foi encontrado
            sistema = platform.system().lower()
            if sistema == 'linux' or sistema == 'linux2':
                soffice_cmd = shutil.which('soffice')
                if not soffice_cmd:
                    return jsonify({
                        'error': 'LibreOffice não encontrado no sistema. Instale com: sudo apt-get install libreoffice (Ubuntu/Debian) ou configure LIBREOFFICE_PATH'
                    }), 500
            return jsonify({
                'error': 'Erro ao converter Excel/ODS para PDF. Verifique os logs do servidor para mais detalhes. Verifique se o LibreOffice está instalado e configurado corretamente.'
            }), 500
        
        if not os.path.exists(generated_pdf_path):
            return jsonify({
                'error': f'PDF não foi gerado no caminho esperado: {generated_pdf_path}. Verifique os logs do servidor para mais detalhes.'
            }), 500
        
        # Verificar se o PDF foi gerado corretamente
        pdf_size = os.path.getsize(generated_pdf_path)
        if pdf_size == 0:
            return jsonify({
                'error': f'PDF gerado está vazio: {generated_pdf_path}'
            }), 500
        
        print(f'[exportar_pdf] PDF gerado com sucesso: {generated_pdf_path}, tamanho: {pdf_size} bytes')
        
        # Ler o PDF gerado para buffer de memória
        output = io.BytesIO()
        with open(generated_pdf_path, 'rb') as f:
            output.write(f.read())
        output.seek(0)
        
        # Nome do arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'relatorio_inspecao_{concretagem_id}_{timestamp}.pdf'
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        # Garantir que a mensagem de erro seja sempre uma string
        try:
            error_msg = str(e) if e is not None else 'Erro desconhecido'
        except:
            error_msg = 'Erro desconhecido ao processar exceção'
        return jsonify({'error': f'Erro ao exportar PDF: {error_msg}'}), 500
    finally:
        # Limpar arquivos temporários (se configurado)
        if excel_path and os.path.exists(excel_path):
            _limpar_arquivo_temp(excel_path)
        if 'generated_pdf_path' in locals() and generated_pdf_path and os.path.exists(generated_pdf_path):
            # Se o PDF está em um diretório temporário do projeto, remover o diretório inteiro
            pdf_dir = os.path.dirname(generated_pdf_path)
            temp_dir_projeto = _obter_pasta_temp_projeto()
            if pdf_dir and os.path.exists(pdf_dir) and temp_dir_projeto in pdf_dir:
                _limpar_diretorio_temp(pdf_dir)
            else:
                _limpar_arquivo_temp(generated_pdf_path)

@databook_inspecao_bp.route('/exportar-massa', methods=['POST'])
@login_required
def exportar_massa():
    """
    Exporta múltiplas concretagens em massa (Excel ou PDF)
    Retorna um arquivo ZIP com todos os arquivos gerados
    """
    try:
        data = request.get_json()
        concretagens_ids = data.get('concretagens_ids', [])
        formato = data.get('formato', 'excel')  # 'excel' ou 'pdf'
        tanque_id = data.get('tanque_id')
        projeto_id = data.get('projeto_id')
        grupo_id = data.get('grupo_id')
        
        if not concretagens_ids:
            return jsonify({'error': 'Nenhuma concretagem fornecida'}), 400
        
        # Criar diretório temporário para os arquivos
        temp_dir = _criar_diretorio_temp_projeto(prefix='export_massa_')
        arquivos_gerados = []
        excel_paths = []
        
        try:
            # Primeiro, gerar todos os arquivos Excel
            for concretagem_id in concretagens_ids:
                try:
                    if formato == 'excel':
                        # Gerar Excel
                        excel_path = _gerar_excel_temp(concretagem_id, tanque_id, projeto_id, grupo_id)
                        if excel_path and os.path.exists(excel_path):
                            # Copiar para o diretório temporário com nome único
                            nome_arquivo = f'relatorio_inspecao_{concretagem_id}.xlsx'
                            destino = os.path.join(temp_dir, nome_arquivo)
                            shutil.copy2(excel_path, destino)
                            arquivos_gerados.append(destino)
                            # Limpar arquivo temporário original (se configurado)
                            _limpar_arquivo_temp(excel_path)
                    else:  # PDF
                        # Gerar arquivo (Excel ou ODS) primeiro e armazenar caminho
                        # Se ODS estiver disponível e processado diretamente, será usado para gerar PDF direto
                        excel_path = _gerar_excel_temp(concretagem_id, tanque_id, projeto_id, grupo_id)
                        if excel_path and os.path.exists(excel_path):
                            excel_paths.append(excel_path)
                            
                except Exception as e:
                    print(f'Erro ao processar concretagem {concretagem_id}: {str(e)}')
                    continue
            
            # Se for PDF, converter todos os arquivos usando LibreOffice
            if formato == 'pdf' and excel_paths:
                # Converter arquivo por arquivo usando LibreOffice
                # Se o arquivo for ODS processado diretamente, gera PDF direto do ODS sem converter para XLSX
                for i, excel_path in enumerate(excel_paths):
                    try:
                        concretagem_id = concretagens_ids[i] if i < len(concretagens_ids) else None
                        # Converter para PDF (aceita tanto XLSX quanto ODS)
                        pdf_path = _converter_excel_para_pdf_libreoffice(excel_path)
                        if pdf_path and os.path.exists(pdf_path):
                            nome_arquivo = f'relatorio_inspecao_{concretagem_id}.pdf'
                            destino = os.path.join(temp_dir, nome_arquivo)
                            shutil.copy2(pdf_path, destino)
                            arquivos_gerados.append(destino)
                            # Limpar PDF temporário (se configurado)
                            pdf_dir = os.path.dirname(pdf_path)
                            temp_dir_projeto = _obter_pasta_temp_projeto()
                            if pdf_dir and temp_dir_projeto in pdf_dir:
                                _limpar_diretorio_temp(pdf_dir)
                            else:
                                _limpar_arquivo_temp(pdf_path)
                    except Exception as e:
                        print(f'Erro ao converter Excel/ODS para PDF (LibreOffice) da concretagem {concretagens_ids[i] if i < len(concretagens_ids) else "desconhecida"}: {str(e)}')
                        continue
            
            if not arquivos_gerados:
                return jsonify({'error': 'Nenhum arquivo foi gerado com sucesso'}), 404
            
            # Criar arquivo ZIP
            zip_buffer = io.BytesIO()
            try:
                # Verificar se todos os arquivos existem antes de criar o ZIP
                arquivos_validos = []
                for arquivo in arquivos_gerados:
                    if arquivo and os.path.exists(arquivo):
                        arquivos_validos.append(arquivo)
                    else:
                        print(f'Aviso: Arquivo não encontrado ou inválido: {arquivo}')
                
                if not arquivos_validos:
                    return jsonify({'error': 'Nenhum arquivo válido encontrado para criar o ZIP'}), 404
                
                print(f'Criando ZIP com {len(arquivos_validos)} arquivos válidos de {len(arquivos_gerados)} totais')
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for arquivo in arquivos_validos:
                        try:
                            nome_arquivo = os.path.basename(arquivo)
                            zip_file.write(arquivo, nome_arquivo)
                            print(f'Adicionado ao ZIP: {nome_arquivo}')
                        except Exception as file_error:
                            print(f'Erro ao adicionar arquivo {arquivo} ao ZIP: {str(file_error)}')
                            continue
                
                zip_buffer.seek(0)
                
                # Limpar arquivos Excel/ODS temporários antes de retornar (já foram copiados para o ZIP)
                for excel_path in excel_paths:
                    if excel_path and os.path.exists(excel_path):
                        _limpar_arquivo_temp(excel_path)
                
                # Nome do arquivo ZIP
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'exportacao_massa_{formato}_{timestamp}.zip'
                
                print(f'Retornando arquivo ZIP com {len(arquivos_validos)} arquivos')
                return send_file(
                    zip_buffer,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=filename
                )
            except Exception as zip_error:
                print(f'Erro ao criar ZIP: {str(zip_error)}')
                import traceback
                print(traceback.format_exc())
                raise
            
        finally:
            # Limpar diretório temporário principal (se configurado)
            try:
                if temp_dir and os.path.exists(temp_dir):
                    _limpar_diretorio_temp(temp_dir)
                    print(f'Diretório temporário limpo: {temp_dir}')
            except Exception as cleanup_error:
                print(f'Erro ao limpar diretório temporário {temp_dir}: {str(cleanup_error)}')
                import traceback
                print(traceback.format_exc())
                
    except Exception as e:
        return jsonify({'error': f'Erro ao exportar em massa: {str(e)}'}), 500

