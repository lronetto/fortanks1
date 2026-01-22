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
import tempfile
import zipfile
import openpyxl
from openpyxl import load_workbook
from openpyxl.worksheet.page import PageMargins
import json

from pylovepdf.tools.officepdf import OfficeToPdf



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
    
    # Converter datas se fornecidas
    data_inicio = None
    data_fim = None
    print(f'grupo_id: {grupo_id}')
    print(f'tanque_id: {tanque_id}')
    print(f'contrato_id: {contrato_id}')
    print(f'data_inicio_str: {data_inicio_str}')
    print(f'data_fim_str: {data_fim_str}')
    usinagens = ConcretoUsinagens.query
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
        total_rompimentos = ConcretoUsinagensRompimentos.query.filter(ConcretoUsinagensRompimentos.numero_serie == usinagem.serie).count()   
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
def _gerar_excel_temp(numero_serie, tanque_id=None, contrato_id=None, grupo_id=None):
    """
    Função auxiliar que gera o Excel e retorna o caminho do arquivo temporário
    Retorna o caminho do arquivo temporário ou None em caso de erro
    """
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
        
        # Caminho do arquivo template
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates_excel', 'RELATORIO_CONCRETAGEM.xlsx'
        )
        
        if not os.path.exists(template_path):
            print(f'Template RELATORIO CONCRETAGEM.xlsx não encontrado')
            return None
        
        # Criar uma cópia temporária do arquivo para preservar imagens
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        temp_file.close()
        shutil.copy2(template_path, temp_file.name)
        
        # Carregar o arquivo Excel base
        # Usar read_only=False para permitir edição
        wb = load_workbook(temp_file.name, data_only=False, keep_vba=False, read_only=False)
       
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
            wb.save(temp_file.name)
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
        if not os.path.exists(temp_file.name):
            return None
        
        file_size = os.path.getsize(temp_file.name)
        if file_size == 0:
            return None
        
        return temp_file.name
    except Exception as e:
        # Em caso de erro, tentar limpar o arquivo temporário
        print(f'Erro em _gerar_excel_temp: {str(e)}')
        import traceback
        print(traceback.format_exc())
        try:
            if 'temp_file' in locals() and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
        except:
            pass
        return None

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
            # Ler o arquivo salvo para o buffer
            output = io.BytesIO()
            with open(excel_path, 'rb') as f:
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
            # Limpar arquivo temporário
            if os.path.exists(excel_path):
                try:
                    os.unlink(excel_path)
                except:
                    pass
        
    except Exception as e:
        return jsonify({'error': f'Erro ao exportar Excel: {str(e)}'}), 500

@databook_concretagem_bp.route('/exportar-pdf/<numero_serie>')
@login_required
def exportar_pdf(numero_serie):
    """
    Exporta dados de uma série específica para PDF convertendo do Excel gerado usando iLovePDF API
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
        print(f'pdf_files: {pdf_files}')

        # Se encontrou arquivo, usar o primeiro
        generated_pdf_path = os.path.join(pdf_temp_dir, pdf_files[0])
        if not os.path.exists(generated_pdf_path):
            return jsonify({'error': 'Arquivo PDF gerado não encontrado'}), 500
        
       
        print(f'pdf_temp_dir: {pdf_temp_dir}')
        # Ler o PDF gerado para buffer de memória
        output = io.BytesIO()
        with open(pdf_temp_dir+'/'+pdf_files[1], 'rb') as f:
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
        # Limpar arquivos temporários
        if excel_path and os.path.exists(excel_path):
            try:
                os.unlink(excel_path)
            except:
                pass
        if pdf_temp_path and os.path.exists(pdf_temp_path):
            try:
                pass#os.unlink(pdf_temp_path)
            except:
                pass
        # Limpar diretório temporário se existir
        if 'pdf_temp_dir' in locals() and pdf_temp_dir and os.path.exists(pdf_temp_dir):
            try:
                shutil.rmtree(pdf_temp_dir)
                pass
            except:
                pass

@databook_concretagem_bp.route('/exportar-massa', methods=['POST'])
@login_required
def exportar_massa():
    """
    Exporta múltiplas séries em massa (Excel ou PDF)
    Retorna um arquivo ZIP com todos os arquivos gerados
    """
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
        temp_dir = tempfile.mkdtemp()
        arquivos_gerados = []
        
        try:
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
                            # Limpar arquivo temporário original
                            try:
                                os.unlink(excel_path)
                            except:
                                pass
                    else:  # PDF
                        # Gerar Excel primeiro
                        excel_path = _gerar_excel_temp(numero_serie_int, tanque_id, contrato_id, grupo_id)
                        if excel_path and os.path.exists(excel_path):
                            # Converter para PDF
                            pdf_path = _gerar_pdf_temp(excel_path, numero_serie_int)
                            if pdf_path and os.path.exists(pdf_path):
                                nome_arquivo = f'relatorio_serie_{numero_serie}.pdf'
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
                    print(f'Erro ao processar série {numero_serie}: {str(e)}')
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

def _gerar_pdf_temp(excel_path, numero_serie):
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
