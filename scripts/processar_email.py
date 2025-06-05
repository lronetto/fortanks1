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
from utils.relatorio_financeiro import gerar_relatorio_financeiro
from models.nota_fiscal import NotaFiscal
from models.upload import Upload
from models.arquivei import Arquivei
import re
import unicodedata

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
from evolutionapi.client import EvolutionClient
from evolutionapi.models.message import TextMessage, QuotedMessage
import requests
import time

def carregar_variaveis_ambiente():
    """
    Carrega as variáveis de ambiente do arquivo .env
    """
    load_dotenv(override=True)
    return {
        'IMAP_HOST': os.getenv('IMAP_HOST'),
        'IMAP_USER': os.getenv('IMAP_USER'),
        'IMAP_PASS': os.getenv('IMAP_PASS'),
        'EVOLUTION_API_INSTANCE': os.getenv('EVOLUTION_API_INSTANCE'),
        'EVOLUTION_API_TOKEN': os.getenv('EVOLUTION_API_TOKEN'),
        'ARQUIVEI_API_KEY': os.getenv('ARQUIVEI_API_KEY'),
        'ARQUIVEI_API_ID': os.getenv('ARQUIVEI_API_ID')
    }

def enviar_mensagem(payload, tipo='sendText'):
    env = carregar_variaveis_ambiente()
    url = f"http://192.168.8.150:8081/message/{tipo}/{env['EVOLUTION_API_INSTANCE']}"
    headers = {
        "apikey": env['EVOLUTION_API_TOKEN'],
        "Content-Type": "application/json"
    }

    try:
        response = requests.request('POST', url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        logging.error(f'Erro ao enviar mensagem: {e}')
        return None

def get_CC(nnf):
    from models.nota_fiscal import NotaFiscal, NotaFiscalItem
    from models.centro_custo import CentroCusto
    from models.contrato import Contrato
    from models.tanque import Tanque
    try:
        cc = db.session.query(CentroCusto).\
        join(Contrato).\
        join(Tanque).\
        join(NotaFiscalItem, NotaFiscalItem.codigo == Tanque.item_nf).\
        join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id).\
        filter(NotaFiscal.numero_nf == nnf, NotaFiscal.cnpj_emitente.like('%27126997000187%')).first()
        if cc:
            return cc.codigo
        else:
            return None
    except Exception as e:
        logging.error(f"Erro ao buscar centro de custo: {e}")
        return None
    
    return cc.codigo

# Constantes que não dependem de variáveis de ambiente
IMAP_FOLDER = 'Inbox'
ASSUNTO_PADRAO_NFE = 'Envio de Nota Fiscal Eletrônica'
ASSUNTO_PADRAO_CTE = 'Envio de Nota Fiscal Eletrônica - DUA'
ASSUNTO_PADRAO_PROTOCOLO = 'ENC: NF\'S PROTOCOLOS'
ASSUNTO_PADRAO_REEMBOLSO = 'REEMBOLSO'
EMAIL_DESTINO = 'leandro.netto@fortanks.ind.br'
IMAGEM_MARCA_DAGUA = 'static/img/carimbo_0014-00.png'
NUMBER_WHATSAPP = '5527996440664-1630085280@g.us'

def normalizar_texto(texto):
    """
    Remove acentos e caracteres especiais do texto
    Exemplo: 'CENTRALFER - CENTRAL DE FERRO LTDA' -> 'CENTRALFER - CENTRAL DE FERRO LTDA'
    """
    if not texto:
        return texto
        
    # Normaliza o texto (NFKD) e remove os caracteres diacríticos
    texto = unicodedata.normalize('NFKD', texto)
    
    # Remove caracteres não ASCII
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    
    # Substitui caracteres específicos
    substituicoes = {
        'ç': 'c', 'Ç': 'C',
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
        'Á': 'A', 'À': 'A', 'Ã': 'A', 'Â': 'A', 'Ä': 'A',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
        'Ó': 'O', 'Ò': 'O', 'Õ': 'O', 'Ô': 'O', 'Ö': 'O',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'ý': 'y', 'ÿ': 'y',
        'Ý': 'Y', 'Ÿ': 'Y',
        'ñ': 'n', 'Ñ': 'N',
        '/': '.',  # Substitui / por .
        '\\': '.', # Substitui \ por .
        '&': 'E',  # Substitui & por E
        'E.': 'E', # Remove ponto após E
        ' S.A': ' SA', # Normaliza S.A
        ' S/A': ' SA', # Normaliza S/A
        ' LTDA': ' LTDA', # Normaliza LTDA
        ' ME': ' ME', # Normaliza ME
        ' EPP': ' EPP', # Normaliza EPP
        '.': '', # Remove ponto
    }
    
    for char, replacement in substituicoes.items():
        texto = texto.replace(char, replacement)
    
    # Remove espaços extras
    texto = ' '.join(texto.split())
    
    return texto

def extrair_numero_fornecedor_do_nome(nome_arquivo):
    """
    Extrai o número da nota fiscal e o nome do fornecedor do nome do arquivo
    Suporta os seguintes formatos:
    - O FORTE DOS PARAFUSOS E FERRAMENTAS LTDA - NF 298.590.pdf (Reembolso)
    - NF162.876 - ES PRODUTOS SIDERURGICOS LTDA.pdf (Protocolo)
    - 03-07-2025 - NF 80.540 - ARCELORMITTAL BRASIL S.A.pdf (Protocolo)
    - 08-06-2025 - NF 2810 - HOLANDA ENGENHARIA LTDA.pdf (Protocolo)
    - 09-06-2025 - FL 3364 - JACKTRACKER GEOPROCESSAMENTO LTDA.pdf (Protocolo)
    - Protocolo 264231708.pdf (Protocolo)
    """
    try:
        print(f"Processando arquivo: {nome_arquivo}")
        numero_nf = None
        fornecedor = None
        # Remove a extensão .pdf
        nome_sem_ext = nome_arquivo.replace('.pdf', '')
        print(f"Nome sem extensão: {nome_sem_ext}")
        
        # Se for um protocolo simples
        if nome_sem_ext.startswith('Protocolo'):
            numero_protocolo = nome_sem_ext.replace('Protocolo', '').strip()
            print(f"Protocolo simples encontrado: {numero_protocolo}")
            return numero_protocolo, 'PROTOCOLO'
        
        qtd_hifens = nome_sem_ext.count('-')
        if qtd_hifens == 1:
            #reembolso
            if '- NF' in nome_sem_ext:
                partes = nome_sem_ext.split(' - NF')
                print(f"Partes do nome (reembolso): {partes}")
                if len(partes) == 2:
                    fornecedor = partes[0].strip()
                    numero_nf = partes[1].replace('.', '').strip()
                    print(f"Reembolso encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
        else:
            #protocolo
            partes = nome_sem_ext.split(' - ')
            print(f"Partes do nome (protocolo): {partes}")
            if len(partes) == 3:
                fornecedor = partes[2].strip()
                partes[1] = partes[1].replace('.', '')
                delimitador = re.sub(r'\d', '', partes[1])
                numero_nf = partes[1].split(delimitador)[1].strip().replace('.', '')
                print(f"Protocolo encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
            elif len(partes) > 3:
                fornecedor = (partes[2]+' - '+partes[3]).strip()
                numero_nf = partes[1].split('NF')[1].strip().replace('.', '')
                print(f"Protocolo encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
            else:
                print("Formato de protocolo inválido")
        
        if numero_nf and fornecedor:
            fornecedor = normalizar_texto(fornecedor)
            return numero_nf, fornecedor
        else:
            print("Formato de protocolo inválido")
            return None, None
    except Exception as e:
        print(f"Erro ao extrair número e fornecedor do nome do arquivo: {e}")
        return None, None


def processar_emails():
    """
    Processa emails com o assunto NF'S PROTOCOLOS e faz upload dos PDFs para as notas fiscais existentes
    """
    env = carregar_variaveis_ambiente()
    if not env['IMAP_HOST'] or not env['IMAP_USER'] or not env['IMAP_PASS']:
        logging.error('Credenciais IMAP não configuradas corretamente.')
        return

    print('processar_emails')
    with MailBox(host=env['IMAP_HOST'], port=993, timeout=400).login(env['IMAP_USER'], env['IMAP_PASS']) as mailbox:
        print(f'buscando emails {mailbox.login_result}')
        try:
            # Buscar e-mails não lidos com o assunto de protocolos, limitando a quantidade
            emails = mailbox.fetch(AND(seen=False, from_='leandro.netto@fortanks.ind.br'), limit=20)
        except Exception as e:
            logging.error(f"Erro ao buscar emails: {e}")
            return

        for msg in emails:
            try:
                if ASSUNTO_PADRAO_PROTOCOLO in msg.subject:

                    logging.info(f'Processando email de protocolo: {msg.subject}')
                    
                    for att in msg.attachments:
                        if att.filename.lower().endswith('.pdf'):
                            # Ignora arquivos que contenham 'protocolo' no nome
                            if 'protocolo' in att.filename.lower():
                                logging.info(f"Ignorando arquivo de protocolo: {att.filename}")
                                continue
                                
                            # Se não encontrou a chave de acesso, tenta pelo número e fornecedor
                            numero_nf, fornecedor = extrair_numero_fornecedor_do_nome(att.filename)
                            if not numero_nf or not fornecedor:
                                logging.error(f"Não foi possível extrair número da NF ou fornecedor do arquivo: {att.filename}")
                                continue
                            
                            # Buscar a nota fiscal no banco de dados
                            from models.nota_fiscal import NotaFiscal
                            from sqlalchemy import func
                            
                            # Primeiro busca todas as notas com o número correspondente
                            notas = NotaFiscal.query.filter(NotaFiscal.numero_nf.like(f'%{numero_nf}%')).all()
                            
                            # Depois procura a que tem o nome do emitente normalizado correspondente
                            nota = None 
                            fornecedor_normalizado = normalizar_texto(fornecedor)
                            if not notas:
                                if Upload('NotaFiscal', 0, 2, att.filename, 'application/pdf'):
                                    logging.info(f"PDF protocolo ja existe {numero_nf}")
                                else:
                                    Upload('NotaFiscal', 0, 2, att.filename, 'application/pdf', att.payload)
                                    logging.info(f"PDF protocolo enviado com sucesso para a NF {numero_nf}")
                            else:
                                for n in notas:
                                    emitente_normalizado = normalizar_texto(n.nome_emitente)
                                    # Verifica se o nome do fornecedor está contido no nome do emitente
                                    if fornecedor_normalizado in emitente_normalizado:
                                        nota = n
                                        break
                                
                                if nota:
                                    try:
                                        if Upload('NotaFiscal', nota.id, 2, att.filename, 'application/pdf'):
                                            logging.info(f"PDF ja existe {numero_nf}")
                                        else:
                                            Upload('NotaFiscal', nota.id, 2, att.filename, 'application/pdf', att.payload)
                                            logging.info(f"PDF protocolo enviado com sucesso para a NF {numero_nf}")
                                    except Exception as e:
                                        logging.error(f"Erro ao fazer upload do PDF protocolo para NF {numero_nf}: {e}")
                                else:
                                    print(f"Nota fiscal {numero_nf} não encontrada no sistema")
                                    if not Upload('NotaFiscal', 0, 2, att.filename, 'application/pdf'):
                                        Upload('NotaFiscal', 0, 2, att.filename, 'application/pdf', att.payload)
                                    else:
                                        logging.info(f"PDF protocolo ja existe {numero_nf}")
                                    logging.warning(f"Nota fiscal {numero_nf} não encontrada no sistema")
                    
                    # Marcar o email como lido
                   
                
                if ASSUNTO_PADRAO_REEMBOLSO in msg.subject:
                    logging.info(f'Processando email de reembolso: {msg.subject}')
                    for att in msg.attachments:
                        if att.filename.lower().endswith('.pdf'):
                            # Ignora arquivos que contenham 'protocolo' no nome
                            if 'protocolo' in att.filename.lower():
                                logging.info(f"Ignorando arquivo de protocolo: {att.filename}")
                                continue
                                
                            # Se não encontrou a chave de acesso, tenta pelo número e fornecedor
                            numero_nf, fornecedor = extrair_numero_fornecedor_do_nome(att.filename)
                            
                            print(f"Numero NF: {numero_nf} Fornecedor: {fornecedor}")
                            if not numero_nf or not fornecedor:
                                logging.error(f"Não foi possível extrair número da NF ou fornecedor do arquivo: {att.filename}")
                                continue
                            
                            # Buscar a nota fiscal no banco de dados
                            from models.nota_fiscal import NotaFiscal
                            from sqlalchemy import func
                            
                            # Primeiro busca todas as notas com o número correspondente
                            notas = NotaFiscal.query.filter(NotaFiscal.numero_nf.like(f'%{numero_nf}%')).all()
                            
                            # Depois procura a que tem o nome do emitente normalizado correspondente
                            nota = None
                            fornecedor_normalizado = normalizar_texto(fornecedor)
                            print(f"Fornecedor normalizado: {fornecedor_normalizado}")
                            for n in notas:
                                emitente_normalizado = normalizar_texto(n.nome_emitente)
                                # Verifica se o nome do fornecedor está contido no nome do emitente
                                if fornecedor_normalizado in emitente_normalizado:
                                    nota = n
                                    break
                            
                            if nota:
                                try:
                                    if Upload('NotaFiscal', nota.id, 3, att.filename, 'application/pdf'):
                                        logging.info(f"PDF reembolso ja existe {numero_nf}")
                                    else:
                                        Upload('NotaFiscal', nota.id, 3, att.filename, 'application/pdf', att.payload)
                                        logging.info(f"PDF reembolso enviado com sucesso para a NF {numero_nf}")
                                except Exception as e:
                                    logging.error(f"Erro ao fazer upload do PDF reembolso para NF {numero_nf}: {e}")
                            else:
                                print(f"Nota fiscal {numero_nf} não encontrada no sistema")
                                if not Upload('NotaFiscal', 0, 3, att.filename, 'application/pdf'):
                                    print(f"Gravando reembolso {numero_nf}")
                                    Upload('NotaFiscal', 0, 3, att.filename, 'application/pdf', att.payload)
                                else:
                                    logging.info(f"PDF reembolso ja existe {numero_nf}")
                                logging.warning(f"Nota fiscal {numero_nf} não encontrada no sistema")
            
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
                                try:
                                    tinicial=time.time()
                                    nf=NotaFiscal(xml_data=att.payload)
                                    Arquivei(xml_data=att.payload)
                                    tfinal=time.time()
                                    logging.info(f"Tempo de execução nota fiscal: {tfinal-tinicial} segundos")
                                except Exception as e:
                                    logging.error(f"Erro ao processar nota fiscal: {e}")
                                if not nf:
                                    logging.error(f"Erro ao processar nota fiscal")
                                    continue
                                print(f"Gerando relatorio financeiro: {nf.numero_nf}")
                                path = os.path.join(temp_dir, 'relatorio_financeiro.xlsx')
                                print(f"Gerando relatorio financeiro: {path}")
                                tinicial=time.time()
                                gerar_relatorio_financeiro(output_path='relatorio_financeiro.xlsx')
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
                                print(f"Processando pdf: {att.filename} nnf: {nf.numero_nf}")
                                tinicial=time.time()
                                if nf:
                                    try:
                                        print(f"Enviando pdf: ")
                                        print('gravando upload')
                                        Upload('NotaFiscal',nf.id, 1, \
                                                f'NF {nf.numero_nf}.pdf', \
                                                'application/pdf', \
                                                att.payload)
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
                                        tfinal1=time.time()
                                        logging.info(f"Tempo de execução1: {tfinal1-tfinal} segundos")
                                    except Exception as e:
                                        logging.error(f"Erro ao enviar mensagem: {e}")
                                    
                                    anexos_processados.append((
                                        f'NF {nf.numero_nf}.pdf',
                                        att.content_type,
                                        att.payload
                                    ))

                mailbox.flag(msg.uid, 'SEEN', True)
                logging.info(f'Email {msg.subject} processado com sucesso')
            except Exception as e:
                logging.error(f"Erro ao processar email {msg.subject}: {e}")
                continue