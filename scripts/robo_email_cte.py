import os
from imap_tools import MailBox, AND
from dotenv import load_dotenv
import logging
import sys

# Carregar variáveis de ambiente
load_dotenv()

IMAP_HOST = os.getenv('IMAP_HOST')
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASS = os.getenv('IMAP_PASS')
IMAP_FOLDER = 'sfortanks'
ASSUNTO_PADRAO = 'Envio de Nota Fiscal Eletrônica'

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def processar_emails():
    if not IMAP_HOST or not IMAP_USER or not IMAP_PASS:
        logging.error('Credenciais IMAP não configuradas corretamente.')
        return
    with MailBox(host=IMAP_HOST, port=993, timeout=400).login(IMAP_USER, IMAP_PASS) as mailbox:
        # Buscar e-mails não lidos com o assunto padrão
        emails = mailbox.fetch(AND(seen=False, from_='leandro.netto@fortanks.ind.br'))
        xmls = []
        for msg in emails:
            if ASSUNTO_PADRAO in msg.subject:
                logging.info(f'Processando e-mail: {msg.subject} de {msg.from_}')
                xmls_encontrados = 0
                for att in msg.attachments:
                    if att.filename.lower().endswith('.xml'):
                        xml_text = att.payload.decode('utf-8')
                        xmls.append(xml_text)
                        xmls_encontrados += 1

                if xmls_encontrados > 0:
                    mailbox.flag(msg.uid, 'SEEN', True)  # Marca como lido
                    logging.info(f'{xmls_encontrados} XML(s) processados neste e-mail.')
                else:
                    logging.info('Nenhum anexo .xml encontrado neste e-mail.')
        return xmls