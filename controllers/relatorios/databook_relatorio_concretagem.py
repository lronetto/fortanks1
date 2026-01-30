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
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from controllers.relatorios.commun import _converter_ods_para_xlsx_libreoffice, _converter_excel_para_pdf_libreoffice
from controllers.relatorios.commun import _obter_pasta_temp_projeto, _criar_diretorio_temp_projeto, _limpar_arquivo_temp, _limpar_diretorio_temp,_criar_arquivo_temp_projeto


# Tentar importar odfpy para suporte a ODS
try:
    from odf.opendocument import load, OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell
    from odf.text import P
    ODFPY_AVAILABLE = True
except ImportError:
    ODFPY_AVAILABLE = False
    print('odfpy não está instalado. Para processar ODS diretamente, instale: pip install odfpy')


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

@databook_concretagem_bp.route('/api/resumo')
@login_required
def api_resumo():
    """
    API para retornar resumo dos dados conforme filtros aplicados
    Retorna informações sobre rompimentos, peças e vinculações
    """
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_id = request.args.get('tanque_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    min_rompimentos = request.args.get('min_rompimentos', type=int)
    
    # Buscar todas as usinagens com os filtros aplicados
    usinagens_query = ConcretoUsinagens.query
    if data_inicio_str:
        usinagens_query = usinagens_query.filter(ConcretoUsinagens.data_usinagem >= data_inicio_str)
    if data_fim_str:
        usinagens_query = usinagens_query.filter(ConcretoUsinagens.data_usinagem <= data_fim_str)
    
    usinagens = usinagens_query.all()
    
    # Coletar dados
    series_com_rompimentos = set()
    series_com_pecas = set()
    series_sem_pecas = set()
    pecas_vinculadas = set()
    total_rompimentos = 0
    
    # Processar cada usinagem
    for usinagem in usinagens:
        numero_serie = usinagem.serie
        
        # Tentar converter para int
        try:
            serie_int = int(numero_serie)
        except (ValueError, TypeError):
            serie_int = None
        
        # Buscar rompimentos
        if serie_int is not None:
            rompimentos = ConcretoUsinagensRompimentos.query.filter(
                ConcretoUsinagensRompimentos.numero_serie == serie_int
            ).all()
            if rompimentos:
                total_rompimentos += len(rompimentos)
                series_com_rompimentos.add(numero_serie)
        
        # Buscar peças
        pecas = buscar_pecas_por_serie(
            numero_serie=numero_serie,
            tanque_id=tanque_id,
            contrato_id=contrato_id,
            grupo_id=grupo_id
        )
        
        if pecas:
            series_com_pecas.add(numero_serie)
            for peca in pecas:
                pecas_vinculadas.add(peca.id)
        else:
            # Aplicar filtro de rompimentos mínimos apenas se não houver peças
            if min_rompimentos is not None:
                if serie_int is not None:
                    count_romp = ConcretoUsinagensRompimentos.query.filter(
                        ConcretoUsinagensRompimentos.numero_serie == serie_int
                    ).count()
                    if count_romp >= min_rompimentos:
                        series_sem_pecas.add(numero_serie)
            else:
                series_sem_pecas.add(numero_serie)
    
    # Buscar todas as peças que deveriam estar vinculadas (baseado nos filtros)
    # Para isso, vamos buscar todas as peças que têm séries no campo qualidade
    pecas_query = TanquesPecas.query.join(Tanques).join(Contrato)
    
    # Aplicar filtros de peças
    if tanque_id:
        pecas_query = pecas_query.filter(TanquesPecas.tanque_id == tanque_id)
    if contrato_id:
        pecas_query = pecas_query.filter(Tanques.contrato_id == contrato_id)
    if grupo_id:
        grupo = TanquesGrupos.query.get(grupo_id)
        if grupo and grupo.tanques:
            tanque_ids_grupo = [tanque.id for tanque in grupo.tanques]
            pecas_query = pecas_query.filter(TanquesPecas.tanque_id.in_(tanque_ids_grupo))
    
    todas_pecas = pecas_query.all()
    
    # Inicializar conjunto de peças não vinculadas
    pecas_nao_vinculadas = set()
    
    # Verificar quais peças têm séries vinculadas
    for peca in todas_pecas:
        if peca.qualidade:
            try:
                qualidade = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else peca.qualidade
                series_peca = qualidade.get('series', [])
                if series_peca:
                    # Verificar se alguma série da peça está nas usinagens filtradas
                    tem_serie_vinculada = False
                    for serie_peca in series_peca:
                        # Normalizar série (pode ser "1059", "1059-c", etc)
                        serie_base = str(serie_peca).split('-')[0]
                        for usinagem in usinagens:
                            if str(usinagem.serie) == serie_base or str(usinagem.serie) == str(serie_peca):
                                tem_serie_vinculada = True
                                break
                        if tem_serie_vinculada:
                            break
                    
                    if not tem_serie_vinculada:
                        pecas_nao_vinculadas.add(peca.id)
                else:
                    pecas_nao_vinculadas.add(peca.id)
            except (json.JSONDecodeError, AttributeError):
                pecas_nao_vinculadas.add(peca.id)
        else:
            pecas_nao_vinculadas.add(peca.id)
    
    # Calcular estatísticas
    total_series = len(usinagens)
    total_series_com_rompimentos = len(series_com_rompimentos)
    total_series_com_pecas = len(series_com_pecas)
    total_series_sem_pecas = len(series_sem_pecas)
    total_pecas = len(todas_pecas)
    total_pecas_com_vinculacao = len(pecas_vinculadas)
    total_pecas_sem_vinculacao = len(pecas_nao_vinculadas)
    
    # Verificar se todas as séries estão vinculadas
    todas_series_vinculadas = total_series_sem_pecas == 0
    todas_pecas_vinculadas = total_pecas_sem_vinculacao == 0
    
    return jsonify({
        'resumo': {
            'total_series': total_series,
            'total_rompimentos': total_rompimentos,
            'total_series_com_rompimentos': total_series_com_rompimentos,
            'total_series_com_pecas': total_series_com_pecas,
            'total_series_sem_pecas': total_series_sem_pecas,
            'series_sem_pecas': sorted(list(series_sem_pecas), key=lambda x: (len(str(x)), str(x))),
            'total_pecas': total_pecas,
            'total_pecas_com_vinculacao': total_pecas_com_vinculacao,
            'total_pecas_sem_vinculacao': total_pecas_sem_vinculacao,
            'todas_series_vinculadas': todas_series_vinculadas,
            'todas_pecas_vinculadas': todas_pecas_vinculadas
        }
    })

@databook_concretagem_bp.route('/exportar-detalhes-excel')
@login_required
def exportar_detalhes_excel():
    """
    Exporta os detalhes das séries, rompimentos e peças em Excel
    com múltiplas abas conforme os filtros aplicados
    """
    try:
        # Obter filtros
        contrato_id = request.args.get('contrato_id', type=int)
        tanque_id = request.args.get('tanque_id', type=int)
        grupo_id = request.args.get('grupo_id', type=int)
        data_inicio_str = request.args.get('data_inicio')
        data_fim_str = request.args.get('data_fim')
        min_rompimentos = request.args.get('min_rompimentos', type=int)
        
        # Buscar todas as usinagens com os filtros aplicados
        usinagens_query = ConcretoUsinagens.query
        if data_inicio_str:
            usinagens_query = usinagens_query.filter(ConcretoUsinagens.data_usinagem >= data_inicio_str)
        if data_fim_str:
            usinagens_query = usinagens_query.filter(ConcretoUsinagens.data_usinagem <= data_fim_str)
        
        usinagens = usinagens_query.all()
        
        # Preparar dados para Excel
        dados_series = []
        dados_rompimentos = []
        dados_pecas = []
        
        # Processar cada usinagem
        for usinagem in usinagens:
            numero_serie = usinagem.serie
            
            # Tentar converter para int
            try:
                serie_int = int(numero_serie)
            except (ValueError, TypeError):
                serie_int = None
            
            # Buscar rompimentos
            rompimentos = []
            if serie_int is not None:
                rompimentos = ConcretoUsinagensRompimentos.query.filter(
                    ConcretoUsinagensRompimentos.numero_serie == serie_int
                ).order_by(ConcretoUsinagensRompimentos.data_rompimento.asc()).all()
            
            # Aplicar filtro de rompimentos mínimos se especificado
            if min_rompimentos is not None and len(rompimentos) < min_rompimentos:
                continue
            
            # Buscar peças
            pecas = buscar_pecas_por_serie(
                numero_serie=numero_serie,
                tanque_id=tanque_id,
                contrato_id=contrato_id,
                grupo_id=grupo_id
            )
            
            # Não filtrar séries sem peças - incluir todas as séries
            # para mostrar também as que não estão vinculadas
            
            # Preparar dados da série
            projetos_unicos = set([peca.tanque.contrato_id for peca in pecas]) if pecas else set()
            projetos_str = ", ".join([Contrato.query.filter(Contrato.id == projeto).first().nome for projeto in projetos_unicos]) if projetos_unicos else "N/A"
            tanques_unicos = set([peca.tanque_id for peca in pecas]) if pecas else set()
            tanques_str = ", ".join([Tanques.query.filter(Tanques.id == tanque).first().nome for tanque in tanques_unicos]) if tanques_unicos else "N/A"
            
            dados_series.append({
                'Número de Série': numero_serie,
                'Data de Moldagem': usinagem.data_usinagem.strftime('%d/%m/%Y %H:%M') if usinagem.data_usinagem else 'N/A',
                'Projeto': projetos_str,
                'Tanque': tanques_str,
                'Total de Rompimentos': len(rompimentos),
                'Total de Peças': len(pecas),
                'Tem Peças Vinculadas': 'Sim' if pecas else 'Não'
            })
            
            # Preparar dados dos rompimentos
            for rompimento in rompimentos:
                resultado_calculado = None
                if rompimento.resultado and rompimento.fator_conversao:
                    resultado_calculado = float(rompimento.resultado) * float(rompimento.fator_conversao)
                
                dados_rompimentos.append({
                    'Número de Série': numero_serie,
                    'Data de Moldagem': usinagem.data_usinagem.strftime('%d/%m/%Y %H:%M') if usinagem.data_usinagem else 'N/A',
                    'Data de Rompimento': rompimento.data_rompimento.strftime('%d/%m/%Y %H:%M') if rompimento.data_rompimento else 'N/A',
                    'Idade (dias)': calcular_idade_cp(usinagem.data_usinagem, rompimento.data_rompimento) if usinagem.data_usinagem and rompimento.data_rompimento else 'N/A',
                    'Resultado (MPa)': round(resultado_calculado, 2) if resultado_calculado else (rompimento.resultado if rompimento.resultado else 'N/A'),
                    'Tipo de Rompimento': rompimento.tipo_rompimento if rompimento.tipo_rompimento else 'N/A',
                    'Fator de Conversão': rompimento.fator_conversao if rompimento.fator_conversao else 'N/A'
                })
            
            # Preparar dados das peças
            for peca in pecas:
                qualidade = None
                series_peca = []
                try:
                    qualidade = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else peca.qualidade
                    series_peca = qualidade.get('series', []) if qualidade else []
                except (json.JSONDecodeError, AttributeError):
                    pass
                
                dados_pecas.append({
                    'Número de Série': numero_serie,
                    'ID da Peça': peca.id,
                    'Nome da Peça': peca.nome,
                    'Tanque': peca.tanque.nome if peca.tanque else 'N/A',
                    'Projeto': peca.tanque.contrato.nome if peca.tanque and peca.tanque.contrato else 'N/A',
                    'Séries na Peça': ", ".join([str(s) for s in series_peca]) if series_peca else 'N/A'
                })
        
        # Adicionar peças não vinculadas (se houver filtros de tanque/contrato/grupo)
        # Buscar todas as peças que deveriam estar vinculadas mas não estão
        if grupo_id or tanque_id or contrato_id:
            pecas_query = TanquesPecas.query.join(Tanques).join(Contrato)
            
            # Aplicar filtros de peças
            if tanque_id:
                pecas_query = pecas_query.filter(TanquesPecas.tanque_id == tanque_id)
            if contrato_id:
                pecas_query = pecas_query.filter(Tanques.contrato_id == contrato_id)
            if grupo_id:
                grupo = TanquesGrupos.query.get(grupo_id)
                if grupo and grupo.tanques:
                    tanque_ids_grupo = [tanque.id for tanque in grupo.tanques]
                    pecas_query = pecas_query.filter(TanquesPecas.tanque_id.in_(tanque_ids_grupo))
            
            todas_pecas_filtradas = pecas_query.all()
            
            # Verificar quais peças não estão vinculadas a séries nas usinagens filtradas
            pecas_ids_ja_incluidas = set([peca['ID da Peça'] for peca in dados_pecas])
            
            for peca in todas_pecas_filtradas:
                if peca.id in pecas_ids_ja_incluidas:
                    continue
                
                qualidade = None
                series_peca = []
                tem_serie_vinculada = False
                
                try:
                    qualidade = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else peca.qualidade
                    series_peca = qualidade.get('series', []) if qualidade else []
                    
                    if series_peca:
                        # Verificar se alguma série da peça está nas usinagens filtradas
                        for serie_peca in series_peca:
                            serie_base = str(serie_peca).split('-')[0]
                            for usinagem in usinagens:
                                if str(usinagem.serie) == serie_base or str(usinagem.serie) == str(serie_peca):
                                    tem_serie_vinculada = True
                                    break
                            if tem_serie_vinculada:
                                break
                except (json.JSONDecodeError, AttributeError):
                    pass
                
                # Se não tem série vinculada ou não tem séries no campo qualidade, adicionar como não vinculada
                if not tem_serie_vinculada:
                    dados_pecas.append({
                        'Número de Série': 'N/A',
                        'ID da Peça': peca.id,
                        'Nome da Peça': peca.nome,
                        'Tanque': peca.tanque.nome if peca.tanque else 'N/A',
                        'Projeto': peca.tanque.contrato.nome if peca.tanque and peca.tanque.contrato else 'N/A',
                        'Séries na Peça': ", ".join([str(s) for s in series_peca]) if series_peca else 'N/A'
                    })
        
        # Verificar se há dados para exportar
        if not dados_series and not dados_rompimentos and not dados_pecas:
            return jsonify({'error': 'Nenhum dado encontrado para exportar com os filtros aplicados'}), 404
        
        # Criar Excel na memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Aba 1: Resumo de Séries
            if dados_series:
                df_series = pd.DataFrame(dados_series)
                df_series.to_excel(writer, index=False, sheet_name='Séries')
                
                # Formatar aba de séries
                worksheet_series = writer.sheets['Séries']
                for idx, col in enumerate(df_series.columns):
                    max_length = max(
                        df_series[col].astype(str).apply(len).max(),
                        len(col)
                    )
                    adjusted_width = min(max_length + 2, 50)
                    col_letter = get_column_letter(idx + 1)
                    worksheet_series.column_dimensions[col_letter].width = adjusted_width
                
                # Formatar cabeçalho
                for cell in worksheet_series[1]:
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
                    cell.font = Font(bold=True, color='FFFFFF')
                    cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # Aba 2: Detalhes de Rompimentos
            if dados_rompimentos:
                df_rompimentos = pd.DataFrame(dados_rompimentos)
                df_rompimentos.to_excel(writer, index=False, sheet_name='Rompimentos')
                
                # Formatar aba de rompimentos
                worksheet_rompimentos = writer.sheets['Rompimentos']
                for idx, col in enumerate(df_rompimentos.columns):
                    max_length = max(
                        df_rompimentos[col].astype(str).apply(len).max(),
                        len(col)
                    )
                    adjusted_width = min(max_length + 2, 50)
                    col_letter = get_column_letter(idx + 1)
                    worksheet_rompimentos.column_dimensions[col_letter].width = adjusted_width
                
                # Formatar cabeçalho
                for cell in worksheet_rompimentos[1]:
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color='ED7D31', end_color='ED7D31', fill_type='solid')
                    cell.font = Font(bold=True, color='FFFFFF')
                    cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # Aba 3: Detalhes de Peças
            if dados_pecas:
                df_pecas = pd.DataFrame(dados_pecas)
                df_pecas.to_excel(writer, index=False, sheet_name='Peças')
                
                # Formatar aba de peças
                worksheet_pecas = writer.sheets['Peças']
                for idx, col in enumerate(df_pecas.columns):
                    max_length = max(
                        df_pecas[col].astype(str).apply(len).max(),
                        len(col)
                    )
                    adjusted_width = min(max_length + 2, 50)
                    col_letter = get_column_letter(idx + 1)
                    worksheet_pecas.column_dimensions[col_letter].width = adjusted_width
                
                # Formatar cabeçalho
                for cell in worksheet_pecas[1]:
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color='70AD47', end_color='70AD47', fill_type='solid')
                    cell.font = Font(bold=True, color='FFFFFF')
                    cell.alignment = Alignment(horizontal='center', vertical='center')
        
        output.seek(0)
        
        # Nome do arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'detalhes_concretagem_{timestamp}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f'Erro ao exportar detalhes Excel: {str(e)}')
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': f'Erro ao exportar Excel: {str(e)}'}), 500

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
            print(f'[_gerar_excel_temp] odfpy não disponível')
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
                            
                            nome_arquivo = f'relatorio_serie_{numero_serie}.xlsx'
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
