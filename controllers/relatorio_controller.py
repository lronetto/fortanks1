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
import os
import tempfile

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