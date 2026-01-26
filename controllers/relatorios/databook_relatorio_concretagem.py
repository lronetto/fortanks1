from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required
from models import TanquesPecas
from models.concreto import ConcretoUsinagensRompimentos, ConcretoUsinagens, ConcretoConcretagens, ConcretoConcretagensTanques
from models.contrato import Contrato
from models.cliente import Cliente
from models.tanque import Tanques, TanquesGrupos
from models.database import db
from sqlalchemy import or_, and_, func
from datetime import datetime, timedelta
import os
import io
import shutil
import zipfile
import openpyxl
from openpyxl import load_workbook
from openpyxl.worksheet.page import PageMargins
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
    temp_dir = os.path.join(base_dir, 'temp', 'databook_concretagem')
    
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


databook_concretagem_bp = Blueprint('databook_concretagem', __name__, url_prefix='/relatorios/databook/concretagem')

@databook_concretagem_bp.route('/')
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
    
    return render_template('relatorios/databook/concretagem/index.html', 
                         contratos=contratos, 
                         grupos=grupos,
                         tanques=tanques,
                         contrato_id=contrato_id,
                         tanque_id=tanque_id,
                         grupo_id=grupo_id,
                         data_inicio=data_inicio,
                         data_fim=data_fim)

@databook_concretagem_bp.route('/api/dados')
@login_required
def api_dados():
    """
    API para retornar dados do relatório em JSON (para DataTable)
    """
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_id = request.args.get('tanque_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    min_rompimentos = request.args.get('min_rompimentos', type=int)
    
    # Converter datas se fornecidas
    data_inicio = None
    data_fim = None
   
    usinagens = ConcretoUsinagens.query.outerjoin(ConcretoUsinagensRompimentos,ConcretoUsinagensRompimentos.numero_serie == ConcretoUsinagens.serie)
    if data_inicio_str:
        usinagens = usinagens.filter(ConcretoUsinagens.data_usinagem >= data_inicio_str)
    if data_fim_str:
        usinagens = usinagens.filter(ConcretoUsinagens.data_usinagem <= data_fim_str)

    usinagens = usinagens.all()
    dados = [] 
    for usinagem in usinagens:
        # Buscar peças usando a função comum
        pecas = buscar_pecas_por_serie(
            numero_serie=usinagem.serie,
            tanque_id=tanque_id,
            contrato_id=contrato_id,
            grupo_id=grupo_id
        )
        #print(pecas)
        projetos_unicos = set([peca.tanque.contrato_id for peca in pecas])
        projetos_str = ", ".join([Contrato.query.filter(Contrato.id == projeto).first().nome for projeto in projetos_unicos])
        tanques_unicos = set([peca.tanque_id for peca in pecas])
        tanques_str = ", ".join([Tanques.query.filter(Tanques.id == tanque).first().nome for tanque in tanques_unicos])
       
    
    # Preparar dados finais (apenas séries únicas)
        # Converter série para int se possível (rompimentos usa Integer)
        try:
            serie_int = int(usinagem.serie)
        except (ValueError, TypeError):
            serie_int = None
        
        # Buscar rompimentos (só funciona se a série for numérica)
        if serie_int is not None:
            total_rompimentos = ConcretoUsinagensRompimentos.query.filter(ConcretoUsinagensRompimentos.numero_serie == serie_int).count()
        else:
            total_rompimentos = 0
        
        # Aplicar filtro de rompimentos mínimos se especificado
        if min_rompimentos is not None and total_rompimentos < min_rompimentos:
            continue
        
       
        if grupo_id or tanque_id or contrato_id:
            if pecas:
                dados.append({
                        'numero_serie': usinagem.serie,
                        'projeto_nome': projetos_str,
                        'tanque_nome': tanques_str,
                        'data_moldagem': usinagem.data_usinagem.strftime('%d/%m/%Y %H:%M') if usinagem.data_usinagem else 'N/A',
                        'data_moldagem_raw': usinagem.data_usinagem.isoformat() if usinagem.data_usinagem else None,
                        'total_rompimentos': total_rompimentos
                    })
        else:
            dados.append({
                'numero_serie': usinagem.serie,
                'projeto_nome': projetos_str,
                'tanque_nome': tanques_str,
                'data_moldagem': usinagem.data_usinagem.strftime('%d/%m/%Y %H:%M') if usinagem.data_usinagem else 'N/A',
                'data_moldagem_raw': usinagem.data_usinagem.isoformat() if usinagem.data_usinagem else None,
                'total_rompimentos': total_rompimentos
            })
        
    #print(dados)
    return jsonify({
        'data': dados,
        'recordsTotal': len(dados),
        'recordsFiltered': len(dados)
    })

# Endpoints api_tanques e api_grupos foram movidos para databook_api_controller.py
# para evitar duplicação de código

def buscar_pecas_por_serie(numero_serie, tanque_id=None, contrato_id=None, grupo_id=None):
    """
    Função auxiliar para buscar peças que contêm a série no array 'series' do campo JSON 'qualidade'
    
    Args:
        numero_serie: Número da série (pode ser int ou string)
        tanque_id: ID do tanque para filtrar (opcional)
        contrato_id: ID do contrato para filtrar (opcional)
        grupo_id: ID do grupo de tanques para filtrar (opcional)
    
    Returns:
        Lista de peças (TanquesPecas) que contêm a série
    """
    # Tentar converter para int
    try:
        serie_numero = int(numero_serie)
    except (ValueError, TypeError):
        serie_numero = None
    
    # Iniciar query com joins necessários
    pecas_query = TanquesPecas.query.join(Tanques).join(Contrato)
    
    # Se a série for numérica, buscar de todas as formas possíveis
    if serie_numero is not None:
        # Buscar como número (caso esteja armazenado como número no JSON)
        filtro_numero = func.json_contains(
            func.json_extract(TanquesPecas.qualidade, '$.series'),
            str(serie_numero)
        ) == 1
        
        # Buscar como string exata (caso esteja como "1059" no JSON)
        filtro_string_exata = func.json_contains(
            func.json_extract(TanquesPecas.qualidade, '$.series'),
            func.json_quote(str(serie_numero))
        ) == 1
        
        # Buscar strings que contenham o número (para casos como "1059-c" no JSON)
        filtro_string_parcial = func.json_search(
            TanquesPecas.qualidade,
            'one',
            f'%{serie_numero}%',
            None,
            '$.series'
        ).isnot(None)
        
        # Combinar todas as buscas com OR para cobrir todos os casos
        pecas_query = pecas_query.filter(or_(filtro_numero, filtro_string_exata, filtro_string_parcial))
    else:
        # Se não for possível converter para número, buscar apenas como string exata e parcial
        filtro_string_exata = func.json_contains(
            func.json_extract(TanquesPecas.qualidade, '$.series'),
            func.json_quote(str(numero_serie))
        ) == 1
        
        filtro_string_parcial = func.json_search(
            TanquesPecas.qualidade,
            'one',
            f'%{numero_serie}%',
            None,
            '$.series'
        ).isnot(None)
        
        pecas_query = pecas_query.filter(or_(filtro_string_exata, filtro_string_parcial))
    
    # Aplicar filtros adicionais
    if tanque_id:
        pecas_query = pecas_query.filter(TanquesPecas.tanque_id == tanque_id)
    
    if contrato_id:
        pecas_query = pecas_query.filter(Tanques.contrato_id == contrato_id)
    
    if grupo_id:
        # Filtrar por grupo de tanques - buscar IDs dos tanques do grupo
        grupo = TanquesGrupos.query.get(grupo_id)
        if grupo and grupo.tanques:
            tanque_ids_grupo = [tanque.id for tanque in grupo.tanques]
            pecas_query = pecas_query.filter(TanquesPecas.tanque_id.in_(tanque_ids_grupo))
    
    return pecas_query.all()

def calcular_data_rompimento_28_dias(data_moldagem_dt):
    """Calcula data de rompimento 28 dias após a moldagem. Se cair em domingo, adiciona 1 dia."""
    data_rompimento = data_moldagem_dt + timedelta(days=28)
    # Verificar se é domingo (weekday() retorna 6 para domingo)
    if data_rompimento.weekday() == 6:  # Domingo
        data_rompimento += timedelta(days=1)  # Adiciona 1 dia (vira segunda-feira)
    return data_rompimento
def calcular_idade_cp(data_moldagem_dt, data_rompimento_dt):
    """Calcula idade do CP baseado na data de moldagem e data de rompimento."""
    if not data_moldagem_dt or not data_rompimento_dt:
        return 0
    diff_hours = (data_rompimento_dt - data_moldagem_dt).total_seconds() / 3600
    return int(diff_hours / 24) if diff_hours >= 24 else int(diff_hours)
def mapear_tipo_rompimento(tipo_rompimento, campos_base):
    """
    Mapeia o tipo de rompimento para os campos correspondentes.
    campos_base: lista de 4 campos (ex: [35, 36, 37, 38])
    Retorna um dicionário com os campos e valores ('X' ou '')
    """
    mapeamento = {
        '1': 0,
        '2': 1,
        '3': 2,
        '4': 3,
        '5': 3  # Assumindo que colunar também mapeia para o último campo
    }
    
    resultado = {}
    indice = mapeamento.get(tipo_rompimento.lower() if tipo_rompimento else '', 0)
    
    for i, campo in enumerate(campos_base):
        resultado[campo] = 'X' if i == indice else ''
    
    return resultado

def _processar_ods_template(ods_path, numero_serie, cliente_nome, tanque_nome, data_moldagem, usinagem, pecas, rompimentos):
    """
    Processa um arquivo ODS diretamente, substituindo placeholders pelos dados.
    
    Args:
        ods_path: Caminho do arquivo ODS
        numero_serie: Número da série
        cliente_nome: Nome do cliente
        tanque_nome: Nome do tanque
        data_moldagem: Data de moldagem
        usinagem: Objeto usinagem
        pecas: Lista de peças
        rompimentos: Lista de rompimentos
    """
    if not ODFPY_AVAILABLE:
        raise ImportError('odfpy não está disponível. Instale com: pip install odfpy')
    
    try:
        # Carregar o documento ODS
        doc = load(ods_path)
        
        # Obter todas as tabelas (planilhas)
        tables = doc.getElementsByType(Table)
        
        for table in tables:
            # Iterar sobre todas as linhas
            rows = table.getElementsByType(TableRow)
            for row_idx, row in enumerate(rows):
                if row_idx == 60:  # Pular linha 60 como no código original
                    continue
                
                # Iterar sobre todas as células
                cells = row.getElementsByType(TableCell)
                for cell_idx, cell in enumerate(cells):
                    if cell_idx == 30:  # Pular coluna 30 como no código original
                        continue
                    
                    # Obter o texto da célula (pode estar em parágrafos ou diretamente)
                    original_text = ''
                    paragraphs = cell.getElementsByType(P)
                    
                    # Coletar texto de todos os parágrafos
                    if paragraphs:
                        for para in paragraphs:
                            # Obter texto do parágrafo
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
                    
                    if original_text and len(original_text.strip()) > 0:
                            new_value = original_text
                            
                            # Substituir placeholders (mesma lógica do código XLSX)
                            new_value = new_value.replace('{1}', str(numero_serie))
                            new_value = new_value.replace('{2}', cliente_nome)
                            new_value = new_value.replace('{3}', tanque_nome)
                            new_value = new_value.replace('{4}', '40 MPa')
                            new_value = new_value.replace('{5}', '40')
                            new_value = new_value.replace('{6}', '0')
                            new_value = new_value.replace('{7}', '24,0')
                            new_value = new_value.replace('{8}', 'CPIII 40 RS')
                            new_value = new_value.replace('{9}', 'CP V')
                            new_value = new_value.replace('{10}', 'superplastificante')
                            new_value = new_value.replace('{11}', 'Fortanks')
                            
                            if data_moldagem:
                                new_value = new_value.replace('{12}', str(data_moldagem.strftime('%d/%m/%Y')))
                            
                            new_value = new_value.replace('{13}', "01")
                            
                            if usinagem and hasattr(usinagem, 'nota'):
                                new_value = new_value.replace('{14}', usinagem.nota)
                            
                            if data_moldagem:
                                new_value = new_value.replace('{15}', str((data_moldagem - timedelta(minutes=15)).strftime('%H:%M')))
                                new_value = new_value.replace('{16}', str((data_moldagem - timedelta(minutes=10)).strftime('%H:%M')))
                            
                            new_value = new_value.replace('{17}', "")
                            new_value = new_value.replace('{18}', "")
                            new_value = new_value.replace('{19}', "X")
                            
                            if usinagem and hasattr(usinagem, 'flow'):
                                new_value = new_value.replace('{20}', str(usinagem.flow))
                            
                            if data_moldagem:
                                new_value = new_value.replace('{21}', str(data_moldagem.strftime('%H:%M')))
                            
                            if usinagem and hasattr(usinagem, 'volume'):
                                new_value = new_value.replace('{22}', str(usinagem.volume))
                            
                            # Processar peças
                            if pecas:
                                pecas_str = ''
                                for peca in pecas:
                                    if peca.nome not in pecas_str:
                                        qualidade = json.loads(peca.qualidade)
                                        try:
                                            numero_serie_int = int(numero_serie)
                                            busca = str(numero_serie_int) + '-c'
                                        except:
                                            busca = str(numero_serie) + '-c'
                                        
                                        series = qualidade.get('series', [])
                                        if qualidade.get('series', []):
                                            if busca in series:
                                                pecas_str += peca.nome + '-c, '
                                            else:
                                                pecas_str += peca.nome + ', '
                                pecas_str = pecas_str[:-2]
                                new_value = new_value.replace('{23}', pecas_str)
                            else:
                                new_value = new_value.replace('{23}', "N/A")
                            
                            # Processar rompimentos (mesma lógica do código XLSX)
                            if (len(rompimentos) >= 4 and 
                                rompimentos[len(rompimentos)-1].data_moldagem and 
                                rompimentos[len(rompimentos)-1].data_rompimento and
                                calcular_idade_cp(rompimentos[len(rompimentos)-1].data_moldagem, rompimentos[len(rompimentos)-1].data_rompimento) >= 25):
                                
                                # Rompimento 1
                                if rompimentos[0].data_rompimento:
                                    new_value = new_value.replace('{30}', str(rompimentos[0].data_rompimento.strftime('%d/%m/%Y')))
                                if rompimentos[0].data_moldagem and rompimentos[0].data_rompimento:
                                    idade = calcular_idade_cp(rompimentos[0].data_moldagem, rompimentos[0].data_rompimento)
                                    if idade is not None:
                                        new_value = new_value.replace('{31}', str(idade))
                                if rompimentos[0].data_rompimento:
                                    new_value = new_value.replace('{32}', str(rompimentos[0].data_rompimento.strftime('%H:%M')))
                                if rompimentos[0].resultado:
                                    resultado_1 = float(rompimentos[0].resultado) * float(rompimentos[0].fator_conversao or 1.2)
                                    new_value = new_value.replace('{34}', str(round(resultado_1, 2)))
                                
                                tipo_romp_1 = mapear_tipo_rompimento(rompimentos[0].tipo_rompimento, [35, 36, 37, 38, 39])
                                for campo, valor in tipo_romp_1.items():
                                    new_value = new_value.replace('{'+str(campo)+'}', valor)
                                
                                # Rompimento 2
                                if rompimentos[1].resultado:
                                    resultado_2 = float(rompimentos[1].resultado) * float(rompimentos[1].fator_conversao or 1.2)
                                    new_value = new_value.replace('{41}', str(round(resultado_2, 2)))
                                tipo_romp_2 = mapear_tipo_rompimento(rompimentos[1].tipo_rompimento, [42, 43, 44, 45, 46])
                                for campo, valor in tipo_romp_2.items():
                                    new_value = new_value.replace('{'+str(campo)+'}', valor)
                                
                                # Rompimento 3
                                if rompimentos[2].data_rompimento:
                                    new_value = new_value.replace('{47}', str(rompimentos[2].data_rompimento.strftime('%d/%m/%Y')))
                                if rompimentos[2].data_rompimento:
                                    new_value = new_value.replace('{48}', str(rompimentos[2].data_rompimento.strftime('%H:%M')))
                                if rompimentos[2].resultado:
                                    resultado_3 = float(rompimentos[2].resultado) * float(rompimentos[2].fator_conversao or 1.2)
                                    new_value = new_value.replace('{49}', str(round(resultado_3, 2)))
                                tipo_romp_3 = mapear_tipo_rompimento(rompimentos[2].tipo_rompimento, [50, 51, 52, 53, 54])
                                for campo, valor in tipo_romp_3.items():
                                    new_value = new_value.replace('{'+str(campo)+'}', valor)
                                
                                # Rompimento 4
                                if rompimentos[3].resultado:
                                    resultado_4 = float(rompimentos[3].resultado) * float(rompimentos[3].fator_conversao or 1.2)
                                    new_value = new_value.replace('{55}', str(round(resultado_4, 2)))
                                tipo_romp_4 = mapear_tipo_rompimento(rompimentos[3].tipo_rompimento, [56, 57, 58, 59, 60])
                                for campo, valor in tipo_romp_4.items():
                                    new_value = new_value.replace('{'+str(campo)+'}', valor)
                                
                                # Resistências finais
                                if rompimentos[0].resultado and rompimentos[1].resultado:
                                    resultado_0 = (rompimentos[0].resultado or 0) * (rompimentos[0].fator_conversao or 1.2)
                                    resultado_1 = (rompimentos[1].resultado or 0) * (rompimentos[1].fator_conversao or 1.2)
                                    resistencia_final_1 = max(resultado_0, resultado_1)
                                    new_value = new_value.replace('{61}', str(round(resistencia_final_1, 2)))
                                
                                if rompimentos[2].resultado and rompimentos[3].resultado:
                                    resultado_2 = (rompimentos[2].resultado or 0) * (rompimentos[2].fator_conversao or 1.2)
                                    resultado_3 = (rompimentos[3].resultado or 0) * (rompimentos[3].fator_conversao or 1.2)
                                    resistencia_final_2 = max(resultado_2, resultado_3)
                                    new_value = new_value.replace('{63}', str(round(resistencia_final_2, 2)))
                            else:
                                # Limpar campos de rompimento se não houver dados suficientes
                                for i in range(30, 64):
                                    new_value = new_value.replace('{'+str(i)+'}', "")
                            
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
        print(f'[_processar_ods_template] ODS processado com sucesso: {ods_path}')
        
    except Exception as e:
        print(f'[_processar_ods_template] Erro ao processar ODS: {str(e)}')
        import traceback
        print(traceback.format_exc())
        raise

def _gerar_excel_temp(numero_serie, tanque_id=None, contrato_id=None, grupo_id=None):
    """
    Função auxiliar que gera o Excel e retorna o caminho do arquivo temporário
    Retorna o caminho do arquivo temporário ou None em caso de erro
    """
    temp_ods_path = None
    try:
        print(f'numero_serie: {numero_serie}')
        print(f'tanque_id: {tanque_id}')
        print(f'contrato_id: {contrato_id}')
        print(f'grupo_id: {grupo_id}')
        

        # Tentar converter para int (para buscar rompimentos, que usa Integer)
        try:
            numero_serie_int = int(numero_serie)
        except (ValueError, TypeError):
            numero_serie_int = None
        
        # Buscar rompimentos (só funciona se a série for numérica, pois o campo é Integer)
        if numero_serie_int is not None:
            print(f'[_gerar_excel_temp] Buscando rompimentos com numero_serie_int: {numero_serie_int}')
            rompimentos = ConcretoUsinagensRompimentos.query\
                .filter(ConcretoUsinagensRompimentos.numero_serie == numero_serie_int)\
                .order_by(ConcretoUsinagensRompimentos.data_rompimento.asc())\
                .all()
            print(f'[_gerar_excel_temp] Rompimentos encontrados (int): {len(rompimentos)}')
        else:
            rompimentos = []
            print(f'[_gerar_excel_temp] Não foi possível converter numero_serie para int: {numero_serie}')
            
        # Buscar usinagem usando a string diretamente (o campo serie é String)
        usinagem = ConcretoUsinagens.query.filter(ConcretoUsinagens.serie == str(numero_serie)).first()
        if usinagem:
            data_moldagem = usinagem.data_usinagem
        else:
            print(f'[_gerar_excel_temp] Usinagem não encontrada para a série {numero_serie}')
            data_moldagem = None
        

        # Buscar peças usando a função comum
        pecas = buscar_pecas_por_serie(
            numero_serie=numero_serie,
            tanque_id=tanque_id,
            contrato_id=contrato_id,
            grupo_id=grupo_id
        )
        tanque_nome = ''
        contrato_nome = ''
        cliente_nome = ''
        tanques = []
        contratos = []
        if pecas:
            quantidade_tanques = len(set([peca.tanque_id for peca in pecas]))
            print(f'[_gerar_excel_temp] Quantidade de tanques: {quantidade_tanques}')
            if quantidade_tanques >=1:
                for peca in pecas:
                    tanque = Tanques.query.join(Contrato, Tanques.contrato_id == Contrato.id).join(Cliente, Contrato.cliente_direto_id == Cliente.id).filter(Tanques.id == peca.tanque_id).first()
                    contrato = tanque.contrato
                    if tanque not in tanques:
                        tanques.append(tanque)
                    if contrato not in contratos:
                        contratos.append(contrato)
                if len(tanques) > 1:
                    for tanque in tanques:
                        tanque_nome += tanque.nome + ", "
                    tanque_nome = tanque_nome[:-2]
                else:
                    tanque_nome = tanques[0].nome
                if len(contratos) > 1:
                    for contrato in contratos:
                        cliente_nome += contrato.cliente_direto.nome + ", "
                    cliente_nome = cliente_nome[:-2]
                else:
                    cliente_nome = contratos[0].cliente_direto.nome
                
        if not rompimentos:
            print(f'[_gerar_excel_temp] Nenhum rompimento encontrado para a série {numero_serie}')
            #return None
        
        print(f'[_gerar_excel_temp] Total de rompimentos encontrados: {len(rompimentos)}')
        
        # Caminho do arquivo template - tentar ODS primeiro, depois XLSX
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates_excel'
        )
        
        template_ods = os.path.join(templates_dir, 'RELATORIO_CONCRETAGEM.ods')
        template_xlsx = os.path.join(templates_dir, 'RELATORIO_CONCRETAGEM.xlsx')
        
        template_path = None
        usar_ods = False
        
        # Verificar qual template existe
        if os.path.exists(template_ods):
            template_path = template_ods
            usar_ods = True
            print(f'[_gerar_excel_temp] Usando template ODS')
        elif os.path.exists(template_xlsx):
            template_path = template_xlsx
            print(f'[_gerar_excel_temp] Usando template XLSX')
        else:
            print(f'Template RELATORIO_CONCRETAGEM não encontrado (nem .ods nem .xlsx)')
            return None
        
        # Se for ODS e odfpy estiver disponível, processar diretamente
        if usar_ods and ODFPY_AVAILABLE:
            # Criar cópia do ODS e processar diretamente
            temp_file_path = _criar_arquivo_temp_projeto(suffix='.ods', prefix='excel_')
            shutil.copy2(template_path, temp_file_path)
            print(f'[_gerar_excel_temp] ODS copiado com sucesso: {temp_file_path}')
            
            # Processar ODS diretamente
            _processar_ods_template(
                temp_file_path,
                numero_serie,
                cliente_nome,
                tanque_nome,
                data_moldagem,
                usinagem,
                pecas,
                rompimentos
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
        # Usar read_only=False para permitir edição
        wb = load_workbook(temp_file_path, data_only=False, keep_vba=False, read_only=False)
       
        # Processar apenas células com texto, preservando imagens e outros objetos
        for sheet in wb.worksheets:
            for index, row in enumerate(sheet.iter_rows()):
                if index == 60:
                    continue
                for index_cell, cell in enumerate(row):
                    if index_cell == 30:
                        continue
                    # Processar apenas células que contêm texto (string) e não estão vazias
                    if cell.value is not None and isinstance(cell.value, str) and len(cell.value.strip()) > 0:
                        # Criar uma cópia do valor original para evitar problemas
                        original_value = str(cell.value)
                        new_value = original_value
                        
                        # Substituir {1}, {2}, etc pelos dados correspondentes
                        new_value = new_value.replace('{1}', str(numero_serie))
                        #Cliente
                        new_value = new_value.replace('{2}', cliente_nome)
                        #Obra
                        new_value = new_value.replace('{3}', tanque_nome)

                        #tipo de concreto   
                        new_value = new_value.replace('{4}', '40 MPa')
                        #traço
                        new_value = new_value.replace('{5}', '40')
                        #brita
                        new_value = new_value.replace('{6}', '0')
                        #restrição
                        new_value = new_value.replace('{7}', '24,0')
                        #cimento 1
                        new_value = new_value.replace('{8}', 'CPIII 40 RS')
                        #cimento 2
                        new_value = new_value.replace('{9}', 'CP V')
                        #aditivo
                        new_value = new_value.replace('{10}', 'superplastificante')
                        #concreteira
                        new_value = new_value.replace('{11}', 'Fortanks')
                        #volume
                        # Data de moldagem
                        if data_moldagem:
                            new_value = new_value.replace('{12}', str(data_moldagem.strftime('%d/%m/%Y')))
                        #Número do caminhao
                        new_value = new_value.replace('{13}', "01")
                        #Nota fiscal
                        new_value = new_value = new_value.replace('{14}', usinagem.nota)
                        #Horário de saída da usina 
                        if data_moldagem:
                            new_value = new_value.replace('{15}', str((data_moldagem - timedelta(minutes=15)).strftime('%H:%M')))
                        #Horário de chegada no destino
                        if data_moldagem:
                            new_value = new_value.replace('{16}', str((data_moldagem - timedelta(minutes=10)).strftime('%H:%M')))
                        #Consistencia SLUMP
                        new_value = new_value.replace('{17}', "")
                        #consistencia Slump
                        new_value = new_value.replace('{18}', "")
                        #consistencia FLOW
                        new_value = new_value.replace('{19}', "X")
                        #consistencia FLOW
                        new_value = new_value.replace('{20}', str(usinagem.flow))
                        # hora de moldagem
                        if data_moldagem:
                            new_value = new_value.replace('{21}', str(data_moldagem.strftime('%H:%M')))
                        #volume
                        new_value = new_value.replace('{22}', str(usinagem.volume).format(2))
                        #pecas - buscar peças que contêm a série no array 'series' do campo JSON 'dados_adicionais'
                        
                        
                        if pecas:
                            pecas_str =''
                            for peca in pecas:
                                if peca.nome not in pecas_str:
                                    qualidade = json.loads(peca.qualidade)
                                    busca = str(numero_serie_int)+'-c'
                                    series = qualidade.get('series', [])
                                    if qualidade.get('series', []):
                                        if busca in series:
                                            pecas_str += peca.nome+'-c, '
                                        else:
                                            pecas_str += peca.nome+', '
                            pecas_str = pecas_str[:-2]
                            new_value = new_value.replace('{23}', pecas_str)
                        else:
                            new_value = new_value.replace('{23}', "N/A")

                        if (len(rompimentos) >= 4 and 
                            rompimentos[len(rompimentos)-1].data_moldagem and 
                            rompimentos[len(rompimentos)-1].data_rompimento and
                            calcular_idade_cp(rompimentos[len(rompimentos)-1].data_moldagem, rompimentos[len(rompimentos)-1].data_rompimento) >= 25):
                            #data de rompimento 1
                            if rompimentos[0].data_rompimento:
                                new_value = new_value.replace('{30}', str(rompimentos[0].data_rompimento.strftime('%d/%m/%Y')))
                            #idade de rompimento 1
                            if rompimentos[0].data_moldagem and rompimentos[0].data_rompimento:
                                idade = calcular_idade_cp(rompimentos[0].data_moldagem, rompimentos[0].data_rompimento)
                                if idade is not None:
                                    new_value = new_value.replace('{31}', str(idade))
                            #hora de rompimento 1
                            if rompimentos[0].data_rompimento:
                                new_value = new_value.replace('{32}', str(rompimentos[0].data_rompimento.strftime('%H:%M')))
                            #resultado de rompimento 1
                            if rompimentos[0].resultado:
                                resultado_1 = float(rompimentos[0].resultado) * float(rompimentos[0].fator_conversao or 1.2)
                                new_value = new_value.replace('{34}', str(round(resultado_1, 2)))
                            #tipo de rompimento 1
                            tipo_romp_1 = mapear_tipo_rompimento(rompimentos[0].tipo_rompimento, [35, 36, 37, 38,39])
                            for campo, valor in tipo_romp_1.items():
                                new_value = new_value.replace('{'+str(campo)+'}', valor)
                            #resultado de rompimento 2
                            if rompimentos[1].resultado:
                                resultado_2 = float(rompimentos[1].resultado) * float(rompimentos[1].fator_conversao or 1.2)
                                new_value = new_value.replace('{41}', str(round(resultado_2, 2)))
                            #tipo de rompimento 2
                            tipo_romp_2 = mapear_tipo_rompimento(rompimentos[1].tipo_rompimento, [42, 43, 44, 45,46])
                            for campo, valor in tipo_romp_2.items():
                                new_value = new_value.replace('{'+str(campo)+'}', valor)
                            #data de rompimento 3 e 4
                            if rompimentos[2].data_rompimento:
                                new_value = new_value.replace('{47}', str(rompimentos[2].data_rompimento.strftime('%d/%m/%Y')))
                            #hora de rompimento 3 e 4
                            if rompimentos[2].data_rompimento:
                                new_value = new_value.replace('{48}', str(rompimentos[2].data_rompimento.strftime('%H:%M')))
                            #resultado de rompimento 3
                            if rompimentos[2].resultado:
                                resultado_3 = float(rompimentos[2].resultado) * float(rompimentos[2].fator_conversao or 1.2)
                                new_value = new_value.replace('{49}', str(round(resultado_3, 2)))
                            #tipo de rompimento 3
                            tipo_romp_3 = mapear_tipo_rompimento(rompimentos[2].tipo_rompimento, [50, 51, 52, 53, 54])
                            for campo, valor in tipo_romp_3.items():
                                new_value = new_value.replace('{'+str(campo)+'}', valor)
                            #resultado de rompimento 4
                            if rompimentos[3].resultado:
                                resultado_4 = float(rompimentos[3].resultado) * float(rompimentos[3].fator_conversao or 1.2)
                                new_value = new_value.replace('{55}', str(round(resultado_4, 2)))
                            #tipo de rompimento 4
                            tipo_romp_4 = mapear_tipo_rompimento(rompimentos[3].tipo_rompimento, [56, 57, 58, 59, 60])
                            for campo, valor in tipo_romp_4.items():
                                new_value = new_value.replace('{'+str(campo)+'}', valor)

                            #resistencia final 1
                            if rompimentos[0].resultado and rompimentos[1].resultado:
                                resultado_0 = (rompimentos[0].resultado or 0) * (rompimentos[0].fator_conversao or 1.2)
                                resultado_1 = (rompimentos[1].resultado or 0) * (rompimentos[1].fator_conversao or 1.2)
                                resistencia_final_1 = max(resultado_0, resultado_1)
                                new_value = new_value.replace('{61}', str(round(resistencia_final_1, 2)))
                            #resistencia final 2
                            if rompimentos[2].resultado and rompimentos[3].resultado:
                                resultado_2 = (rompimentos[2].resultado or 0) * (rompimentos[2].fator_conversao or 1.2)
                                resultado_3 = (rompimentos[3].resultado or 0) * (rompimentos[3].fator_conversao or 1.2)
                                resistencia_final_2 = max(resultado_2, resultado_3)
                                new_value = new_value.replace('{63}', str(round(resistencia_final_2, 2)))
                        else:
                            for i in range(30, 64):
                                new_value = new_value.replace('{'+str(i)+'}', "")
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
        
        # Salvar o arquivo temporário (preserva imagens melhor que BytesIO)
        # Garantir que o arquivo seja salvo corretamente
        try:
            # Salvar o arquivo
            wb.save(temp_file_path)
        except Exception as save_error:
            # Se houver erro ao salvar, retornar None
            raise Exception(f'Erro ao salvar arquivo Excel: {str(save_error)}')
        finally:
            # Sempre fechar o workbook
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
        # Em caso de erro, tentar limpar os arquivos temporários
        print(f'Erro em _gerar_excel_temp: {str(e)}')
        import traceback
        print(traceback.format_exc())
        try:
            if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
                _limpar_arquivo_temp(temp_file_path)
            # Limpar arquivo ODS temporário se existir
            if 'temp_ods_path' in locals() and temp_ods_path and os.path.exists(temp_ods_path):
                _limpar_arquivo_temp(temp_ods_path)
        except:
            pass
        return None
    finally:
        # Limpar arquivo ODS temporário após uso (se configurado)
        if 'temp_ods_path' in locals() and temp_ods_path and os.path.exists(temp_ods_path):
            _limpar_arquivo_temp(temp_ods_path)

@databook_concretagem_bp.route('/exportar-excel/<numero_serie>')
@login_required
def exportar_excel(numero_serie):
    """
    Exporta dados de uma série específica para Excel usando template base
    """
    try:
        print(f'[exportar_excel] Iniciando exportação para série: {numero_serie}')
        # Converter para int se possível, caso contrário manter como string
        try:
            numero_serie_int = int(numero_serie)
            print(f'[exportar_excel] Série convertida para int: {numero_serie_int}')
        except (ValueError, TypeError):
            numero_serie_int = numero_serie
            print(f'[exportar_excel] Série mantida como string: {numero_serie_int}')
        
        tanque_id = request.args.get('tanque_id', type=int) or None
        contrato_id = request.args.get('contrato_id', type=int) or None
        print(f'[exportar_excel] Filtros - tanque_id: {tanque_id}, contrato_id: {contrato_id}')
        
        excel_path = _gerar_excel_temp(numero_serie_int, tanque_id, contrato_id)
        print(f'[exportar_excel] excel_path retornado: {excel_path}')
        
        if not excel_path:
            # Verificar o que está faltando para dar uma mensagem mais específica
            usinagem = ConcretoUsinagens.query.filter(ConcretoUsinagens.serie == str(numero_serie_int)).first()
            if not usinagem:
                error_msg = f'Usinagem não encontrada para a série {numero_serie}'
            else:
                rompimentos = ConcretoUsinagensRompimentos.query.filter(
                    ConcretoUsinagensRompimentos.numero_serie == numero_serie_int
                ).count()
                if rompimentos == 0:
                    error_msg = f'Nenhum rompimento encontrado para a série {numero_serie}'
                else:
                    error_msg = f'Nenhuma peça encontrada para a série {numero_serie} com os filtros aplicados (tanque_id={tanque_id}, contrato_id={contrato_id})'
            return jsonify({'error': error_msg}), 404
        
        try:
            # Verificar se o arquivo é ODS e converter para XLSX se necessário
            arquivo_final = excel_path
            ods_original = None
            
            if excel_path.lower().endswith('.ods'):
                print(f'[exportar_excel] Arquivo ODS detectado, convertendo para XLSX: {excel_path}')
                # Criar caminho para o arquivo XLSX convertido
                xlsx_path = _criar_arquivo_temp_projeto(suffix='.xlsx', prefix='excel_convertido_')
                # Converter ODS para XLSX
                arquivo_convertido = _converter_ods_para_xlsx_libreoffice(excel_path, xlsx_path)
                if arquivo_convertido:
                    arquivo_final = arquivo_convertido
                    ods_original = excel_path  # Guardar referência para limpar depois
                    print(f'[exportar_excel] Conversão concluída: {arquivo_final}')
                else:
                    print(f'[exportar_excel] Erro ao converter ODS para XLSX, usando arquivo original')
            
            # Ler o arquivo salvo para o buffer
            output = io.BytesIO()
            with open(arquivo_final, 'rb') as f:
                output.write(f.read())
            output.seek(0)
            
            # Nome do arquivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'relatorio_concretagem_serie_{numero_serie}_{timestamp}.xlsx'
            
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

@databook_concretagem_bp.route('/exportar-pdf/<numero_serie>')
@login_required
def exportar_pdf(numero_serie):
    """
    Exporta dados de uma série específica para PDF convertendo do Excel/ODS gerado usando LibreOffice
    """
    excel_path = None
    pdf_temp_path = None
    
    try:
        # Converter para int se possível, caso contrário manter como string
        try:
            numero_serie_int = int(numero_serie)
        except (ValueError, TypeError):
            numero_serie_int = numero_serie
        
        tanque_id = request.args.get('tanque_id', type=int) or None
        contrato_id = request.args.get('contrato_id', type=int) or None
        grupo_id = request.args.get('grupo_id', type=int) or None
        excel_path = _gerar_excel_temp(numero_serie_int, tanque_id, contrato_id, grupo_id)
        
        if not excel_path or not os.path.exists(excel_path):
            return jsonify({'error': 'Nenhum rompimento encontrado para a série ' + str(numero_serie)}), 404
        
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
        filename = f'relatorio_concretagem_serie_{numero_serie}_{timestamp}.pdf'
        
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

@databook_concretagem_bp.route('/exportar-massa', methods=['POST'])
@login_required
def exportar_massa():
    """
    Exporta múltiplas séries em massa (Excel ou PDF)
    Retorna um arquivo ZIP com todos os arquivos gerados
    """
    excel_paths = []
    temp_dir = None
    
    try:
        data = request.get_json()
        series = data.get('series', [])
        formato = data.get('formato', 'excel')  # 'excel' ou 'pdf'
        tanque_id = data.get('tanque_id')
        contrato_id = data.get('contrato_id')
        grupo_id = data.get('grupo_id')
        
        if not series:
            return jsonify({'error': 'Nenhuma série fornecida'}), 400
        
        # Criar diretório temporário para os arquivos
        temp_dir = _criar_diretorio_temp_projeto(prefix='export_massa_')
        arquivos_gerados = []
        series_validas = []  # Armazenar séries que tiveram Excel gerado com sucesso
        
        try:
            # Primeiro, gerar todos os arquivos Excel
            for numero_serie in series:
                try:
                    # Converter série para int se possível
                    try:
                        numero_serie_int = int(numero_serie)
                    except (ValueError, TypeError):
                        numero_serie_int = numero_serie
                    
                    if formato == 'excel':
                        # Gerar Excel
                        excel_path = _gerar_excel_temp(numero_serie_int, tanque_id, contrato_id, grupo_id)
                        if excel_path and os.path.exists(excel_path):
                            # Copiar para o diretório temporário com nome único
                            nome_arquivo = f'relatorio_serie_{numero_serie}.xlsx'
                            destino = os.path.join(temp_dir, nome_arquivo)
                            shutil.copy2(excel_path, destino)
                            arquivos_gerados.append(destino)
                            # Limpar arquivo temporário original (se configurado)
                            _limpar_arquivo_temp(excel_path)
                    else:  # PDF
                        # Gerar Excel primeiro e armazenar caminho e série correspondente
                        excel_path = _gerar_excel_temp(numero_serie_int, tanque_id, contrato_id, grupo_id)
                        if excel_path and os.path.exists(excel_path):
                            excel_paths.append(excel_path)
                            series_validas.append(numero_serie)  # Armazenar série correspondente
                            
                except Exception as e:
                    print(f'Erro ao processar série {numero_serie}: {str(e)}')
                    continue
            
            # Se for PDF, converter todos os arquivos usando LibreOffice
            if formato == 'pdf' and excel_paths:
                # Converter arquivo por arquivo usando LibreOffice
                # Se o arquivo for ODS processado diretamente, gera PDF direto do ODS sem converter para XLSX
                for i, excel_path in enumerate(excel_paths):
                    try:
                        if i < len(series_validas):
                            numero_serie = series_validas[i]
                            # Converter para PDF (aceita tanto XLSX quanto ODS)
                            pdf_path = _converter_excel_para_pdf_libreoffice(excel_path)
                            if pdf_path and os.path.exists(pdf_path):
                                nome_arquivo = f'relatorio_serie_{numero_serie}.pdf'
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
                        print(f'Erro ao converter Excel/ODS para PDF (LibreOffice) da série {series_validas[i] if i < len(series_validas) else "desconhecida"}: {str(e)}')
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
                
                # Nome do arquivo ZIP
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'exportacao_massa_{formato}_{timestamp}.zip'
                
                # Limpar arquivos temporários antes de retornar (já foram copiados para o ZIP)
                # Limpar arquivos Excel/ODS temporários (se configurado)
                try:
                    for excel_path in excel_paths:
                        if excel_path and os.path.exists(excel_path):
                            _limpar_arquivo_temp(excel_path)
                except Exception as e:
                    print(f'Erro ao limpar arquivos Excel/ODS temporários: {str(e)}')
                
                # Não limpar temp_dir ainda, pois os arquivos podem estar sendo usados
                # A limpeza será feita no finally
                
                print(f'Retornando arquivo ZIP com {len(arquivos_gerados)} arquivos')
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
            # Fazer isso no finally para garantir que sempre seja limpo
            try:
                if temp_dir and os.path.exists(temp_dir):
                    _limpar_diretorio_temp(temp_dir)
                    print(f'Diretório temporário limpo: {temp_dir}')
            except Exception as cleanup_error:
                print(f'Erro ao limpar diretório temporário {temp_dir}: {str(cleanup_error)}')
                import traceback
                print(traceback.format_exc())
                
    except Exception as e:
        print(f'Erro ao exportar em massa: {str(e)}')
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': f'Erro ao exportar em massa: {str(e)}'}), 500

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
                            print(f'[_converter_ods_para_xlsx_libreoffice] Caminho encontrado: {path}')
                
                # Buscar em /opt
                opt_paths = glob.glob('/opt/libreoffice*/program/soffice')
                possiveis_caminhos.extend(opt_paths)
                for path in opt_paths:
                    print(f'[_converter_ods_para_xlsx_libreoffice] Caminho encontrado em /opt: {path}')
                
                print(f'[_converter_ods_para_xlsx_libreoffice] Total de caminhos a verificar: {len(possiveis_caminhos)}')
                
                # Verificar cada caminho
                for caminho in possiveis_caminhos:
                    print(f'[_converter_ods_para_xlsx_libreoffice] Verificando caminho: {caminho}')
                    if os.path.exists(caminho):
                        print(f'[_converter_ods_para_xlsx_libreoffice] Caminho existe: {caminho}')
                        if os.access(caminho, os.X_OK):
                            print(f'[_converter_ods_para_xlsx_libreoffice] Caminho tem permissão de execução: {caminho}')
                            # Verificar se é um executável real (ELF binary) ou um link simbólico válido
                            try:
                                # Verificar se é um link simbólico
                                if os.path.islink(caminho):
                                    real_path = os.path.realpath(caminho)
                                    print(f'[_converter_ods_para_xlsx_libreoffice] É um link simbólico apontando para: {real_path}')
                                    if os.path.exists(real_path) and os.access(real_path, os.X_OK):
                                        caminho = real_path
                                
                                with open(caminho, 'rb') as f:
                                    header = f.read(4)
                                    if header.startswith(b'\x7fELF'):  # ELF binary
                                        soffice_cmd = caminho
                                        print(f'[_converter_ods_para_xlsx_libreoffice] Encontrado executável real (ELF): {soffice_cmd}')
                                        break
                                    else:
                                        # Pode ser um script ou link simbólico, mas vamos usar se existir e tiver permissão
                                        print(f'[_converter_ods_para_xlsx_libreoffice] Arquivo não é ELF, mas existe e tem permissão: {caminho}')
                                        # Usar este arquivo se ainda não encontrou nenhum
                                        if not soffice_cmd:
                                            soffice_cmd = caminho
                                            print(f'[_converter_ods_para_xlsx_libreoffice] Usando arquivo encontrado: {soffice_cmd}')
                            except Exception as e:
                                print(f'[_converter_ods_para_xlsx_libreoffice] Erro ao verificar {caminho}: {str(e)}')
                                # Se não encontrou nenhum ainda e o arquivo existe, usar como último recurso
                                if not soffice_cmd and os.path.exists(caminho):
                                    soffice_cmd = caminho
                                    print(f'[_converter_ods_para_xlsx_libreoffice] Usando como último recurso: {soffice_cmd}')
                        else:
                            print(f'[_converter_ods_para_xlsx_libreoffice] Caminho existe mas não tem permissão de execução: {caminho}')
                    else:
                        print(f'[_converter_ods_para_xlsx_libreoffice] Caminho não existe: {caminho}')
                
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
        
        # Comando para converter ODS para XLSX
        # --headless: modo sem interface gráfica
        # --convert-to xlsx: converter para XLSX
        # --outdir: diretório de saída
        cmd = [
            soffice_cmd,
            '--headless',
            '--convert-to', 'xlsx',
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
        
        print(f'[_converter_ods_para_xlsx_libreoffice] Executando: {" ".join(cmd)}')
        print(f'[_converter_ods_para_xlsx_libreoffice] Arquivo ODS: {ods_path}')
        print(f'[_converter_ods_para_xlsx_libreoffice] Diretório de saída: {output_dir}')
        print(f'[_converter_ods_para_xlsx_libreoffice] Executável: {soffice_cmd}')
        
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
            
            print(f'[_converter_ods_para_xlsx_libreoffice] PATH: {env.get("PATH", "")[:200]}...')
            print(f'[_converter_ods_para_xlsx_libreoffice] LD_LIBRARY_PATH: {env.get("LD_LIBRARY_PATH", "")[:200]}...')
            
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
        
        # O LibreOffice gera o XLSX com o mesmo nome do arquivo ODS
        ods_basename = os.path.basename(ods_path)
        xlsx_basename = ods_basename.replace('.ods', '.xlsx')
        generated_xlsx_path = os.path.join(output_dir, xlsx_basename)
        
        # Aguardar um pouco para garantir que o arquivo foi criado
        max_tentativas = 10
        tentativa = 0
        while tentativa < max_tentativas:
            if os.path.exists(generated_xlsx_path):
                # Verificar se o arquivo não está sendo escrito (tamanho estável)
                tamanho_anterior = os.path.getsize(generated_xlsx_path)
                time.sleep(0.5)
                tamanho_atual = os.path.getsize(generated_xlsx_path)
                if tamanho_anterior == tamanho_atual:
                    # Se o caminho de saída especificado é diferente, mover o arquivo
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
                print(f'[_converter_excel_para_pdf_libreoffice] Usando LIBREOFFICE_PATH: {soffice_cmd}')
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
                            print(f'[_converter_excel_para_pdf_libreoffice] Caminho encontrado: {path}')
                
                # Buscar em /opt
                opt_paths = glob.glob('/opt/libreoffice*/program/soffice')
                possiveis_caminhos.extend(opt_paths)
                for path in opt_paths:
                    print(f'[_converter_excel_para_pdf_libreoffice] Caminho encontrado em /opt: {path}')
                
                print(f'[_converter_excel_para_pdf_libreoffice] Total de caminhos a verificar: {len(possiveis_caminhos)}')
                
                # Verificar cada caminho
                for caminho in possiveis_caminhos:
                    print(f'[_converter_excel_para_pdf_libreoffice] Verificando caminho: {caminho}')
                    if os.path.exists(caminho):
                        print(f'[_converter_excel_para_pdf_libreoffice] Caminho existe: {caminho}')
                        if os.access(caminho, os.X_OK):
                            print(f'[_converter_excel_para_pdf_libreoffice] Caminho tem permissão de execução: {caminho}')
                            # Verificar se é um executável real (ELF binary) ou um link simbólico válido
                            try:
                                # Verificar se é um link simbólico
                                if os.path.islink(caminho):
                                    real_path = os.path.realpath(caminho)
                                    print(f'[_converter_excel_para_pdf_libreoffice] É um link simbólico apontando para: {real_path}')
                                    if os.path.exists(real_path) and os.access(real_path, os.X_OK):
                                        caminho = real_path
                                
                                with open(caminho, 'rb') as f:
                                    header = f.read(4)
                                    if header.startswith(b'\x7fELF'):  # ELF binary
                                        soffice_cmd = caminho
                                        print(f'[_converter_excel_para_pdf_libreoffice] Encontrado executável real (ELF): {soffice_cmd}')
                                        break
                                    else:
                                        # Pode ser um script ou link simbólico, mas vamos usar se existir e tiver permissão
                                        print(f'[_converter_excel_para_pdf_libreoffice] Arquivo não é ELF, mas existe e tem permissão: {caminho}')
                                        # Usar este arquivo se ainda não encontrou nenhum
                                        if not soffice_cmd:
                                            soffice_cmd = caminho
                                            print(f'[_converter_excel_para_pdf_libreoffice] Usando arquivo encontrado: {soffice_cmd}')
                            except Exception as e:
                                print(f'[_converter_excel_para_pdf_libreoffice] Erro ao verificar {caminho}: {str(e)}')
                                # Se não encontrou nenhum ainda e o arquivo existe, usar como último recurso
                                if not soffice_cmd and os.path.exists(caminho):
                                    soffice_cmd = caminho
                                    print(f'[_converter_excel_para_pdf_libreoffice] Usando como último recurso: {soffice_cmd}')
                        else:
                            print(f'[_converter_excel_para_pdf_libreoffice] Caminho existe mas não tem permissão de execução: {caminho}')
                    else:
                        print(f'[_converter_excel_para_pdf_libreoffice] Caminho não existe: {caminho}')
                
                # Se não encontrou o executável real, tentar extrair do wrapper
                if not soffice_cmd:
                    # Tentar encontrar usando shutil.which (pode retornar o wrapper)
                    wrapper_path = shutil.which('soffice')
                    if wrapper_path:
                        print(f'[_converter_excel_para_pdf_libreoffice] Encontrado wrapper no PATH: {wrapper_path}')
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
                                                        print(f'[_converter_excel_para_pdf_libreoffice] Executável real encontrado via wrapper: {soffice_cmd}')
                                                        break
                                            except:
                                                continue
                                    if soffice_cmd:
                                        break
                        except Exception as e:
                            print(f'[_converter_excel_para_pdf_libreoffice] Não foi possível encontrar executável real via wrapper: {str(e)}')
                
                # Se ainda não encontrou, NÃO usar o wrapper - retornar erro
                if not soffice_cmd:
                    print('[_converter_excel_para_pdf_libreoffice] Executável real do LibreOffice não encontrado')
                    print('[_converter_excel_para_pdf_libreoffice] Tentou buscar em: /usr/lib/libreoffice/program/soffice, /usr/lib64/libreoffice/program/soffice, /opt/libreoffice*/program/soffice')
                    print('[_converter_excel_para_pdf_libreoffice] Configure a variável LIBREOFFICE_PATH com o caminho completo do executável')
                    print('[_converter_excel_para_pdf_libreoffice] Exemplo: export LIBREOFFICE_PATH=/usr/lib/libreoffice/program/soffice')
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
        
        print(f'[_converter_excel_para_pdf_libreoffice] Executando: {" ".join(cmd)}')
        print(f'[_converter_excel_para_pdf_libreoffice] Arquivo de entrada: {excel_path}')
        print(f'[_converter_excel_para_pdf_libreoffice] Diretório de saída: {output_dir}')
        print(f'[_converter_excel_para_pdf_libreoffice] Executável: {soffice_cmd}')
        
        # Verificar se o executável existe e tem permissões
        if not os.path.exists(soffice_cmd):
            print(f'[_converter_excel_para_pdf_libreoffice] Executável não existe: {soffice_cmd}')
            return None
        
        if not os.access(soffice_cmd, os.X_OK):
            print(f'[_converter_excel_para_pdf_libreoffice] Executável não tem permissão de execução: {soffice_cmd}')
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
            
            print(f'[_converter_excel_para_pdf_libreoffice] PATH: {env.get("PATH", "")[:200]}...')
            print(f'[_converter_excel_para_pdf_libreoffice] LD_LIBRARY_PATH: {env.get("LD_LIBRARY_PATH", "")[:200]}...')
            
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
                print(f'[_converter_excel_para_pdf_libreoffice] Erro ao converter (código {result.returncode})')
                print(f'[_converter_excel_para_pdf_libreoffice] stdout: {result.stdout}')
                print(f'[_converter_excel_para_pdf_libreoffice] stderr: {result.stderr}')
                return None
            else:
                print(f'[_converter_excel_para_pdf_libreoffice] Comando executado com sucesso')
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
        
    except Exception as e:
        print(f'[_converter_excel_para_pdf_libreoffice] Erro ao converter Excel para PDF: {str(e)}')
        import traceback
        print(traceback.format_exc())
        return None

