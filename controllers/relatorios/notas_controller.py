from flask import Blueprint, render_template, request, send_file
from datetime import datetime, timedelta
from functools import wraps
from flask_login import login_required
from decimal import Decimal

import pandas as pd
from models.centro_custo import CentroCusto
from models.tanque import Tanques
from models.contrato import Contrato
from models.nota_fiscal import NotaFiscal, NotaFiscalItem, CFOPS_VENDA
from models.dados_analiticos import DadoAnalitico
from models.plano_conta import PlanoConta
from sqlalchemy import func, and_
from models.database import db
from weasyprint import HTML, CSS
from controllers.nota_fiscal.services.query_notas import api_get_dados_notas_fiscais
import os
import tempfile
import io
import zipfile
import base64
from models.upload import Upload
import time

notas_bp = Blueprint('relatorios_notas', __name__, url_prefix='/relatorios/notas')

def login_required_decorator(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def _criar_mock_request(data_inicio=None, data_fim=None, centro_custo_ids=None, status_pagamento=None):
    """Cria um objeto MockRequest para usar com api_get_dados_notas_fiscais"""
    class MockRequest:
        def __init__(self):
            self.args = {}
            if data_inicio:
                self.args['data_emissao_inicio'] = data_inicio
            if data_fim:
                self.args['data_emissao_fim'] = data_fim
            if centro_custo_ids:
                # Adicionar centro_custo ao args para o filtro funcionar
                self.args['centro_custo'] = centro_custo_ids
            if status_pagamento:
                self.args['status_pagamento'] = status_pagamento
            self.args['emitente'] = 'Matriz'
            self.args['tipo_operacao'] = 'venda'
        
        def getlist(self, key, default=None):
            """Implementar getlist para compatibilidade"""
            if key in self.args:
                value = self.args[key]
                if isinstance(value, list):
                    return value
                return [value]
            return default or []
    
    return MockRequest()

def _processar_notas_fiscais(query):
    """
    Processa a query de notas fiscais e retorna lista de dicionários no formato esperado.
    A query já retorna:
    - pagamento_column: data de pagamento (datetime.date) ou NULL
    - centro_custo_column: ID do centro de custo ou NULL
    """
    # Executar query e obter IDs das notas
    # Resultado da query: (NotaFiscal, pagamento_column, centro_custo_column, upload_column, ...)
    resultados = query.all()
    nf_ids = [resultado[0].id for resultado in resultados]
    
    if not nf_ids:
        return []
    
    # Buscar todos os itens de nota fiscal relacionados de uma vez (para quantidade e data prevista)
    nf_items_dict = {}
    nf_items_query = db.session.query(NotaFiscalItem, Tanques, Contrato)\
        .join(Tanques, Tanques.item_nf == NotaFiscalItem.codigo)\
        .join(Contrato, Contrato.id == Tanques.contrato_id)\
        .filter(NotaFiscalItem.nf_id.in_(nf_ids))\
        .group_by(NotaFiscalItem.nf_id).all()
    
    for nf_item, tanque, contrato in nf_items_query:
        if nf_item.nf_id not in nf_items_dict:
            nf_items_dict[nf_item.nf_id] = {
                'tanque': tanque,
                'contrato': contrato,
                'quantidade': nf_item.quantidade
            }
        else:
            # Se houver múltiplos itens, somar a quantidade
            nf_items_dict[nf_item.nf_id]['quantidade'] += nf_item.quantidade
    
    # Buscar todos os centros de custo de uma vez (otimização)
    centro_custo_ids_unicos = set()
    for resultado in resultados:
        centro_custo_id = resultado[2]  # centro_custo_column
        if centro_custo_id:
            centro_custo_ids_unicos.add(centro_custo_id)
    
    centros_custo_dict = {}
    if centro_custo_ids_unicos:
        centros_custo_query = db.session.query(CentroCusto)\
            .filter(CentroCusto.id.in_(list(centro_custo_ids_unicos)))\
            .all()
        for cc in centros_custo_query:
            centros_custo_dict[cc.id] = cc.nome
      
    # Processar resultados
    dados_relatorio = []
    nf_processadas = set()  # Para evitar duplicatas
    
    for resultado in resultados:
        nf = resultado[0]  # NotaFiscal
        data_pagamento = resultado[1]  # pagamento_column (data de pagamento ou NULL)
        centro_custo_id = resultado[2]  # centro_custo_column (ID do centro de custo ou NULL)
        
        # Evitar processar a mesma NF múltiplas vezes
        if nf.id in nf_processadas:
            continue
        nf_processadas.add(nf.id)
        
        # Obter dados relacionados
        nf_data = nf_items_dict.get(nf.id, {})
        tanque = nf_data.get('tanque')
        contrato = nf_data.get('contrato')
        quantidade = nf_data.get('quantidade', 0)
        
        # Calcular data prevista
        data_prevista = None
        if tanque and contrato:
            data_prevista = nf.data_emissao + timedelta(days=contrato.prazo_pagamento_mat)
        
        # Buscar centro de custo pelo ID retornado na coluna (já buscado em batch)
        centro_custo_codigo = 'Não definido'
        if centro_custo_id and centro_custo_id in centros_custo_dict:
            centro_custo_codigo = centros_custo_dict[centro_custo_id]
        
        # Usar data_pagamento diretamente da coluna
        pago_str = 'Não'
        if data_pagamento:
            if isinstance(data_pagamento, datetime):
                pago_str = data_pagamento.strftime('%d/%m/%Y')
            elif hasattr(data_pagamento, 'strftime'):
                pago_str = data_pagamento.strftime('%d/%m/%Y')
            else:
                # Se for string ou outro formato, tentar converter
                try:
                    if isinstance(data_pagamento, str):
                        data_pagamento_dt = datetime.strptime(data_pagamento, '%Y-%m-%d')
                        pago_str = data_pagamento_dt.strftime('%d/%m/%Y')
                    else:
                        pago_str = str(data_pagamento)
                except:
                    pago_str = str(data_pagamento) if data_pagamento else 'Não'
        
        if nf.vencimento and nf.vencimento != 'null':
            data_prevista = datetime.strptime(nf.vencimento, '%Y-%m-%d').strftime('%d/%m/%Y')
        else:
            data_prevista = data_prevista.strftime('%d/%m/%Y') if data_prevista else 'Não definido'
        dados_relatorio.append({
            'id': nf.id,
            'Data': nf.data_emissao.strftime('%d/%m/%Y'),
            'Centro de Custo': centro_custo_codigo,
            'Nota Fiscal': nf.numero_nf,
            'Valor': Decimal(nf.valor_total),
            'Quantidade': quantidade,
            'Data Prevista': data_prevista,
            'Pago': pago_str,
            'Status': nf.status_processamento
        })
    
    return dados_relatorio

@notas_bp.route('/', methods=['GET'])
@login_required_decorator
def index():
    """Página principal do relatório de notas fiscais"""
    centros_custo = CentroCusto.query.order_by(CentroCusto.codigo).all()
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]
    
    # Criar um objeto request mock para api_get_dados_notas_fiscais
    #mock_request = _criar_mock_request(data_inicio, data_fim, centro_custo_ids_int if centro_custo_ids_int else None)
    #query = api_get_dados_notas_fiscais(mock_request)
    
    #dados_relatorio = _processar_notas_fiscais(query)
    
    return render_template(
        'relatorios/notas/index.html',
        #relatorio=dados_relatori,
        centros_custo=centros_custo
    )

@notas_bp.route('/api/dados', methods=['GET'])
@login_required_decorator
def api_dados():
    """Endpoint AJAX para buscar dados do relatório"""
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    status_pagamento = request.args.get('status_pagamento')
    
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]
    
    time_start = time.time()
    # Criar um objeto request mock para api_get_dados_notas_fiscais
    mock_request = _criar_mock_request(data_inicio, data_fim, centro_custo_ids_int if centro_custo_ids_int else None, status_pagamento)
    print(f'tempo de criação do mock request: {time.time() - time_start}')
    time_start = time.time()
    query = api_get_dados_notas_fiscais(mock_request)
    print(f'tempo de execução da query: {time.time() - time_start}')
    time_start = time.time()
    dados_relatorio = _processar_notas_fiscais(query)
    print(f'tempo de processamento dos dados: {time.time() - time_start}')
    # Calcular totais por categoria
    total_valor = sum([d['Valor'] if d['Status'] != 'cancelada' else 0 for d in dados_relatorio])
    total_quantidade = sum([d['Quantidade'] if d['Status'] != 'cancelada' else 0 for d in dados_relatorio])
    
    # Calcular quantidade total de placas dos contratos (material)
    query_placas = db.session.query(
        func.sum((Tanques.placas_normais + Tanques.placas_fecho) * Tanques.quantidade)
    ).join(Contrato, Contrato.id == Tanques.contrato_id)
    
    if centro_custo_ids_int:
        query_placas = query_placas.filter(Contrato.centro_custo_id.in_(centro_custo_ids_int))
    
    total_placas_contratos = query_placas.scalar() or 0
    
    # Calcular valores faturados (emitidos)
    valor_faturado = sum([d['Valor'] if d['Status'] != 'cancelada' else 0 for d in dados_relatorio])
    
    # Calcular valores recebidos (pagos)
    valor_recebido = sum([
        d['Valor'] for d in dados_relatorio
        if d['Pago'] != 'Não' and d['Pago'] != 'Não definido' and d['Status'] != 'cancelada'
    ])
    
    # Calcular quantidades de placas recebidas (pagos)
    quantidade_recebida = sum([
        d['Quantidade'] for d in dados_relatorio
        if d['Pago'] != 'Não' and d['Pago'] != 'Não definido' and d['Status'] != 'cancelada'
    ])
    
    # Calcular valores a faturar (emitidos mas não pagos)
    valor_a_faturar = valor_faturado - valor_recebido
    
    # Calcular quantidades a faturar (emitidas mas não pagas)
    quantidade_a_faturar = total_placas_contratos - total_quantidade
    
    # Buscar valores dos contratos separados por material e serviço
    query_contratos_total = db.session.query(func.sum(Contrato.valor_total))
    query_contratos_mat = db.session.query(func.sum(Contrato.valor_mat))
    query_contratos_ser = db.session.query(func.sum(Contrato.valor_ser))
    
    if centro_custo_ids_int:
        query_contratos_total = query_contratos_total.filter(Contrato.centro_custo_id.in_(centro_custo_ids_int))
        query_contratos_mat = query_contratos_mat.filter(Contrato.centro_custo_id.in_(centro_custo_ids_int))
        query_contratos_ser = query_contratos_ser.filter(Contrato.centro_custo_id.in_(centro_custo_ids_int))
    
    valor_total_contratos = query_contratos_total.scalar() or 0
    valor_total_material = query_contratos_mat.scalar() or 0
    valor_total_servico = query_contratos_ser.scalar() or 0
    
    # As notas fiscais são sempre de material, então:
    # Material: valor das notas fiscais
    # Serviço: valor total de serviço dos contratos (não tem notas fiscais)
    valor_material_faturado = valor_faturado  # NFE são sempre material
    valor_servico_faturado = 0  # Serviços não têm notas fiscais
    
    # Calcular valores ainda não faturados
    valor_material_nao_faturado = valor_total_material - valor_material_faturado
    valor_servico_nao_faturado = valor_total_servico - valor_servico_faturado
    
    # Calcular quantidades de placas não faturadas
    quantidade_material_nao_faturada = total_placas_contratos - total_quantidade
    
    # Calcular percentuais para material
    percentual_material_faturado = (valor_material_faturado / valor_total_material * 100) if valor_total_material > 0 else 0
    percentual_material_recebido = (valor_recebido / valor_total_material * 100) if valor_total_material > 0 else 0
    percentual_material_a_faturar = (valor_a_faturar / valor_total_material * 100) if valor_total_material > 0 else 0
    percentual_material_nao_faturado = (valor_material_nao_faturado / valor_total_material * 100) if valor_total_material > 0 else 0
    
    # Calcular percentuais para serviço (sempre 0% faturado pois não há NFE)
    percentual_servico_faturado = 0
    percentual_servico_recebido = 0
    percentual_servico_a_faturar = 0
    percentual_servico_nao_faturado = 100 if valor_total_servico > 0 else 0
    
    return render_template(
        'relatorios/notas/tabela.html',
        relatorio=dados_relatorio,
        total_valor=total_valor if total_valor else 0,
        total_quantidade=total_quantidade if total_quantidade else 0,
        total_placas_contratos=total_placas_contratos,
        quantidade_recebida=quantidade_recebida,
        quantidade_a_faturar=quantidade_a_faturar,
        quantidade_material_nao_faturada=quantidade_material_nao_faturada,
        valor_faturado=valor_faturado,
        valor_recebido=valor_recebido,
        valor_a_faturar=valor_a_faturar,
        valor_total_contratos=valor_total_contratos,
        valor_total_material=valor_total_material,
        valor_total_servico=valor_total_servico,
        valor_material_faturado=valor_material_faturado,
        valor_servico_faturado=valor_servico_faturado,
        valor_material_nao_faturado=valor_material_nao_faturado,
        valor_servico_nao_faturado=valor_servico_nao_faturado,
        percentual_material_faturado=percentual_material_faturado,
        percentual_material_recebido=percentual_material_recebido,
        percentual_material_a_faturar=percentual_material_a_faturar,
        percentual_material_nao_faturado=percentual_material_nao_faturado,
        percentual_servico_faturado=percentual_servico_faturado,
        percentual_servico_recebido=percentual_servico_recebido,
        percentual_servico_a_faturar=percentual_servico_a_faturar,
        percentual_servico_nao_faturado=percentual_servico_nao_faturado
    )

@notas_bp.route('/exportar/zip', methods=['GET'])
@login_required_decorator
def exportar_zip():
    """Exportar relatório em formato ZIP com PDFs e XMLs das notas"""
    tinicio = time.time()
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    status_pagamento = request.args.get('status_pagamento')
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]
    
    # Criar um objeto request mock para api_get_dados_notas_fiscais
    mock_request = _criar_mock_request(data_inicio, data_fim, centro_custo_ids_int if centro_custo_ids_int else None, status_pagamento)
    query = api_get_dados_notas_fiscais(mock_request)
    
    # Buscar dados do relatório (notas filtradas)
    dados_relatorio = _processar_notas_fiscais(query)
    
    # Criar ZIP em memória
    notas = []
    for d in dados_relatorio:
        nota = db.session.query(NotaFiscal, Upload).\
            join(Upload, Upload.pai_id == NotaFiscal.id and Upload.pai == 'NotaFiscal').\
            filter(NotaFiscal.id == d['id'], Upload.tipo == 1).first()
        if nota:
            notas.append(nota)
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Adicionar XML e PDF de cada nota
        total = 0
        for nota in notas:
            total += nota[0].valor_total
            # XML
            if nota[0].xml_data:
                xml_bytes = base64.b64decode(nota[0].xml_data)
                zipf.writestr(f'NF {nota[0].numero_nf}.xml', xml_bytes)
            # PDF
            if nota[1] and nota[1].blob:
                pdf_bytes = base64.b64decode(nota[1].blob)
                zipf.writestr(f'NF {nota[0].numero_nf}.pdf', pdf_bytes)
        
        # Gerar PDF da tabela
        logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
        logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
        html = render_template(
            'relatorios/notas/pdf.html',
            relatorio=dados_relatorio,
            total=total,
            now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            logo_path=logo_path_uri
        )
        pdf_bytes = HTML(string=html).write_pdf(
            stylesheets=[CSS(string='body { font-family: Arial, sans-serif;}')]
        )
        zipf.writestr('relatorio_notas.pdf', pdf_bytes)
        
        # Gerar Excel
        df = _get_dataframe(dados_relatorio)
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, sheet_name='Relatório Financeiro')
        excel_buffer.seek(0)
        zipf.writestr('relatorio_notas.xlsx', excel_buffer.read())
    
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='notas_exportadas.zip'
    )

@notas_bp.route('/exportar/pdf', methods=['GET'])
@login_required_decorator
def exportar_pdf():
    """Exportar relatório em formato PDF"""
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    status_pagamento = request.args.get('status_pagamento')
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]

    # Criar um objeto request mock para api_get_dados_notas_fiscais
    mock_request = _criar_mock_request(data_inicio, data_fim, centro_custo_ids_int if centro_custo_ids_int else None, status_pagamento)
    query = api_get_dados_notas_fiscais(mock_request)
    
    # Buscar dados do relatório (notas filtradas)
    dados_relatorio = _processar_notas_fiscais(query)

    notas = db.session.query(NotaFiscal).filter(
        NotaFiscal.id.in_([d['id'] for d in dados_relatorio])
    ).all()
    
    # Adicionar XML e PDF de cada nota
    total = 0
    for nota in notas:
        total += nota.valor_total
    
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
    logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
    html = render_template(
        'relatorios/notas/pdf.html',
        relatorio=dados_relatorio,
        total=total,
        now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        logo_path=logo_path_uri
    )
    pdf_bytes = HTML(string=html).write_pdf(
        stylesheets=[CSS(string='body { font-family: Arial, sans-serif;}')]
    )

    pdf_io = io.BytesIO(pdf_bytes)
    pdf_io.seek(0)
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='relatorio_notas.pdf'
    )

@notas_bp.route('/exportar/excel', methods=['GET'])
@login_required_decorator
def exportar_excel():
    """Exportar relatório em formato Excel"""
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    status_pagamento = request.args.get('status_pagamento')
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]

    # Criar um objeto request mock para api_get_dados_notas_fiscais
    mock_request = _criar_mock_request(data_inicio, data_fim, centro_custo_ids_int if centro_custo_ids_int else None, status_pagamento)
    query = api_get_dados_notas_fiscais(mock_request)
    
    dados_relatorio = _processar_notas_fiscais(query)

    df = _get_dataframe(dados_relatorio)
    
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Relatório Financeiro')
    excel_buffer.seek(0)

    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='relatorio_notas.xlsx'
    )

def _get_dataframe(dados_relatorio):
    """Helper function para criar DataFrame do relatório"""
    df = pd.DataFrame(dados_relatorio)
    # Ordenar por data de emissão
    df['Valor'] = df['Valor'].apply(
        lambda x: 'R$ ' + '{:,.2f}'.format(x).replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    df['Quantidade'] = df['Quantidade'].apply(lambda x: int(x))
    df.rename(columns={
        'Data Prevista': 'VENCIMENTO',
        'Data': 'DATA EMISSÃO',
        'Nota Fiscal': 'NF',
        'Quantidade': 'QTDE DE PLACA',
        'Valor': 'VALOR',
        'Status': 'STATUS',
        'Pago': 'PAGO'
    }, inplace=True)

    return df[['DATA EMISSÃO', 'NF', 'QTDE DE PLACA', 'VALOR', 'STATUS', 'VENCIMENTO', 'PAGO']]

