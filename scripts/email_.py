import os
import tempfile
from imap_tools import MailBox, AND
from dotenv import load_dotenv
import logging
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
import io
import base64
from models.database import db
from utils.email_utils import enviar_email
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from controllers.nota_fiscal_controller import processar_nota_fiscal_xml, extrair_dados_xml
from utils.relatorio_financeiro import gerar_relatorio_financeiro

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
from evolutionapi.client import EvolutionClient
from evolutionapi.models.message import TextMessage, QuotedMessage
import requests
import time
# Carregar variáveis de ambiente
load_dotenv()

EVOLUTION_API_INSTANCE= os.getenv('EVOLUTION_API_INSTANCE')
EVOLUTION_API_TOKEN= os.getenv('EVOLUTION_API_TOKEN')
ARQUIVEI_API_KEY = os.getenv('ARQUIVEI_API_KEY')
ARQUIVEI_API_ID = os.getenv('ARQUIVEI_API_ID')


def enviar_mensagem(payload,tipo='sendText'):
    url = f"http://192.168.8.150:8081/message/{tipo}/{EVOLUTION_API_INSTANCE}"
    headers = {
        "apikey": EVOLUTION_API_TOKEN,
        "Content-Type": "application/json"
    }

    try:
        response = requests.request('POST',url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        logging.error(f'Erro ao enviar mensagem: {e}')
        return None
    
def get_CC(nnf):
    from models.nota_fiscal import NotaFiscal,NotaFiscalItem
    from models.centro_custo import CentroCusto
    from models.contrato import Contrato
    from models.tanque import Tanque
    cc = db.session.query(CentroCusto).\
    join(Contrato).\
    join(Tanque).\
    join(NotaFiscalItem,NotaFiscalItem.codigo == Tanque.item_nf).\
    join(NotaFiscal,NotaFiscal.id == NotaFiscalItem.nf_id).\
    filter(NotaFiscal.numero_nf == nnf,NotaFiscal.cnpj_emitente.like('%27126997000187%')).first()
    print(cc)
    return cc.codigo

IMAP_HOST = os.getenv('IMAP_HOST')
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASS = os.getenv('IMAP_PASS')
IMAP_FOLDER = 'sfortanks'
ASSUNTO_PADRAO_NFE = 'Envio de Nota Fiscal Eletrônica'
ASSUNTO_PADRAO_CTE = 'Envio de Nota Fiscal Eletrônica - DUA'
EMAIL_DESTINO = 'leandro.netto@fortanks.ind.br'  # Email para reenvio
IMAGEM_MARCA_DAGUA = 'static/img/carimbo_0014-00.png'  # Ajuste para o caminho da sua imagem

#difal
#NUMBER_WHATSAPP = '120363399210607974@g.us'
NUMBER_WHATSAPP = '5527996440664-1630085280@g.us'
def processar_pdf_com_marca_dagua(pdf_bytes, imagem_marca_dagua):
    """
    Adiciona uma imagem como marca d'água no canto superior direito da primeira página do PDF.
    """
    try:
        # Ler o PDF original
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        pdf_writer = PdfWriter()

        # Pega o tamanho da primeira página
        first_page = pdf_reader.pages[0]
        width = float(first_page.mediabox.width)
        height = float(first_page.mediabox.height)

        # Cria um PDF temporário com a imagem no canto superior direito
        marca_dagua_stream = io.BytesIO()
        c = canvas.Canvas(marca_dagua_stream, pagesize=(width, height))
        img = ImageReader(imagem_marca_dagua)
        img_width, img_height = img.getSize()
        # Redimensiona a imagem se necessário (exemplo: 120x120 px)
        max_img_width = 120
        max_img_height = 240
        scale = min(max_img_width / img_width, max_img_height / img_height, 1)
        img_width_scaled = img_width * scale
        img_height_scaled = img_height * scale
        # Posição: canto superior direito
        x = width - img_width_scaled - 1000  # 20 px de margem
        y = height - img_height_scaled - 20
        c.drawImage(img, x, y, width=img_width_scaled, height=img_height_scaled, mask='auto')
        c.save()
        marca_dagua_stream.seek(0)

        # Mescla a marca d'água na primeira página
        from PyPDF2 import PdfReader as RLReader
        marca_dagua_pdf = RLReader(marca_dagua_stream)
        first_page.merge_page(marca_dagua_pdf.pages[0])
        pdf_writer.add_page(first_page)

        # Adiciona as demais páginas sem alteração
        for page in pdf_reader.pages[1:]:
            pdf_writer.add_page(page)

        # Salva o PDF modificado
        output = io.BytesIO()
        pdf_writer.write(output)
        return output.getvalue()
    except Exception as e:
        logging.error(f"Erro ao processar PDF: {e}")
        return None

def processar_emails():
    if not IMAP_HOST or not IMAP_USER or not IMAP_PASS:
        logging.error('Credenciais IMAP não configuradas corretamente.')
        return

    with MailBox(host=IMAP_HOST, port=993, timeout=400).login(IMAP_USER, IMAP_PASS) as mailbox:
        # Buscar e-mails não lidos com o assunto padrão
        emails = mailbox.fetch(AND(seen=False, from_='leandro.netto@fortanks.ind.br'))
        emailsDat = []
        cc = None
        for msg in emails:
            if ASSUNTO_PADRAO_CTE in msg.subject:
                logging.info(f'Processando e-mail: {msg.subject} de {msg.from_}')

            if ASSUNTO_PADRAO_NFE in msg.subject:
                logging.info(f'Processando e-mail: {msg.subject} de {msg.from_}')
                
                # Lista para armazenar os anexos processados
                anexos_processados = []
                # Criar diretório temporário para os anexos
                with tempfile.TemporaryDirectory() as temp_dir:
                    key = None
                    nf = None
                    for att in msg.attachments:
                        if att.filename.lower().endswith('.xml'):
                            print(f"Processando xml: {att.filename}")
                            xml_text = att.payload.decode('utf-8')
                            try:
                                tinicial=time.time()
                                nf = processar_nota_fiscal_xml(xml_text)
                                tfinal=time.time()
                                logging.info(f"Tempo de execução nota fiscal: {tfinal-tinicial} segundos")
                            except Exception as e:
                                logging.error(f"Erro ao processar nota fiscal: {e}")
                            if not nf:
                                #chave,data = extrair_dados_xml(xml_text)
                                #nf = data['numero']
                                continue
                            path = os.path.join(temp_dir, 'relatorio_financeiro.xlsx')
                            print(f"Gerando relatorio financeiro: {path}")
                            tinicial=time.time()
                            #gerar_relatorio_financeiro(output_path='relatorio_financeiro.xlsx')
                            tfinal=time.time()
                            logging.info(f"Tempo de execução relatorio financeiro: {tfinal-tinicial} segundos")
                            cc = get_CC(nf.numero_nf)
                            print(f"CC: {cc} NNF: {nf.numero_nf}")
                            upload = nf.upload_arquivei()
                            print(f"Upload: {upload}")
                            if cc:
                                payload = {
                                    "number": NUMBER_WHATSAPP,
                                    "textMessage": {"text": f"""Nova nota fiscal Emitida
                                                                Nota Fiscal: {nf.numero_nf}
                                                                Centro de Custo: {cc}"""}
                                    }
                                print(f"Enviando mensagem: ")
                                tinicial=time.time()
                                response = None
                               # response = enviar_mensagem(payload)
                                tfinal=time.time()
                                logging.info(f"Tempo de execução xml: {tfinal-tinicial} segundos")
                                if response:
                                    key = response.get('key')
                                    
                            if os.path.exists(path):
                                with open(path, 'rb') as f:
                                    anexos_processados.append((
                                        'relatorio_financeiro.xlsx',
                                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                        f.read()
                                    ))
                    for att in msg.attachments:
                        if att.filename.lower().endswith('.pdf'):
                            print(f"Processando pdf: {att.filename} nnf: {nnf}")
                            tinicial=time.time()
                            if nf:
                                try:
                                    print(f"Enviando pdf: ")
                                    base64_pdf = base64.b64encode(att.payload).decode('utf-8')
                                    tfinal=time.time()
                                    logging.info(f"Tempo de execução: {tfinal-tinicial} segundos")
                                    payload = {
                                        "number": NUMBER_WHATSAPP,
                                        "mediaMessage": {
                                            "mediatype": "document",
                                            "fileName": f'NF {nf.numero_nf}.pdf',
                                            "caption": f'NF {nf.numero_nf}.pdf - CC: {cc}',
                                            "media": base64_pdf}

                                    }
                                    response = enviar_mensagem(payload,tipo='sendMedia')
                                    #print(f"Resposta: {response}")
                                    tfinal1=time.time()
                                    logging.info(f"Tempo de execução1: {tfinal1-tfinal} segundos")
                                    if response:
                                        key = response.get('key')
                                except Exception as e:
                                    logging.error(f"Erro ao enviar mensagem: {e}")
                                
                                anexos_processados.append((
                                    f'NF {nnf}.pdf',
                                    att.content_type,
                                    att.payload
                                ))
                    
                # Reenviar email com anexos processados
                if False:
                    if anexos_processados:

                        corpo_html = f"""
                        <html>
                            <body>
                                <p>Segue o email original de {msg.from_} com os anexos processados.</p>
                                <p>Assunto original: {msg.subject}</p>
                            </body>
                        </html>
                        """
                        cte = '1234567890'
                        nfe = '1234567890'
                        enviar_email(
                            destinatario=EMAIL_DESTINO,
                            assunto=f"Documentos CTE ${cte} e NFe ${nfe} ",
                            corpo_html=corpo_html,
                            anexos=anexos_processados
                        )
                     # Marcar email como lido
                        mailbox.flag(msg.uid, 'SEEN', True)
                        logging.info(f'Email processado e reenviado com sucesso para {EMAIL_DESTINO}')
             # Marcar email como lido
            mailbox.flag(msg.uid, 'SEEN', True)
                       

def procurar_anexos_xml():
    """
    Procura por anexos XML em emails não lidos.
    
    Returns:
        list: Lista de dicionários contendo informações dos XMLs encontrados
        Cada dicionário contém:
        - email_subject: Assunto do email
        - email_from: Remetente do email
        - xml_filename: Nome do arquivo XML
        - xml_content: Conteúdo do arquivo XML
    """
    if not IMAP_HOST or not IMAP_USER or not IMAP_PASS:
        logging.error('Credenciais IMAP não configuradas corretamente.')
        return []

    xmls_encontrados = []
    
    with MailBox(host=IMAP_HOST, port=993, timeout=400).login(IMAP_USER, IMAP_PASS) as mailbox:
        # Buscar e-mails não lidos
        emails = mailbox.fetch(AND(seen=False))
        
        for msg in emails:
            logging.info(f'Verificando e-mail: {msg.subject} de {msg.from_}')
            xmls_no_email = 0
            
            for att in msg.attachments:
                if att.filename.lower().endswith('.xml'):
                    try:
                        xml_text = att.payload.decode('utf-8')
                        xmls_encontrados.append({
                            'email_subject': msg.subject,
                            'email_from': msg.from_,
                            'xml_filename': att.filename,
                            'xml_content': xml_text
                        })
                        xmls_no_email += 1
                    except Exception as e:
                        logging.error(f'Erro ao processar XML {att.filename}: {str(e)}')
            
            if xmls_no_email > 0:
                logging.info(f'Encontrados {xmls_no_email} XML(s) no email: {msg.subject}')
                # Opcional: marcar como lido
                # mailbox.flag(msg.uid, 'SEEN', True)
    
    return xmls_encontrados
