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

from pylovepdf.tools.officepdf import OfficeToPdf



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
    
    # Função auxiliar para extrair IDs de tanques do JSON
    def extrair_tanque_ids_do_json(pecas_json_str):
        """
        Extrai os IDs únicos de tanques do JSON da coluna pecas.
        
        Formato esperado do JSON:
        [
            {"placa": "PN-02", "tanque": 1, "forma": "4"},
            {"placa": "PN-03", "tanque": 1, "forma": "6"},
            ...
        ]
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
        
        # Buscar informações dos tanques
        tanques_info = []
        if tanque_ids_set:
            tanques_query = Tanques.query.filter(Tanques.id.in_(tanque_ids_set))
            
            # Aplicar filtro de contrato se especificado
            if contrato_id:
                tanques_query = tanques_query.filter(Tanques.contrato_id == contrato_id)
            
            # Aplicar filtro de grupo se especificado
            if grupo_id:
                grupo = TanquesGrupos.query.get(grupo_id)
                if grupo and grupo.tanques:
                    tanque_ids_grupo = [t.id for t in grupo.tanques]
                    tanques_query = tanques_query.filter(Tanques.id.in_(tanque_ids_grupo))
            
            tanques = tanques_query.all()
            
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



def _gerar_excel_temp(concretagem_id,tanque_id=None,projeto_id=None,grupo_id=None):
    """
    Função auxiliar que gera o Excel e retorna o caminho do arquivo temporário
    Retorna o caminho do arquivo temporário ou None em caso de erro
    """
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
        
      

        
        # Caminho do arquivo template - RELATORIO INSPECAO.xlsx
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates_excel', 'RELATORIO_INSPECAO.xlsx'
        )
        
        if not os.path.exists(template_path):
            print(f'Template path: {template_path}')
            print(f'Template RELATORIO INSPECAO.xlsx não encontrado')
            return None
        
        # Criar uma cópia temporária do arquivo para preservar imagens
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        temp_file.close()
        shutil.copy2(template_path, temp_file.name)
        
        # Carregar o arquivo Excel base
        wb = load_workbook(temp_file.name, data_only=False, keep_vba=False, read_only=False)
       
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
                            # Extrair todos os IDs únicos de tanques do JSON
                            tanques_ids_json = set()
                            for peca in pecas:
                                if isinstance(peca, dict) and 'tanque' in peca and peca['tanque'] is not None:
                                    tanques_ids_json.add(peca['tanque'])
                                
                               

                            
                            if tanques_ids_json:
                                # Buscar informações dos tanques
                                tanques_query = Tanques.query.filter(Tanques.id.in_(tanques_ids_json))
                                
                                # Aplicar filtro de projeto se especificado
                                if projeto_id is not None:
                                    tanques_query = tanques_query.filter(Tanques.contrato_id == projeto_id)
                                
                                # Aplicar filtro de grupo se especificado
                                if grupo_id:
                                    grupo = TanquesGrupos.query.get(grupo_id)
                                    if grupo and grupo.tanques:
                                        tanque_ids_grupo = [t.id for t in grupo.tanques]
                                        tanques_query = tanques_query.filter(Tanques.id.in_(tanque_ids_grupo))
                                if tanque_id:
                                    tanques_query = tanques_query.filter(Tanques.id == tanque_id)
                                
                                tanques = tanques_query.all()
                                
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
                                                        peca_tanque_query = TanquesPecas.query.filter(
                                                            TanquesPecas.tanque_id == peca['tanque'],
                                                            TanquesPecas.nome == peca['placa']
                                                        )
                                                        if tanque_id:
                                                            peca_tanque_query = peca_tanque_query.filter(TanquesPecas.tanque_id==tanque_id)
                                                        if grupo_id:
                                                            grupo = TanquesGrupos.query.get(grupo_id)
                                                            if grupo and grupo.tanques:
                                                                tanque_ids_grupo = [t.id for t in grupo.tanques]
                                                                peca_tanque_query = peca_tanque_query.filter(TanquesPecas.tanque_id.in_(tanque_ids_grupo))
                                                        peca_tanque = peca_tanque_query.first()
                                                        
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
                                    if total_alongamentos > 16:
                                        new_value = new_value.replace('{122}', 'C-17')
                                        # Preencher C-17 até o último alongamento
                                        for i in range(17, total_alongamentos + 1):
                                            chave = f'C-{i}'
                                            if chave in alongamentos:
                                                valor = alongamentos[chave]
                                                placeholder = 79 + (i - 17)
                                                new_value = new_value.replace(f'{{{placeholder}}}', str(valor))
                                    else:
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
            wb.save(temp_file.name)
        except Exception as save_error:
            raise Exception(f'Erro ao salvar arquivo Excel: {str(save_error)}')
        finally:
            try:
                wb.close()
            except:
                pass
        
        # Verificar se o arquivo foi salvo corretamente
        if not os.path.exists(temp_file.name):
            return None
        
        file_size = os.path.getsize(temp_file.name)
        if file_size == 0:
            return None
        
        return temp_file.name
    except Exception as e:
        try:
            if 'temp_file' in locals() and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
        except:
            pass
        print(f'Erro ao gerar Excel: {str(e)}')
        return None

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
            # Limpar arquivo temporário
            if os.path.exists(excel_path):
                try:
                    os.unlink(excel_path)
                except:
                    pass
        
    except Exception as e:
        return jsonify({'error': f'Erro ao exportar Excel: {str(e)}'}), 500

@databook_inspecao_bp.route('/exportar-pdf')
@login_required
def exportar_pdf():
    """
    Exporta dados de uma concretagem específica para PDF convertendo do Excel gerado usando iLovePDF API
    """
    excel_path = None
    pdf_temp_path = None
    pdf_temp_dir = None
    
    try:
        concretagem_id = request.args.get('concretagem_id', type=int)
        tanque_id = request.args.get('tanque_id', type=int) or None
        projeto_id = request.args.get('projeto_id', type=int) or None
        
        if not concretagem_id:
            return jsonify({'error': 'Parâmetro concretagem_id é obrigatório'}), 400
        
        excel_path = _gerar_excel_temp(concretagem_id, tanque_id, projeto_id)
        
        if not excel_path or not os.path.exists(excel_path):
            return jsonify({'error': f'Nenhuma concretagem encontrada para o ID {concretagem_id}'}), 404
        
        # Obter credenciais da API do ambiente
        ilovepdf_public_key = os.getenv('ILOVEPDF_PUBLIC_KEY')
        ilovepdf_secret_key = os.getenv('ILOVEPDF_SECRET_KEY')
        
        if not ilovepdf_public_key or not ilovepdf_secret_key:
            return jsonify({
                'error': 'Credenciais iLovePDF não configuradas. Configure as variáveis ILOVEPDF_PUBLIC_KEY e ILOVEPDF_SECRET_KEY.'
            }), 500
        
        # Inicializar cliente iLovePDF
        officepdf = OfficeToPdf(ilovepdf_public_key, verify_ssl=True, proxies=None)
        
        # Criar diretório temporário para salvar o PDF
        pdf_temp_dir = tempfile.mkdtemp()
        
        # Criar arquivo PDF temporário
        pdf_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', dir=pdf_temp_dir)
        pdf_temp_file.close()
        pdf_temp_path = pdf_temp_file.name
        
        # Adicionar arquivo Excel
        officepdf.add_file(excel_path)
        
        # Definir diretório de saída (deve ser um diretório, não um arquivo)
        officepdf.set_output_folder(pdf_temp_dir)
        
        # Executar conversão
        officepdf.execute()
        
        # Baixar PDF gerado
        officepdf.download()
        
        # Limpar tarefa na API
        officepdf.delete_current_task()
        
        # Encontrar o arquivo PDF gerado (pode ter nome diferente)
        pdf_files = [f for f in os.listdir(pdf_temp_dir) if f.endswith('.pdf')]
        if not pdf_files:
            return jsonify({'error': 'PDF não foi gerado pela API iLovePDF'}), 500

        # Se encontrou arquivo, usar o primeiro
        generated_pdf_path = os.path.join(pdf_temp_dir, pdf_files[0])
        if not os.path.exists(generated_pdf_path):
            return jsonify({'error': 'Arquivo PDF gerado não encontrado'}), 500
        
        # Mover para o caminho esperado
        if generated_pdf_path != pdf_temp_path:
            if os.path.exists(pdf_temp_path):
                os.unlink(pdf_temp_path)
            shutil.move(generated_pdf_path, pdf_temp_path)
        
        # Verificar se o PDF foi gerado corretamente
        if not os.path.exists(pdf_temp_path) or os.path.getsize(pdf_temp_path) == 0:
            return jsonify({'error': 'PDF não foi gerado corretamente pela API iLovePDF'}), 500
        
        # Ler o PDF gerado para buffer de memória
        output = io.BytesIO()
        with open(pdf_temp_path, 'rb') as f:
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
        # Limpar arquivos temporários
        if excel_path and os.path.exists(excel_path):
            try:
                os.unlink(excel_path)
            except:
                pass
        if pdf_temp_path and os.path.exists(pdf_temp_path):
            try:
                os.unlink(pdf_temp_path)
            except:
                pass
        # Limpar diretório temporário se existir
        if pdf_temp_dir and os.path.exists(pdf_temp_dir):
            try:
                shutil.rmtree(pdf_temp_dir)
            except:
                pass

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
        temp_dir = tempfile.mkdtemp()
        arquivos_gerados = []
        
        try:
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
                            # Limpar arquivo temporário original
                            try:
                                os.unlink(excel_path)
                            except:
                                pass
                    else:  # PDF
                        # Gerar Excel primeiro
                        excel_path = _gerar_excel_temp(concretagem_id, tanque_id, projeto_id, grupo_id)
                        if excel_path and os.path.exists(excel_path):
                            # Converter para PDF
                            pdf_path = _gerar_pdf_temp(excel_path, concretagem_id)
                            if pdf_path and os.path.exists(pdf_path):
                                nome_arquivo = f'relatorio_inspecao_{concretagem_id}.pdf'
                                destino = os.path.join(temp_dir, nome_arquivo)
                                shutil.copy2(pdf_path, destino)
                                arquivos_gerados.append(destino)
                                # Limpar arquivos temporários
                                try:
                                    os.unlink(excel_path)
                                    if pdf_path != excel_path:
                                        os.unlink(pdf_path)
                                except:
                                    pass
                except Exception as e:
                    print(f'Erro ao processar concretagem {concretagem_id}: {str(e)}')
                    continue
            
            if not arquivos_gerados:
                return jsonify({'error': 'Nenhum arquivo foi gerado com sucesso'}), 404
            
            # Criar arquivo ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for arquivo in arquivos_gerados:
                    nome_arquivo = os.path.basename(arquivo)
                    zip_file.write(arquivo, nome_arquivo)
            
            zip_buffer.seek(0)
            
            # Nome do arquivo ZIP
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'exportacao_massa_{formato}_{timestamp}.zip'
            
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=filename
            )
            
        finally:
            # Limpar diretório temporário
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
                
    except Exception as e:
        return jsonify({'error': f'Erro ao exportar em massa: {str(e)}'}), 500

def _gerar_pdf_temp(excel_path, concretagem_id):
    """
    Função auxiliar que converte Excel para PDF usando iLovePDF API
    Retorna o caminho do arquivo PDF temporário ou None em caso de erro
    """
    pdf_temp_path = None
    pdf_temp_dir = None
    
    try:
        if not excel_path or not os.path.exists(excel_path):
            return None
        
        # Obter credenciais da API do ambiente
        ilovepdf_public_key = os.getenv('ILOVEPDF_PUBLIC_KEY')
        ilovepdf_secret_key = os.getenv('ILOVEPDF_SECRET_KEY')
        
        if not ilovepdf_public_key or not ilovepdf_secret_key:
            print('Credenciais iLovePDF não configuradas')
            return None
        
        # Inicializar cliente iLovePDF
        officepdf = OfficeToPdf(ilovepdf_public_key, verify_ssl=True, proxies=None)
        
        # Criar diretório temporário para salvar o PDF
        pdf_temp_dir = tempfile.mkdtemp()
        
        # Criar arquivo PDF temporário
        pdf_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', dir=pdf_temp_dir)
        pdf_temp_file.close()
        pdf_temp_path = pdf_temp_file.name
        
        # Adicionar arquivo Excel
        officepdf.add_file(excel_path)
        
        # Definir diretório de saída
        officepdf.set_output_folder(pdf_temp_dir)
        
        # Executar conversão
        officepdf.execute()
        
        # Baixar PDF gerado
        officepdf.download()
        
        # Limpar tarefa na API
        officepdf.delete_current_task()
        
        # Encontrar o arquivo PDF gerado
        pdf_files = [f for f in os.listdir(pdf_temp_dir) if f.endswith('.pdf')]
        if not pdf_files:
            return None
        
        # Usar o primeiro arquivo PDF encontrado
        generated_pdf_path = os.path.join(pdf_temp_dir, pdf_files[0])
        if os.path.exists(generated_pdf_path):
            return generated_pdf_path
        
        return None
        
    except Exception as e:
        print(f'Erro ao gerar PDF: {str(e)}')
        return None
    finally:
        # Limpar diretório temporário se necessário
        if pdf_temp_dir and os.path.exists(pdf_temp_dir):
            try:
                # Não remover ainda, o arquivo será usado
                pass
            except:
                pass
