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
import tarfile
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
from scripts.email import processar_emails
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


def _encontrar_mysql_binario(nome):
    """Encontra o caminho do executável MySQL (mysqldump ou mysql)."""
    path = shutil.which(nome)
    if path:
        return path
    caminhos_comuns = [
        f'/usr/bin/{nome}',
        f'/usr/local/bin/{nome}',
        f'/opt/mysql/bin/{nome}',
        f'/usr/local/mysql/bin/{nome}'
    ]
    for caminho in caminhos_comuns:
        if os.path.exists(caminho) and os.access(caminho, os.X_OK):
            return caminho
    return None


def _obter_tabelas_mysql(host, port, username, password, database, mysql_path):
    """Obtém lista de tabelas do banco via SHOW TABLES."""
    cmd = [
        mysql_path,
        f'--host={host}',
        f'--port={port}',
        f'--user={username}',
        f'--password={password}',
        '-N',
        database,
        '-e',
        'SHOW TABLES'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        raise RuntimeError(result.stderr or 'Falha ao listar tabelas')
    tabelas = [linha.strip() for linha in result.stdout.strip().splitlines() if linha.strip()]
    return tabelas


def fazer_backup_banco_dados(logs):
    """
    Faz backup do banco de dados MySQL: um arquivo .sql por tabela,
    depois compacta tudo em um único .tar.gz.
    Remove backups antigos (mantém apenas os últimos 30 dias).
    """
    logs['backup'] = {
        'mensagem': [],
        'erro': False,
        'erro_mensagem': [],
        'erro_traceback': []
    }
    try:
        logger.info("Iniciando backup do banco de dados (um .sql por tabela)...")

        database_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not database_uri:
            logger.error("DATABASE_URI não configurado")
            logs['backup']['erro'] = True
            logs['backup']['erro_mensagem'].append("DATABASE_URI não configurado")
            return False

        if not database_uri.startswith('mysql'):
            logger.warning(f"Tipo de banco não suportado para backup: {database_uri.split('://')[0]}")
            return False

        username = 'remote'
        password = os.getenv('DB_PASSWORD')
        host = '192.168.8.10'
        port = 3306
        database = 'sfortanks'

        if not all([username, password, host, database]):
            logger.error("Informações de conexão incompletas no DATABASE_URI")
            logs['backup']['erro'] = True
            logs['backup']['erro_mensagem'].append("Informações de conexão incompletas")
            return False

        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            logger.info(f"Pasta de backups criada: {backup_dir}")

        mysqldump_path = _encontrar_mysql_binario('mysqldump')
        mysql_path = _encontrar_mysql_binario('mysql')
        if not mysqldump_path or not mysql_path:
            logger.error("mysqldump ou mysql não encontrado no sistema.")
            logs['backup']['erro'] = True
            logs['backup']['erro_mensagem'].append("mysqldump ou mysql não encontrado. Verifique se o MySQL está instalado.")
            return False

        logger.info(f"Usando mysqldump: {mysqldump_path}")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dir_backup = os.path.join(backup_dir, f"backup_{database}_{timestamp}")
        os.makedirs(dir_backup, exist_ok=True)

        try:
            tabelas = _obter_tabelas_mysql(host, port, username, password, database, mysql_path)
        except Exception as e:
            logger.error(f"Erro ao listar tabelas: {str(e)}")
            logs['backup']['erro'] = True
            logs['backup']['erro_mensagem'].append(f"Erro ao listar tabelas: {str(e)}")
            if os.path.exists(dir_backup):
                shutil.rmtree(dir_backup, ignore_errors=True)
            return False

        if not tabelas:
            logger.warning("Nenhuma tabela encontrada no banco.")
            logs['backup']['mensagem'].append("Nenhuma tabela encontrada no banco.")

        base_cmd = [
            mysqldump_path,
            f'--host={host}',
            f'--port={port}',
            f'--user={username}',
            f'--password={password}',
            '--single-transaction',
            '--routines',
            '--triggers',
            '--quick',
            '--lock-tables=false',
            database
        ]

        logs['backup']['mensagem'].append(f"Executando backup do banco: {database} ({len(tabelas)} tabelas)")

        for tabela in tabelas:
            sql_path = os.path.join(dir_backup, f"{tabela}.sql")
            cmd = base_cmd + [tabela]
            try:
                with open(sql_path, 'w', encoding='utf-8') as f:
                    result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
                if result.returncode != 0:
                    logger.error(f"Erro ao fazer dump da tabela {tabela}: {result.stderr}")
                    if os.path.exists(sql_path):
                        os.remove(sql_path)
                    continue
            except Exception as e:
                logger.error(f"Erro ao fazer dump da tabela {tabela}: {str(e)}")
                if os.path.exists(sql_path):
                    os.remove(sql_path)
                continue

        # Rotinas e eventos (sem dados de tabelas)
        rotinas_path = os.path.join(dir_backup, '_routines_events.sql')
        cmd_rotinas = [
            mysqldump_path,
            f'--host={host}',
            f'--port={port}',
            f'--user={username}',
            f'--password={password}',
            '--single-transaction',
            '--routines',
            '--events',
            '--no-create-info',
            '--no-data',
            database
        ]
        try:
            with open(rotinas_path, 'w', encoding='utf-8') as f:
                result = subprocess.run(cmd_rotinas, stdout=f, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0 or os.path.getsize(rotinas_path) == 0:
                os.remove(rotinas_path)
            else:
                logger.info("Backup de rotinas e eventos criado: _routines_events.sql")
        except Exception as e:
            if os.path.exists(rotinas_path):
                os.remove(rotinas_path)
            logger.warning(f"Não foi possível exportar rotinas/eventos: {str(e)}")

        # Compactar tudo em um único .tar.gz
        archive_name = f"backup_{database}_{timestamp}.tar.gz"
        archive_path = os.path.join(backup_dir, archive_name)
        try:
            with tarfile.open(archive_path, 'w:gz') as tar:
                for nome in os.listdir(dir_backup):
                    path_completo = os.path.join(dir_backup, nome)
                    if os.path.isfile(path_completo):
                        tar.add(path_completo, arcname=nome)
        except Exception as e:
            import traceback
            logger.error(f"Erro ao compactar backup: {str(e)}")
            logs['backup']['erro'] = True
            logs['backup']['erro_mensagem'].append(f"Erro ao compactar backup: {str(e)}")
            logs['backup']['erro_traceback'].append(traceback.format_exc())
            if os.path.exists(dir_backup):
                shutil.rmtree(dir_backup, ignore_errors=True)
            return False

        shutil.rmtree(dir_backup, ignore_errors=True)
        tamanho_mb = os.path.getsize(archive_path) / 1024 / 1024
        logger.info(f"Backup concluído: {archive_name} ({tamanho_mb:.2f} MB)")
        logs['backup']['mensagem'].append(f"Backup criado com sucesso: {archive_name} ({tamanho_mb:.2f} MB)")

        try:
            limpar_backups_antigos(backup_dir, dias_manter=30)
        except Exception as e:
            logger.warning(f"Erro ao limpar backups antigos: {str(e)}")
            logs['backup']['erro_mensagem'].append(f"Erro ao limpar backups antigos: {str(e)}")

        logs['backup']['mensagem'].append("Backup do banco de dados concluído com sucesso")
        return True

    except Exception as e:
        import traceback
        logger.error(f"Erro ao fazer backup do banco de dados: {str(e)}", exc_info=True)
        logs['backup']['erro'] = True
        logs['backup']['erro_mensagem'].append(f"Erro ao fazer backup: {str(e)}")
        logs['backup']['erro_traceback'].append(traceback.format_exc())
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
            db.session.query(Upload).filter(Upload.tipo == 1, Upload.data < datetime.now() - timedelta(days=180)).delete(synchronize_session=False)
            db.session.commit()
            logger.info("Limpeza de uploads antigos concluída com sucesso")
    except Exception as e:
        logger.error(f"Erro ao limpar uploads antigos: {str(e)}", exc_info=True)
def _consumir_lote_sefaz_xmls(xml_iteravel, *, processar_xml_fn, pendentes, cliente_mi) -> tuple[int, int, list[str]]:
    """
    Para cada XML: SAVEPOINT isolado na sessão SQLAlchemy; um único COMMIT ao final.
    Os arquivos pendentes no disco só são removidos após o commit bem-sucedido,
    garantindo WAL consistente caso o commit falhe.
    """
    confirmados = []
    erros: list[str] = []

    def _marcar_inserido(doc) -> bool:
        dc = getattr(doc, "data_criacao", None)
        return bool(dc and (datetime.now() - dc).total_seconds() < 120)

    for xml in xml_iteravel:
        try:
            with db.session.begin_nested():
                doc = processar_xml_fn(
                    xml,
                    commit_sessao=False,
                    cliente_minio=cliente_mi,
                )
                if not doc:
                    raise RuntimeError("processador devolveu None")
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "ingestao (lote) falhou tipo=%s nsu=%s chave=%s: %s",
                getattr(xml, "tipo", ""),
                getattr(xml, "nsu", ""),
                getattr(xml, "chave", ""),
                exc,
                exc_info=True,
            )
            erros.append(f"{xml.tipo} nsu={xml.nsu}: {exc}")
            continue

        confirmados.append((xml, doc))

    if confirmados:
        try:
            db.session.commit()
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            logger.error("Commit do lote SEFAZ falhou: %s", exc, exc_info=True)
            for xml, doc in confirmados:
                erros.append(
                    f"{xml.tipo} nsu={xml.nsu}: commit lote perdido ({doc.id}): {exc}"
                )
            return 0, 0, erros

    inseridos = existentes = 0
    for xml, doc in confirmados:
        pendentes.remover(xml)
        if _marcar_inserido(doc):
            inseridos += 1
        else:
            existentes += 1

    return inseridos, existentes, erros


def processar_sefaz():
    """
    Baixa XMLs novos da SEFAZ Distribuição DF-e (NFe/CTe) e do ADN (NFSe Nacional)
    e persiste cada XML como `Upload` (MinIO) + `DocumentoSefaz` (DB).

    Cada XML baixado é gravado em `.tmp/sefaz/pendentes/` antes da ingestão
    no DB/MinIO. Se a ingestão falhar (por qualquer motivo), o arquivo
    permanece em disco e a próxima execução o re-processa antes de chamar
    a SEFAZ novamente.

    Cursor de NSU lido do próprio banco (`MAX(DocumentoSefaz.nsu)` por tipo).
    Configuração via .env:
        SEFAZ_PFX        caminho do .pfx/.p12
        SEFAZ_SENHA      senha do certificado
        SEFAZ_CNPJ       14 dígitos
        SEFAZ_UF         opcional (default 35)
        SEFAZ_AMBIENTE   1=produção (default), 2=homologação
    """
    try:
        with app.app_context():
            pfx = os.getenv("SEFAZ_PFX")
            senha = os.getenv("SEFAZ_SENHA")
            cnpj = os.getenv("SEFAZ_CNPJ")
            if not (pfx and senha and cnpj):
                logger.warning(
                    "processar_sefaz: SEFAZ_PFX/SEFAZ_SENHA/SEFAZ_CNPJ não definidos no .env; pulando."
                )
                return
            uf = int(os.getenv("SEFAZ_UF", "35"))
            ambiente = int(os.getenv("SEFAZ_AMBIENTE", "1"))

            from models.documento_sefaz import DocumentoSefaz, processar_xml
            from models.documento_sefaz.services import pendentes
            from models.sefaz_distribuicao import BuscadorXMLs, CertificadoA1

            inseridos = 0
            existentes = 0
            erros: list[str] = []
            re_processados = 0

            from models.upload.services import minio_service

            cliente_mi = minio_service.obter_cliente()

            # ---- 1) Drena pendentes do disco antes de chamar a SEFAZ. ----
            qtd_pendentes = pendentes.contar()
            if qtd_pendentes:
                logger.info("Re-processando %d pendente(s) do disco...", qtd_pendentes)
                lista_reproc = list(pendentes.listar())
                ins_p, ex_p, er_p = _consumir_lote_sefaz_xmls(
                    lista_reproc,
                    processar_xml_fn=processar_xml,
                    pendentes=pendentes,
                    cliente_mi=cliente_mi,
                )
                inseridos += ins_p
                existentes += ex_p
                re_processados += ins_p
                erros.extend(f"[pendente] {msg}" for msg in er_p)

            # ---- 2) Consulta SEFAZ. ----
            logger.info("Iniciando processar_sefaz (CNPJ %s, ambiente=%d)...", cnpj, ambiente)
            cert = CertificadoA1(caminho_pfx=pfx, senha=senha)
            bus = BuscadorXMLs(cert, cnpj=cnpj, uf_autor=uf, ambiente=ambiente)

            ult_nsu_nfe = "000000000000001" if DocumentoSefaz.maior_nsu_por_tipo("nfe") in [None, "0", 0] else DocumentoSefaz.maior_nsu_por_tipo("nfe")
            ult_nsu_cte = "000000000000001" if DocumentoSefaz.maior_nsu_por_tipo("cte") in [None, "0", 0] else DocumentoSefaz.maior_nsu_por_tipo("cte")
            logger.info("Cursor lido do DB: nfe=%s cte=%s", ult_nsu_nfe, ult_nsu_cte)

            lote = bus.buscar(
                ultimo_nsu_nfe=ult_nsu_nfe,
                ultimo_nsu_cte=ult_nsu_cte,
                # NSU já é o filtro natural; sem filtro de data para não descartar eventos.
                incluir_nfse=False,
            )

            xmls_para_wal_e_ingerir = list(lote)
            xml_pos_wal: list = []

            logger.info(
                "lote: %s NFe, %s CTE, %s NFSe (total %s)",
                len(lote.nfe),
                len(lote.cte),
                len(lote.nfse),
                len(xmls_para_wal_e_ingerir),
            )
            # ---- 3) WAL em disco por item; ingestão DB+MinIO num único COMMIT ao final ----
            for xml in xmls_para_wal_e_ingerir:
                try:
                    pendentes.salvar(xml)  # WAL: garante recuperação em caso de falha
                    xml_pos_wal.append(xml)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Falha ao gravar pendente em disco tipo=%s nsu=%s: %s",
                        xml.tipo, xml.nsu, exc, exc_info=True,
                    )
                    erros.append(f"{xml.tipo} nsu={xml.nsu}: pendente disco: {exc}")

            ins_l, ex_l, er_l = _consumir_lote_sefaz_xmls(
                xml_pos_wal,
                processar_xml_fn=processar_xml,
                pendentes=pendentes,
                cliente_mi=cliente_mi,
            )
            inseridos += ins_l
            existentes += ex_l
            erros.extend(er_l)

            resumo = {
                "nfe_baixadas": len(lote.nfe),
                "cte_baixados": len(lote.cte),
                "nfse_baixadas": len(lote.nfse),
                "re_processados_pendentes": re_processados,
                "pendentes_no_inicio": qtd_pendentes,
                "pendentes_no_fim": pendentes.contar(),
                "inseridos": inseridos,
                "existentes": existentes,
                "erros": len(erros),
                "ult_nsu_nfe": lote.ultimo_nsu_nfe,
                "max_nsu_nfe": lote.max_nsu_nfe,
                "ult_nsu_cte": lote.ultimo_nsu_cte,
                "max_nsu_cte": lote.max_nsu_cte,
                "primeiros_erros": erros[:10],
            }
            logger.info(
                "processar_sefaz concluído: %d inseridos (%d eram pendentes), "
                "%d existentes, %d erros (NFe %d/CTe %d). Pendentes em disco: %d",
                inseridos, re_processados, existentes, len(erros),
                len(lote.nfe), len(lote.cte), pendentes.contar(),
            )
            if inseridos > 0 or erros:
                Logs(
                    local="processar_sefaz_automatico",
                    data=datetime.now(),
                    texto=json_dumps_safe(resumo),
                )
    except Exception as e:
        logger.error(f"Erro ao processar SEFAZ: {str(e)}", exc_info=True)


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
            if True:
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
            processar_sefaz()
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

    #job_diario()
    
    try:
        #job_diario()
        #processar_sefaz()
        job_email5min()
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
