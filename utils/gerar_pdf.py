import lxml.etree as ET
from weasyprint import HTML
import datetime
import io

def parse_nf_xml(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

    ide = root.find('.//ns:ide', ns)
    emit = root.find('.//ns:emit', ns)
    dest = root.find('.//ns:dest', ns)
    total = root.find('.//ns:ICMSTot', ns)
    produtos = root.findall('.//ns:det', ns)
    transp = root.find('.//ns:transporta', ns)
    infProt = root.find('.//ns:protNFe/ns:infProt', ns)

    dados = {
        'numero': ide.find('ns:nNF', ns).text,
        'serie': ide.find('ns:serie', ns).text,
        'data_emissao': ide.find('ns:dhEmi', ns).text[:10],
        'natureza': ide.find('ns:natOp', ns).text,
        'emitente': emit.find('ns:xNome', ns).text,
        'cnpj_emitente': emit.find('ns:CNPJ', ns).text,
        'destinatario': dest.find('ns:xNome', ns).text,
        'cnpj_destinatario': dest.find('ns:CNPJ', ns).text,
        'produtos': [],
        'vNF': total.find('ns:vNF', ns).text,
        'vProd': total.find('ns:vProd', ns).text,
        'vICMS': total.find('ns:vICMS', ns).text,
        'chave_acesso': infProt.find('ns:chNFe', ns).text,
        'protocolo': infProt.find('ns:nProt', ns).text,
        'data_autorizacao': infProt.find('ns:dhRecbto', ns).text,
        'transportadora': transp.find('ns:xNome', ns).text if transp is not None else ''
    }

    for prod in produtos:
        prod_info = prod.find('ns:prod', ns)
        dados['produtos'].append({
            'descricao': prod_info.find('ns:xProd', ns).text,
            'qtd': prod_info.find('ns:qCom', ns).text,
            'vl_unit': prod_info.find('ns:vUnCom', ns).text,
            'vl_total': prod_info.find('ns:vProd', ns).text
        })

    return dados

def gerar_html_danfe(dados):
    html = \
    f"""
    <style>
        @media print {{
            @page {{
                margin-left: 15mm;
                margin-right: 15mm;
            }}

            footer {{
                page-break-after: always;
            }}
        }}
        * {{
            margin: 0;
        }}

        .ui-widget-content {{
            border: none !important;
        }}

        .nfe-square {{
            margin: 0 auto 2cm;
            box-sizing: border-box;
            width: 2cm;
            height: 1cm;
            border: 1px solid #000;
        }}

        .nfeArea.page {{
            width: 18cm;
            position: relative;
            font-family: "Times New Roman", serif;
            color: #000;
            margin: 0 auto;
            overflow: hidden;
        }}

        .nfeArea .font-12 {{
            font-size: 12pt;
        }}

        .nfeArea .font-8 {{
            font-size: 8pt;
        }}

        .nfeArea .bold {{
            font-weight: bold;
        }}
        /* == TABELA == */
        .nfeArea .area-name {{
            font-family: "Times New Roman", serif;
            color: #000;
            font-weight: bold;
            margin: 2mm 0 0;
            font-size: 6pt;
            text-transform: uppercase;
        }}

        .nfeArea .txt-upper {{
            text-transform: uppercase;
        }}

        .nfeArea .txt-center {{
            text-align: center;
        }}

        .nfeArea .txt-right {{
            text-align: right;
        }}

        .nfeArea .nf-label {{
            text-transform: uppercase;
            margin-bottom: 3px;
            display: block;
        }}

        .nfeArea .nf-label.label-small {{
            letter-spacing: -0.5px;
            font-size: 4pt;
        }}

        .nfeArea .info {{
            font-weight: bold;
            font-size: 8pt;
            display: block;
            line-height: 1em;
        }}

        .nfeArea table {{
            font-family: "Times New Roman", serif;
            color: #000;
            font-size: 5pt;
            border-collapse: collapse;
            width: 100%;
            border-color: #000;
            border-radius: 5px;
        }}

        .nfeArea .no-top {{
            margin-top: -1px;
        }}

        .nfeArea .mt-table {{
            margin-top: 3px;
        }}

        .nfeArea .valign-middle {{
            vertical-align: middle;
        }}

        .nfeArea td {{
            vertical-align: top;
            box-sizing: border-box;
            overflow: hidden;
            border-color: #000;
            padding: 1px;
            height: 5mm;
        }}

        .nfeArea .tserie {{
            width: 32.2mm;
            vertical-align: middle;
            font-size: 8pt;
            font-weight: bold;
        }}

        .nfeArea .tserie span {{
            display: block;
        }}

        .nfeArea .tserie h3 {{
            display: inline-block;
        }}

        .nfeArea .entradaSaida .legenda {{
            text-align: left;
            margin-left: 2mm;
            display: block;
        }}

        .nfeArea .entradaSaida .legenda span {{
            display: block;
        }}

        .nfeArea .entradaSaida .identificacao {{    
            float: right;
            margin-right: 2mm;
            border: 1px solid black;
            width: 5mm;
            height: 5mm;
            text-align: center;
            padding-top: 0;
            line-height: 5mm;
        }}

        .nfeArea .hr-dashed {{
            border: none;
            border-top: 1px dashed #444;
            margin: 5px 0;
        }}

        .nfeArea .client_logo {{
            height: 27.5mm;
            width: 28mm;
            margin: 0.5mm;
        }}

        .nfeArea .title {{
            font-size: 10pt;
            margin-bottom: 2mm;
        }}

        .nfeArea .txtc {{
            text-align: center;
        }}

        .nfeArea .pd-0 {{
            padding: 0;
        }}

        .nfeArea .mb2 {{
            margin-bottom: 2mm;
        }}

        .nfeArea table table {{
            margin: -1pt;
            width: 100.5%;
        }}

        .nfeArea .wrapper-table {{
            margin-bottom: 2pt;
        }}

        .nfeArea .wrapper-table table {{
            margin-bottom: 0;
        }}

        .nfeArea .wrapper-table table + table {{
            margin-top: -1px;
        }}

        .nfeArea .boxImposto {{
            table-layout: fixed;
        }}

        .nfeArea .boxImposto td {{
            width: 11.11%;
        }}

        .nfeArea .boxImposto .nf-label {{
            font-size: 5pt;
        }}

        .nfeArea .boxImposto .info {{
            text-align: right;
        }}

        .nfeArea .wrapper-border {{
            border: 1px solid #000;
            border-width: 0 1px 1px;
            height: 75.7mm; 
        }}

        .nfeArea .wrapper-border table {{
            margin: 0 -1px;
            width: 100.4%;
        }}

        .nfeArea .content-spacer {{ 
            display: block;
            height: 10px;
        }}

        .nfeArea .titles th {{
            padding: 3px 0;
        }}

        .nfeArea .listProdutoServico td {{
            padding: 0;
        }}

        .nfeArea .codigo {{
            display: block;
            text-align: center;
            margin-top: 5px;
        }}

        .nfeArea .boxProdutoServico tr td:first-child {{
            border-left: none;
        }}

        .nfeArea .boxProdutoServico td {{
            font-size: 6pt;
            height: auto;
        }}

        .nfeArea .boxFatura span {{
            display: block;
        }}

        .nfeArea .boxFatura td {{
            border: 1px solid #000;
        }}

        .nfeArea .freteConta .border {{
            width: 5mm;
            height: 5mm;
            float: right;
            text-align: center;
            line-height: 5mm;
            border: 1px solid black;
        }}

        .nfeArea .freteConta .info {{
            line-height: 5mm;
        }}

        .page .boxFields td p {{
            font-family: "Times New Roman", serif;
            font-size: 5pt;
            line-height: 1.2em;
            color: #000;
        }}

        .nfeArea .imgCanceled {{
            position: absolute;
            top: 75mm;
            left: 30mm;
            z-index: 3;
            opacity: 0.8;
            display: none;
        }}

        .nfeArea.invoiceCanceled .imgCanceled {{
            display: block;
        }}

        .nfeArea .imgNull {{    
            position: absolute;
            top: 75mm;
            left: 20mm;
            z-index: 3;
            opacity: 0.8;
            display: none;
        }}

        .nfeArea.invoiceNull .imgNull {{
            display: block;
        }}

        .nfeArea.invoiceCancelNull .imgCanceled {{
            top: 100mm;
            left: 35mm;
            display: block;
        }}

        .nfeArea.invoiceCancelNull .imgNull {{
            top: 65mm;
            left: 15mm;
            display: block;
        }}

        .nfeArea .page-break {{
            page-break-before: always;
        }}

        .nfeArea .block {{
            display: block;
        }}

        .label-mktup {{
            font-family: Arial;
            font-size: 8px;
            padding-top: 8px;
        }}
    </style>
    <!-- /Header -->
    <!-- Recebimentos -->
    <div class="page nfeArea">
        <img class="imgCanceled" src="tarja_nf_cancelada.png" alt="" />
        <img class="imgNull" src="tarja_nf_semvalidade.png" alt="" />
        <div class="boxFields" style="padding-top: 20px;">
            <table cellpadding="0" cellspacing="0" border="1">
                <tbody>
                    <tr>
                        <td colspan="2" class="txt-upper">
                            Recebemos de {dados['emitente']} os produtos e serviços constantes na nota fiscal indicada ao lado
                        </td>
                        <td class="tserie">
                            <span>NF-e</span>
                            <h3>Nº {dados['numero']}</h3>
                            <span>Série {dados['serie']}</span>
                        </td>
                    </tr>
                    <tr>
                        <td colspan="3" class="txt-upper">
                            <div class="entradaSaida">
                                <span class="legenda">
                                    <span>ENTRADA</span>
                                    <span>SAÍDA</span>
                                </span>
                                <span class="identificacao">X</span>
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="wrapper-border">
            <table cellpadding="0" cellspacing="0">
                <tbody>
                    <tr>
                        <td class="field" style="width: 85mm; height: 24mm">
                            <span class="nf-label">DESTINATÁRIO / REMETENTE</span>
                            <span class="info">{dados['destinatario']}</span>
                            <span class="info">CNPJ: {dados['cnpj_destinatario']}</span>
                        </td>
                        <td class="field" style="width: 85mm; height: 24mm">
                            <span class="nf-label">NATUREZA DA OPERAÇÃO</span>
                            <span class="info">{dados['natureza']}</span>
                        </td>
                    </tr>
                    <tr>
                        <td class="field" style="width: 85mm; height: 24mm">
                            <span class="nf-label">PROTOCOLO DE AUTORIZAÇÃO DE USO</span>
                            <span class="info">{dados['protocolo']}</span>
                            <span class="info">Data: {dados['data_autorizacao']}</span>
                        </td>
                        <td class="field" style="width: 85mm; height: 24mm">
                            <span class="nf-label">CHAVE DE ACESSO</span>
                            <span class="info">{dados['chave_acesso']}</span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="wrapper-table">
            <table cellpadding="0" cellspacing="0">
                <tbody>
                    <tr>
                        <td class="field" style="width: 85mm; height: 24mm">
                            <span class="nf-label">PRODUTOS / SERVIÇOS</span>
                            <table cellpadding="0" cellspacing="0">
                                <tbody>"""
    for prod in dados['produtos']:
        html += f"""
                                    <tr>
                                        <td>{prod['descricao']}</td>
                                        <td>{prod['qtd']}</td>
                                        <td>{prod['vl_unit']}</td>
                                        <td>{prod['vl_total']}</td>
                                    </tr>
                                    """
    html += f"""
                                </tbody>
                            </table>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="wrapper-table">
            <table cellpadding="0" cellspacing="0">
                <tbody>
                    <tr>
                            <td class="field" style="width: 85mm; height: 24mm">
                            <span class="nf-label">VALORES</span>
                            <table cellpadding="0" cellspacing="0">
                                <tbody>
                                    <tr>
                                        <td>Valor Total dos Produtos:</td>
                                        <td>{dados['vProd']}</td>
                                    </tr>
                                    <tr>
                                        <td>Valor do ICMS:</td>
                                        <td>{dados['vICMS']}</td>
                                    </tr>
                                    <tr>
                                        <td>Valor Total da NF-e:</td>
                                        <td>{dados['vNF']}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="wrapper-table">
            <table cellpadding="0" cellspacing="0">
                <tbody>
                    <tr>
                        <td class="field" style="width: 85mm; height: 24mm">
                            <span class="nf-label">TRANSPORTADOR</span>
                            <span class="info">{dados['transportadora']}</span>
                        </td>
                        <td class="field reservaFisco" style="width: 85mm; height: 24mm">
                            <span class="nf-label">RESERVA AO FISCO</span>
                            <span></span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <footer>
            <table cellpadding="0" cellspacing="0">
                <tbody>
                    <tr>
                        <td style="text-align: right"><strong>Empresa de Software www.empresa.com</strong></td>
                    </tr>
                </tbody>
            </table>
        </footer>
    </div>
    [page-break]
    </div>
"""
    return html

def gerar_pdf_danfe(xml_path):
    dados = parse_nf_xml(xml_path)
    html_content = gerar_html_danfe(dados)
    pdf = HTML(string=html_content).write_pdf()
    return pdf
