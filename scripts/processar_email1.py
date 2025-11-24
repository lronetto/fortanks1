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
import imaplib

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
ASSUNTO_PADRAO_NFE = ['Envio de Nota Fiscal Eletrônica']
ASSUNTO_PADRAO_CTE = ['Envio de Nota Fiscal Eletrônica - DUA']
ASSUNTO_PADRAO_DUA = ['CTE, NF Fortanks e DUA']
ASSUNTO_PADRAO_PROTOCOLO = ["ENC: NF´S PROTOCOLOS","ENC: NF PROTOCOLO","NF PROTOCOLO","Protocolo"]
ASSUNTO_PADRAO_REEMBOLSO = ['REEMBOLSO','REEBOLSO', 'ENC: REEBOLSO','ENC: reembolso']
EMAIL_DESTINO = 'leandro.netto@fortanks.ind.br'
IMAGEM_MARCA_DAGUA = 'static/img/carimbo_0014-00.png'
NUMBER_WHATSAPP = '5527996440664-1630085280@g.us'

# Configurações para otimização de quota IMAP
MAX_EMAILS_POR_EXECUCAO = int(os.getenv('MAX_EMAILS_POR_EXECUCAO', '10'))  # Limite de emails por execução
DELAY_ENTRE_EMAILS = float(os.getenv('DELAY_ENTRE_EMAILS', '0.5'))  # Delay em segundos entre emails
MARCAR_LIDOS_EM_LOTE = os.getenv('MARCAR_LIDOS_EM_LOTE', 'true').lower() == 'true'  # Marcar emails como lidos em lote
TAMANHO_LOTE_MARCAR_LIDOS = int(os.getenv('TAMANHO_LOTE_MARCAR_LIDOS', '10'))  # Quantidade de emails para marcar em lote

# Configurações para otimização de anexos
MAX_ANEXOS_POR_EMAIL = int(os.getenv('MAX_ANEXOS_POR_EMAIL', '50'))  # Limite de anexos processados por email
TAMANHO_MAX_ANEXO_MB = float(os.getenv('TAMANHO_MAX_ANEXO_MB', '10.0'))  # Tamanho máximo de anexo em MB
PROCESSAR_APENAS_PDF_XML = os.getenv('PROCESSAR_APENAS_PDF_XML', 'true').lower() == 'true'  # Processar apenas PDF e XML
PRIORIZAR_XML = os.getenv('PRIORIZAR_XML', 'true').lower() == 'true'  # Processar XML antes de PDF

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
        logging.info(f"Processando arquivo: {nome_arquivo}")
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

    logging.info('processar_emails')
    quota_exceeded = False
    try:
        with Imbox(env['IMAP_HOST'], env['IMAP_USER'], env['IMAP_PASS']) as imap:
            emails = imap.messages(unread=True,sent_from='leandro.netto@fortanks.ind.br',
                                   raw='has:attachment')
            print(f"emails: {len(emails)}")
            
            log_email = {
                'qtd email': len(emails),
                'processados': 0,
                'email': []
            }
            
            # Limita a quantidade de emails processados por execução
            emails_lista = list(emails)
            total_emails = len(emails_lista)
            emails_para_processar = emails_lista[:MAX_EMAILS_POR_EXECUCAO]
            
            if total_emails > MAX_EMAILS_POR_EXECUCAO:
                logging.info(f'Total de emails: {total_emails}. Processando apenas {MAX_EMAILS_POR_EXECUCAO} por execução para evitar exceder quota.')
            
            # Lista para armazenar UIDs dos emails processados (para marcar como lidos em lote)
            uids_processados = []
            
            if len(emails_para_processar) > 0:
                for idx, (uid, msg) in enumerate(emails_para_processar):
                    # Verifica se já excedeu a quota antes de processar
                    if quota_exceeded:
                        logging.warning('Quota de comandos IMAP excedida. Interrompendo processamento.')
                        break
                    log_email['processados'] += 1
                    logging.info(f'Processando e-mail: {msg.subject}')
                    protocolo = False
                    reembolso = False
                    nfe = False

                    nfe = any(p in msg.subject for p in ASSUNTO_PADRAO_NFE)
                    protocolo = any(p in msg.subject for p in ASSUNTO_PADRAO_PROTOCOLO)
                    reembolso = any(p in msg.subject for p in ASSUNTO_PADRAO_REEMBOLSO)
                    
                    
                    if protocolo:
                        tipo = 2
                    elif reembolso:
                        tipo = 3
                    elif nfe:
                        tipo = 1
                    else:
                        tipo = 0

                    logging.info(f"tipo: {tipo}")
                    
                    #arquivo = {
                    #    'filename': filename,
                    #    'tipo': tipo,
                    #    'chave_acesso': chave_acesso,
                    #    'codigo_barra: true/false,
                    #    'numero_nf': numero_nf,
                    #    'fornecedor': fornecedor
                    #}
                    log_email['email'].append({
                        'subject': msg.subject,
                        'anexos_total': len(msg.attachments),
                        'anexos_processados': 0,
                        'anexos_existentes': {
                            'files': [],
                            'qtd': 0
                        },
                        'tipo': tipo,
                        'anexos': []
                    })
                    if tipo > 0:
                        total = 0
                        ignorado = 0
                        anexos_processados = 0
                        
                        if len(msg.attachments) > 0:
                            # Filtra anexos por tipo se configurado
                            anexos_filtrados = msg.attachments
                            if PROCESSAR_APENAS_PDF_XML:
                                anexos_filtrados = [
                                    att for att in msg.attachments 
                                    if att["filename"].lower().endswith(('.pdf', '.xml'))
                                ]
                                if len(anexos_filtrados) < len(msg.attachments):
                                    logging.info(f'Filtrados {len(msg.attachments) - len(anexos_filtrados)} anexos não-PDF/XML de {len(msg.attachments)} totais')
                            
                            # Ordena anexos (XML primeiro se priorizado, depois PDF, depois outros)
                            if PRIORIZAR_XML:
                                anexos_ordenados = sorted(
                                    anexos_filtrados,
                                    key=lambda att: (
                                        0 if att["filename"].lower().endswith('.xml') else
                                        1 if att["filename"].lower().endswith('.pdf') else 2
                                    )
                                )
                            else:
                                anexos_ordenados = sorted(
                                    anexos_filtrados,
                                    key=lambda att: (0 if att["filename"].lower().endswith('.pdf') else
                                                     1 if att["filename"].lower().endswith('.xml') else 2)
                                )
                            
                            # Limita quantidade de anexos processados
                            total_anexos = len(anexos_ordenados)
                            if total_anexos > MAX_ANEXOS_POR_EMAIL:
                                logging.warning(f'Email tem {total_anexos} anexos. Processando apenas os primeiros {MAX_ANEXOS_POR_EMAIL} para otimização.')
                                anexos_ordenados = anexos_ordenados[:MAX_ANEXOS_POR_EMAIL]
                            
                            for att in anexos_ordenados:
                                # Verifica se já processou o limite de anexos
                                if anexos_processados >= MAX_ANEXOS_POR_EMAIL:
                                    logging.warning(f'Limite de {MAX_ANEXOS_POR_EMAIL} anexos por email atingido. Pulando anexos restantes.')
                                    break
                                
                                filename = att["filename"]
                                
                                if Upload.query.filter(Upload.filename==filename).first():
                                    logging.info(f"arquivo {filename} ja existe no db")
                                    log_email['email'][len(log_email['email'])-1]['anexos_existentes']['files'].append(filename)
                                    log_email['email'][len(log_email['email'])-1]['anexos_existentes']['qtd'] += 1
                                    continue
                                # Verifica tamanho do anexo antes de processar
                                try:
                                    payload = att["content"].getvalue()
                                    tamanho_mb = len(payload) / (1024 * 1024)  # Converte bytes para MB
                                    
                                    if tamanho_mb > TAMANHO_MAX_ANEXO_MB:
                                        logging.warning(f'Anexo {filename} muito grande ({tamanho_mb:.2f} MB). Limite: {TAMANHO_MAX_ANEXO_MB} MB. Pulando.')
                                        ignorado += 1
                                        continue
                                except Exception as e:
                                    logging.error(f'Erro ao verificar tamanho do anexo {filename}: {e}')
                                    continue
                                
                                anexo={
                                    'filename': filename,
                                    'tamanho_mb': round(tamanho_mb, 2),
                                    'codbarras': {
                                        'qtd': 0,
                                        'codigos': []
                                    },
                                    'db':[],
                                    'upload': False,
                                    'nao_identificados':0
                                }
                                
                                anexos_processados += 1

                                if filename.lower().endswith('.pdf'):
                                    total += 1
                                    
                                
                                    # Ignora arquivos que contenham 'protocolo' no nome
                                    if 'protocolo' in filename.lower():
                                        logging.info(f"Ignorando arquivo de protocolo: {filename}")
                                        ignorado += 1
                                        continue
                                    logging.info(f"tentando a chave por codigo de barras do arquivo {filename}")
                                    dec1 = None
                                    #img = convert_from_bytes(payload,500)[0]
                                    img = convert_from_bytes(payload,500,poppler_path='/usr/bin/')[0]
                                    #print(f"img: {img}")
                                    #logging.info(f"img1")
                                    decs = decode(img)
                                    dec1 = None
                                    anexo['codbarras'] = {
                                        'qtd': len(decs),
                                        'codigos': []
                                    }

                                    if decs:
                                        dec = [dec for dec in decs if dec.type == 'CODE128']
                                        tiponf = None
                                        if dec:
                                            dec1 = dec[0].data.decode('utf-8') if dec[0].data else None
                                            tiponf = dec1[20:22]
                            
                                        for dec in decs:
                                            anexo['codbarras']['codigos'].append({
                                                'decodificado': dec.data.decode('utf-8'),
                                                'tiponf': dec.type
                                            })
                                            #log_email['codigo_barras']['codigos_nao_identificados'].append(decs)
                                    if dec1:
                                        logging.info(f"com codigo de barras tipo: {tiponf} dec1: {dec1}")
                                        nota = NotaFiscal.query.filter(NotaFiscal.chave_acesso==dec1).first()
                                        anexo['db'].append({
                                            'chave_acesso': dec1,
                                            'nota': nota.id if nota else None
                                        })
                                        if nota:
                                            #verifica se existe nos uploads se nao existir insere
                                            #logging.info(f"Nota: {nota.id} {nota.numero_nf}")
                                            up = Upload('NotaFiscal', nota.id, tipo, filename, 'application/pdf',payload)
                                            if up:
                                                anexo['upload'] = True
                                                logging.info(f"upload realizado {nota.numero_nf}")
                                            else:
                                                logging.info(f"upload ja existe {nota.numero_nf}")
                                                
                                            continue
                                        else:
                                            tiponfc = ('nfe' if tiponf == 55 else 'cte' if tiponf == 57 else None)
                                            if tiponfc:
                                                arquivei = Arquivei(chave_acesso=dec1,tipo=tiponfc)
                                                if arquivei.xml_data:
                                                    logging.info(f"achado arquivei")
                                                    nota = NotaFiscal(xml_data=arquivei.xml_data,tipo=tiponfc)
                                                    if nota:
                                                        logging.info(f"fazendo o upload da nota: {nota}")
                                                        up = Upload('NotaFiscal', nota.id, tipo, filename, 'application/pdf', payload)
                                                        if up.id:
                                                            logging.info(f"upload ja existe {nota.numero_nf}")
                                            else:
                                                logging.info(f"codBarras nao identificado {dec1}")
                                                anexo['nao_identificados']+=1
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
                                        try:
                                            Arquivei(xml_data=base64.b64encode(payload).decode('utf-8'))
                                        except Exception as e:
                                            logging.error(f"Erro ao processar arquivo xml {filename}: {e}")
                                            continue
                                    else:
                                        logging.info(f"nota fiscal nao inserida {filename}")
                                        continue
                                
                                log_email['email'][len(log_email['email'])-1]['anexos'].append(anexo)
                            
                            # Log de resumo de anexos proxcessados
                            if len(msg.attachments) > 0:
                                logging.info(f'Email processado: {anexos_processados} anexos processados de {len(msg.attachments)} totais (ignorados: {ignorado})')
                                # Atualiza log_email com estatísticas
                                log_email['email'][len(log_email['email'])-1]['anexos_processados'] = anexos_processados
                                log_email['email'][len(log_email['email'])-1]['anexos_ignorados'] = ignorado
         
                    # Adiciona o UID à lista de processados (para marcar como lido em lote)
                    uids_processados.append(uid)
                    
                    # Se está marcando em lote, só marca quando atingir o tamanho do lote ou for o último email
                    if MARCAR_LIDOS_EM_LOTE:
                        deve_marcar_lote = (
                            len(uids_processados) >= TAMANHO_LOTE_MARCAR_LIDOS or 
                            idx == len(emails_para_processar) - 1
                        )
                        
                        if deve_marcar_lote and not quota_exceeded:
                            # Marca todos os UIDs do lote individualmente (mais compatível com diferentes servidores IMAP)
                            try:
                                marcados = 0
                                for uid_lote in uids_processados:
                                    try:
                                        imap.mark_seen(uid_lote)
                                        marcados += 1
                                    except Exception as e_uid:
                                        logging.warning(f'Erro ao marcar UID {uid_lote} como lido: {e_uid}')
                                if marcados > 0:
                                    logging.info(f'{marcados} de {len(uids_processados)} emails marcados como lidos em lote')
                                uids_processados = []  # Limpa a lista após marcar
                            except imaplib.IMAP4.abort as e:
                                error_msg = str(e)
                                if 'OVERQUOTA' in error_msg:
                                    quota_exceeded = True
                                    logging.error(f'Quota de comandos IMAP excedida ao marcar emails como lidos: {error_msg}')
                                    logging.warning(f'{len(uids_processados)} emails foram processados mas não foram marcados como lidos devido à quota excedida')
                                    uids_processados = []
                                else:
                                    logging.error(f'Erro IMAP ao marcar emails como lidos: {error_msg}')
                                    uids_processados = []
                            except Exception as e:
                                logging.error(f'Erro não tratado ao marcar emails como lidos: {e}')
                                uids_processados = []
                    else:
                        # Marca individualmente (comportamento antigo)
                        try:
                            imap.mark_seen(uid)
                            logging.info(f'Email {msg.subject} processado com sucesso')
                        except imaplib.IMAP4.abort as e:
                            error_msg = str(e)
                            if 'OVERQUOTA' in error_msg:
                                quota_exceeded = True
                                logging.error(f'Quota de comandos IMAP excedida ao marcar email como lido: {error_msg}')
                                logging.warning(f'Email {msg.subject} foi processado mas não foi marcado como lido devido à quota excedida')
                            else:
                                logging.error(f'Erro IMAP ao marcar email como lido: {error_msg}')
                                raise
                        except Exception as e:
                            logging.error(f'Erro não tratado ao marcar email como lido: {e}')
                            raise
                    
                    # Adiciona delay entre processamento de emails para reduzir carga no servidor
                    if DELAY_ENTRE_EMAILS > 0 and idx < len(emails_para_processar) - 1:
                        time.sleep(DELAY_ENTRE_EMAILS)
                    
                    # Salva o log apenas se não excedeu a quota (e apenas no final do lote ou último email)
                    if not quota_exceeded and (not MARCAR_LIDOS_EM_LOTE or len(uids_processados) == 0 or idx == len(emails_para_processar) - 1):
                        try:
                            Logs(local='processar_email',data=datetime.now(),texto=json.dumps(log_email))
                        except Exception as e:
                            logging.error(f'Erro ao salvar log: {e}')
                    
                    # Se excedeu a quota, interrompe o processamento
                    if quota_exceeded:
                        logging.warning('Interrompendo processamento devido à quota excedida')
                        break
                
                # Marca qualquer email restante que não foi marcado em lote
                if MARCAR_LIDOS_EM_LOTE and len(uids_processados) > 0 and not quota_exceeded:
                    try:
                        # Marca os emails restantes individualmente (mais compatível com diferentes servidores IMAP)
                        marcados = 0
                        for uid_lote in uids_processados:
                            try:
                                imap.mark_seen(uid_lote)
                                marcados += 1
                            except Exception as e_uid:
                                logging.warning(f'Erro ao marcar UID {uid_lote} como lido: {e_uid}')
                        if marcados > 0:
                            logging.info(f'{marcados} de {len(uids_processados)} emails restantes marcados como lidos')
                    except imaplib.IMAP4.abort as e:
                        error_msg = str(e)
                        if 'OVERQUOTA' in error_msg:
                            logging.error(f'Quota de comandos IMAP excedida ao marcar emails restantes: {error_msg}')
                        else:
                            logging.error(f'Erro IMAP ao marcar emails restantes: {error_msg}')
                    except Exception as e:
                        logging.error(f'Erro ao marcar emails restantes: {e}')
    except imaplib.IMAP4.abort as e:
        error_msg = str(e)
        if 'OVERQUOTA' in error_msg:
            logging.error(f'Quota de comandos IMAP excedida durante operação: {error_msg}')
            logging.warning('Processamento interrompido. Aguarde alguns minutos antes de tentar novamente.')
        else:
            logging.error(f'Erro IMAP não tratado: {error_msg}')
            raise
    except Exception as e:
        logging.error(f'Erro não tratado: {e}')
        raise