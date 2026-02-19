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
from models.usuario import Usuario
from models.logs import Logs
from scripts.processar_email1 import processar_emails
from scripts.importador_dados_analiticos import executar_importacao_async
from controllers.relatorios.script_email import relatorio_semanal


def obter_usuario_sistema():
    """
    Obtém o ID de um usuário admin para executar tarefas do sistema.
    Retorna o primeiro usuário admin encontrado ou None.
    """
    try:
        # Buscar um usuário admin (gerente ou superior)
        usuario = Usuario.query.filter(
            Usuario.cargo_id.in_([4, 5, 16])
        ).first()
        
        if usuario:
            return usuario.id
        
        # Se não encontrar, buscar qualquer usuário
        usuario = Usuario.query.first()
        if usuario:
            return usuario.id
        
        # Se não houver usuários, retornar 0 (será tratado como erro)
        logger.warning("Nenhum usuário encontrado para executar tarefas do sistema")
        return 0
    except Exception as e:
        logger.error(f"Erro ao obter usuário sistema: {str(e)}")
        return 0


def fazer_backup_banco_dados(logs):
    """
    Faz backup completo do banco de dados MySQL.
    Salva o backup em uma pasta dedicada com timestamp no nome do arquivo.
    Remove backups antigos (mantém apenas os últimos 30 dias).
    """
    logs['backup'] = {
        'mensagem': [],
        'erro': False,
        'erro_mensagem': [],
        'erro_traceback': []
        }
    try:
        with app.app_context():
            logger.info("Iniciando backup do banco de dados...")
            
            # Obter URI do banco de dados
            database_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            
            if not database_uri:
                logger.error("DATABASE_URI não configurado")
                return False
            
            # Verificar se é MySQL
            if not database_uri.startswith('mysql'):
                logger.warning(f"Tipo de banco de dados não suportado para backup: {database_uri.split('://')[0]}")
                return False
            
            # Parse da URI do banco de dados
            # Formato: mysql+pymysql://user:password@host:port/database
            parsed = urlparse(database_uri.replace('mysql+pymysql://', 'mysql://'))
            
            # Extrair informações de conexão
            username = 'remote'
            password = os.getenv('DB_PASSWORD')
            host = '192.168.8.10'
            port = 3306
            database = 'sfortanks'
            
            if not all([username, password, host, database]):
                logger.error("Informações de conexão incompletas no DATABASE_URI")
                return False
            
            # Criar pasta de backups se não existir
            backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
                logger.info(f"Pasta de backups criada: {backup_dir}")
            
            # Nome do arquivo de backup com timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{database}_{timestamp}.sql"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Comando mysqldump
            # Usar --single-transaction para garantir consistência sem bloquear tabelas
            # Usar --routines e --triggers para incluir procedures e triggers
            cmd = [
                'mysqldump',
                f'--host={host}',
                f'--port={port}',
                f'--user={username}',
                f'--password={password}',
                '--single-transaction',
                '--routines',
                '--triggers',
                '--events',
                '--quick',
                '--lock-tables=false',
                database
            ]
            
            logger.info(f"Executando backup do banco de dados: {database}")
            logs['backup']['mensagem'].append(f"Executando backup do banco de dados: {database}")
            # Executar mysqldump e salvar em arquivo
            with open(backup_path, 'w', encoding='utf-8') as backup_file:
                result = subprocess.run(
                    cmd,
                    stdout=backup_file,
                    stderr=subprocess.PIPE,
                    text=True
                )
            
            if result.returncode != 0:
                logger.error(f"Erro ao executar mysqldump: {result.stderr}")
                # Remover arquivo de backup parcial se houver erro
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                return False
            
            # Verificar se o arquivo foi criado e tem conteúdo
            if not os.path.exists(backup_path):
                logger.error("Arquivo de backup não foi criado")
                logs['backup']['erro'] = True
                logs['backup']['erro_mensagem'].append(f"Arquivo de backup não foi criado")
                return False
            
            file_size = os.path.getsize(backup_path)
            if file_size == 0:
                logger.error("Arquivo de backup está vazio")
                logs['backup']['erro'] = True
                logs['backup']['erro_mensagem'].append(f"Arquivo de backup está vazio")
                os.remove(backup_path)
                return False
            
            logger.info(f"Backup criado com sucesso: {backup_filename} ({file_size / 1024 / 1024:.2f} MB)")
            logs['backup']['mensagem'].append(f"Backup do banco de dados criado com sucesso: {backup_filename} ({file_size / 1024 / 1024:.2f} MB)")
            # Comprimir o backup para economizar espaço (opcional)
            try:
                compressed_path = f"{backup_path}.gz"
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Remover arquivo não comprimido
                os.remove(backup_path)
                compressed_size = os.path.getsize(compressed_path)
                logger.info(f"Backup comprimido: {backup_filename}.gz ({compressed_size / 1024 / 1024:.2f} MB)")
                backup_path = compressed_path
                logs['backup']['mensagem'].append(f"Backup do banco de dados comprimido com sucesso: {backup_filename}.gz ({compressed_size / 1024 / 1024:.2f} MB)")
            except Exception as e:
                logger.warning(f"Não foi possível comprimir o backup: {str(e)}")
                logs['backup']['erro'] = True
                logs['backup']['erro_mensagem'].append(f"Não foi possível comprimir o backup: {str(e)}")
            
            # Limpar backups antigos (manter apenas os últimos 30 dias)
            try:
                limpar_backups_antigos(backup_dir, dias_manter=30)
            except Exception as e:
                logger.warning(f"Erro ao limpar backups antigos: {str(e)}")
                logs['backup']['erro'] = True
                logs['backup']['erro_mensagem'].append(f"Erro ao limpar backups antigos: {str(e)}")
            logger.info("Backup do banco de dados concluído com sucesso")
            logs['backup']['mensagem'].append(f"Backup do banco de dados concluído com sucesso")
            return True
            
    except Exception as e:
        logger.error(f"Erro ao fazer backup do banco de dados: {str(e)}", exc_info=True)
        logs['backup']['erro'] = True
        logs['backup']['erro_mensagem'].append(f"Erro ao fazer backup do banco de dados: {str(e)}")
        return False


def limpar_backups_antigos(backup_dir, dias_manter=30):
    """
    Remove backups mais antigos que o número de dias especificado.
    
    Args:
        backup_dir: Diretório onde estão os backups
        dias_manter: Número de dias de backups a manter (padrão: 30)
    """
    try:
        if not os.path.exists(backup_dir):
            return
        
        data_limite = datetime.now() - timedelta(days=dias_manter)
        backups_removidos = 0
        espaco_liberado = 0
        
        for filename in os.listdir(backup_dir):
            if not filename.startswith('backup_'):
                continue
            
            filepath = os.path.join(backup_dir, filename)
            
            # Obter data de modificação do arquivo
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if mtime < data_limite:
                try:
                    file_size = os.path.getsize(filepath)
                    os.remove(filepath)
                    backups_removidos += 1
                    espaco_liberado += file_size
                    logger.info(f"Backup antigo removido: {filename}")
                except Exception as e:
                    logger.warning(f"Erro ao remover backup antigo {filename}: {str(e)}")
        
        if backups_removidos > 0:
            logger.info(f"Limpeza concluída: {backups_removidos} backup(s) removido(s), "
                       f"{espaco_liberado / 1024 / 1024:.2f} MB liberado(s)")
        
    except Exception as e:
        logger.error(f"Erro ao limpar backups antigos: {str(e)}", exc_info=True)

def limpar_logs_antigos():
    """
    Remove logs mais antigos que o número de dias especificado.
    """
    try:
        with app.app_context():
            logger.info("Iniciando limpeza de logs antigos...")
            db.session.query(Logs).filter(Logs.data < datetime.now() - timedelta(days=30)).delete(synchronize_session=False)
            db.session.commit()
            logger.info("Limpeza de logs antigos concluída com sucesso")
    except Exception as e:
        logger.error(f"Erro ao limpar logs antigos: {str(e)}", exc_info=True)
def limpar_uploads_antigos():
    """
    Remove uploads mais antigos que o número de dias especificado.
    """
    try:
        with app.app_context():
            logger.info("Iniciando limpeza de uploads antigos...")
            db.session.query(Upload).filter(Upload.tipo == 1, Upload.data < datetime.now() - timedelta(days=60)).delete(synchronize_session=False)
            db.session.commit()
            logger.info("Limpeza de uploads antigos concluída com sucesso")
    except Exception as e:
        logger.error(f"Erro ao limpar uploads antigos: {str(e)}", exc_info=True)
def processar_arquivei():
    """Processa importações do Arquivei"""
    try:
        with app.app_context():
            logs = []
            logger.info("Iniciando processamento do Arquivei...")
            log=NotaFiscal.importar_arquivei(
                data_inicial=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                data_final=(datetime.now()).strftime('%Y-%m-%d'),tipo='nfe'
            )
            logs.append(log)
            log=NotaFiscal.importar_arquivei(
                data_inicial=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                data_final=(datetime.now()).strftime('%Y-%m-%d'),
                tipo='cte'
            )
            logs.append(log)
            log=NotaFiscal.importar_arquivei(
                data_inicial=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                data_final=(datetime.now()).strftime('%Y-%m-%d'),
                tipo='nfse'
            )
            logs.append(log)
            Logs(local="processar_arquivei_automatico", data=datetime.now(), texto=json_dumps_safe(logs))
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
    logs = {
        'backup': {
            'mensagem': [],
            'erro': False,
            'erro_mensagem': [],
            'erro_traceback': []
        },
        'dados_analiticos': {
            'mensagem': [],
            'erro': False,
            'erro_mensagem': [],
            'erro_traceback': []
        }
    }
    try:
        with app.app_context():
            logger.info("Executando job diário...")
            
            logger.info("Iniciando limpeza de logs antigos...")
            limpar_logs_antigos()
            logger.info("Limpeza de logs antigos concluída com sucesso")

            logger.info("Iniciando limpeza de uploads antigos...")
            limpar_uploads_antigos()
            logger.info("Limpeza de uploads antigos concluída com sucesso")
            
            # Fazer backup do banco de dados
            logger.info("Iniciando backup do banco de dados...")
            backup_sucesso = fazer_backup_banco_dados(logs)
            if backup_sucesso:
                logger.info("Backup do banco de dados concluído com sucesso")
            else:
                logger.error("Falha no backup do banco de dados")
            
            # Executar importação de dados analíticos
            usuario_id = obter_usuario_sistema()
            if usuario_id == 0:
                logger.error("Não foi possível obter usuário para executar importação")
                return
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Iniciando extração de dados analíticos...")
            resultado = loop.run_until_complete(
                executar_importacao_async(usuario_id, logs)
            )
            logger.info(f"Resultado da extração: {resultado}")
            loop.close()
            Logs('scheduler_service', datetime.now(),json.dumps(logs))
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
    logs = {
        'backup': {
            'mensagem': [],
            'erro': False,
            'erro_mensagem': [],
            'erro_traceback': []
        }
    }
    fazer_backup_banco_dados(logs)


if __name__ == '__main__':
    main()
