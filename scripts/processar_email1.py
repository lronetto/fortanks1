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
import email
from email.header import decode_header

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
ASSUNTO_PADRAO_PROTOCOLO = ["ENC: NF´S PROTOCOLOS","ENC: NF PROTOCOLO","NF PROTOCOLO","Protocolo","ENC: PROTOCOLO"]
ASSUNTO_PADRAO_REEMBOLSO = ['REEMBOLSO','REEBOLSO', 'ENC: REEBOLSO','ENC: reembolso']
EMAIL_DESTINO = 'leandro.netto@fortanks.ind.br'
IMAGEM_MARCA_DAGUA = 'static/img/carimbo_0014-00.png'
NUMBER_WHATSAPP = '5527996440664-1630085280@g.us'

# Configurações para otimização de quota IMAP
MAX_EMAILS_POR_EXECUCAO = 20  # Limite de emails por execução (reduzido para evitar quota)
DELAY_ENTRE_EMAILS = float(os.getenv('DELAY_ENTRE_EMAILS', '1.0'))  # Delay em segundos entre emails (aumentado)
DELAY_ENTRE_BUSCAS_IMAP = float(os.getenv('DELAY_ENTRE_BUSCAS_IMAP', '0.5'))  # Delay entre buscas IMAP
MARCAR_LIDOS_EM_LOTE = os.getenv('MARCAR_LIDOS_EM_LOTE', 'true').lower() == 'true'  # Marcar emails como lidos em lote
TAMANHO_LOTE_MARCAR_LIDOS = int(os.getenv('TAMANHO_LOTE_MARCAR_LIDOS', '10'))  # Quantidade de emails para marcar em lote

# Configurações para otimização de anexos
MAX_ANEXOS_POR_EMAIL = int(os.getenv('MAX_ANEXOS_POR_EMAIL', '50'))  # Limite de anexos processados por email
MAX_ANEXOS_POR_EMAIL_PROCESSAR = int(os.getenv('MAX_ANEXOS_POR_EMAIL_PROCESSAR', '50'))  # Limite de anexos processados por email por execução
TAMANHO_MAX_ANEXO_MB = float(os.getenv('TAMANHO_MAX_ANEXO_MB', '10.0'))  # Tamanho máximo de anexo em MB
PROCESSAR_APENAS_PDF_XML = os.getenv('PROCESSAR_APENAS_PDF_XML', 'true').lower() == 'true'  # Processar apenas PDF e XML
PRIORIZAR_XML = os.getenv('PRIORIZAR_XML', 'true').lower() == 'true'  # Processar XML antes de PDF
ORDENAR_EMAILS_POR_ANEXOS = os.getenv('ORDENAR_EMAILS_POR_ANEXOS', 'true').lower() == 'true'  # Ordenar emails por quantidade de anexos (menos primeiro)

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

def contar_anexos_por_header(imap_conn, uid):
    """
    Conta anexos de um email usando apenas o BODYSTRUCTURE, sem baixar o conteúdo.
    Retorna o número de anexos ou 0 se houver erro.
    """
    try:
        # Busca apenas a estrutura do email (BODYSTRUCTURE) - muito mais leve que baixar o email completo
        status, data = imap_conn.fetch(str(uid), '(BODYSTRUCTURE)')
        if status != 'OK' or not data or not data[0]:
            return 0
        
        # Parse do BODYSTRUCTURE
        # O formato retornado pelo imaplib é uma tupla: (b'1 (BODYSTRUCTURE ...)', estrutura_parseada)
        body_data = data[0]
        
        # A estrutura parseada está no segundo elemento da tupla
        estrutura = None
        if isinstance(body_data, tuple):
            if len(body_data) >= 2:
                estrutura = body_data[1]
            elif len(body_data) == 1:
                # Pode estar em formato diferente
                estrutura = body_data[0]
        else:
            estrutura = body_data
        
        if estrutura is None:
            return 0
        
        # Converte toda a estrutura para string para análise
        estrutura_str = str(estrutura).lower()
        estrutura_original = str(estrutura)  # Mantém original para verificação case-sensitive
        
        # Método 1: Conta ocorrências explícitas de "attachment" no disposition (case-insensitive)
        count_attachment = estrutura_str.count('attachment')
        
        # Método 2: Verifica se tem "filename" ou "name" (indicativo de anexo)
        tem_filename = ('filename' in estrutura_str or 'name' in estrutura_str or 
                       'filename' in estrutura_original or 'name' in estrutura_original)
        
        # Método 3: Verifica tipos MIME que geralmente são anexos
        tipos_anexo = ['application/pdf', 'application/zip', 'application/x-zip', 
                      'application/octet-stream', 'image/', 'video/', 'audio/',
                      'application/msword', 'application/vnd.ms-excel',
                      'application/vnd.openxmlformats']
        tem_tipo_anexo = any(tipo in estrutura_str for tipo in tipos_anexo)
        
        # Método 4: Conta partes multipart (cada parte além do corpo pode ser anexo)
        multipart_count = estrutura_str.count('multipart')
        
        # Se encontrou "attachment" explicitamente, usa esse valor
        if count_attachment > 0:
            return count_attachment
        
        # Se tem filename/name E não é apenas text, provavelmente tem anexos
        if tem_filename:
            # Se é multipart, cada parte além do corpo principal pode ser anexo
            if multipart_count > 0:
                # Heurística: multipart geralmente tem 1 corpo + N anexos
                # Conta partes que não são text/plain ou text/html
                partes_nao_texto = estrutura_str.count('application/') + estrutura_str.count('image/') + \
                                  estrutura_str.count('video/') + estrutura_str.count('audio/')
                if partes_nao_texto > 0:
                    return partes_nao_texto
                # Se não encontrou tipos específicos, assume pelo menos 1 anexo se tem filename
                return 1
            else:
                # Email simples com filename = provavelmente é anexo
                return 1
        
        # Se tem tipos de anexo conhecidos, conta
        if tem_tipo_anexo:
            count_tipos = sum(1 for tipo in tipos_anexo if tipo in estrutura_str)
            if count_tipos > 0:
                return count_tipos
        
        # Se tem múltiplos multipart, provavelmente tem anexos
        if multipart_count > 1:
            # Cada multipart adicional além do principal pode indicar anexos
            return multipart_count - 1
        
        # Se não detectou nada, retorna 0 (será processado com prioridade menor)
        return 0
        
    except Exception as e:
        logging.warning(f'Erro ao contar anexos do email UID {uid}: {e}')
        import traceback
        logging.debug(f'Traceback: {traceback.format_exc()}')
        return 0

def buscar_uids_ordenados_por_anexos(imap_host, imap_user, imap_pass, remetente=None, max_emails=None):
    """
    Busca UIDs de emails não lidos com anexos e os ordena por quantidade de anexos
    (menos anexos primeiro), usando apenas BODYSTRUCTURE para evitar exceder quota.
    
    Args:
        imap_host: Host do servidor IMAP
        imap_user: Usuário IMAP
        imap_pass: Senha IMAP
        remetente: Email do remetente para filtrar (opcional)
        max_emails: Número máximo de emails para retornar (opcional)
    
    Retorna lista de UIDs ordenados.
    """
    try:
        # Conecta usando imaplib para ter mais controle
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(imap_user, imap_pass)
        mail.select('INBOX')
        
        # Monta critério de busca como string única (formato IMAP)
        # Nota: "HAS attachment" não é padrão IMAP, então buscamos todos os UNSEEN
        # e depois filtramos pelos que têm anexos usando BODYSTRUCTURE
        if remetente:
            # Formata o email do remetente com aspas
            criterio = f'UNSEEN FROM "{remetente}"'
        else:
            criterio = 'UNSEEN'
        
        # Busca emails não lidos
        status, messages = mail.search(None, criterio)
        if status != 'OK' or not messages[0]:
            mail.close()
            mail.logout()
            logging.info('Nenhum email não lido encontrado com os critérios especificados.')
            return [], {}
        
        uids = messages[0].split()
        total_uids = len(uids)
        
        logging.info(f'Encontrados {total_uids} emails não lidos. Contando anexos para ordenação...')
        
        # Conta anexos de cada email usando apenas BODYSTRUCTURE (muito mais leve)
        # Inclui todos os emails, mesmo se não detectar anexos (para evitar falsos negativos)
        emails_com_contagem = []
        for idx, uid in enumerate(uids):
            try:
                uid_str = uid.decode()
                num_anexos = contar_anexos_por_header(mail, uid_str)
                
                # Debug: loga os primeiros 2 emails para ver o que está acontecendo
                if idx < 2:
                    # Busca o BODYSTRUCTURE novamente para debug
                    status, data = mail.fetch(uid_str, '(BODYSTRUCTURE)')
                    if status == 'OK' and data and data[0]:
                        estrutura_str = str(data[0][1] if len(data[0]) > 1 else data[0]).lower()
                        logging.info(f'UID {uid_str}: num_anexos={num_anexos}, estrutura (primeiros 500 chars): {estrutura_str[:500]}')
                
                # Adiciona todos os emails, mas com num_anexos=0 se não detectou
                # Isso permite ordenar mesmo quando a detecção falha
                # Emails com num_anexos=0 vão para o final (menos prioridade)
                emails_com_contagem.append((uid_str, num_anexos))
                
                if num_anexos == 0 and idx < 5:  # Loga os primeiros 5 que não têm anexos detectados para debug
                    logging.info(f'UID {uid_str}: Nenhum anexo detectado (será processado com prioridade menor)')
                    
                if (idx + 1) % 10 == 0:
                    logging.info(f'Verificados {idx + 1}/{total_uids} emails... ({len(emails_com_contagem)} com anexos encontrados)')
            except Exception as e:
                logging.warning(f'Erro ao processar UID {uid}: {e}')
                import traceback
                logging.debug(f'Traceback: {traceback.format_exc()}')
                # Em caso de erro, pula o email (não assume que tem anexos)
                continue
        
        emails_com_anexos = [e for e in emails_com_contagem if e[1] > 0]
        logging.info(f'Total de {len(emails_com_contagem)} emails processados. {len(emails_com_anexos)} com anexos detectados, {len(emails_com_contagem) - len(emails_com_anexos)} sem anexos detectados (serão processados com prioridade menor).')
        
        # Ordena por quantidade de anexos (menos primeiro)
        emails_com_contagem.sort(key=lambda x: x[1])
        
        # Log da ordenação para debug
        if len(emails_com_contagem) > 0:
            primeiro = emails_com_contagem[0]
            ultimo = emails_com_contagem[-1]
            logging.info(f'Ordenação: Primeiro email (UID {primeiro[0]}) tem {primeiro[1]} anexos, último (UID {ultimo[0]}) tem {ultimo[1]} anexos.')
            if len(emails_com_contagem) <= 10:
                logging.info(f'Lista completa ordenada: {[(uid, count) for uid, count in emails_com_contagem]}')
        
        # Cria dicionário com contagem de anexos por UID
        contagem_anexos_dict = {uid: count for uid, count in emails_com_contagem}
        
        # Retorna apenas os UIDs ordenados, limitado ao máximo se especificado
        if max_emails and len(emails_com_contagem) > max_emails:
            uids_ordenados = [uid for uid, _ in emails_com_contagem[:max_emails]]
            logging.info(f'Selecionados {len(uids_ordenados)} emails com menos anexos para processar (de {len(emails_com_contagem)} totais).')
        else:
            uids_ordenados = [uid for uid, _ in emails_com_contagem]
            logging.info(f'Todos os {len(uids_ordenados)} emails serão processados (ordenados por anexos - menos primeiro).')
        
        mail.close()
        mail.logout()
        
        return uids_ordenados, contagem_anexos_dict
        
    except Exception as e:
        logging.error(f'Erro ao buscar UIDs ordenados: {e}')
        try:
            mail.close()
            mail.logout()
        except:
            pass
        return [], {}

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

def decodificar_assunto_email(subject_raw):
    """
    Decodifica o assunto do email que pode vir codificado (ex: =?iso-8859-1?Q?...?=).
    Retorna o assunto decodificado como string.
    """
    if not subject_raw:
        return ''
    
    # Se for bytes, converte para string primeiro
    if isinstance(subject_raw, bytes):
        try:
            subject_raw = subject_raw.decode('utf-8', errors='ignore')
        except:
            subject_raw = str(subject_raw)
    
    # Se já é uma string decodificada (não começa com =?), retorna
    if isinstance(subject_raw, str) and not subject_raw.strip().startswith('=?'):
        return subject_raw.strip()
    
    try:
        # Decodifica usando email.header.decode_header
        decoded_parts = decode_header(subject_raw)
        decoded_subject = ''
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    # Tenta decodificar com o encoding especificado
                    if encoding:
                        decoded_subject += part.decode(encoding, errors='ignore')
                    else:
                        # Tenta UTF-8 primeiro, depois latin-1 como fallback
                        try:
                            decoded_subject += part.decode('utf-8', errors='ignore')
                        except:
                            decoded_subject += part.decode('latin-1', errors='ignore')
                except Exception:
                    # Fallback: tenta UTF-8 e depois latin-1
                    try:
                        decoded_subject += part.decode('utf-8', errors='ignore')
                    except:
                        decoded_subject += part.decode('latin-1', errors='ignore')
            else:
                decoded_subject += str(part)
        
        return decoded_subject.strip()
    except Exception as e:
        logging.warning(f'Erro ao decodificar assunto do email: {e}')
        # Retorna o assunto original se falhar
        return str(subject_raw).strip()

def determinar_tipo_email(subject):
    """
    Determina o tipo de email baseado no assunto.
    Retorna: 0=desconhecido, 1=NFE, 2=Protocolo, 3=Reembolso
    """
    # Decodifica o assunto antes de verificar
    subject_decodificado = decodificar_assunto_email(subject)
    
    if any(p in subject_decodificado for p in ASSUNTO_PADRAO_PROTOCOLO):
        return 2
    elif any(p in subject_decodificado for p in ASSUNTO_PADRAO_REEMBOLSO):
        return 3
    elif any(p in subject_decodificado for p in ASSUNTO_PADRAO_NFE):
        return 1
    return 0

def extrair_anexos_do_email(msg_obj):
    """
    Extrai anexos de um objeto email.message.Message.
    Retorna lista de anexos no formato compatível com Imbox.
    """
    attachments = []
    for part in msg_obj.walk():
        if not isinstance(part, email.message.Message):
            continue
        
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        
        is_attachment = (disposition == 'attachment') or (filename and disposition != 'inline')
        
        if is_attachment and filename:
            # Decodifica o filename
            try:
                decoded_parts = decode_header(filename)
                decoded_filename = ''
                for header_part, encoding in decoded_parts:
                    if isinstance(header_part, bytes):
                        decoded_filename += header_part.decode(encoding or 'utf-8', errors='ignore')
                    else:
                        decoded_filename += header_part
                filename = decoded_filename
            except Exception as e:
                logging.debug(f'Erro ao decodificar filename: {e}')
            
            # Extrai conteúdo
            try:
                content_bytes = part.get_payload(decode=True)
                if content_bytes and isinstance(content_bytes, bytes):
                    attachments.append({
                        'filename': filename,
                        'content': io.BytesIO(content_bytes)
                    })
            except Exception as e:
                logging.warning(f'Erro ao extrair conteúdo do anexo {filename}: {e}')
    
    return attachments

def buscar_emails_por_uids(env, uids_ordenados, contagem_anexos=None):
    """
    Busca emails individualmente pelos UIDs usando imaplib.
    Retorna lista de tuplas (uid, msg_wrapper).
    
    Args:
        env: Variáveis de ambiente
        uids_ordenados: Lista de UIDs ordenados por quantidade de anexos
        contagem_anexos: Dicionário com contagem de anexos por UID (opcional)
    """
    emails_para_processar = []
    
    # Ajusta limite baseado na quantidade de anexos
    # Se o primeiro email tem muitos anexos, processa apenas 1 email
    limite_emails = MAX_EMAILS_POR_EXECUCAO
    if contagem_anexos and uids_ordenados:
        primeiro_uid = uids_ordenados[0]
        anexos_primeiro = contagem_anexos.get(primeiro_uid, 0)
        if anexos_primeiro > 20:  # Se tem mais de 20 anexos, processa apenas 1
            limite_emails = 1
            logging.info(f'Primeiro email tem {anexos_primeiro} anexos. Processando apenas 1 email por execução para evitar quota.')
        elif anexos_primeiro > 10:  # Se tem mais de 10 anexos, processa apenas 2
            limite_emails = min(2, MAX_EMAILS_POR_EXECUCAO)
            logging.info(f'Primeiro email tem {anexos_primeiro} anexos. Limitando a {limite_emails} emails por execução.')
    
    uids_para_buscar = uids_ordenados[:limite_emails] if len(uids_ordenados) > limite_emails else uids_ordenados
    
    if len(uids_ordenados) > limite_emails:
        logging.info(f'Limitando processamento a {limite_emails} emails (de {len(uids_ordenados)} totais) para evitar quota.')
    
    mail_direct = imaplib.IMAP4_SSL(env['IMAP_HOST'])
    mail_direct.login(env['IMAP_USER'], env['IMAP_PASS'])
    mail_direct.select('INBOX')
    
    try:
        for idx, uid_str in enumerate(uids_para_buscar):
            try:
                # Adiciona delay entre buscas para reduzir carga no servidor
                if idx > 0 and DELAY_ENTRE_BUSCAS_IMAP > 0:
                    time.sleep(DELAY_ENTRE_BUSCAS_IMAP)
                
                status, data = mail_direct.fetch(uid_str, '(RFC822)')
                if status == 'OK' and data and data[0]:
                    email_body = data[0][1]
                    msg_obj = email.message_from_bytes(email_body)
                    attachments = extrair_anexos_do_email(msg_obj)
                    
                    # Cria wrapper compatível com Imbox
                    class MsgWrapper:
                        def __init__(self, msg_obj, attachments, uid):
                            subject_raw = msg_obj.get('Subject', '')
                            self.subject = decodificar_assunto_email(subject_raw)
                            self.attachments = attachments
                            self.uid = uid
                    
                    msg = MsgWrapper(msg_obj, attachments, uid_str)
                    emails_para_processar.append((uid_str, msg))
                    logging.info(f'Email {idx+1}/{len(uids_para_buscar)} (UID {uid_str}): {len(attachments)} anexos - {msg.subject[:60]}...')
            except Exception as e:
                logging.error(f'Erro ao buscar email UID {uid_str}: {e}')
                continue
    finally:
        mail_direct.close()
        mail_direct.logout()
    
    return emails_para_processar

def processar_anexo_pdf(anexo, filename, payload, tipo):
    """
    Processa um anexo PDF: tenta identificar por código de barras ou nome do arquivo.
    Retorna True se processou com sucesso, False caso contrário.
    """
    anexo['codbarras'] = {
        'qtd': 0,
        'codigos': [],
        'erro': None
    }
    # Ignora arquivos que contenham 'protocolo' no nome
    if 'protocolo' in filename.lower():
        logging.info(f"Ignorando arquivo de protocolo: {filename}")
        return False
    
    logging.info(f"tentando a chave por codigo de barras do arquivo {filename}")
    try:
        img = convert_from_bytes(payload, 500,poppler_path='/usr/bin')[0]
    except Exception as e:
        logging.error(f"Erro ao converter o arquivo {filename} para imagem: {e}")
        anexo['codbarras']['erro'].append(str(e))
        img = convert_from_bytes(payload, 500)[0]
        
    
    decs = []
    try:
        decs = decode(img)
        anexo['codbarras']['qtd'] = len(decs)
    except Exception as e:
        logging.error(f"Erro ao decodificar o arquivo {filename}: {e}")
        anexo['codbarras']['erro'].append(str(e))
    
   
    
    dec1 = None
    tiponf = None
    
    if decs:
        for dec in decs:
            anexo['codbarras']['codigos'].append({
                'decodificado': dec.data.decode('utf-8'),
                'tiponf': dec.type
            })
        dec = [dec for dec in decs if dec.type == 'CODE128']
        if dec:
            dec1 = dec[0].data.decode('utf-8') if dec[0].data else None
            tiponf = dec1[20:22] if dec1 and len(dec1) > 22 else None
        else:
            dec = [dec for dec in decs if dec.type == 'QRCODE']
            if dec:
                dec1 = dec[0].data.decode('utf-8') if dec[0].data else None
                if "https://nfe.fazenda.sp.gov.br/CTeConsulta" in dec1:
                    dec1 = dec1.split('=')[1]
                    dec1 = dec1.split('&')[0]
                tiponf ='57'
    
    if dec1:
        logging.info(f"com codigo de barras /qrcode tipo: {tiponf} dec1: {dec1}")
        nota = NotaFiscal.query.filter(NotaFiscal.chave_acesso == dec1).first()
        anexo['db'].append({
            'chave_acesso': dec1,
            'nota': nota.id if nota else None
        })
        
        if nota:
            processar_upload(anexo, nota, filename, payload, tipo)
        else:
            tiponfc = ('nfe' if tiponf == '55' else 'cte' if tiponf == '57' else None)
            if tiponfc:
                arquivei = Arquivei(chave_acesso=dec1, tipo=tiponfc)
                if arquivei.xml_data:
                    logging.info(f"achado arquivei")
                    nota = NotaFiscal(xml_data=arquivei.xml_data, tipo=tiponfc)
                    if nota:
                        logging.info(f"fazendo o upload da nota: {nota}")
                        processar_upload(anexo, nota, filename, payload, tipo)
                    return True
            else:
                logging.info(f"codBarras nao identificado {dec1}")
                anexo['nao_identificados'] += 1
                return False
    else:
        # Tenta pelo número e fornecedor
        logging.info(f"tentando pelo numero e fornecedor {filename}")
        numero_nf, fornecedor = extrair_numero_fornecedor_do_nome(filename)
        if not numero_nf or not fornecedor:
            logging.error(f"Não foi possível extrair número da NF ou fornecedor do arquivo: {filename}")
            return False
        
        numero_nf = int(numero_nf.strip())
        notas = NotaFiscal.query.filter(NotaFiscal.numero_nf == numero_nf).all()
        
        fornecedor_normalizado = normalizar_texto(fornecedor)
        if not notas:
            logging.info(f"numero nf {numero_nf} nao encontrado no db")
            up = Upload('NotaFiscal', 0, tipo, filename, 'application/pdf')
            if not up.id:
                Upload('NotaFiscal', 0, tipo, filename, 'application/pdf', payload)
                logging.info(f"upload realizado sem nota {numero_nf}")
            return True
        else:
            nota = None
            for n in notas:
                emitente_normalizado = normalizar_texto(n.nome_emitente)
                if fornecedor_normalizado in emitente_normalizado:
                    nota = n
                    break
            
            if nota:
                logging.info(f"nota encontrada {nota.id} {nota.numero_nf}")
                try:
                    up = Upload(pai='NotaFiscal', pai_id=nota.id, tipo=tipo, filename=filename, mimetype='application/pdf')
                    if not up.id:
                        Upload(pai='NotaFiscal', pai_id=nota.id, tipo=tipo, filename=filename, mimetype='application/pdf', blob=payload)
                        logging.info(f"upload realizado {numero_nf}")
                    return True
                except Exception as e:
                    logging.error(f"Erro ao fazer upload do PDF protocolo para NF {numero_nf}: {e}")
                    return False
            else:
                logging.info(f"fornecedor nao encontrado {numero_nf}")
                up = Upload(pai='NotaFiscal', pai_id=0, tipo=tipo, filename=filename, mimetype='application/pdf')
                if not up.id:
                    Upload(pai='NotaFiscal', pai_id=0, tipo=tipo, filename=filename, mimetype='application/pdf', blob=payload)
                    logging.info(f"upload realizado sem nota {numero_nf}")
                return True

def processar_anexo_xml(filename, payload,log_email_entry):
    """
    Processa um anexo XML: cria NotaFiscal e Arquivei.
    Retorna True se processou com sucesso, False caso contrário.
    """
    try:
        chave_acesso = filename.split('.')[0]
        if len(chave_acesso) == 44:
            tipo = 'cte' if chave_acesso[20:22] == '57' else 'nfe' if chave_acesso[20:22] == '55' else None
            
        nf = NotaFiscal(xml_data=base64.b64encode(payload).decode('utf-8'), tipo=tipo)
        if nf.inserido:
            try:
                resp= Arquivei(xml_data=base64.b64encode(payload).decode('utf-8'))
                log_email_entry['arquivei'].append({
                    'arquivei': resp.json(),
                    'chave_acesso': chave_acesso,
                    'tipo': tipo,
                })
                return True
            except Exception as e:
                logging.error(f"Erro ao processar arquivo xml {filename}: {e}")
                return False
        else:
            logging.info(f"nota fiscal nao inserida {filename}")
            return False
    except Exception as e:
        logging.error(f"Erro ao processar XML {filename}: {e}")
        return False

def marcar_email_como_lido(uid, usar_imaplib, mail_marcar=None, imap=None):
    """
    Marca um email como lido usando imaplib ou Imbox.
    """
    try:
        if usar_imaplib and mail_marcar:
            mail_marcar.store(str(uid), '+FLAGS', '\\Seen')
        elif imap:
            imap.mark_seen(uid)
        return True
    except Exception as e:
        logging.warning(f'Erro ao marcar UID {uid} como lido: {e}')
        return False

def processar_upload(anexo, nota, filename, payload, tipo):
    up = Upload.query.filter(Upload.filename==filename).first()
    if not up:
        up = Upload('NotaFiscal', nota.id, tipo, filename, 'application/pdf', payload)
        if up.id:
            anexo['upload'] = True
            logging.info(f"upload realizado {nota.numero_nf}")
            return True
        else:
            logging.info(f"upload ja existe {nota.numero_nf}")
            return False
    else:
        if up.nota == nota.id and up.tipo == tipo and up.mimetype == 'application/pdf':
            anexo['upload'] = True
            logging.info(f"upload ja existe {nota.numero_nf}")
        else:
            up.nota = nota.id
            up.tipo = tipo
            up.mimetype = 'application/pdf'
            up.save()
            logging.info(f"upload atualizado {nota.numero_nf}")
            anexo['upload'] = True
def processar_anexos_email(msg, tipo, log_email_entry):
    """
    Processa todos os anexos de um email.
    Retorna: (anexos_processados, ignorado, total_nao_processados)
    """
    if not msg.attachments or len(msg.attachments) == 0:
        return 0, 0, 0
    
    # Filtra e ordena anexos
    anexos_filtrados = msg.attachments
    if PROCESSAR_APENAS_PDF_XML:
        anexos_filtrados = [att for att in msg.attachments if att["filename"].lower().endswith(('.pdf', '.xml'))]
        if len(anexos_filtrados) < len(msg.attachments):
            logging.info(f'Filtrados {len(msg.attachments) - len(anexos_filtrados)} anexos não-PDF/XML de {len(msg.attachments)} totais')
    
    # Ordena anexos
    if PRIORIZAR_XML:
        anexos_ordenados = sorted(anexos_filtrados, key=lambda att: (
            0 if att["filename"].lower().endswith('.xml') else
            1 if att["filename"].lower().endswith('.pdf') else 2
        ))
    else:
        anexos_ordenados = sorted(anexos_filtrados, key=lambda att: (
            0 if att["filename"].lower().endswith('.pdf') else
            1 if att["filename"].lower().endswith('.xml') else 2
        ))
    
    # Filtra anexos já processados
    anexos_nao_processados = []
    for att in anexos_ordenados:
        filename = att["filename"]
        if Upload.query.filter(Upload.filename == filename).first():
            logging.info(f"arquivo {filename} ja existe no db")
            log_email_entry['anexos_existentes']['files'].append(filename)
            log_email_entry['anexos_existentes']['qtd'] += 1
        else:
            anexos_nao_processados.append(att)

    total_anexos = len(anexos_ordenados)
    total_nao_processados = len(anexos_nao_processados)
    
    if total_anexos > MAX_ANEXOS_POR_EMAIL:
        logging.warning(f'Email tem {total_anexos} anexos. Limite máximo por email: {MAX_ANEXOS_POR_EMAIL}.')
    
    # Processa apenas um número limitado de anexos por execução
    anexos_para_processar = anexos_nao_processados[:MAX_ANEXOS_POR_EMAIL_PROCESSAR]
    
    if total_nao_processados > MAX_ANEXOS_POR_EMAIL_PROCESSAR:
        logging.info(f'Email tem {total_nao_processados} anexos não processados. Processando apenas {MAX_ANEXOS_POR_EMAIL_PROCESSAR} nesta execução.')
    
    anexos_processados = 0
    ignorado = 0
    
    for att in anexos_para_processar:
        if anexos_processados >= MAX_ANEXOS_POR_EMAIL_PROCESSAR:
            logging.warning(f'Limite de {MAX_ANEXOS_POR_EMAIL_PROCESSAR} anexos por email por execução atingido.')
            break
        
        filename = att["filename"]
        
        # Verifica tamanho do anexo
        try:
            payload = att["content"].getvalue()
            tamanho_mb = len(payload) / (1024 * 1024)
            
            if tamanho_mb > TAMANHO_MAX_ANEXO_MB:
                logging.warning(f'Anexo {filename} muito grande ({tamanho_mb:.2f} MB). Limite: {TAMANHO_MAX_ANEXO_MB} MB. Pulando.')
                ignorado += 1
                continue
        except Exception as e:
            logging.error(f'Erro ao verificar tamanho do anexo {filename}: {e}')
            continue
        
        anexo = {
            'filename': filename,
            'tamanho_mb': round(tamanho_mb, 2),
            'codbarras': {'qtd': 0, 'codigos': []},
            'db': [],
            'upload': False,
            'nao_identificados': 0
        }
        
        anexos_processados += 1
        
        # Processa PDF ou XML
        if filename.lower().endswith('.pdf'):
            processar_anexo_pdf(anexo, filename, payload, tipo)
        elif filename.lower().endswith('.xml'):
            processar_anexo_xml(filename, payload, log_email_entry)
        
        log_email_entry['anexos'].append(anexo)
    
    return anexos_processados, ignorado, total_nao_processados

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
        # Se ordenação por anexos estiver habilitada, busca UIDs ordenados usando apenas headers
        uids_ordenados = []
        contagem_anexos = {}
        if ORDENAR_EMAILS_POR_ANEXOS:
            logging.info('Buscando emails ordenados por quantidade de anexos (usando apenas BODYSTRUCTURE)...')
            uids_ordenados, contagem_anexos = buscar_uids_ordenados_por_anexos(
                env['IMAP_HOST'], 
                env['IMAP_USER'], 
                env['IMAP_PASS'],
                remetente='leandro.netto@fortanks.ind.br',
                max_emails=MAX_EMAILS_POR_EXECUCAO
            )
            if not uids_ordenados:
                logging.info('Nenhum email encontrado ou erro ao buscar UIDs ordenados.')
                return
        
        # Busca emails: usa imaplib se temos UIDs ordenados, senão usa Imbox (fallback)
        if uids_ordenados:
            total_emails_ordenados = len(uids_ordenados)
            logging.info(f'Encontrados {total_emails_ordenados} emails ordenados por quantidade de anexos.')
            logging.info(f'UIDs ordenados (menos anexos primeiro): {uids_ordenados[:5]}...' if len(uids_ordenados) > 5 else f'UIDs ordenados: {uids_ordenados}')
            logging.info('Buscando emails individualmente do servidor (um por vez na ordem otimizada)...')
            
            emails_para_processar = buscar_emails_por_uids(env, uids_ordenados, contagem_anexos)
            logging.info(f'{len(emails_para_processar)} emails encontrados e ordenados corretamente (menos anexos primeiro).')
            usar_imaplib_para_marcar = True
        else:
            # Fallback: busca todos os emails não lidos com anexos usando Imbox
            usar_imaplib_para_marcar = False
            with Imbox(env['IMAP_HOST'], env['IMAP_USER'], env['IMAP_PASS']) as imap:
                emails = imap.messages(unread=True, sent_from='leandro.netto@fortanks.ind.br',
                                       raw='has:attachment')
                emails_lista = list(emails)
                total_emails = len(emails_lista)
                emails_para_processar = emails_lista[:MAX_EMAILS_POR_EXECUCAO]
                if total_emails > MAX_EMAILS_POR_EXECUCAO:
                    logging.info(f'Total de emails: {total_emails}. Processando apenas {MAX_EMAILS_POR_EXECUCAO} por execução para evitar exceder quota.')
            
        print(f"emails: {len(emails_para_processar)}")
        
        log_email = {
            'qtd email': len(emails_para_processar),
            'processados': 0,
            'email': []
        }
        
        # Lista para armazenar UIDs dos emails processados (para marcar como lidos em lote)
        uids_processados = []
        
        # Prepara conexão imaplib para marcar como lido se necessário
        if usar_imaplib_para_marcar:
            mail_marcar = imaplib.IMAP4_SSL(env['IMAP_HOST'])
            mail_marcar.login(env['IMAP_USER'], env['IMAP_PASS'])
            mail_marcar.select('INBOX')
            imap = None  # Não usa Imbox
        else:
            mail_marcar = None  # Usa Imbox para marcar
        
        if len(emails_para_processar) > 0:
            for idx, (uid, msg) in enumerate(emails_para_processar):
                # Verifica se já excedeu a quota antes de processar
                if quota_exceeded:
                    logging.warning('Quota de comandos IMAP excedida. Interrompendo processamento.')
                    break
                log_email['processados'] += 1
                num_anexos_email = len(msg.attachments) if msg.attachments else 0
                logging.info(f'[{idx+1}/{len(emails_para_processar)}] Processando e-mail (UID {uid}): {num_anexos_email} anexos - {msg.subject}')
                
                tipo = determinar_tipo_email(msg.subject)
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
                    log_email_entry = log_email['email'][-1]
                    anexos_processados, ignorado, total_nao_processados = processar_anexos_email(msg, tipo, log_email_entry)
                    
                    # Atualiza log com estatísticas
                    if len(msg.attachments) > 0:
                        anexos_existentes_qtd = log_email_entry['anexos_existentes']['qtd']
                        anexos_restantes = total_nao_processados - anexos_processados
                        logging.info(f'Email processado: {anexos_processados} anexos novos processados, {anexos_existentes_qtd} já existiam, {anexos_restantes} restantes para próxima execução (total: {len(msg.attachments)}, ignorados: {ignorado})')
                        log_email_entry['anexos_processados'] = anexos_processados
                        log_email_entry['anexos_ignorados'] = ignorado
                        log_email_entry['anexos_restantes'] = anexos_restantes
        
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
                                    if usar_imaplib_para_marcar:
                                        # Usa imaplib para marcar como lido
                                        mail_marcar.store(uid_lote, '+FLAGS', '\\Seen')
                                    else:
                                        # Usa Imbox para marcar como lido
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
                        if usar_imaplib_para_marcar:
                            # Usa imaplib para marcar como lido
                            mail_marcar.store(str(uid), '+FLAGS', '\\Seen')
                        else:
                            # Usa Imbox para marcar como lido
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
                            if usar_imaplib_para_marcar:
                                # Usa imaplib para marcar como lido
                                mail_marcar.store(str(uid_lote), '+FLAGS', '\\Seen')
                            else:
                                # Usa Imbox para marcar como lido
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
            
            # Fecha conexão imaplib se foi usada
            if usar_imaplib_para_marcar and mail_marcar:
                try:
                    mail_marcar.close()
                    mail_marcar.logout()
                except:
                    pass
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
    