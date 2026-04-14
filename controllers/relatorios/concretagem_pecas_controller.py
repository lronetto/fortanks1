from flask import Blueprint, render_template, request, send_file, jsonify
from models.tanque import TanquesPecas, Tanques, TanquesGrupos, tanques_grupos
from models.contrato import Contrato
from models.concreto import ConcretoConcretagens, ConcretoConcretagensTanques
from models.database import db
from datetime import datetime, timedelta

from controllers.cronograma.matriz_routes import ler_indices_simulacao_sessao
from utils.concretagem_previsto_cronograma import pecas_previsto_por_mes_alinhado
import json
import pandas as pd
import io
from weasyprint import HTML, CSS
import os

concretagem_pecas_bp = Blueprint('relatorios_concretagem_pecas', __name__, url_prefix='/relatorios/concretagem-pecas')

def get_dados_concretagem(data_inicio=None, data_fim=None, tanque_id=None, contrato_id=None, grupo_id=None):
    """
    Busca dados de concretagem de peças com filtros opcionais
    """
    query = TanquesPecas.query.join(Tanques)
    
    # Aplicar filtros
    if grupo_id:
        query = query.join(
            tanques_grupos,
            tanques_grupos.c.tanque_id == TanquesPecas.tanque_id,
        ).filter(tanques_grupos.c.grupo_id == grupo_id)
        query = query.distinct()

    if tanque_id:
        query = query.filter(TanquesPecas.tanque_id == tanque_id)
    
    if contrato_id:
        query = query.filter(Tanques.contrato_id == contrato_id)
    
    # Filtrar apenas peças com data_concretagem
    query = query.filter(TanquesPecas.data_concretagem.isnot(None))
    
    pecas = query.all()
    
    dados = []
    for peca in pecas:
        if not peca.data_concretagem:
            continue
            
        try:
            # Converter data_concretagem para date
            if isinstance(peca.data_concretagem, datetime):
                data_concretagem = peca.data_concretagem.date()
            else:
                data_concretagem = peca.data_concretagem
            
            # Aplicar filtro de data se fornecido
            if data_inicio and data_concretagem < data_inicio:
                continue
            if data_fim and data_concretagem > data_fim:
                continue
            
            # Buscar pista do campo qualidade
            pista = None
            qualidade = peca.qualidade or '{}'
            qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
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
                'data_concretagem': data_concretagem,
                'pista': pista,
                'tipo': peca.tipo,
                'metros_placas': metros_placas
            })
        except (ValueError, TypeError) as e:
            continue
    
    return dados

def agrupar_por_mes(dados):
    """
    Agrupa dados de concretagem por mês
    """
    agrupado = {}
    
    for item in dados:
        data = item['data_concretagem']
        pista = item.get('pista', '')
        chave = f"{data.year}-{data.month:02d}"
        
        if chave not in agrupado:
            agrupado[chave] = {
                'mes': data.month,
                'ano': data.year,
                'quantidade': 0,
                'quantidade_concretagens': 0,
                'metros_placas': 0.0,
                'pecas': [],
                'concretagens_unicas': set()  # Conjunto para rastrear concretagens únicas deste mês
            }
        
        agrupado[chave]['quantidade'] += 1
        agrupado[chave]['metros_placas'] += item.get('metros_placas', 0)
        agrupado[chave]['pecas'].append(item)
        
        # Contar concretagem única (data + pista)
        chave_concretagem = f"{data.isoformat()}_{pista}"
        if chave_concretagem not in agrupado[chave]['concretagens_unicas']:
            agrupado[chave]['concretagens_unicas'].add(chave_concretagem)
            agrupado[chave]['quantidade_concretagens'] += 1
       # print(chave_concretagem)
       # print(chave)
    # Converter sets para contagem e remover do dicionário
    for chave in agrupado:
        if 'concretagens_unicas' in agrupado[chave]:
            del agrupado[chave]['concretagens_unicas']
    
    # Ordenar por data
    return dict(sorted(agrupado.items()))

def agrupar_por_semana(dados):
    """
    Agrupa dados de concretagem por semana
    """
    agrupado = {}
    
    for item in dados:
        data = item['data_concretagem']
        pista = item.get('pista', '')
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
                'quantidade_concretagens': 0,
                'metros_placas': 0.0,
                'pecas': [],
                'concretagens_unicas': set()  # Conjunto para rastrear concretagens únicas desta semana
            }
        
        agrupado[chave]['quantidade'] += 1
        agrupado[chave]['metros_placas'] += item.get('metros_placas', 0)
        agrupado[chave]['pecas'].append(item)
        
        # Contar concretagem única (data + pista)
        chave_concretagem = f"{data.isoformat()}_{pista}"
        if chave_concretagem not in agrupado[chave]['concretagens_unicas']:
            agrupado[chave]['concretagens_unicas'].add(chave_concretagem)
            agrupado[chave]['quantidade_concretagens'] += 1
    
    # Converter sets para contagem e remover do dicionário
    for chave in agrupado:
        if 'concretagens_unicas' in agrupado[chave]:
            del agrupado[chave]['concretagens_unicas']
    
    # Ordenar por data
    return dict(sorted(agrupado.items()))

@concretagem_pecas_bp.route('/')
def index():
    """
    Página principal do relatório de concretagem de peças
    """
    # Filtros padrão: últimos 6 meses
    data_fim = datetime.now().date()
    data_inicio = (data_fim - timedelta(days=180))
    
    # Obter filtros da requisição
    data_inicio_str = request.args.get('data_inicio', data_inicio.strftime('%Y-%m-%d'))
    data_fim_str = request.args.get('data_fim', data_fim.strftime('%Y-%m-%d'))
    tanque_id = request.args.get('tanque_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
    except ValueError:
        data_inicio = (datetime.now().date() - timedelta(days=180))
        data_fim = datetime.now().date()
    
    # Buscar dados
    dados = get_dados_concretagem(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
        grupo_id=grupo_id,
    )
    
    # Agrupar dados
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    
    # Preparar dados para gráficos
    labels_mes = [f"{v['mes']:02d}/{v['ano']}" for v in dados_mes.values()]
    valores_mes = [v['quantidade'] for v in dados_mes.values()]
    if contrato_id and dados_mes:
        try:
            valores_previsto_mes = pecas_previsto_por_mes_alinhado(
                contrato_id,
                data_inicio,
                data_fim,
                dados_mes,
                tanque_id=tanque_id,
                grupo_id=grupo_id,
                indices_por_tanque=ler_indices_simulacao_sessao(contrato_id),
            )
        except Exception:
            valores_previsto_mes = [0.0] * len(valores_mes)
    else:
        valores_previsto_mes = [0.0] * len(valores_mes)
    valores_concretagens_mes = [v.get('quantidade_concretagens', 0) for v in dados_mes.values()]
    metros_placas_mes = [round(v.get('metros_placas', 0), 2) for v in dados_mes.values()]
    
    labels_semana = [f"Sem {v['semana']}/{v['ano']}" for v in dados_semana.values()]
    valores_semana = [v['quantidade'] for v in dados_semana.values()]
    valores_concretagens_semana = [v.get('quantidade_concretagens', 0) for v in dados_semana.values()]
    metros_placas_semana = [round(v.get('metros_placas', 0), 2) for v in dados_semana.values()]
    
    # Calcular total de metros de placas
    total_metros_placas = sum(item.get('metros_placas', 0) for item in dados)
    
    # Buscar tanques para filtro (filtrados por projeto e/ou grupo se selecionados)
    q_tanques = Tanques.query
    if contrato_id:
        q_tanques = q_tanques.filter(Tanques.contrato_id == contrato_id)
    if grupo_id:
        q_tanques = q_tanques.join(
            tanques_grupos,
            tanques_grupos.c.tanque_id == Tanques.id,
        ).filter(tanques_grupos.c.grupo_id == grupo_id)
    tanques = q_tanques.order_by(Tanques.nome).all()
    if contrato_id:
        tanques = [t for t in tanques if t.contrato and t.contrato.ativo]
    else:
        tanques = [t for t in tanques if not t.contrato or t.contrato.ativo]
        if not grupo_id:
            tanques.sort(key=lambda x: x.nome)
    
    contratos = Contrato.query.filter(Contrato.ativo == True).order_by(Contrato.nome).all()
    grupos = TanquesGrupos.get_all()
    
    # Calcular total de concretagens únicas
    concretagens_unicas = set()
    for item in dados:
        data = item['data_concretagem']
        pista = item.get('pista', '')
        chave_concretagem = f"{data.isoformat()}_{pista}"
        concretagens_unicas.add(chave_concretagem)
    total_concretagens = len(concretagens_unicas)
    
    return render_template(
        'relatorios/concretagem_cadastros/pecas/index.html',
        dados_mes=dados_mes,
        dados_semana=dados_semana,
        labels_mes=labels_mes,
        valores_mes=valores_mes,
        valores_previsto_mes=valores_previsto_mes,
        valores_concretagens_mes=valores_concretagens_mes,
        metros_placas_mes=metros_placas_mes,
        labels_semana=labels_semana,
        valores_semana=valores_semana,
        valores_concretagens_semana=valores_concretagens_semana,
        metros_placas_semana=metros_placas_semana,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
        grupo_id=grupo_id,
        tanques=tanques,
        contratos=contratos,
        grupos=grupos,
        total_pecas=len(dados),
        total_concretagens=total_concretagens,
        total_metros_placas=round(total_metros_placas, 2)
    )

@concretagem_pecas_bp.route('/api/tanques-por-projeto')
def api_tanques_por_projeto():
    """
    API para retornar tanques filtrados por projeto (contrato)
    """
    contrato_id = request.args.get('contrato_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)

    q = Tanques.query
    if contrato_id:
        q = q.filter(Tanques.contrato_id == contrato_id)
    if grupo_id:
        q = q.join(
            tanques_grupos,
            tanques_grupos.c.tanque_id == Tanques.id,
        ).filter(tanques_grupos.c.grupo_id == grupo_id)
    tanques = q.order_by(Tanques.nome).all()
    
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

@concretagem_pecas_bp.route('/api/dados')
def api_dados():
    """
    API para retornar dados do relatório em JSON (para gráficos e tabelas)
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    tanque_id = request.args.get('tanque_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_concretagem(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
        grupo_id=grupo_id,
    )
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)

    valores_mes_api = [v['quantidade'] for v in dados_mes.values()]
    if contrato_id and dados_mes and data_inicio is not None and data_fim is not None:
        try:
            previsto_mes_api = pecas_previsto_por_mes_alinhado(
                contrato_id,
                data_inicio,
                data_fim,
                dados_mes,
                tanque_id=tanque_id,
                grupo_id=grupo_id,
                indices_por_tanque=ler_indices_simulacao_sessao(contrato_id),
            )
        except Exception:
            previsto_mes_api = [0.0] * len(valores_mes_api)
    else:
        previsto_mes_api = [0.0] * len(valores_mes_api)

    # Preparar dados das tabelas
    resumo_mes = []
    for chave, valor in dados_mes.items():
        resumo_mes.append({
            'mes_ano': f"{valor['mes']:02d}/{valor['ano']}",
            'mes': valor['mes'],
            'ano': valor['ano'],
            'quantidade': valor['quantidade'],
            'quantidade_concretagens': valor.get('quantidade_concretagens', 0),
            'metros_placas': round(valor.get('metros_placas', 0), 2)
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
            'quantidade_concretagens': valor.get('quantidade_concretagens', 0),
            'metros_placas': round(valor.get('metros_placas', 0), 2)
        })
    
    # Calcular total de metros de placas
    total_metros_placas = sum(item.get('metros_placas', 0) for item in dados)
    
    # Calcular total de concretagens únicas
    concretagens_unicas = set()
    for item in dados:
        data = item['data_concretagem']
        pista = item.get('pista', '')
        chave_concretagem = f"{data.isoformat()}_{pista}"
        concretagens_unicas.add(chave_concretagem)
    total_concretagens = len(concretagens_unicas)
    
    return jsonify({
        'mes': {
            'labels': [f"{v['mes']:02d}/{v['ano']}" for v in dados_mes.values()],
            'valores': valores_mes_api,
            'previsto': previsto_mes_api,
            'concretagens': [v.get('quantidade_concretagens', 0) for v in dados_mes.values()],
            'metros_placas': [round(v.get('metros_placas', 0), 2) for v in dados_mes.values()]
        },
        'semana': {
            'labels': [f"Sem {v['semana']}/{v['ano']}" for v in dados_semana.values()],
            'valores': [v['quantidade'] for v in dados_semana.values()],
            'concretagens': [v.get('quantidade_concretagens', 0) for v in dados_semana.values()],
            'metros_placas': [round(v.get('metros_placas', 0), 2) for v in dados_semana.values()]
        },
        'resumo_mes': resumo_mes,
        'resumo_semana': resumo_semana,
        'total': len(dados),
        'total_concretagens': total_concretagens,
        'total_metros_placas': round(total_metros_placas, 2),
        'data_inicio': data_inicio_str,
        'data_fim': data_fim_str
    })

@concretagem_pecas_bp.route('/exportar_excel')
def exportar_excel():
    """
    Exporta relatório para Excel
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    tanque_id = request.args.get('tanque_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_concretagem(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
        grupo_id=grupo_id,
    )
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    
    # Preparar dados para Excel
    excel_data = []
    
    # Aba 1: Detalhamento por peça
    for item in dados:
        excel_data.append({
            'Data Concretagem': item['data_concretagem'].strftime('%d/%m/%Y'),
            'Projeto': item.get('contrato_nome', ''),
            'Tanque': item['tanque_nome'],
            'Peça': item['nome'],
            'Número Sequencial': item['numero_sequencial'],
            'Tipo': item['tipo'],
            'Metros de Placas': round(item.get('metros_placas', 0), 2)
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
    
    nome_arquivo = f'relatorio_concretagem_pecas_{data_inicio_str or "todos"}_{data_fim_str or "todos"}.xlsx'
    
    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nome_arquivo
    )

@concretagem_pecas_bp.route('/exportar_pdf')
def exportar_pdf():
    """
    Exporta relatório para PDF
    """
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    tanque_id = request.args.get('tanque_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        data_inicio = None
        data_fim = None
    
    dados = get_dados_concretagem(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
        grupo_id=grupo_id,
    )
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

    grupo_nome = None
    if grupo_id:
        g = TanquesGrupos.query.get(grupo_id)
        grupo_nome = g.nome if g else None
    
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
    logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
    
    # Calcular total de metros de placas
    total_metros_placas = sum(item.get('metros_placas', 0) for item in dados)
    
    html = render_template(
        'relatorios/concretagem_cadastros/pecas/pdf.html',
        dados=dados,
        dados_mes=dados_mes,
        dados_semana=dados_semana,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_nome=tanque_nome,
        projeto_nome=projeto_nome,
        grupo_nome=grupo_nome,
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
    
    nome_arquivo = f'relatorio_concretagem_pecas_{data_inicio_str or "todos"}_{data_fim_str or "todos"}.pdf'
    
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=nome_arquivo
    )

