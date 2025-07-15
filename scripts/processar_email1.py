import os
import tempfile
from imap_tools import MailBox, AND
from imbox import Imbox
from dotenv import load_dotenv
import logging
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
import io
import base64
from models.database import db
from models.logs import Logs
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
import json
from datetime import datetime

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
from evolutionapi.client import EvolutionClient
from evolutionapi.models.message import TextMessage, QuotedMessage
import requests
import time
from pyzbar.pyzbar import decode
from pdf2image import convert_from_path, convert_from_bytes

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
ASSUNTO_PADRAO_DUA = 'CTE, NF Fortanks e DUA'
ASSUNTO_PADRAO_PROTOCOLO = ["ENC: NF´S PROTOCOLOS","ENC: NF PROTOCOLO","NF PROTOCOLO"]
ASSUNTO_PADRAO_REEMBOLSO = ['REEMBOLSO']
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
        'LTDA.': 'LTDA', # Normaliza LTDA
        ' ME': ' ME', # Normaliza ME
        ' EPP': ' EPP', # Normaliza EPP
        '.': '', # Remove ponto
        'DADALTO LUCAS E UNIFORMES ME': 'DADALTO LUVAS E UNIFORMES ME',
        'DADALTO LUVAS E UNIFORMES - ME': 'DADALTO LUVAS E UNIFORMES ME',
        'MIRANDA RESTAURANTE LTDA': 'MIRANDA RESTAURANTES LTDA',
        'BRASITALIA AGREGADOS LTDA':'BRASITALIA AGREGADOS PARA CONSTRUCAO LTDA',
        'NEOBETEL EQUIP DE PROTEÇÃO INDIVIDUAL LTDA': 'NEOBETEL EPI, EQUIPAMENTOS DE PROTECAO INDIVIDUAL LTDA',
        'ES PRODUTOS SIDERGÚRGICOS LTDA': 'ES PRODUTOS SIDERURGICOS LTDA',
        'FERRARI MAQ E FERRAMENTAS LTDA': 'FERRARI MAQUINAS E FERRAMENTAS LTDA EPP',
        'TECNOSIL IND E COM DE PRODUTOS QUIMICOS': 'Tecnosil Industria e Comercio de Produtos Quimicos Ltda.'
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
        #print(f"Nome sem extensão: {nome_sem_ext}")
        
        # Se for um protocolo simples
        if nome_sem_ext.startswith('Protocolo'):
            numero_protocolo = nome_sem_ext.replace('Protocolo', '').strip()
            #print(f"Protocolo simples encontrado: {numero_protocolo}")
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
            #print(f"Partes do nome (protocolo): {partes}")
            if len(partes) == 3:
                fornecedor = partes[2].strip()
                partes[1] = partes[1].replace('.', '')
                delimitador = re.sub(r'\d', '', partes[1])
                numero_nf = partes[1].split(delimitador)[1].strip().replace('.', '')
                #print(f"Protocolo encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
            elif len(partes) > 3:
                fornecedor = (partes[2]+' - '+partes[3]).strip()
                numero_nf = partes[1].split('NF')[1].strip().replace('.', '')
                #print(f"Protocolo encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
            else:
                print("Formato inválido")
        
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
    with Imbox(env['IMAP_HOST'], env['IMAP_USER'], env['IMAP_PASS']) as imap:
        emails = imap.messages(unread=True,sent_from='leandro.netto@fortanks.ind.br',
                               raw='has:attachment')
        log = {}
        log['total'] = len(emails)
        log['email'] = []
        #log['email'].append({
        #    'subject': msg.subject,
        #    'anexos': len(msg.attachments)
        #    'tipo': tipo
        #    'data': datetime.now()
        #    'email': msg.subject
        #})
        if len(emails) > 0:
            for uid, msg in emails:
                logging.info(f'Processando e-mail: {msg.subject}')
                protocolo = False
                reembolso = False

                nfe = False
                nfe = any(p in msg.subject for p in ASSUNTO_PADRAO_NFE)
                protocolo = any(p in msg.subject for p in ASSUNTO_PADRAO_PROTOCOLO)
                reembolso = any(p in msg.subject for p in ASSUNTO_PADRAO_REEMBOLSO)
                
                tipo = 2 if protocolo else 3 if reembolso else 1 if nfe else 0

                log_email = {
                    'subject': msg.subject,
                    'anexos': len(msg.attachments),
                    'tipo': tipo,
                    'arquivos': [],
                    'codigo_barras': {
                        'qtd_Identificados': 0,
                        'qtd_Nao_Identificados': 0,
                        'qtd_Nao_Identificados_DB': 0,
                        'qtd_Identificados_arquivei': 0,
                        'qtd_Identificados_arquivei_DB': 0,
                        'qtd_Upload_Existente': 0,
                        'qtd_Upload_Realizado': 0
                    }
                }
                #arquivo = {
                #    'filename': filename,
                #    'tipo': tipo,
                #    'chave_acesso': chave_acesso,
                #    'codigo_barra: true/false,
                #    'numero_nf': numero_nf,
                #    'fornecedor': fornecedor
                #}
                if tipo > 0:
                    total = 0
                    ignorado = 0
                    if len(msg.attachments) > 0:
                        anexos_ordenados = sorted(
                            msg.attachments,
                            key=lambda att: (0 if att["filename"].lower().endswith('.xml') else
                                             1 if att["filename"].lower().endswith('.pdf') else 2)
                        )
                        for att in anexos_ordenados:
                            filename = att["filename"]
                            payload = att["content"].getvalue()
                            if filename.lower().endswith('.pdf'):
                                total += 1
                                
                            
                                # Ignora arquivos que contenham 'protocolo' no nome
                                if 'protocolo' in filename.lower():
                                    logging.info(f"Ignorando arquivo de protocolo: {filename}")
                                    ignorado += 1
                                    continue
                                logging.info(f"tentando a chave por codigo de barras do arquivo {filename}")
                                dec1 = None
                                #img = convert_from_bytes(payload,500,poppler_path='/usr/bin/')[0]
                                img = convert_from_bytes(payload,500,poppler_path='/usr/bin/')[0]
                                #print(f"img: {img}")
                                #logging.info(f"img1")
                                decs = decode(img)
                                dec1 = None
                                if decs:
                                    dec = [dec for dec in decs if dec.type == 'CODE128']
                                    tiponf = None
                                    if dec:
                                        dec1 = dec[0].data.decode('utf-8') if dec[0].data else None
                                        tiponf = int(dec1[20:22])
                                    else:
                                        log_email['codigo_barras']['qtd_Nao_Identificados'] += 1
                                        #log_email['codigo_barras']['codigos_nao_identificados'].append(decs)
                                else:
                                    log_email['codigo_barras']['qtd_Nao_Identificados'] += 1
                                if dec1:
                                    logging.info(f"com codigo de barras tipo: {tiponf} dec1: {dec1}")
                                    nota = NotaFiscal.query.filter(NotaFiscal.chave_acesso==dec1).first()
                                    
                                    if nota:
                                        log_email['codigo_barras']['qtd_Identificados'] += 1
                                        #logging.info(f"Nota: {nota.id} {nota.numero_nf}")
                                        up = Upload('NotaFiscal', nota.id, tipo, filename, 'application/pdf')
                                        if up.id:
                                            logging.info(f"upload ja existe {nota.numero_nf}")
                                            log_email['codigo_barras']['qtd_Upload_Existente'] += 1
                                        else:
                                            Upload('NotaFiscal', nota.id, tipo, filename, 'application/pdf', payload)
                                            log_email['codigo_barras']['qtd_Upload_Realizado'] += 1
                                            logging.info(f"upload realizado {nota.numero_nf}")
                                        continue
                                    else:
                                        logging.info(f"tentando cte")
                                        log_email['codigo_barras']['qtd_Nao_Identificados_DB'] += 1
                                        tiponfc = ('nfe' if tiponf == 55 else 'cte' if tiponf == 57 else None)
                                        if tiponfc:
                                            arquivei = Arquivei(chave_acesso=dec1,tipo=tiponfc)
                                            if arquivei.xml_data:
                                                log_email['codigo_barras']['qtd_Identificados_arquivei'] += 1
                                                logging.info(f"achado arquivei")
                                                nota = NotaFiscal(xml_data=arquivei.xml_data,tipo=tiponfc)
                                                if nota:
                                                    log_email['codigo_barras']['qtd_Identificados_arquivei_DB'] += 1
                                                    logging.info(f"fazendo o upload da nota: {nota}")
                                                    up = Upload('NotaFiscal', nota.id, tipo, filename, 'application/pdf', payload)
                                                    if up.id:
                                                        logging.info(f"upload ja existe {nota.numero_nf}")
                                        else:
                                            log_email['codigo_barras']['qtd_Nao_Identificados_DB'] += 1
                                            logging.info(f"codBarras nao identificado {dec1}")
                                            #log_email['codigo_barras']['codigos_nao_identificados'].append(dec1)
                                else:
                                    logging.info(f"tentando pelo numero e fornecedor {filename}")
                                    numero_nf, fornecedor = extrair_numero_fornecedor_do_nome(filename)
                                    if not numero_nf or not fornecedor:
                                        logging.error(f"Não foi possível extrair número da NF ou fornecedor do arquivo: {filename}")
                                        continue
                                
                                    
                                    # Primeiro busca todas as notas com o número correspondente
                                    numero_nf = int(numero_nf.strip())
                                    notas = NotaFiscal.query.filter(NotaFiscal.numero_nf==numero_nf).all()
                                    
                                    # Depois procura a que tem o nome do emitente normalizado correspondente
                                    nota = None 
                                    fornecedor_normalizado = normalizar_texto(fornecedor)
                                    if not notas:
                                        logging.info(f"numero nf {numero_nf} nao encontrado no db")
                                        up = Upload('NotaFiscal', 0, tipo, filename, 'application/pdf')
                                        if up.id:
                                            logging.info(f"upload ja existe sem nota {numero_nf}")
                                        else:
                                            Upload('NotaFiscal', 0, tipo, filename, 'application/pdf', payload)
                                            logging.info(f"upload realizado sem nota {numero_nf}")
                                    else:
                                        for n in notas:
                                            emitente_normalizado = normalizar_texto(n.nome_emitente)
                                            # Verifica se o nome do fornecedor está contido no nome do emitente
                                            if fornecedor_normalizado in emitente_normalizado:
                                                nota = n
                                                break
                                        
                                        if nota:
                                            logging.info(f"nota encontrada {nota.id} {nota.numero_nf}")
                                            try:
                                                up = Upload(pai='NotaFiscal', pai_id=nota.id, tipo=tipo, filename=filename, mimetype='application/pdf')
                                                if up.id:
                                                    logging.info(f"upload ja existe {numero_nf}")
                                                else:
                                                    Upload(pai='NotaFiscal', pai_id=nota.id, tipo=tipo, filename=filename, mimetype='application/pdf', blob=payload)
                                                    logging.info(f"upload realizado {numero_nf}")
                                            except Exception as e:
                                                logging.error(f"Erro ao fazer upload do PDF protocolo para NF {numero_nf}: {e}")
                                        else:
                                            logging.info(f"fornecedor nao encontrado {numero_nf}")
                                            up = Upload(pai='NotaFiscal', pai_id=0, tipo=tipo, filename=filename, mimetype='application/pdf')
                                            if not up.id:
                                                logging.info(f"upload realizado sem nota {numero_nf}")
                                                Upload(pai='NotaFiscal', pai_id=0, tipo=tipo, filename=filename, mimetype='application/pdf', blob=payload)
                                            else:
                                                logging.info(f"upload ja existe sem nota {numero_nf}")
                        
                        # Marcar o email como lido
                
                            if filename.lower().endswith('.xml'):
                                
                                nf=NotaFiscal(xml_data=base64.b64encode(payload).decode('utf-8'))
                                if nf.inserido:
                                    Arquivei(xml_data=base64.b64encode(payload).decode('utf-8'))
                        
                imap.mark_seen(uid)
                logging.info(f'Email {msg.subject} processado com sucesso')
                Logs(local='processar_email',data=datetime.now(),texto=json.dumps(log_email))