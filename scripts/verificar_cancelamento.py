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
# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
from evolutionapi.client import EvolutionClient
from evolutionapi.models.message import TextMessage, QuotedMessage
import requests
import time
from models.nota_fiscal import NotaFiscal

#from pynfe.processamento.comunicacao import ComunicacaoSefaz
# Carregar variáveis de ambiente
load_dotenv()

EVOLUTION_API_INSTANCE= os.getenv('EVOLUTION_API_INSTANCE')
EVOLUTION_API_TOKEN= os.getenv('EVOLUTION_API_TOKEN')
ARQUIVEI_API_KEY = os.getenv('ARQUIVEI_API_KEY')
ARQUIVEI_API_ID = os.getenv('ARQUIVEI_API_ID')

def verificar():

    nf = db.session.query(NotaFiscal).filter(NotaFiscal.status_processamento == 'importado').all()
    print('quantidade de notas fiscais: ',len(nf))
    i=0
    j=0
    for n in nf:
        if n.verificar_cancelamento():
            print(f"Nota fiscal {n.numero_nf} foi cancelada")
            n.status_processamento = 'cancelada'
            db.session.add(n)
            db.session.commit()

            i+=1
        else:
            print(f"Nota fiscal {n.numero_nf} não foi cancelada")
            j+=1
        print('total: {} canceladas: {} importadas: {}'.format(i+j,i,j))

