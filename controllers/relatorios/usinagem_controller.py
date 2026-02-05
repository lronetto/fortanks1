from flask import Blueprint, render_template, request, send_file, jsonify
from models.concreto import ConcretoUsinagens
from models.database import db
from datetime import datetime, timedelta
import pandas as pd
import io
from weasyprint import HTML, CSS
import os

usinagem_bp = Blueprint('relatorios_usinagem', __name__, url_prefix='/relatorios/usinagem')

def get_dados_usinagem(data_inicio=None, data_fim=None):
    """
    Busca dados de usinagem com filtros opcionais
    """
    query = ConcretoUsinagens.query
    
    # Filtrar apenas usinagens com data_usinagem
    query = query.filter(ConcretoUsinagens.data_usinagem.isnot(None))
    
    usinagens = query.order_by(ConcretoUsinagens.data_usinagem).all()
    
    dados = []
    for usinagem in usinagens:
        if not usinagem.data_usinagem:
            continue
            
        try:
            # Converter data_usinagem para date
            if isinstance(usinagem.data_usinagem, datetime):
                data_usinagem = usinagem.data_usinagem.date()
            else:
                data_usinagem = usinagem.data_usinagem
            
            # Aplicar filtro de data se fornecido
            if data_inicio and data_usinagem < data_inicio:
                continue
            if data_fim and data_usinagem > data_fim:
                continue
            
            # Obter volume
            volume = float(usinagem.volume) if usinagem.volume else 0.0
            
            dados.append({
                'id': usinagem.id,
                'serie': usinagem.serie,
                'data_usinagem': data_usinagem,
                'volume': volume,
                'produto_composto_nome': usinagem.produto_composto.nome if usinagem.produto_composto else 'N/A',
                'flow': usinagem.flow or 'N/A',
                'nota': usinagem.nota or 'N/A'
            })
        except (ValueError, TypeError) as e:
            continue
    
    return dados

def agrupar_por_mes(dados):
    """
    Agrupa dados de usinagem por mês
    """
    agrupado = {}
    
    for item in dados:
        data = item['data_usinagem']
        chave = f"{data.year}-{data.month:02d}"
        
        if chave not in agrupado:
            agrupado[chave] = {
                'mes': data.month,
                'ano': data.year,
                'quantidade': 0,
                'volume': 0.0,
                'usinagens': []
            }
        
        agrupado[chave]['quantidade'] += 1
        agrupado[chave]['volume'] += item.get('volume', 0)
        agrupado[chave]['usinagens'].append(item)
    
    # Ordenar por data
    return dict(sorted(agrupado.items()))

def agrupar_por_semana(dados):
    """
    Agrupa dados de usinagem por semana
    """
    agrupado = {}
    
    for item in dados:
        data = item['data_usinagem']
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
                'volume': 0.0,
                'usinagens': []
            }
        
        agrupado[chave]['quantidade'] += 1
        agrupado[chave]['volume'] += item.get('volume', 0)
        agrupado[chave]['usinagens'].append(item)
    
    # Ordenar por data
    return dict(sorted(agrupado.items()))

@usinagem_bp.route('/relatorio')
def index():
    """
    Página principal do relatório de usinagem
    """
    # Filtros padrão: últimos 6 meses
    data_fim = datetime.now().date()
    data_inicio = (data_fim - timedelta(days=180))
    
    # Obter filtros da requisição
    data_inicio_str = request.args.get('data_inicio', data_inicio.strftime('%Y-%m-%d'))
    data_fim_str = request.args.get('data_fim', data_fim.strftime('%Y-%m-%d'))
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
    except ValueError:
        data_inicio = (datetime.now().date() - timedelta(days=180))
        data_fim = datetime.now().date()
    
    # Buscar dados
    dados = get_dados_usinagem(data_inicio=data_inicio, data_fim=data_fim)
    
    # Agrupar dados
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    
    # Preparar dados para gráficos
    labels_mes = [f"{v['mes']:02d}/{v['ano']}" for v in dados_mes.values()]
    valores_mes = [v['quantidade'] for v in dados_mes.values()]
    volume_mes = [round(v.get('volume', 0), 2) for v in dados_mes.values()]
    
    labels_semana = [f"Sem {v['semana']}/{v['ano']}" for v in dados_semana.values()]
    valores_semana = [v['quantidade'] for v in dados_semana.values()]
    volume_semana = [round(v.get('volume', 0), 2) for v in dados_semana.values()]
    
    # Calcular total de volume
    total_volume = sum(item.get('volume', 0) for item in dados)
    
    return render_template(
        'relatorios/usinagem/relatorio.html',
        dados_mes=dados_mes,
        dados_semana=dados_semana,
        labels_mes=labels_mes,
        valores_mes=valores_mes,
        volume_mes=volume_mes,
        labels_semana=labels_semana,
        valores_semana=valores_semana,
        volume_semana=volume_semana,
        data_inicio=data_inicio,
        data_fim=data_fim,
        total_usinagens=len(dados),
        total_volume=round(total_volume, 2)
    )

@usinagem_bp.route('/api/dados')
def api_dados():
    """
    API para retornar dados do relatório em JSON (para gráficos e tabelas)
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_usinagem(data_inicio=data_inicio, data_fim=data_fim)
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    
    # Preparar dados das tabelas
    resumo_mes = []
    for chave, valor in dados_mes.items():
        resumo_mes.append({
            'mes_ano': f"{valor['mes']:02d}/{valor['ano']}",
            'mes': valor['mes'],
            'ano': valor['ano'],
            'quantidade': valor['quantidade'],
            'volume': round(valor.get('volume', 0), 2)
        })
    
    resumo_semana = []
    for chave, valor in dados_semana.items():
        resumo_semana.append({
            'semana': f"Sem {valor['semana']}/{valor['ano']}",
            'semana_num': valor['semana'],
            'ano': valor['ano'],
            'inicio': valor['inicio_semana'].strftime('%d/%m/%Y'),
            'fim': valor['fim_semana'].strftime('%d/%m/%Y'),
            'quantidade': valor['quantidade'],
            'volume': round(valor.get('volume', 0), 2)
        })
    
    # Calcular total de volume
    total_volume = sum(item.get('volume', 0) for item in dados)
    
    return jsonify({
        'mes': {
            'labels': [f"{v['mes']:02d}/{v['ano']}" for v in dados_mes.values()],
            'valores': [v['quantidade'] for v in dados_mes.values()],
            'volume': [round(v.get('volume', 0), 2) for v in dados_mes.values()]
        },
        'semana': {
            'labels': [f"Sem {v['semana']}/{v['ano']}" for v in dados_semana.values()],
            'valores': [v['quantidade'] for v in dados_semana.values()],
            'volume': [round(v.get('volume', 0), 2) for v in dados_semana.values()]
        },
        'resumo_mes': resumo_mes,
        'resumo_semana': resumo_semana,
        'total': len(dados),
        'total_volume': round(total_volume, 2),
        'data_inicio': data_inicio_str,
        'data_fim': data_fim_str
    })

@usinagem_bp.route('/exportar_excel')
def exportar_excel():
    """
    Exporta relatório para Excel
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_usinagem(data_inicio=data_inicio, data_fim=data_fim)
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    
    # Preparar dados para Excel
    excel_data = []
    
    # Aba 1: Detalhamento por usinagem
    for item in dados:
        excel_data.append({
            'Data Usinagem': item['data_usinagem'].strftime('%d/%m/%Y'),
            'Série': item['serie'],
            'Volume (m³)': round(item.get('volume', 0), 2),
            'Produto Composto': item.get('produto_composto_nome', 'N/A'),
            'Flow': item.get('flow', 'N/A'),
            'Nota': item.get('nota', 'N/A')
        })
    
    df_detalhes = pd.DataFrame(excel_data)
    
    # Aba 2: Resumo por mês
    resumo_mes = []
    for chave, valor in dados_mes.items():
        resumo_mes.append({
            'Mês/Ano': f"{valor['mes']:02d}/{valor['ano']}",
            'Quantidade': valor['quantidade'],
            'Volume (m³)': round(valor.get('volume', 0), 2)
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
            'Volume (m³)': round(valor.get('volume', 0), 2)
        })
    df_semana = pd.DataFrame(resumo_semana)
    
    # Criar arquivo Excel em memória
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df_detalhes.to_excel(writer, index=False, sheet_name='Detalhamento')
        df_mes.to_excel(writer, index=False, sheet_name='Resumo Mensal')
        df_semana.to_excel(writer, index=False, sheet_name='Resumo Semanal')
    
    excel_buffer.seek(0)
    
    nome_arquivo = f'relatorio_usinagem_{data_inicio_str or "todos"}_{data_fim_str or "todos"}.xlsx'
    
    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nome_arquivo
    )

@usinagem_bp.route('/exportar_pdf')
def exportar_pdf():
    """
    Exporta relatório para PDF
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_usinagem(data_inicio=data_inicio, data_fim=data_fim)
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
    logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
    
    # Calcular total de volume
    total_volume = sum(item.get('volume', 0) for item in dados)
    
    html = render_template(
        'relatorios/usinagem/pdf.html',
        dados=dados,
        dados_mes=dados_mes,
        dados_semana=dados_semana,
        data_inicio=data_inicio,
        data_fim=data_fim,
        total_usinagens=len(dados),
        total_volume=round(total_volume, 2),
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
    
    nome_arquivo = f'relatorio_usinagem_{data_inicio_str or "todos"}_{data_fim_str or "todos"}.pdf'
    
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=nome_arquivo
    )
