from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, make_response
from flask_login import login_required, current_user
from models import UsinagemConcreto, TracoConcreto, ItemTracoConcreto, RompimentoCorpoProva, Contrato, Cliente
from models import Concretagem, ConcretagemPeca, ConcretagemTanque, Tanque, Peca
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
    """Gera um PDF da ficha de moldagem e rompimento para uma usinagem específica"""
    usinagem = UsinagemConcreto.query.get_or_404(usinagem_id)
    
    # Buscar concretagem relacionada a esta usinagem
    concretagem = Concretagem.query.join(ConcretagemPeca).filter(
        ConcretagemPeca.usinagem_id == usinagem_id,
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
    
    # Buscar o cliente final (usaremos o cliente do contrato)
    cliente = None
    tanque = None
    obra = None
    
    if concretagem and concretagem.tanques_associados:
        # Pegar o primeiro tanque associado para simplificar
        tanque = concretagem.tanques[0] if concretagem.tanques else None
        
        if tanque and tanque.contrato_id:
            # Buscar contrato relacionado ao centro de custo do tanque
            contrato = tanque.contrato
            
            if contrato and contrato.cliente_final_id:
                cliente = Cliente.query.get(contrato.cliente_final_id)
            
            # Definir obra como a descrição do tanque
            obra = f"{tanque.nome}"
    
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
    
    header_table = Table(header_data, colWidths=[doc.width*0.2, doc.width*0.7, doc.width*0.1])
    header_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
       
        ('SPAN', (0, 0), (0, 2)),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
       
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Especificação do concreto
    spec_title = Paragraph("ESPECIFICAÇÃO DO CONCRETO", title_style)
    elements.append(spec_title)
    
    # Dados da especificação
    spec_data = [
        ['TIPO DO CONCRETO:', f'fck>= {traco.resistencia}', 'MPa', f'28 dias', 'TRAÇO FTK:', f'{traco.codigo}', 'BRITA:', '0'],
        ['RESTRIÇÃO:', 'fck>= 24,0', 'MPa p/ desprotensão', 'CIMENTO 1:', 'CPIII 40 RS', 'CIMENTO 2:', 'CP V'],
        ['CONSISTÊNCIA PREVISTA:', f'{"SLUMP=" if traco.tipo_abatimento == "slump" else "FLOW="}', 'mm', f'{traco.valor_abatimento} ± 50', 'CONSUMO DE CIMENTO (kg/m³):', '1 (50%)', '2 (50%)'],
        ['ADITIVO:', 'SUPER PLASTIFICANTE', 'LANÇAMENTO:', 'BOMBEADO', 'X', 'CONVENCIONAL', '']
    ]
    
    spec_table = Table(spec_data,colWidths=[doc.width*0.2, doc.width*0.1, doc.width*0.1, doc.width*0.1, doc.width*0.1, doc.width*0.1, doc.width*0.1])
    spec_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('SPAN', (1, 0), (2, 0)),  # fck
        ('SPAN', (3, 0), (3, 0)),  # 28 dias
        ('SPAN', (1, 1), (2, 1)),  # fck desprotensão
        ('SPAN', (4, 1), (4, 1)),  # CPIII 40 RS
        ('SPAN', (1, 2), (1, 2)),  # SLUMP=
        ('SPAN', (3, 2), (3, 2)),  # valor abatimento
        ('SPAN', (1, 3), (1, 3)),  # SUPER PLASTIFICANTE
        ('SPAN', (3, 3), (3, 3)),  # BOMBEADO
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
    ]))
    elements.append(spec_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Recebimento do concreto / moldagem
    receb_title = Paragraph("RECEBIMENTO DO CONCRETO / MOLDAGEM (NBR 5738 / 2015)", title_style)
    elements.append(receb_title)
    
    # Data formatada
    data_usinagem = usinagem.data_usinagem.strftime('%d/%m/%Y')
    horario_saida = usinagem.data_usinagem.strftime('%H:%M')
    
    receb_data = [
        ['CONCRETEIRA:', 'FORTANKS', 'DATA:', data_usinagem, 'NÚMERO DO CAMINHÃO / PLACA:', '01'],
        ['NOTA FISCAL:', f'{usinagem.id}', 'HORÁRIO SAÍDA DA USINA:', horario_saida, 'HORÁRIO CHEGADA NO DESTINO:', horario_saida]
    ]
    
    receb_table = Table(receb_data)
    receb_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(receb_table)
    
    # Consistência real
    consist_data = [
        ['CONSISTÊNCIA REAL:', 'SLUMP=', 'mm', 'MOLDADOR: GEAN JR'],
        ['', 'FLOW=', '660/670', 'mm', 'caso não aceitar concreto justificar:']
    ]
    
    consist_table = Table(consist_data)
    consist_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('SPAN', (3, 0), (4, 0)),  # Moldador
        ('SPAN', (2, 1), (2, 1)),  # FLOW valor
        ('SPAN', (4, 1), (4, 1)),  # Justificativa
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(consist_table)
    
    # Verificado as características e liberação
    verificado_data = [
        ['verificada as características do concreto na Nota e o abatimento,'],
        ['liberar para lançamento ?', 'X', 'sim', '', 'não']
    ]
    
    verificado_table = Table(verificado_data)
    verificado_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('GRID', (1, 1), (4, 1), 0.5, colors.black),
        ('SPAN', (0, 0), (4, 0)),  # Primeira linha
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(verificado_table)
    
    # Horário e volume
    horario_data = [
        ['HORÁRIO DA MOLDAGEM:', '10:02', 'VOLUME:', '8,15', 'm³', 'observações:'],
        ['SÉRIE Nº:', f'{usinagem.id}', 'CRITÉRIO DE ROMPIMENTO PREVISTO:', 'TP: (sentido da concretagem TOPO para "PÉ" do painel)'],
        ['QUANTIDADE DE CP\'s:', f'{usinagem.quantidade_cps}', '2 (24 h) - 2 (28 dias)', '']
    ]
    
    horario_table = Table(horario_data)
    horario_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('SPAN', (2, 1), (5, 1)),  # Critério de rompimento
        ('SPAN', (2, 2), (5, 2)),  # Critério dias
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(horario_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Peça concretada
    peca_title = Paragraph("PEÇA CONCRETADA", title_style)
    elements.append(peca_title)
    
    peca_data = [
        [f'PN-{tanque.nome if tanque else "?"}-P']
    ]
    
    peca_table = Table(peca_data, colWidths=[doc.width])
    peca_table.setStyle(TableStyle([
        ('BOX', (0, 0), (0, 0), 1, colors.black),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 12),
    ]))
    elements.append(peca_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Rompimento do concreto
    romp_title = Paragraph("ROMPIMENTO DO CONCRETO - RESISTÊNCIA À COMPRESSÃO (NBR 5739 / 2007)", title_style)
    elements.append(romp_title)
    
    # Tipo da ruptura
    tipo_ruptura_data = [
        ['TIPO DA RUPTURA DO CORPO DE PROVA (x)'],
        ['cônica', 'cônica e bipartida', 'cônica e cisalhada', 'cisalhada', 'colunar']
    ]
    
    tipo_ruptura_table = Table(tipo_ruptura_data)
    tipo_ruptura_table.setStyle(TableStyle([
        ('BOX', (0, 0), (4, 1), 1, colors.black),
        ('GRID', (0, 1), (4, 1), 0.5, colors.black),
        ('SPAN', (0, 0), (4, 0)),  # Título
        ('ALIGN', (0, 0), (4, 0), 'CENTER'),
        ('VALIGN', (0, 0), (4, 1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (4, 0), colors.lightgrey),
        ('FONTNAME', (0, 0), (4, 0), 'Helvetica-Bold'),
    ]))
    
    # Tabela de rompimentos
    romp_data = [
        ['Responsável pelo rompimento', 'Rompimento', 'DATA', 'PRAZO dia (d) ou hora (h)', 'HORÁRIO', 'Fck obtido (MPa)'],
    ]
    
    # Adicionar rompimentos existentes
    for rompimento in rompimentos:
        # Determinar o prazo (dias ou horas)
        data_usinagem = usinagem.data_usinagem.date()
        data_rompimento = rompimento.data_rompimento.date()
        
        dias_diff = (data_rompimento - data_usinagem).days
        horas = "H" if dias_diff < 1 else "D"
        prazo = f"{dias_diff if dias_diff >= 1 else rompimento.idade_cp}"
        
        # Adicionar linha
        romp_data.append([
            "RR-1",
            str(rompimento.numero_cp),
            rompimento.data_rompimento.strftime('%d/%m/%Y'),
            f"{prazo}",
            f"{horas}",
            f"{rompimento.resultado}" if rompimento.resultado else ""
        ])
    
    # Preencher até 8 linhas no total (para manter o formato)
    while len(romp_data) < 9:
        romp_data.append(["RR-1", "", "", "", "", ""])
    
    # Adicionar linhas de assinatura
    romp_data.extend([
        ['CÓDIGO', 'NOME', '', 'FUNÇÃO', 'ASSINATURA', ''],
        ['RR-1', 'Gean Junior Reinholz', '', 'Técnico de Edificações', '', ''],
        ['RR-2', 'Leandro Rodrigues Netto', '', 'Gestor de Fábrica', '', ''],
        ['RR-3', '', '', '', '', '']
    ])
    
    romp_table = Table(romp_data)
    romp_table.setStyle(TableStyle([
        ('BOX', (0, 0), (5, -1), 1, colors.black),
        ('GRID', (0, 0), (5, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (5, 0), colors.lightgrey),
        ('BACKGROUND', (0, 9), (0, 12), colors.lightgrey),
        ('BACKGROUND', (0, 9), (5, 9), colors.lightgrey),
        ('FONTNAME', (0, 0), (5, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 9), (5, 9), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (5, 0), 'CENTER'),
        ('VALIGN', (0, 0), (5, -1), 'MIDDLE'),
        ('SPAN', (1, 9), (2, 9)),  # Nome título
        ('SPAN', (1, 10), (2, 10)),  # Nome Gean
        ('SPAN', (1, 11), (2, 11)),  # Nome Leandro
        ('SPAN', (1, 12), (2, 12)),  # Nome vazio
        ('SPAN', (3, 9), (5, 9)),  # Função título
        ('SPAN', (3, 10), (3, 10)),  # Função Gean
        ('SPAN', (3, 11), (3, 11)),  # Função Leandro
        ('SPAN', (3, 12), (3, 12)),  # Função vazia
        ('SPAN', (4, 10), (5, 10)),  # Assinatura Gean
        ('SPAN', (4, 11), (5, 11)),  # Assinatura Leandro
        ('SPAN', (4, 12), (5, 12)),  # Assinatura vazia
    ]))
    
    # Adicionar tabelas à tabela principal de rompimento
    romp_tables = [tipo_ruptura_table, romp_table]
    elements.extend(romp_tables)
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