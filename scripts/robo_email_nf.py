import os
from imap_tools import MailBoxTls, AND
from dotenv import load_dotenv
import logging
import sys

# Ajustar o path para importar o controller
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from controllers.nota_fiscal_controller import processar_nota_fiscal_xml

# Carregar variáveis de ambiente
load_dotenv()

IMAP_HOST = os.getenv('IMAP_SERVER')
IMAP_USER = os.getenv('MAIL_USERNAME')
IMAP_PASS = os.getenv('MAIL_PASSWORD')
IMAP_FOLDER = 'InBox'
ASSUNTO_PADRAO = 'Envio de Nota Fiscal Eletrônica'

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def processar_emails():
    if not IMAP_HOST or not IMAP_USER or not IMAP_PASS:
        logging.error('Credenciais IMAP não configuradas corretamente.')
        return
    with MailBoxTls(host=IMAP_HOST, port=597, timeout=400).login(IMAP_USER, IMAP_PASS, initial_folder=IMAP_FOLDER) as mailbox:
        # Buscar e-mails não lidos com o assunto padrão
        emails = mailbox.fetch(AND(seen=False, subject=ASSUNTO_PADRAO, from_='leandro.netto@fortanks.ind.br'))
        for msg in emails:
            logging.info(f'Processando e-mail: {msg.subject} de {msg.from_}')
            xmls_encontrados = 0
            for att in msg.attachments:
                if att.filename.lower().endswith('.xml'):
                    xml_text = att.payload.decode('utf-8')
                    try:
                        processar_nota_fiscal_xml(xml_text)
                        xmls_encontrados += 1
                        logging.info(f'Anexo {att.filename} processado com sucesso.')
                    except Exception as e:
                        logging.error(f'Erro ao processar anexo {att.filename}: {e}')
            if xmls_encontrados > 0:
                mailbox.flag(msg.uid, MailBox.flags.SEEN, True)  # Marca como lido
                logging.info(f'{xmls_encontrados} XML(s) processados neste e-mail.')
            else:
                logging.info('Nenhum anexo .xml encontrado neste e-mail.')

def main():
    logging.info('Iniciando robô de leitura de e-mails de NF-e...')
    processar_emails()
    logging.info('Execução finalizada.')

if __name__ == '__main__':
    main() 