from flask import Blueprint, render_template, request, send_file, jsonify
from models.tanque import TanquesPecas, Tanques
from models.contrato import Contrato
from models.database import db
from datetime import datetime, timedelta
import json
import pandas as pd
import io
from weasyprint import HTML, CSS
import os

acabamento_pecas_bp = Blueprint('relatorios_acabamento_pecas', __name__, url_prefix='/relatorios/acabamento-pecas')

def get_dados_acabamento(data_inicio=None, data_fim=None, tanque_id=None, contrato_id=None):
    """
    Busca dados de acabamento de peças com filtros opcionais
    """
    query = TanquesPecas.query.join(Tanques)
    
    # Aplicar filtros
    if tanque_id:
        query = query.filter(TanquesPecas.tanque_id == tanque_id)
    
    if contrato_id:
        query = query.filter(Tanques.contrato_id == contrato_id)
    
    pecas = query.all()
    
    dados = []
    for peca in pecas:
        qualidade = peca.qualidade or '{}'
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        
        if 'acabamento' in qualidade_dict and qualidade_dict['acabamento']:
            data_acabamento_str = qualidade_dict['acabamento']
            try:
                # Tentar diferentes formatos de data
                if isinstance(data_acabamento_str, str):
                    if len(data_acabamento_str) == 10:  # YYYY-MM-DD
                        data_acabamento = datetime.strptime(data_acabamento_str, '%Y-%m-%d').date()
                    else:
                        data_acabamento = datetime.strptime(data_acabamento_str, '%Y-%m-%d %H:%M:%S').date()
                else:
                    continue
                
                # Aplicar filtro de data se fornecido
                if data_inicio and data_acabamento < data_inicio:
                    continue
                if data_fim and data_acabamento > data_fim:
                    continue
                
                # Buscar pista do campo qualidade
                pista = None
                if 'pista' in qualidade_dict:
                    pista = qualidade_dict['pista']
                
                # Calcular metros de placas (altura_total do tanque)
                metros_placas = 0
                if peca.tanque and peca.tanque.altura_total:
                    metros_placas = float(peca.tanque.altura_total)
                
                dados.append({
                    'id': peca.id,
                    'nome': peca.nome,
                    'numero_sequencial': peca.numero_sequencial,
                    'tanque_nome': peca.tanque.nome,
                    'tanque_id': peca.tanque_id,
                    'contrato_id': peca.tanque.contrato_id if peca.tanque else None,
                    'contrato_nome': peca.tanque.contrato.nome if (peca.tanque and peca.tanque.contrato) else None,
                    'data_acabamento': data_acabamento,
                    'data_concretagem': peca.data_concretagem.date() if peca.data_concretagem else None,
                    'pista': pista,
                    'tipo': peca.tipo,
                    'metros_placas': metros_placas
                })
            except (ValueError, TypeError) as e:
                continue
    
    return dados

def agrupar_por_mes(dados):
    """
    Agrupa dados de acabamento por mês
    """
    agrupado = {}
    for item in dados:
        data = item['data_acabamento']
        chave = f"{data.year}-{data.month:02d}"
        if chave not in agrupado:
            agrupado[chave] = {
                'mes': data.month,
                'ano': data.year,
                'quantidade': 0,
                'metros_placas': 0.0,
                'pecas': []
            }
        agrupado[chave]['quantidade'] += 1
        agrupado[chave]['metros_placas'] += item.get('metros_placas', 0)
        agrupado[chave]['pecas'].append(item)
    
    # Ordenar por data
    return dict(sorted(agrupado.items()))

def agrupar_por_semana_por_pista(dados):
    """
    Agrupa dados de acabamento por semana e por pista
    Retorna um dicionário com estrutura: {semana: {pista: quantidade}}
    """
    agrupado = {}
    pistas_unicas = set()
    
    for item in dados:
        data = item['data_acabamento']
        pista = item.get('pista', 'Sem pista')
        pistas_unicas.add(pista)
        
        # Calcular número da semana ISO
        ano, semana, dia_semana = data.isocalendar()
        chave = f"{ano}-W{semana:02d}"
        
        if chave not in agrupado:
            # Calcular início da semana (segunda-feira)
            inicio_semana = data - timedelta(days=dia_semana - 1)
            agrupado[chave] = {
                'ano': ano,
                'semana': semana,
                'inicio_semana': inicio_semana,
                'fim_semana': inicio_semana + timedelta(days=6),
                'pistas': {}
            }
        
        if pista not in agrupado[chave]['pistas']:
            agrupado[chave]['pistas'][pista] = 0
        
        agrupado[chave]['pistas'][pista] += 1
    
    # Ordenar por data
    return dict(sorted(agrupado.items())), sorted(list(pistas_unicas))

def agrupar_por_semana(dados):
    """
    Agrupa dados de acabamento por semana (compatibilidade com exportações)
    """
    agrupado = {}
    for item in dados:
        data = item['data_acabamento']
        # Calcular número da semana ISO
        ano, semana, dia_semana = data.isocalendar()
        chave = f"{ano}-W{semana:02d}"
        
        if chave not in agrupado:
            # Calcular início da semana (segunda-feira)
            inicio_semana = data - timedelta(days=dia_semana - 1)
            agrupado[chave] = {
                'ano': ano,
                'semana': semana,
                'inicio_semana': inicio_semana,
                'fim_semana': inicio_semana + timedelta(days=6),
                'quantidade': 0,
                'metros_placas': 0.0,
                'pecas': []
            }
        agrupado[chave]['quantidade'] += 1
        agrupado[chave]['metros_placas'] += item.get('metros_placas', 0)
        agrupado[chave]['pecas'].append(item)
    
    # Ordenar por data
    return dict(sorted(agrupado.items()))

@acabamento_pecas_bp.route('/')
def index():
    """
    Página principal do relatório de acabamento de peças
    """
    # Filtros padrão: últimos 6 meses
    data_fim = datetime.now().date()
    data_inicio = (data_fim - timedelta(days=180))
    
    # Obter filtros da requisição
    data_inicio_str = request.args.get('data_inicio', data_inicio.strftime('%Y-%m-%d'))
    data_fim_str = request.args.get('data_fim', data_fim.strftime('%Y-%m-%d'))
    tanque_id = request.args.get('tanque_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
    except ValueError:
        data_inicio = (datetime.now().date() - timedelta(days=180))
        data_fim = datetime.now().date()
    
    # Buscar dados
    dados = get_dados_acabamento(data_inicio=data_inicio, data_fim=data_fim, tanque_id=tanque_id, contrato_id=contrato_id)
    
    # Agrupar dados
    dados_mes = agrupar_por_mes(dados)
    dados_semana, pistas = agrupar_por_semana_por_pista(dados)
    
    # Preparar dados para gráficos por pista
    labels_semana = [f"Sem {v['semana']}/{v['ano']}" for v in dados_semana.values()]
    
    # Preparar dados por pista para o gráfico
    dados_por_pista = {}
    medias_diarias_por_pista = {}
    for pista in pistas:
        dados_por_pista[pista] = []
        medias_diarias_por_pista[pista] = []
        for chave, valor in dados_semana.items():
            quantidade = valor['pistas'].get(pista, 0)
            dados_por_pista[pista].append(quantidade)
            # Calcular média diária (quantidade / 7 dias)
            media_diaria = round(quantidade / 7.0, 2) if quantidade > 0 else 0
            medias_diarias_por_pista[pista].append(media_diaria)
    
    # Calcular total de metros de placas
    total_metros_placas = sum(item.get('metros_placas', 0) for item in dados)
    
    # Buscar tanques para filtro (filtrados por projeto se selecionado)
    if contrato_id:
        tanques = Tanques.query.filter(
            Tanques.contrato_id == contrato_id
        ).order_by(Tanques.nome).all()
        # Filtrar apenas tanques com contrato ativo
        tanques = [t for t in tanques if t.contrato and t.contrato.ativo]
    else:
        # Retornar todos os tanques com contrato ativo
        tanques = Tanques.query.all()
        tanques = [t for t in tanques if not t.contrato or t.contrato.ativo]
        tanques.sort(key=lambda x: x.nome)
    
    contratos = Contrato.query.filter(Contrato.ativo == True).order_by(Contrato.nome).all()
    
    return render_template(
        'relatorios/acabamento_pecas/index.html',
        dados_semana=dados_semana,
        labels_semana=labels_semana,
        dados_por_pista=dados_por_pista,
        medias_diarias_por_pista=medias_diarias_por_pista,
        pistas=pistas,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
        tanques=tanques,
        contratos=contratos,
        total_pecas=len(dados),
        total_metros_placas=round(total_metros_placas, 2)
    )

@acabamento_pecas_bp.route('/api/tanques-por-projeto')
def api_tanques_por_projeto():
    """
    API para retornar tanques filtrados por projeto (contrato)
    """
    contrato_id = request.args.get('contrato_id', type=int)
    
    if contrato_id:
        # Filtrar tanques do projeto específico
        tanques = Tanques.query.filter(
            Tanques.contrato_id == contrato_id
        ).order_by(Tanques.nome).all()
    else:
        # Retornar todos os tanques (com ou sem contrato)
        tanques = Tanques.query.order_by(Tanques.nome).all()
    
    tanques_json = []
    for tanque in tanques:
        # Verificar se o contrato está ativo (se existir)
        if tanque.contrato:
            if not tanque.contrato.ativo:
                continue
        tanques_json.append({
            'id': tanque.id,
            'nome': tanque.nome
        })
    
    return jsonify({'tanques': tanques_json})

@acabamento_pecas_bp.route('/api/dados')
def api_dados():
    """
    API para retornar dados do relatório em JSON (para gráficos e tabelas)
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    tanque_id = request.args.get('tanque_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_acabamento(data_inicio=data_inicio, data_fim=data_fim, tanque_id=tanque_id, contrato_id=contrato_id)
    dados_semana, pistas = agrupar_por_semana_por_pista(dados)
    
    # Preparar dados para gráfico por pista
    labels_semana = [f"Sem {v['semana']}/{v['ano']}" for v in dados_semana.values()]
    
    # Preparar dados por pista
    dados_por_pista = {}
    medias_diarias_por_pista = {}
    for pista in pistas:
        dados_por_pista[pista] = []
        medias_diarias_por_pista[pista] = []
        for chave, valor in dados_semana.items():
            quantidade = valor['pistas'].get(pista, 0)
            dados_por_pista[pista].append(quantidade)
            # Calcular média diária (quantidade / 7 dias)
            media_diaria = round(quantidade / 7.0, 2) if quantidade > 0 else 0
            medias_diarias_por_pista[pista].append(media_diaria)
    
    # Calcular total de metros de placas
    total_metros_placas = sum(item.get('metros_placas', 0) for item in dados)
    
    return jsonify({
        'semana': {
            'labels': labels_semana,
            'pistas': pistas,
            'dados_por_pista': dados_por_pista,
            'medias_diarias_por_pista': medias_diarias_por_pista
        },
        'total': len(dados),
        'total_metros_placas': round(total_metros_placas, 2),
        'data_inicio': data_inicio_str,
        'data_fim': data_fim_str
    })

@acabamento_pecas_bp.route('/exportar_excel')
def exportar_excel():
    """
    Exporta relatório para Excel
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    tanque_id = request.args.get('tanque_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_acabamento(data_inicio=data_inicio, data_fim=data_fim, tanque_id=tanque_id, contrato_id=contrato_id)
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    
    # Preparar dados para Excel
    excel_data = []
    
    # Aba 1: Detalhamento por peça
    for item in dados:
        excel_data.append({
            'Data Acabamento': item['data_acabamento'].strftime('%d/%m/%Y'),
            'Projeto': item.get('contrato_nome', ''),
            'Tanque': item['tanque_nome'],
            'Peça': item['nome'],
            'Número Sequencial': item['numero_sequencial'],
            'Tipo': item['tipo'],
            'Data Concretagem': item['data_concretagem'].strftime('%d/%m/%Y') if item['data_concretagem'] else ''
        })
    
    df_detalhes = pd.DataFrame(excel_data)
    
    # Aba 2: Resumo por mês
    resumo_mes = []
    for chave, valor in dados_mes.items():
        resumo_mes.append({
            'Mês/Ano': f"{valor['mes']:02d}/{valor['ano']}",
            'Quantidade': valor['quantidade'],
            'Metros de Placas': round(valor.get('metros_placas', 0), 2)
        })
    df_mes = pd.DataFrame(resumo_mes)
    
    # Aba 3: Resumo por semana
    resumo_semana = []
    for chave, valor in dados_semana.items():
        resumo_semana.append({
            'Semana': f"Sem {valor['semana']}/{valor['ano']}",
            'Início': valor['inicio_semana'].strftime('%d/%m/%Y'),
            'Fim': valor['fim_semana'].strftime('%d/%m/%Y'),
            'Quantidade': valor['quantidade'],
            'Metros de Placas': round(valor.get('metros_placas', 0), 2)
        })
    df_semana = pd.DataFrame(resumo_semana)
    
    # Criar arquivo Excel em memória
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df_detalhes.to_excel(writer, index=False, sheet_name='Detalhamento')
        df_mes.to_excel(writer, index=False, sheet_name='Resumo Mensal')
        df_semana.to_excel(writer, index=False, sheet_name='Resumo Semanal')
    
    excel_buffer.seek(0)
    
    nome_arquivo = f'relatorio_acabamento_pecas_{data_inicio_str or "todos"}_{data_fim_str or "todos"}.xlsx'
    
    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nome_arquivo
    )

@acabamento_pecas_bp.route('/exportar_pdf')
def exportar_pdf():
    """
    Exporta relatório para PDF
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    tanque_id = request.args.get('tanque_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_acabamento(data_inicio=data_inicio, data_fim=data_fim, tanque_id=tanque_id, contrato_id=contrato_id)
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    
    # Buscar nome do tanque e projeto se filtrado
    tanque_nome = None
    if tanque_id:
        tanque = Tanques.query.get(tanque_id)
        tanque_nome = tanque.nome if tanque else None
    
    projeto_nome = None
    if contrato_id:
        contrato = Contrato.query.get(contrato_id)
        projeto_nome = contrato.nome if contrato else None
    
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
    logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
    
    # Calcular total de metros de placas
    total_metros_placas = sum(item.get('metros_placas', 0) for item in dados)
    
    html = render_template(
        'relatorios/acabamento_pecas/pdf.html',
        dados=dados,
        dados_mes=dados_mes,
        dados_semana=dados_semana,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_nome=tanque_nome,
        projeto_nome=projeto_nome,
        total_pecas=len(dados),
        total_metros_placas=round(total_metros_placas, 2),
        logo_path=logo_path_uri,
        data_geracao=datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    )
    
    pdf_bytes = HTML(string=html).write_pdf(
        stylesheets=[CSS(string='''
            @page {
                margin: 2cm;
                size: A4;
            }
            body {
                font-family: Arial, sans-serif;
                font-size: 10pt;
                color: #333;
            }
            .header {
                text-align: center;
                margin-bottom: 20px;
                border-bottom: 2px solid #3a72ab;
                padding-bottom: 10px;
            }
            .logo {
                max-width: 150px;
            }
            .section {
                margin-bottom: 20px;
            }
            .section-title {
                background-color: #3a72ab;
                color: white;
                padding: 8px;
                margin-bottom: 10px;
                font-weight: bold;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 15px;
                font-size: 9pt;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 6px;
                text-align: left;
            }
            th {
                background-color: #f5f5f5;
                font-weight: bold;
            }
            .total-row {
                font-weight: bold;
                background-color: #f8f9fa;
            }
            .footer {
                text-align: center;
                margin-top: 30px;
                font-size: 8pt;
                color: #666;
            }
        ''')]
    )
    
    pdf_io = io.BytesIO(pdf_bytes)
    pdf_io.seek(0)
    
    nome_arquivo = f'relatorio_acabamento_pecas_{data_inicio_str or "todos"}_{data_fim_str or "todos"}.pdf'
    
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=nome_arquivo
    )

