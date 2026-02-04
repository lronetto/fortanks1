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
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv('.env')

# Configuração de logs
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configurar o logger
logger = logging.getLogger('scheduler_service')
logger.setLevel(logging.INFO)

# Handler para arquivo
file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(log_dir, 'scheduler.log'),
    maxBytes=10240000,  # 10MB
    backupCount=10
)
file_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
))

# Handler para console
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
))

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Importar o app Flask
from app import app
from models.nota_fiscal import NotaFiscal
from scripts.processar_email1 import processar_emails
from controllers.dados_analiticos_controller import executar_importacao_async
from controllers.relatorios.script_email import relatorio_semanal


def processar_arquivei():
    """Processa importações do Arquivei"""
    try:
        with app.app_context():
            logger.info("Iniciando processamento do Arquivei...")
            NotaFiscal.importar_arquivei(
                data_inicial=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                data_final=(datetime.now()).strftime('%Y-%m-%d')
            )
            NotaFiscal.importar_arquivei(
                data_inicial=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                data_final=(datetime.now()).strftime('%Y-%m-%d'),
                tipo='cte'
            )
            logger.info("Processamento do Arquivei concluído com sucesso")
    except Exception as e:
        logger.error(f"Erro ao processar Arquivei: {str(e)}", exc_info=True)


def job_email5min():
    """Job que executa a cada 5 minutos"""
    try:
        with app.app_context():
            logger.info("Executando job de email (5min)...")
            processar_emails()
            logger.info("Job de email (5min) concluído")
    except Exception as e:
        logger.error(f"Erro no job de email (5min): {str(e)}", exc_info=True)


def job_email15min():
    """Job que executa a cada 15 minutos"""
    try:
        with app.app_context():
            logger.info("Executando job de email (15min)...")
            # Adicionar outras funções aqui se necessário
            # processar_protocolos()
            # processar_reembolsos()
            # processar_notas_fiscais()
            logger.info("Job de email (15min) concluído")
    except Exception as e:
        logger.error(f"Erro no job de email (15min): {str(e)}", exc_info=True)


def job_diario():
    """Job que executa uma vez por dia"""
    try:
        with app.app_context():
            logger.info("Executando job diário...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Iniciando extração de dados analíticos...")
            resultado = loop.run_until_complete(
                executar_importacao_async()
            )
            logger.info(f"Resultado da extração: {resultado}")
            loop.close()
            logger.info("Job diário concluído")
    except Exception as e:
        logger.error(f"Erro no job diário: {str(e)}", exc_info=True)


def job_semanal():
    """Job que executa uma vez por semana (todo domingo às 23:59)"""
    try:
        with app.app_context():
            logger.info("Executando job semanal...")
            relatorio_semanal()
            logger.info("Job semanal concluído")
    except Exception as e:
        logger.error(f"Erro no job semanal: {str(e)}", exc_info=True)


def job_hora():
    """Job que executa a cada hora"""
    try:
        with app.app_context():
            logger.info("Executando job horário...")
            processar_arquivei()
            logger.info("Job horário concluído")
    except Exception as e:
        logger.error(f"Erro no job horário: {str(e)}", exc_info=True)


def iniciar_scheduler():
    """Inicia o scheduler com todos os jobs configurados"""
    try:
        logger.info("Iniciando serviço de scheduler...")
        
        # Criar scheduler
        scheduler = BackgroundScheduler(timezone='America/Sao_Paulo')
        
        # Adicionar jobs
        scheduler.add_job(job_email5min, 'cron', minute='*/5', id='job_email5min')
        logger.info("Job de email (5min) adicionado ao scheduler")
        
        scheduler.add_job(job_email15min, 'cron', minute='*/15', id='job_email15min')
        logger.info("Job de email (15min) adicionado ao scheduler")
        
        scheduler.add_job(job_diario, 'cron', hour=0, minute=0, id='job_diario')
        logger.info("Job diário adicionado ao scheduler")
        
        scheduler.add_job(job_semanal, 'cron', day_of_week='sun', hour=23, minute=59, id='job_semanal')
        logger.info("Job semanal adicionado ao scheduler")
        
        scheduler.add_job(job_hora, 'cron', hour='*', id='job_hora')
        logger.info("Job horário adicionado ao scheduler")
        
        # Iniciar scheduler
        scheduler.start()
        logger.info("Scheduler iniciado com sucesso")
        
        return scheduler
    except Exception as e:
        logger.error(f"Erro ao iniciar scheduler: {str(e)}", exc_info=True)
        raise


def main():
    """Função principal para executar o serviço"""
    sistema = platform.system().lower()
    
    if sistema != 'linux':
        logger.warning(f"Sistema operacional detectado: {sistema}. Scheduler normalmente roda apenas em Linux.")
        logger.info("Iniciando scheduler mesmo assim...")
    
    try:
        scheduler = iniciar_scheduler()
        logger.info("Serviço de scheduler em execução. Pressione Ctrl+C para parar.")
        
        # Manter o script rodando
        import signal
        
        def signal_handler(sig, frame):
            logger.info("Recebido sinal de interrupção. Parando scheduler...")
            scheduler.shutdown()
            logger.info("Scheduler parado com sucesso")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Manter o processo vivo
        while True:
            import time
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Interrupção do teclado detectada. Parando scheduler...")
        if 'scheduler' in locals():
            scheduler.shutdown()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Erro fatal no serviço de scheduler: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
