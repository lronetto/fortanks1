from flask import Blueprint, render_template, request, send_file
from datetime import datetime, timedelta
from models.dados_analiticos import DadoAnalitico, PL_RECOP
from models.nota_fiscal import NotaFiscal, CFOPS_VENDA
from models.centro_custo import CentroCusto
from models.plano_conta import PlanoConta
from models.tanque import Tanque
from models.contrato import Contrato
from models.nota_fiscal import NotaFiscalItem
from sqlalchemy import func
from models.database import db
from weasyprint import HTML, CSS
from utils.relatorio_financeiro import dados_relatorio_financeiro
import os
import tempfile
import io
import zipfile
import base64
from models.upload import Upload

relatorio_bp = Blueprint('relatorio', __name__)

@relatorio_bp.route('/semanal')
def relatorio_semanal():
    """
    Gera um relatório semanal com dados de recebimentos, notas emitidas e custos
    """
    # Definir período (última semana)
    data_fim = datetime.now()
    data_inicio = data_fim - timedelta(days=7)
    
    # Buscar recebimentos (plano de conta 118)
    recebimentos = db.session.query(
        CentroCusto.nome,
        func.sum(DadoAnalitico.valor).label('valor')
    ).join(
        DadoAnalitico,
        DadoAnalitico.centro_custo_id == CentroCusto.id  
    ).join(
        PlanoConta,
        PlanoConta.id == DadoAnalitico.plano_conta_id
    ).filter(
        DadoAnalitico.data_pagamento.between(data_inicio, data_fim),
        PlanoConta.codigo.in_(PL_RECOP)
    ).group_by(
        CentroCusto.nome
    ).all()
    
    # Buscar notas emitidas
    notas_emitidas = db.session.query(
        CentroCusto.nome,
        func.count(NotaFiscal.id).label('quantidade'),
        func.sum(NotaFiscal.valor_total).label('valor_total')
    ).join(
        NotaFiscalItem,
        NotaFiscalItem.nf_id == NotaFiscal.id
    ).join(
        Tanque,
        Tanque.item_nf == NotaFiscalItem.codigo
    ).join(
        Contrato,
        Contrato.id == Tanque.contrato_id
    ).join(
        CentroCusto,
        CentroCusto.id == Contrato.centro_custo_id
    ).filter(
        NotaFiscal.data_emissao.between(data_inicio, data_fim),
        NotaFiscal.status_processamento == 'importado'
    ).group_by(
        CentroCusto.nome
    ).all()
    
    # Buscar custos realizados
    custos = db.session.query(
        CentroCusto.nome,
        func.sum(DadoAnalitico.valor).label('valor')
    ).join(
        DadoAnalitico,
        DadoAnalitico.centro_custo_id == CentroCusto.id
    ).filter(
        DadoAnalitico.data_pagamento.between(data_inicio, data_fim),
        DadoAnalitico.debito_credito == 'D'
    ).group_by(
        CentroCusto.nome
    ).all()
    
    # Renderizar template
    html = render_template(
        'relatorios/relatorio_semanal.html',
        data_inicio=data_inicio,
        data_fim=data_fim,
        data_geracao=datetime.now(),
        recebimentos=recebimentos,
        notas_emitidas=notas_emitidas,
        custos=custos
    )
    return html
    
    # Criar arquivo temporário para o PDF
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        # Gerar PDF usando WeasyPrint
        HTML(string=html).write_pdf(
            tmp.name,
            stylesheets=[
                CSS(string='''
                    @page {
                        margin: 2.5cm;
                        size: A4;
                    }
                    body {
                        font-family: Arial, sans-serif;
                        margin: 20px;
                        color: #333;
                    }
                    .header {
                        text-align: center;
                        margin-bottom: 30px;
                    }
                    .logo {
                        max-width: 200px;
                        margin-bottom: 20px;
                    }
                    .section {
                        margin-bottom: 30px;
                    }
                    .section-title {
                        color: #2c3e50;
                        border-bottom: 2px solid #3498db;
                        padding-bottom: 5px;
                        margin-bottom: 15px;
                    }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                        margin-bottom: 20px;
                    }
                    th, td {
                        border: 1px solid #ddd;
                        padding: 8px;
                        text-align: left;
                    }
                    th {
                        background-color: #f5f5f5;
                    }
                    .total-row {
                        font-weight: bold;
                        background-color: #f8f9fa;
                    }
                    .footer {
                        text-align: center;
                        margin-top: 50px;
                        font-size: 12px;
                        color: #666;
                    }
                ''')
            ]
        )
        
        # Enviar arquivo
        return send_file(
            tmp.name,
            as_attachment=True,
            download_name=f'relatorio_semanal_{data_inicio.strftime("%Y%m%d")}_{data_fim.strftime("%Y%m%d")}.pdf',
            mimetype='application/pdf'
        ) 

@relatorio_bp.route('/notas', methods=['GET'])
def relatorio_notas():
    centros_custo = CentroCusto.query.order_by(CentroCusto.codigo).all()
    dados_relatorio = dados_relatorio_financeiro()
    return render_template('relatorios/relatorio_notas.html', relatorio=dados_relatorio, centros_custo=centros_custo)

@relatorio_bp.route('/notas/ajax', methods=['GET'])
def relatorio_notas_ajax():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]
    
    dados_relatorio = dados_relatorio_financeiro(data_inicio=data_inicio_dt, data_fim=data_fim_dt, centro_custo_ids=centro_custo_ids_int if centro_custo_ids_int else None)
    return render_template('relatorios/relatorio_notas_tabela.html', relatorio=dados_relatorio)

@relatorio_bp.route('/notas/exportar', methods=['GET'])
def relatorio_notas_exportar():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]

    # Buscar dados do relatório (notas filtradas)
    dados_relatorio = dados_relatorio_financeiro(data_inicio=data_inicio_dt, data_fim=data_fim_dt, centro_custo_ids=centro_custo_ids_int if centro_custo_ids_int else None)

    notas = db.session.query(NotaFiscal).filter(NotaFiscal.id.in_([d['id'] for d in dados_relatorio])).all()

    # Criar ZIP em memória
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Adicionar XML e PDF de cada nota
        total = 0
        for nota in notas:
            total += nota.valor_total
            # XML
            if nota.xml_data:
                xml_bytes = base64.b64decode(nota.xml_data)
                zipf.writestr(f'NF {nota.numero_nf}.xml', xml_bytes)
            # PDF
            upload = Upload.query.filter_by(pai='NotaFiscal', pai_id=nota.id, tipo=1).first()
            if upload and upload.blob:
                pdf_bytes = base64.b64decode(upload.blob)
                zipf.writestr(f'NF {nota.numero_nf}.pdf', pdf_bytes)
        # Gerar PDF da tabela
            logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
    logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
    html = render_template('relatorios/relatorio_notas_pdf.html', relatorio=dados_relatorio, total=total, now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'), logo_path=logo_path_uri)
    pdf_bytes = HTML(string=html).write_pdf(stylesheets=[CSS(string='body { font-family: Arial, sans-serif;}')])

    zipf.writestr('relatorio_notas.pdf', pdf_bytes)
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='notas_exportadas.zip'
    )
@relatorio_bp.route('/notas/exportar_pdf', methods=['GET'])
def relatorio_notas_exportar_pdf():
    import os
    import io
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]

    # Buscar dados do relatório (notas filtradas)
    dados_relatorio = dados_relatorio_financeiro(data_inicio=data_inicio_dt, data_fim=data_fim_dt, centro_custo_ids=centro_custo_ids_int if centro_custo_ids_int else None)

    notas = db.session.query(NotaFiscal).filter(NotaFiscal.id.in_([d['id'] for d in dados_relatorio])).all()
    # Adicionar XML e PDF de cada nota
    total = 0
    for nota in notas:
        total += nota.valor_total
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
    logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
    html = render_template('relatorios/relatorio_notas_pdf.html', relatorio=dados_relatorio, total=total, now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'), logo_path=logo_path_uri)
    pdf_bytes = HTML(string=html).write_pdf(stylesheets=[CSS(string='body { font-family: Arial, sans-serif;}')])

    pdf_io = io.BytesIO(pdf_bytes)
    pdf_io.seek(0)
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='relatorio_notas.pdf'
    )