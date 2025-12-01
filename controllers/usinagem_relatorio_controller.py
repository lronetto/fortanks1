from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, make_response
from flask_login import login_required, current_user
from models import UsinagemConcreto, TracoConcreto, ItemTracoConcreto, RompimentoCorpoProva, Contrato, Cliente
from models import Concretagem, ConcretagemTanque, Tanque, Peca
from datetime import datetime
import io
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from sqlalchemy import or_

# Criar o blueprint
relatorio_usinagem_bp = Blueprint('relatorio_usinagem', __name__, url_prefix='/relatorios-usinagem')

@relatorio_usinagem_bp.route('/')
@login_required
def index():
    """Página inicial do módulo de relatórios de usinagem"""
    contratos = Contrato.query.order_by(Contrato.nome).all()
    return render_template('relatorios/usinagem/index.html', contratos=contratos)

@relatorio_usinagem_bp.route('/por-contrato/<int:contrato_id>')
@login_required
def por_contrato(contrato_id):
    """Lista as usinagens relacionadas a um contrato específico"""
    contrato = Contrato.query.get_or_404(contrato_id)
    
    # Buscar concretagens relacionadas ao contrato (através do centro de custo)
    concretagens = Concretagem.query.join(ConcretagemTanque).join(Tanque).join(Contrato).filter(
        Contrato.id == contrato_id
    ).distinct().order_by(Concretagem.data_concretagem.desc()).all()
    
    # Buscar usinagens relacionadas às concretagens
    usinagens_ids = []
    for concretagem in concretagens:
        for cp in concretagem.pecas_associadas:
            if cp.usinagem_id and cp.usinagem_id not in usinagens_ids:
                usinagens_ids.append(cp.usinagem_id)
    
    usinagens = UsinagemConcreto.query.filter(UsinagemConcreto.id.in_(usinagens_ids)).all()
    
    return render_template('relatorios/usinagem/por_contrato.html', 
                          contrato=contrato,
                          usinagens=usinagens,
                          concretagens=concretagens)

@relatorio_usinagem_bp.route('/ficha-moldagem-rompimento/<int:usinagem_id>')
@login_required
def ficha_moldagem_rompimento(usinagem_id):
    """Gera uma ficha de moldagem e rompimento de corpo de prova para uma usinagem específica"""
    usinagem = UsinagemConcreto.query.get_or_404(usinagem_id)
    
    # Buscar concretagem relacionada a esta usinagem
    concretagem = Concretagem.query.join(ConcretagemPeca).filter(
        ConcretagemPeca.usinagem_id == usinagem_id
    ).first()
    
    if not concretagem:
        flash('Não foi encontrada concretagem relacionada a esta usinagem', 'warning')
        return redirect(url_for('relatorio_usinagem.index'))
    
    # Buscar rompimentos desta usinagem
    rompimentos = RompimentoCorpoProva.query.filter_by(usinagem_id=usinagem_id).order_by(
        RompimentoCorpoProva.numero_cp
    ).all()
    
    # Buscar traço relacionado
    traco = usinagem.traco
    
    # Buscar tanque relacionado à concretagem
    tanque = None
    if concretagem and concretagem.tanques_associados:
        # Pegar o primeiro tanque associado para simplificar
        tanque = concretagem.tanques[0] if concretagem.tanques else None
    
    return render_template('relatorios/usinagem/ficha_moldagem_rompimento.html',
                          usinagem=usinagem,
                          concretagem=concretagem,
                          rompimentos=rompimentos,
                          traco=traco,
                          tanque=tanque)

@relatorio_usinagem_bp.route('/ficha-moldagem-rompimento-pdf/<int:usinagem_id>')
@login_required
def ficha_moldagem_rompimento_pdf(usinagem_id):
    """Gera um PDF da ficha de moldagem e rompimento para uma usinagem específica, filtrando por tanque se fornecido"""
    usinagem = UsinagemConcreto.query.get_or_404(usinagem_id)
    concretagem = Concretagem.query.join(ConcretagemPeca).filter(
        ConcretagemPeca.usinagem_id == usinagem_id,
    ).first()
    if not concretagem:
        flash('Não foi encontrada concretagem relacionada a esta usinagem', 'warning')
        return redirect(url_for('relatorio_usinagem.index'))
    tanque_id = request.args.get('tanque_id', type=int)
    print(tanque_id)
    tanques = concretagem.tanques
    if tanque_id:
        tanque = next((t for t in tanques if t.id == tanque_id), None)
    else:
        tanque = None  # Para exibir todos os tanques/agregado
    rompimentos = RompimentoCorpoProva.query.filter_by(usinagem_id=usinagem_id).order_by(
        RompimentoCorpoProva.numero_cp
    ).all()
    traco = usinagem.traco
    cliente = None
    obra = None
    if tanque:
        if tanque.contrato_id:
            contrato = tanque.contrato
            if contrato and contrato.cliente_final_id:
                cliente = Cliente.query.get(contrato.cliente_final_id)
            obra = f"{tanque.nome}"
    elif tanques:
        # Se for todos, pegar o primeiro para exibir cliente/obra genérico
        t = tanques[0]
        if t.contrato_id:
            contrato = t.contrato
            if contrato and contrato.cliente_final_id:
                cliente = Cliente.query.get(contrato.cliente_final_id)
            obra = f"{t.nome} (e outros)"
    # Criar PDF na memória
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        alignment=TA_CENTER,
        fontSize=12,
        spaceAfter=12
    )
    
    # Lista de elementos a serem adicionados ao PDF
    elements = []
    
    # Cabeçalho
    logo=Image(os.path.join(os.path.dirname(__file__), '..', 'static', 'img', 'logo.png'), width=80, height=30)
    header_data = [
        [logo, 'FICHA DE MOLDAGEM E ROMPIMENTO DE CONCRETO', f'FMRC Nº: {usinagem.id}'],
        ['', f'CLIENTE: {cliente.nome if cliente else "Não especificado"}', ''],
        ['', f'OBRA: {obra if obra else "Não especificada"}', '']
    ]
    
    header_table = Table(header_data, rowHeights=[0.6*cm,0.5*cm,0.5*cm],colWidths=[doc.width*0.2, doc.width*0.68, doc.width*0.12])
    header_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (1, 0), (1, 0), 'Times-Bold'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('FONTSIZE', (1, 0), (1, 0), 10),
        ('SPAN', (0, 0), (0, 2)),
        ('SPAN', (1, 1), (2, 1)),
        ('SPAN', (1, 2), (2, 2)),
        
       
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.5*cm))
    tipo_concreto = "fck>= 40 MPa 28 Dias" 
    traco_concreto = "FTK 40"
    restricoes = "fck>=15,0 MPa P/ DESPROTENÇÂO"
    spec_data = [
        ['ESPECIFICAÇÃO DO CONCRETO', '', '', '', '', '', ''],
        ['TIPO DO CONCRETO:', tipo_concreto, 'TRAÇO:', traco_concreto, '', '', ''],
        ['RESTRIÇÂO:', restricoes, '', '', '', '', ''],
        ['', '', '', '', '', '', ''],
        ['', '', '', '', '', '', ''],
        ['', '', '', '', '', '', ''],
        ['', '', '', '', '', '', '']
    ]
    
    spec_table = Table(spec_data,rowHeights=[0.5*cm,
                                             0.5*cm,
                                             0.5*cm,
                                             0.5*cm,
                                             0.5*cm,
                                             0.5*cm,
                                             0.5*cm],colWidths=[doc.width*0.2, 
                                                                doc.width*0.3, 
                                                                doc.width*0.1, 
                                                                doc.width*0.1, 
                                                                doc.width*0.1, 
                                                                doc.width*0.1, 
                                                                doc.width*0.2])
    spec_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (0, 0), 'Times-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 10),
        ('SPAN', (0, 0), (-1, 0)),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
    ]))
    elements.append(spec_table)
    elements.append(Spacer(1, 0.5*cm))
    
    
    # Data formatada
    data_usinagem = usinagem.data_usinagem.strftime('%d/%m/%Y')
    horario_saida = usinagem.data_usinagem.strftime('%H:%M')
    
    receb_data = [
        ['RECEBIMENTO DO CONCRETO / MOLDAGEM (NBR 5738 / 2015)'],
        ['CONCRETEIRA', 'FORTANKS', 'DATA:', data_usinagem, 'NOTA FISCAL:', f'{usinagem.nota}'],
        ['SAÍDA DA USINA:', horario_saida,'N. CAMINHÃO:', usinagem.nbt],
        ['', '', '', '', '', '', ''],
        ['', '', '', '', '', '', ''],
        ['', '', '', '', '', '', ''],
        ['', '', '', '', '', '', ''],
        ['', '', '', '', '', '', ''],
        
        
    ]
    
    receb_table = Table(receb_data,colWidths=[doc.width*0.2, 
                                              doc.width*0.2, 
                                              doc.width*0.13, 
                                              doc.width*0.10, 
                                              doc.width*0.12, 
                                              doc.width*0.1, 
                                              doc.width*0.2])
    receb_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (0, 0), 'Times-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 10),
        ('SPAN', (0, 0), (-1, 0)),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
    ]))
    elements.append(receb_table)
    
    elements.append(Spacer(1, 0.5*cm))
    pcstxt = ""
    for peca in concretagem.pecas:
        pcstxt += f"P{peca.nome} / "
    peca_data = [
        ['PEÇA CONCRETADA'],
        [pcstxt]
    ]
    
    peca_table = Table(peca_data, rowHeights=[0.5*cm,2*cm],colWidths=[doc.width])
    peca_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (0, 0), 'Times-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 10),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
    ]))
    elements.append(peca_table)
    elements.append(Spacer(1, 0.5*cm))
    

    cisalhada=Image(os.path.join(os.path.dirname(__file__), '..', 'static', 'img', 'cisalhada.png'), width=50, height=90)
    bipartida=Image(os.path.join(os.path.dirname(__file__), '..', 'static', 'img', 'conicaecisalhada.png'), width=50, height=90)
    colunar=Image(os.path.join(os.path.dirname(__file__), '..', 'static', 'img', 'colunar.png'), width=50, height=90)
    conica=Image(os.path.join(os.path.dirname(__file__), '..', 'static', 'img', 'conica.png'), width=50, height=90)
    conicaebipartida=Image(os.path.join(os.path.dirname(__file__), '..', 'static', 'img', 'conicaecisalhada.png'), width=50, height=90)
    
    # Tipo da ruptura
    tipo_ruptura_data = [
        ['ROMPIMENTO DO CONCRETO - RESISTÊNCIA À COMPRESSÃO (NBR 5739 / 2007)','','','','','','','','','','','',''],
        ['RESPONSÁVEL PELO ROMPIMENTO','ROMPIMENTO','DATA','PRAZO','HORÁRIO','FCK OBTIDO','TIPO DA RUPTURA DO CORPO DE PROVA','','','','',''],
        ['','','','','','','','',conica,conicaebipartida,colunar,cisalhada,bipartida],
        ['','','','','','','','','','','','']
        
    ]
    
    tipo_ruptura_table = Table(tipo_ruptura_data,colWidths=[doc.width*0.1, 
                                                            doc.width*0.1, 
                                                            doc.width*0.1, 
                                                            doc.width*0.1, 
                                                            doc.width*0.1, 
                                                            doc.width*0.1, 
                                                            doc.width*0.1,
                                                            doc.width*0.1,
                                                            doc.width*0.01,
                                                            doc.width*0.01,
                                                            doc.width*0.01,
                                                            doc.width*0.01,
                                                            doc.width*0.01])
    tipo_ruptura_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (0, 0), 'Times-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 10),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('SPAN', (0, 1), (0, 3)),
        ('ROTATE', (0, 1), (0, 1), 45),
        ('SPAN', (1, 1), (1, 3)),
        ('SPAN', (2, 1), (2, 3)),
        ('SPAN', (3, 1), (3, 3)),
        ('SPAN', (4, 1), (4, 3)),
        ('SPAN', (5, 1), (5, 3)),
        ('SPAN', (6, 1), (12, 1)),
    ]))
    elements.append(tipo_ruptura_table)
    # Tabela de rompimentos

    elements.append(Spacer(1, 0.5*cm))
    
    # Ensaio executado
    ensaio_data = [
        ['ENSAIO EXECUTADO NA PRENSA  MARCA PAVITEST / CONTENCO - FAIXA NOMINAL 100 tf, CERTIFICADO DE CALIBRAÇÃO NT 10409/2024, EMITIDA PELO LABORATÓRIO DE METROLOGIA DA NEWTONTEST EM 12/03/2024']
    ]
    
    ensaio_table = Table(ensaio_data, colWidths=[doc.width])
    ensaio_table.setStyle(TableStyle([
        ('BOX', (0, 0), (0, 0), 1, colors.black),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica'),
        ('FONTSIZE', (0, 0), (0, 0), 8),
    ]))
    elements.append(ensaio_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Resistência final
    resist_title = Paragraph("RESISTÊNCIA FINAL", title_style)
    elements.append(resist_title)
    
    # Adicionar apenas os resultados de 28 dias ou os últimos resultados disponíveis
    resistencia_final = []
    for rompimento in rompimentos:
        if rompimento.idade_cp == 28 or rompimento.idade_cp >= 24:
            resistencia_final.append({
                'data': rompimento.data_rompimento,
                'prazo': rompimento.idade_cp,
                'resultado': rompimento.resultado
            })
    
    # Pegar os 2 resultados mais recentes
    resistencia_final = sorted(resistencia_final, key=lambda x: x['data'], reverse=True)[:2]
    
    # Criar tabela de resistência final
    resist_data = [
        ['DATA DA RUPTURA', 'PRAZO dia (d) ou hora (h)', 'RESISTÊNCIA (MPa) Valor adotado', 'DATA DA RUPTURA', 'PRAZO dia (d) ou hora (h)', 'RESISTÊNCIA (MPa) Valor adotado']
    ]
    
    # Adicionar resultados à tabela
    if len(resistencia_final) > 0:
        resist_data.append([
            resistencia_final[0]['data'].strftime('%d/%m/%Y'),
            f"{resistencia_final[0]['prazo']}",
            f"{resistencia_final[0]['resultado']}",
            resistencia_final[1]['data'].strftime('%d/%m/%Y') if len(resistencia_final) > 1 else "",
            f"{resistencia_final[1]['prazo']}" if len(resistencia_final) > 1 else "",
            f"{resistencia_final[1]['resultado']}" if len(resistencia_final) > 1 else ""
        ])
    else:
        resist_data.append(["", "", "", "", "", ""])
    
    # Adicionar linha para responsável final
    resist_data.extend([
        ['responsável final pelo controle tecnógico:', 'função:', 'assinatura:', 'data'],
        ['Leandro Rodrigues Netto', 'Gestor de Fábrica', '', '']
    ])
    
    resist_table = Table(resist_data)
    resist_table.setStyle(TableStyle([
        ('BOX', (0, 0), (5, -1), 1, colors.black),
        ('GRID', (0, 0), (5, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (5, 0), colors.lightgrey),
        ('BACKGROUND', (0, 2), (0, 3), colors.lightgrey),
        ('VALIGN', (0, 0), (5, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (5, 0), 'Helvetica-Bold'),
        ('SPAN', (0, 2), (0, 2)),  # responsável final
        ('SPAN', (1, 2), (1, 2)),  # função
        ('SPAN', (2, 2), (2, 2)),  # assinatura
        ('SPAN', (3, 2), (5, 2)),  # data
        ('SPAN', (0, 3), (0, 3)),  # Leandro
        ('SPAN', (1, 3), (1, 3)),  # Gestor
        ('SPAN', (2, 3), (2, 3)),  # espaço assinatura
        ('SPAN', (3, 3), (5, 3)),  # espaço data
    ]))
    elements.append(resist_table)
    
    # Gerar o PDF
    doc.build(elements)
    
    # Obter o PDF da memória
    pdf = buffer.getvalue()
    buffer.close()
    
    # Criar resposta com o PDF
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=ficha-moldagem-{usinagem_id}.pdf'
    
    return response

@relatorio_usinagem_bp.route('/ficha-moldagem-rompimento-modal/<int:usinagem_id>')
@login_required
def ficha_moldagem_rompimento_modal(usinagem_id):
    """Retorna apenas o conteúdo HTML do relatório para exibir no modal (sem layout base) ou lista de tanques se solicitado"""
    from flask import jsonify
    usinagem = UsinagemConcreto.query.get_or_404(usinagem_id)
    concretagem = Concretagem.query.join(ConcretagemPeca).filter(
        ConcretagemPeca.usinagem_id == usinagem_id
    ).first()
    if not concretagem:
        if request.args.get('tanques') == '1':
            return jsonify({'tanques': []})
        return '<div class="alert alert-warning">Não foi encontrada concretagem relacionada a esta usinagem.</div>'
    if request.args.get('tanques') == '1':
        tanques = concretagem.tanques
        return jsonify({'tanques': [ {'id': t.id, 'nome': t.nome, 'descricao': getattr(t, 'descricao', None)} for t in tanques ]})
    tanque_id = request.args.get('tanque_id', type=int)
    tanques = concretagem.tanques
    if tanque_id:
        tanque = next((t for t in tanques if t.id == tanque_id), None)
    else:
        tanque = None  # Para exibir todos os tanques/agregado
    rompimentos = RompimentoCorpoProva.query.filter_by(usinagem_id=usinagem_id).order_by(
        RompimentoCorpoProva.numero_cp
    ).all()
    traco = usinagem.traco
    return render_template('relatorios/usinagem/_ficha_moldagem_rompimento_modal.html',
                          usinagem=usinagem,
                          concretagem=concretagem,
                          rompimentos=rompimentos,
                          traco=traco,
                          tanque=tanque,
                          tanques=tanques)

@relatorio_usinagem_bp.route('/api/contratos')
@login_required
def api_listar_contratos():
    """API para listar contratos, com opção de filtro"""
    termo_busca = request.args.get('termo', '')
    
    # Consulta base
    query = Contrato.query
    
    # Aplicar filtro se termo de busca fornecido
    if termo_busca:
        termo_busca = f"%{termo_busca}%"
        query = query.filter(
            or_(
                Contrato.nome.ilike(termo_busca),
                Contrato.descricao.ilike(termo_busca),
                Contrato.cliente.ilike(termo_busca)
            )
        )
    
    # Ordenar por nome
    contratos = query.order_by(Contrato.nome).all()
    
    # Transformar em lista de dicionários para JSON
    contratos_json = []
    for contrato in contratos:
        cliente_nome = None
        if contrato.cliente_direto_id:
            cliente = Cliente.query.get(contrato.cliente_direto_id)
            if cliente:
                cliente_nome = cliente.nome
        
        contratos_json.append({
            'id': contrato.id,
            'nome': contrato.nome,
            'descricao': contrato.descricao,
            'cliente': cliente_nome or contrato.cliente
        })
    
    return jsonify({'contratos': contratos_json}) 