"""
Serviço de agendamento de tarefas (scheduler)
Este script deve ser executado como um serviço separado da aplicação principal.
"""
import asyncio
import platform
import logging
import logging.handlers
import os
import sys
import subprocess
import shutil
import gzip
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from urllib.parse import urlparse
import json
from models.database import db
from models.upload import Upload
from models.logs import Logs
from utils.utils import json_dumps_safe
from sqlalchemy import func
from models import (
    NotaFiscal,
    Reembolsos,
    ReembolsosDocumentos,
)
from app import app
# Carregar variáveis de ambiente
load_dotenv('.env')

# Configuração de logs
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configurar o logger
logger = logging.getLogger('scheduler_service')
logger.setLevel(logging.INFO)



def main():
    """Função principal para executar o serviço"""
    try:
        with app.app_context():
            reembolsos = Reembolsos.query.filter(
                func.json_extract(Reembolsos.dados_adicionais, '$.enviado')==True,
                ReembolsosDocumentos.tipo=='nota').\
                join(ReembolsosDocumentos, ReembolsosDocumentos.reembolso_id==Reembolsos.id).\
                join(NotaFiscal, ReembolsosDocumentos.nota_fiscal_id==NotaFiscal.id)
            for reembolso in reembolsos:
                for documento in reembolso.documentos:
                    
                    if documento.tipo == 'nota':
                        print(documento.tipo)
                        nota = NotaFiscal.query.get(documento.nota_fiscal_id)
                        if nota.dados_adicionais:
                            try:
                                dados_adicionais = json.loads(nota.dados_adicionais) if isinstance(nota.dados_adicionais, str) else nota.dados_adicionais
                            except (json.JSONDecodeError, TypeError):
                                dados_adicionais = {}
                            if 'enviado_reembolso' not in dados_adicionais:
                                dados_adicionais['reembolso'] = {
                                    'id': reembolso.id,
                                    'enviado': True
                                }
                                nota.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)
                                print(nota.dados_adicionais)
                                nota.save()
                           

    except Exception as e:
        logger.error(f"Erro no job horário: {str(e)}", exc_info=True)


if __name__ == '__main__':
    main()
