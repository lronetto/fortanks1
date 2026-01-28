import logging
from time import time
from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required
from openpyxl.worksheet.page import PageMargins
from models import tanque
from models.concreto import ConcretoConcretagens, ConcretoConcretagensTanques, ConcretoUsinagens
from models.contrato import Contrato
from models.tanque import Tanques, TanquesPecas, TanquesGrupos
from models.database import db
from models.certificado import Certificados
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
        {"nome": "PN-02", "tanque_id": 1, "forma": "4"},
        {"nome": "PN-03", "tanque_id": 1, "forma": "6"},
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
                    tanque_id = item.get('tanque_id')
                    if tanque_id:
                        tanque_ids.add(int(tanque_id))
        # Se for um objeto com uma lista de peças
        elif isinstance(pecas_data, dict):
            if 'pecas' in pecas_data and isinstance(pecas_data['pecas'], list):
                for item in pecas_data['pecas']:
                    if isinstance(item, dict):
                        tanque_id = item.get('tanque_id')
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
                            logging.info(f'[_converter_excel_para_pdf_libreoffice] Caminho encontrado: {path}')
                
                # Buscar em /opt
                opt_paths = glob.glob('/opt/libreoffice*/program/soffice')
                possiveis_caminhos.extend(opt_paths)
                for path in opt_paths:
                    logging.info(f'[_converter_excel_para_pdf_libreoffice] Caminho encontrado em /opt: {path}')
                
                logging.info(f'[_converter_excel_para_pdf_libreoffice] Total de caminhos a verificar: {len(possiveis_caminhos)}')
                
                # Verificar cada caminho
                for caminho in possiveis_caminhos:
                    logging.info(f'[_converter_excel_para_pdf_libreoffice] Verificando caminho: {caminho}')
                    if os.path.exists(caminho):
                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Caminho existe: {caminho}')
                        if os.access(caminho, os.X_OK):
                            logging.info(f'[_converter_excel_para_pdf_libreoffice] Caminho tem permissão de execução: {caminho}')
                            # Verificar se é um executável real (ELF binary) ou um link simbólico válido
                            try:
                                # Verificar se é um link simbólico
                                if os.path.islink(caminho):
                                    real_path = os.path.realpath(caminho)
                                    logging.info(f'[_converter_excel_para_pdf_libreoffice] É um link simbólico apontando para: {real_path}')
                                    if os.path.exists(real_path) and os.access(real_path, os.X_OK):
                                        caminho = real_path
                                
                                with open(caminho, 'rb') as f:
                                    header = f.read(4)
                                    if header.startswith(b'\x7fELF'):  # ELF binary
                                        soffice_cmd = caminho
                                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Encontrado executável real (ELF): {soffice_cmd}')
                                        break
                                    else:
                                        # Pode ser um script ou link simbólico, mas vamos usar se existir e tiver permissão
                                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Arquivo não é ELF, mas existe e tem permissão: {caminho}')
                                        # Usar este arquivo se ainda não encontrou nenhum
                                        if not soffice_cmd:
                                            soffice_cmd = caminho
                                            logging.info(f'[_converter_excel_para_pdf_libreoffice] Usando arquivo encontrado: {soffice_cmd}')
                            except Exception as e:
                                logging.warning(f'[_converter_excel_para_pdf_libreoffice] Erro ao verificar {caminho}: {str(e)}')
                                # Se não encontrou nenhum ainda e o arquivo existe, usar como último recurso
                                if not soffice_cmd and os.path.exists(caminho):
                                    soffice_cmd = caminho
                                    logging.info(f'[_converter_excel_para_pdf_libreoffice] Usando como último recurso: {soffice_cmd}')
                        else:
                            logging.warning(f'[_converter_excel_para_pdf_libreoffice] Caminho existe mas não tem permissão de execução: {caminho}')
                    else:
                        logging.debug(f'[_converter_excel_para_pdf_libreoffice] Caminho não existe: {caminho}')
                
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
        
        # Verificar se o executável existe e tem permissões
        if not os.path.exists(soffice_cmd):
            logging.error(f'[_converter_excel_para_pdf_libreoffice] Executável não existe: {soffice_cmd}')
            return None
        
        if not os.access(soffice_cmd, os.X_OK):
            logging.error(f'[_converter_excel_para_pdf_libreoffice] Executável não tem permissão de execução: {soffice_cmd}')
            return None
        
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Executando: {" ".join(cmd)}')
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Arquivo de entrada: {excel_path}')
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Diretório de saída: {output_dir}')
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Executável: {soffice_cmd}')
        
        try:
            # Configurar ambiente completo para o LibreOffice funcionar
            env = os.environ.copy()
            
            # Garantir que comandos básicos estejam no PATH
            basic_paths = ['/usr/bin', '/bin', '/usr/local/bin', '/sbin', '/usr/sbin']
            current_path = env.get('PATH', '')
            for path in basic_paths:
                if path not in current_path:
                    env['PATH'] = f"{path}:{env.get('PATH', '')}"
            
            # Configurar LD_LIBRARY_PATH para encontrar bibliotecas do LibreOffice
            libreoffice_lib_dir = os.path.dirname(os.path.dirname(soffice_cmd))
            lib_paths = [
                f'{libreoffice_lib_dir}/program',
                f'{libreoffice_lib_dir}/ure/lib',
                '/usr/lib',
                '/usr/lib64',
                '/lib',
                '/lib64',
            ]
            
            current_ld_path = env.get('LD_LIBRARY_PATH', '')
            for lib_path in lib_paths:
                if os.path.exists(lib_path) and lib_path not in current_ld_path:
                    env['LD_LIBRARY_PATH'] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"
            
            # Configurar variáveis específicas do LibreOffice
            env['SAL_USE_VCLPLUGIN'] = 'headless'
            env['SAL_DISABLE_OPENCL'] = '1'
            
            # Remover variáveis que podem causar problemas
            env.pop('DISPLAY', None)  # Garantirx modo headless
            
            logging.info(f'[_converter_excel_para_pdf_libreoffice] PATH: {env.get("PATH", "")[:200]}...')
            logging.info(f'[_converter_excel_para_pdf_libreoffice] LD_LIBRARY_PATH: {env.get("LD_LIBRARY_PATH", "")[:200]}...')
            
            # Executar conversão com ambiente configurado
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # Timeout de 2 minutos
                check=False,
                env=env,
                cwd=os.path.dirname(soffice_cmd)  # Executar no diretório do LibreOffice
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
                                    break
                        except Exception as e:
                            print(f'[_converter_ods_para_xlsx_libreoffice] Erro ao verificar {caminho}: {str(e)}')
                            continue
                
                # Se não encontrou o executável real, tentar extrair do wrapper
                if not soffice_cmd:
                    # Tentar encontrar usando shutil.which (pode retornar o wrapper)
                    wrapper_path = shutil.which('soffice')
                    if wrapper_path:
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
        
        # Observação: em algumas instalações Linux, `--convert-to xlsx` sem filtro pode falhar silenciosamente
        # (ou gerar outro formato). O filtro abaixo é o mais compatível para XLSX.
        convert_to_arg = 'xlsx:"Calc MS Excel 2007 XML"'

        cmd = [
            soffice_cmd,
            '--headless',
            '--nologo',
            '--nolockcheck',
            '--nodefault',
            '--norestore',
            '--convert-to', convert_to_arg,
            '--outdir', output_dir,
            ods_path
        ]
        
        # Verificar se o executável existe e tem permissões
        if not os.path.exists(soffice_cmd):
            print(f'[_converter_ods_para_xlsx_libreoffice] Executável não existe: {soffice_cmd}')
            return None
        
        if not os.access(soffice_cmd, os.X_OK):
            print(f'[_converter_ods_para_xlsx_libreoffice] Executável não tem permissão de execução: {soffice_cmd}')
            return None
        
            
        try:
            # Configurar ambiente completo para o LibreOffice funcionar
            env = os.environ.copy()
            
            # Garantir que comandos básicos estejam no PATH
            basic_paths = ['/usr/bin', '/bin', '/usr/local/bin', '/sbin', '/usr/sbin']
            current_path = env.get('PATH', '')
            for path in basic_paths:
                if path not in current_path:
                    env['PATH'] = f"{path}:{env.get('PATH', '')}"
            
            # Configurar LD_LIBRARY_PATH para encontrar bibliotecas do LibreOffice
            libreoffice_lib_dir = os.path.dirname(os.path.dirname(soffice_cmd))
            lib_paths = [
                f'{libreoffice_lib_dir}/program',
                f'{libreoffice_lib_dir}/ure/lib',
                '/usr/lib',
                '/usr/lib64',
                '/lib',
                '/lib64',
            ]
            
            current_ld_path = env.get('LD_LIBRARY_PATH', '')
            for lib_path in lib_paths:
                if os.path.exists(lib_path) and lib_path not in current_ld_path:
                    env['LD_LIBRARY_PATH'] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"
            
            # Configurar variáveis específicas do LibreOffice
            env['SAL_USE_VCLPLUGIN'] = 'headless'
            env['SAL_DISABLE_OPENCL'] = '1'
            
            # Remover variáveis que podem causar problemas
            env.pop('DISPLAY', None)  # Garantir modo headless
            
             
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=env,
                cwd=os.path.dirname(soffice_cmd)  # Executar no diretório do LibreOffice
            )
            
            if result.returncode != 0:
                print(f'[_converter_ods_para_xlsx_libreoffice] Erro ao converter (código {result.returncode})')
                print(f'[_converter_ods_para_xlsx_libreoffice] stdout: {result.stdout}')
                print(f'[_converter_ods_para_xlsx_libreoffice] stderr: {result.stderr}')
                return None
            else:
                # LibreOffice costuma escrever mensagens úteis no stdout mesmo quando dá certo
                if result.stdout:
                    print(f'[_converter_ods_para_xlsx_libreoffice] stdout: {result.stdout}')
                if result.stderr:
                    print(f'[_converter_ods_para_xlsx_libreoffice] stderr: {result.stderr}')
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
            # Caso 1: caminho "esperado" existe
            if os.path.exists(generated_xlsx_path):
                tamanho_anterior = os.path.getsize(generated_xlsx_path)
                time.sleep(0.5)
                tamanho_atual = os.path.getsize(generated_xlsx_path)
                if tamanho_anterior == tamanho_atual and tamanho_atual > 0:
                    logging.info(f'[_converter_ods_para_xlsx_libreoffice] XLSX gerado com sucesso: {generated_xlsx_path}')
                    if generated_xlsx_path != xlsx_path:
                        shutil.move(generated_xlsx_path, xlsx_path)
                    return xlsx_path

            # Caso 2 (Linux): LO pode gerar com nome ligeiramente diferente; procurar qualquer .xlsx no outdir
            try:
                candidatos = [
                    os.path.join(output_dir, f)
                    for f in os.listdir(output_dir)
                    if f.lower().endswith('.xlsx')
                ]
                if candidatos:
                    # Pegar o mais recente
                    candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                    candidato = candidatos[0]
                    tamanho = os.path.getsize(candidato)
                    if tamanho > 0:
                        if candidato != xlsx_path:
                            shutil.move(candidato, xlsx_path)
                        return xlsx_path
            except Exception as e:
                print(f'[_converter_ods_para_xlsx_libreoffice] Erro ao procurar XLSX no diretório de saída: {str(e)}')

            tentativa += 1
            time.sleep(0.5)
        
        print(f'[_converter_ods_para_xlsx_libreoffice] XLSX não foi gerado após {max_tentativas} tentativas')
        try:
            arquivos_no_dir = os.listdir(output_dir)
            print(f'[_converter_ods_para_xlsx_libreoffice] Arquivos no diretório de saída: {arquivos_no_dir}')
        except Exception:
            pass
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
        time_start = time.time()
        # Preparar dados para substituição
        pecas = None
        tanques_ids = []
        tanques_nomes = []
        pecas_concretadas = []
        series_concretadas = []
        tanques_sistemas = []
        clientes_nome = []
        contratos_nome = []
        data_conclusao = None 
        if tanque_id:
            tanque = Tanques.query.get(tanque_id)
            tanques_ids = [tanque_id]
            tanques_nomes = [tanque.nome]
            tanques_sistemas = [tanque.sistema]
            clientes_nome = [tanque.contrato.cliente_direto.nome]
            contratos_nome = [tanque.contrato.nome]
        elif grupo_id:
            grupo = TanquesGrupos.query.get(grupo_id)
            if grupo and grupo.tanques:
                for tanque in grupo.tanques:
                    if tanque.id in concretagem.get_tanques_ids():
                        if tanque.id not in tanques_ids:
                            tanques_ids.append(tanque.id)
                            tanques_nomes.append(tanque.nome)
                        if tanque.sistema not in tanques_sistemas:
                            tanques_sistemas.append(tanque.sistema)
                        if tanque.contrato.cliente_direto.nome not in clientes_nome:
                            clientes_nome.append(tanque.contrato.cliente_direto.nome)
                        if tanque.contrato.nome not in contratos_nome:
                            contratos_nome.append(tanque.contrato.nome)
        elif projeto_id:
            tanques = Tanques.query.filter_by(contrato_id=projeto_id).all()
            if tanques:
                for tanque in tanques:
                    if tanque.id in concretagem.get_tanques_ids():
                        if tanque.id not in tanques_ids:
                            tanques_ids.append(tanque.id)
                            tanques_nomes.append(tanque.nome)
                        if tanque.sistema not in tanques_sistemas:
                            tanques_sistemas.append(tanque.sistema)
                        if tanque.contrato.cliente_direto.nome not in clientes_nome:
                            clientes_nome.append(tanque.contrato.cliente_direto.nome)
                        if tanque.contrato.nome not in contratos_nome:
                            contratos_nome.append(tanque.contrato.nome)
        else:
            concretagem = ConcretoConcretagens.query.get(concretagem_id)
            if concretagem:
                pecas = concretagem.get_pecas()
                if pecas:
                    for peca in pecas:
                        tanque = Tanques.query.get(peca['tanque_id'])
                        if tanque:
                            if tanque.id not in tanques_ids:
                                tanques_ids.append(tanque.id)
                                tanques_nomes.append(tanque.nome)
                            if tanque.sistema not in tanques_sistemas:
                                tanques_sistemas.append(tanque.sistema)
                            if tanque.contrato.cliente_direto.nome not in clientes_nome:
                                clientes_nome.append(tanque.contrato.cliente_direto.nome)
                            if tanque.contrato.nome not in contratos_nome:
                                contratos_nome.append(tanque.contrato.nome)
            
       
       
        # Buscar primeira peça válida para usar no processamento de alongamentos
        peca_tanque_global = None
        if tanques_ids:
            pecasb = concretagem.get_pecas()
            if pecasb:
                for peca in pecasb:
                    if peca['tanque_id'] in tanques_ids:
                        peca_tanque = TanquesPecas.query.filter(TanquesPecas.tanque_id == peca['tanque_id'], TanquesPecas.nome == peca['nome']).first()
                        series = peca_tanque.get_series_de_pecas()
                        if peca_tanque:
                            peca['tipo'] = peca_tanque.tipo
                            pecas_concretadas.append(peca)
                            if len(series) > 0:
                                for serie in series:
                                    if serie not in series_concretadas:
                                        usinagem = ConcretoUsinagens.query.filter(ConcretoUsinagens.serie == serie).first()
                                        if usinagem:
                                            data = usinagem.data_usinagem
                                            if data:
                                                if data_conclusao < data:
                                                    data_conclusao = data
                                        series_concretadas.append(serie)
        else:
            pecas_concretadasb = concretagem.get_pecas()
            if pecas_concretadasb:
                for peca_tanque in pecas_concretadasb:
                    peca_obj = TanquesPecas.query.filter(TanquesPecas.tanque_id == peca_tanque['tanque_id'], TanquesPecas.nome == peca_tanque['nome']).first()
                    series = peca_obj.get_series_de_pecas()
                    if peca_obj:
                        peca = {
                            'tanque_id': peca_tanque['tanque_id'],
                            'nome': peca_tanque['nome'],
                            'tipo': peca_obj.tipo,
                            'series': series
                        }
                        pecas_concretadas.append(peca)
                        for serie in series:
                            if serie not in series_concretadas:
                                usinagem = ConcretoUsinagens.query.filter(ConcretoUsinagens.serie == serie).first()
                                if usinagem:
                                    data = usinagem.data_usinagem
                                    if data:
                                        if data_conclusao < data:
                                            data_conclusao = data
                                series_concretadas.append(serie)
        print(f'[_processar_ods_template_inspecao] Tanques IDs: {len(tanques_ids)}')
        print(f'[_processar_ods_template_inspecao] Tanques Nomes: {len(tanques_nomes)}')
        print(f'[_processar_ods_template_inspecao] Tanques Sistemas: {len(tanques_sistemas)}')
        print(f'[_processar_ods_template_inspecao] Clientes Nome: {len(clientes_nome)}')
        print(f'[_processar_ods_template_inspecao] Contratos Nome: {len(contratos_nome)}')
        print(f'[_processar_ods_template_inspecao] Data de Conclusão: {data_conclusao}')
        print(f'[_processar_ods_template_inspecao] Pecas Concretadas: {len(pecas_concretadas)}')
        print(f'[_processar_ods_template_inspecao] Series Concretadas: {len(series_concretadas)}')
        time_end = time.time()
        print(f'[_processar_ods_template_inspecao] Tempo de execução dados iniciais: {time_end - time_start} segundos')
        
        time_start = time.time()
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
                        if clientes_nome:
                            if len(clientes_nome) > 1:
                                cliente_nome = ', '.join(clientes_nome)
                            else:
                                cliente_nome = clientes_nome[0]
                        new_value = new_value.replace('{2}', str(cliente_nome))
                        contrato_nome = 'N/A'
                        if contratos_nome:
                            if len(contratos_nome) > 1:
                                contrato_nome = ', '.join(contratos_nome)
                            else:
                                contrato_nome = contratos_nome[0]
                        new_value = new_value.replace('{3}', str(contrato_nome))
                        new_value = new_value.replace('{4}', str(concretagem.data_concretagem.strftime('%d/%m/%Y')))
                        
                        if tanques_nomes:
                            if len(tanques_nomes) > 1:
                                nomes = ', '.join(tanques_nomes)
                            else:
                                nomes = tanques_nomes[0]
                            new_value = new_value.replace('{5}', str(nomes))
                               
                        else:
                            new_value = new_value.replace('{5}', '')

                        if tanques_sistemas:
                            if len(tanques_sistemas) > 1:
                                sistemas = ', '.join(tanques_sistemas)
                            else:
                                sistemas = tanques_sistemas[0]
                            new_value = new_value.replace('{6}', str(sistemas))
                        else:
                            new_value = new_value.replace('{6}', '')
                                
                        new_value = new_value.replace('{7}', concretagem.pista)
                                
                        # Processar formas
                        formas = [0,1,2,3,4,5,6,7,8,9,10,11,12]
                        for forma in formas:
                            count = 0
                            for peca in pecas_concretadas:
                                if peca['forma'] is not None:
                                    forma_peca = peca['forma']
                                    if forma_peca == forma:
                                        new_value = new_value.replace(f'{{{7+forma}}}', str(forma))
                                        new_value = new_value.replace(f'{{{19+forma}}}', str(peca['nome']))
                                        new_value = new_value.replace(f'{{{31+forma}}}', str(peca['tipo']))
                                        
                                        if peca_tanque.tipo == 'PF':
                                            tipo_painel = 'FECHO'
                                        elif peca_tanque.tipo in ['PN','P']:
                                            tipo_painel = 'NORMAL'
                                        else:
                                            tipo_painel = 'ESPECIAL'
                                        new_value = new_value.replace(f'{{{43+forma}}}', str(tipo_painel))
                                        count += 1

                            if count == 0:
                                new_value = new_value.replace(f'{{{7+forma}}}', '')
                                new_value = new_value.replace(f'{{{19+forma}}}', '')
                                new_value = new_value.replace(f'{{{31+forma}}}', '')
                                new_value = new_value.replace(f'{{{43+forma}}}', '')
                           
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
                        
                        if 'PF' in peca_tanque.tipo:
                            alongamento_maximo_unitario = 120
                            alongamento_minimo_unitario = 100
                        else:
                            alongamento_maximo_unitario = 356
                            alongamento_minimo_unitario = 321
                        # Processar alongamentos
                        alongamentos_soma = 0  # Inicializar variável para uso posterior
                        alongamentos_lista = []
                        alongamentos_total = 0
                        alongamento_maior = 0
                        alongamento_menor = 0
                        alongamento_maximo_teorico = 0
                        alongamento_minimo_teorico = 0
                        alongamentos_fora_da_tolerancia = []
                        if concretagem.cordoalhas:
                            cordoalhas_data = json.loads(concretagem.cordoalhas) if isinstance(concretagem.cordoalhas, str) else concretagem.cordoalhas
                            if cordoalhas_data and isinstance(cordoalhas_data, dict) and 'alongamentos' in cordoalhas_data:
                                alongamentos = cordoalhas_data['alongamentos']
                                
                                
                                # Suportar tanto array quanto dict (retrocompatibilidade)
                                if isinstance(alongamentos, list):
                                    # Novo formato: array de valores [350, 351, 347, ...]
                                    for alongamento in alongamentos:
                                        if alongamento is not None and alongamento != 'null':
                                            alongamentos_lista.append(alongamento)
                                        else:
                                            break
                                else:
                                    alongamentos_lista = [a for a in alongamentos.values() if a is not None]
                        
                        alongamentos_total = len(alongamentos_lista)
                       #print(f'[_processar_ods_template_inspecao] Alongamentos: {alongamentos_total}')
                        alongamento_maximo_teorico = alongamento_maximo_unitario * alongamentos_total
                        alongamento_minimo_teorico = alongamento_minimo_unitario * alongamentos_total

                        new_value = new_value.replace(f'{{{98}}}', f'{alongamento_minimo_unitario:.2f}')
                        new_value = new_value.replace(f'{{{99}}}', f'{alongamento_maximo_unitario:.2f}')
                        new_value = new_value.replace(f'{{{115}}}', f'{alongamento_minimo_teorico:.2f}')
                        new_value = new_value.replace(f'{{{116}}}', f'{alongamento_maximo_teorico:.2f}')

                        if alongamentos_total > 0:
                            for alongamento in alongamentos_lista:
                                alongamentos_soma += alongamento
                                if alongamento > alongamento_maior:
                                    alongamento_maior = alongamento
                                if alongamento < alongamento_menor or alongamento_menor == 0:
                                    alongamento_menor = alongamento
                                if alongamento > alongamento_maximo_unitario or alongamento < alongamento_minimo_unitario:
                                    alongamentos_fora_da_tolerancia.append(alongamento)
                                        
                            if len(alongamentos_fora_da_tolerancia) < 12:
                                for i in range(1, 13 - len(alongamentos_fora_da_tolerancia)):
                                    new_value = new_value.replace(f'{{{102+len(alongamentos_fora_da_tolerancia)+i}}}', '')
                                    
                            for index, alongamento in enumerate(alongamentos_lista):
                                new_value = new_value.replace(f'{{{62+index}}}', str(alongamento))

                            if alongamentos_total > 16:
                                new_value = new_value.replace('{122}', 'C-17')
                                for i in range(17, alongamentos_total):
                                    new_value = new_value.replace(f'{{{88-17+i}}}', f'C-{i+1}')

                                for i in range(alongamentos_total-17, 9):
                                    new_value = new_value.replace(f'{{{88+i}}}', '')
                                    new_value = new_value.replace(f'{{{79+i}}}', '')
                            else:    
                                new_value = new_value.replace('{122}', '')
                                for i in range(1, 11):
                                    new_value = new_value.replace(f'{{{86+i}}}', '')
                                    new_value = new_value.replace(f'{{{77+i}}}', '')

                                        # Somatório
                            new_value = new_value.replace('{97}', str(alongamentos_soma))
                                
                            # Alongamentos individuais maior e menor
                            if alongamento_menor < alongamento_minimo_unitario or alongamento_maior > alongamento_maximo_unitario:
                                new_value = new_value.replace('{101}', '')
                                new_value = new_value.replace('{102}', 'X')
                            else:
                                new_value = new_value.replace('{101}', 'X')
                                new_value = new_value.replace('{102}', '')
                            
                            if alongamentos_soma < alongamento_minimo_teorico or alongamentos_soma > alongamento_maximo_teorico:
                                new_value = new_value.replace('{117}', '')
                                new_value = new_value.replace('{118}', 'X')
                            else:
                                new_value = new_value.replace('{117}', 'X')
                                new_value = new_value.replace('{118}', '')

                        certificado = Certificados.query.filter(\
                            Certificados.tipo_id==2,\
                            Certificados.dados_adicionais.contains('"tipo": "2"'),\
                            Certificados.data_vencimento>=datetime.now(),\
                            Certificados.ativo==True).first()
                        if certificado:
                            dados = json.loads(certificado.dados_adicionais)
                            new_value = new_value.replace('{119}', str(dados.get('certificado', '')))
                        else:
                            new_value = new_value.replace('{119}', '')
                        # Processar series concretadas
                        if series_concretadas:
                            if len(series_concretadas) > 1:
                                series_concretadas_nome = ', '.join(str(serie) for serie in series_concretadas)
                            else:
                                series_concretadas_nome = series_concretadas[0]
                            new_value = new_value.replace('{120}', str(series_concretadas_nome))
                        else:
                            new_value = new_value.replace('{120}', '')

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
        time_end = time.time()
        print(f'[_processar_ods_template_inspecao] Tempo de execução processamento: {time_end - time_start} segundos')
        # Salvar o documento modificado
        doc.save(ods_path)
        
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
            print(f'[_gerar_excel_temp] odfpy não disponível')
            return None
    except Exception as e:
        print(f'[_gerar_excel_temp] Erro ao gerar Excel: {str(e)}')
        import traceback
        print(traceback.format_exc())
        raise
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
            # Verificar se o arquivo é ODS e converter para XLSX se necessário
            arquivo_final = excel_path
            ods_original = None
            
            if excel_path.lower().endswith('.ods'):
                # Criar caminho para o arquivo XLSX convertido
                xlsx_path = _criar_arquivo_temp_projeto(suffix='.xlsx', prefix='excel_convertido_')
                time_start = time.time()
                # Converter ODS para XLSX
                arquivo_convertido = _converter_ods_para_xlsx_libreoffice(excel_path, xlsx_path)
                time_end = time.time()
                print(f'[exportar_excel] Tempo de conversão ODS para XLSX: {time_end - time_start} segundos')
                if arquivo_convertido:
                    arquivo_final = arquivo_convertido
                    ods_original = excel_path  # Guardar referência para limpar depois
                else:
                    print(f'[exportar_excel] Erro ao converter ODS para XLSX, usando arquivo original')
            
            # Ler o arquivo salvo para o buffer
            output = io.BytesIO()
            with open(arquivo_final, 'rb') as f:
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
            if 'arquivo_final' in locals() and arquivo_final and os.path.exists(arquivo_final):
                _limpar_arquivo_temp(arquivo_final)
            # Limpar arquivo ODS original se foi convertido
            if 'ods_original' in locals() and ods_original and os.path.exists(ods_original):
                _limpar_arquivo_temp(ods_original)
        
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
        time_start = time.time()
        generated_pdf_path = _converter_excel_para_pdf(excel_path)
        time_end = time.time()
        print(f'[exportar_pdf] Tempo de conversão Excel para PDF: {time_end - time_start} segundos')
        
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
            time_start = time.time()
            # Primeiro, gerar todos os arquivos Excel
            for concretagem_id in concretagens_ids:
                try:
                    if formato == 'excel':
                        # Gerar Excel (pode retornar ODS ou XLSX)
                        excel_path = _gerar_excel_temp(concretagem_id, tanque_id, projeto_id, grupo_id)
                        if excel_path and os.path.exists(excel_path):
                            arquivo_final = excel_path
                            ods_original = None
                            # Se o arquivo gerado for ODS, converter para XLSX usando LibreOffice
                            if excel_path.lower().endswith('.ods'):
                                # Criar caminho para o arquivo XLSX convertido
                                xlsx_path = _criar_arquivo_temp_projeto(suffix='.xlsx', prefix='excel_convertido_')
                                # Converter ODS para XLSX
                                arquivo_convertido = _converter_ods_para_xlsx_libreoffice(excel_path, xlsx_path)
                                if arquivo_convertido:
                                    arquivo_final = arquivo_convertido
                                    ods_original = excel_path  # Guardar referência para limpar depois
                                else:
                                    print(f'[exportar_massa] Erro ao converter ODS para XLSX, usando arquivo original')
                            
                            # Copiar para o diretório temporário com nome único
                            nome_arquivo = f'relatorio_inspecao_{concretagem_id}.xlsx'
                            destino = os.path.join(temp_dir, nome_arquivo)
                            shutil.copy2(arquivo_final, destino)
                            arquivos_gerados.append(destino)
                            
                            # Limpar arquivos temporários (se configurado)
                            if arquivo_final != excel_path:
                                _limpar_arquivo_temp(arquivo_final)
                            if ods_original:
                                _limpar_arquivo_temp(ods_original)
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
            time_end = time.time()
            print(f'[exportar_massa] Tempo de geração de Excel: {time_end - time_start} segundos')
            time_start = time.time()
            # Se for PDF, converter todos os arquivos usando LibreOffice
            if formato == 'pdf' and excel_paths:
                # Converter arquivo por arquivo usando LibreOffice
                # Se o arquivo for ODS processado diretamente, gera PDF direto do ODS sem converter para XLSX
                time_start = time.time()
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
            time_end = time.time()
            print(f'[exportar_massa] Tempo de conversão de Excel para PDF: {time_end - time_start} segundos')
            if not arquivos_gerados:
                return jsonify({'error': 'Nenhum arquivo foi gerado com sucesso'}), 404
            
            # Criar arquivo ZIP
            time_start = time.time()
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
                time_end = time.time()
                print(f'[exportar_massa] Tempo de criação do ZIP: {time_end - time_start} segundos')
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

