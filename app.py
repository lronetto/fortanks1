import asyncio
from controllers.seguranca_controller import seguranca_bp
from controllers.colaborador_controller import colaborador_bp
from controllers.equipamento_controller import equipamento_bp
from controllers.concretagem_controller import concretagem
from controllers.api_controller import api_bp
from controllers.peca_controller import peca
from controllers.tanque_controller import tanque_bp
from controllers.cliente_controller import cliente_bp
from controllers.usuario_controller import usuario_bp
from controllers.plano_conta_controller import plano_conta_bp
from controllers.material_controller import material_bp
from controllers.contrato_controller import contrato_bp
from controllers.centro_custo_controller import centro_custo_bp
from controllers.dashboard_controller import dashboard_bp
from controllers.admin_controller import admin_bp
from controllers.auth_controller import auth_bp
from controllers.usinagem_concreto_controller import usinagem_concreto
from controllers.conversao_unidade_controller import conversao_unidade_bp
from controllers.solicitacao_controller import solicitacao_bp
from controllers.cargo_controller import cargo_bp
from controllers.departamento_controller import departamento_bp
from controllers.nota_fiscal_controller import nota_fiscal_bp
from controllers.estoque_controller import estoque_bp
from controllers.unidade_controller import unidade_bp
from controllers.produto_composto_controller import produto_composto_bp
from controllers.dados_analiticos_controller import dados_analiticos_bp
from controllers.usinagem_relatorio_controller import relatorio_usinagem_bp
from controllers.reembolso_controller import reembolso_bp, notas_json, avulsos_json
from controllers.acabamento_transporte_controller import acabamento_transporte_bp
from models.usuario import Usuario
from models.arquivei import Arquivei
from models.nota_fiscal import NotaFiscal
# Isso carregará e configurará todos os modelos
from models import configure_mappers
from models.database import db, init_db
from config.config import Config
from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sys
from datetime import datetime, timedelta
from werkzeug.exceptions import HTTPException
from flask_migrate import Migrate
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_sslify import SSLify
from logging.handlers import RotatingFileHandler
from flask_mail import Mail
from dotenv import load_dotenv
from scripts.processar_email1 import processar_emails
from apscheduler.schedulers.background import BackgroundScheduler
from controllers.relatorio_controller import relatorio_bp
from controllers.dados_analiticos_controller import executar_importacao_async
from controllers.upload_controller import upload_bp
load_dotenv('.env')

# Configuração de logs
import logging
from logging.handlers import RotatingFileHandler
import os

# Criar diretório de logs se não existir
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Criar a aplicação Flask
app = Flask(__name__, template_folder='templates', static_folder='static')


#sslify = SSLify(app)
# Configurar o logger da aplicação
if False:
    # Configurar o handler para arquivo
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'fortanks.log'),
        maxBytes=10240000,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    # Configurar o handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    ))
    console_handler.setLevel(logging.INFO)
    app.logger.addHandler(console_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Fortanks startup')

# Configurar o logger do módulo
logger = app.logger

# Log de inicialização
logger.info("Iniciando aplicação Flask...")

# Criar a aplicação Flask
logger.info("Criando instância da aplicação Flask...")

app.config.from_object(Config)
CORS(app)  # Habilitar CORS para todas as rotas
mail = Mail(app)

# Inicializar proteção CSRF
csrf = CSRFProtect(app)
logger.info("CSRF Protection inicializada...")

# Isentar algumas rotas da proteção CSRF
@csrf.exempt
def csrf_exempt_rule():
    # Lista de padrões de URL que serão isentos de proteção CSRF
    exempt_urls = [
        '/concretagens/api/tanques/pecas',
        '/concretagens/api/concretagem',
    ]
    
    for url in exempt_urls:
        if request.path.startswith(url):
            return True
    return False

# Manipulador de erro para CSRF
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.error(f"Erro CSRF: {str(e)}")
    return jsonify({"error": "CSRF token inválido ou ausente", "message": str(e)}), 400

# Inicializar os componentes
logger.info("Inicializando SQLAlchemy...")
db.init_app(app)


# Inicializar Flask-Migrate
logger.info("Inicializando Flask-Migrate...")
migrate = Migrate(app, db)

# Importar explicitamente todos os modelos para garantir carregamento correto
# A ordem aqui é importante!
logger.info("Configurando mappers do SQLAlchemy...")

# Importar os blueprints após a inicialização do db
logger.info("Importando modelos e controladores...")
# from controllers.fornecedor_controller import fornecedor_bp

# Inicializar o login manager
logger.info("Inicializando Login Manager...")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# Registrar os blueprints (modularização)
logger.info("Registrando blueprints...")
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
app.register_blueprint(centro_custo_bp, url_prefix='/centro-custo')
app.register_blueprint(contrato_bp, url_prefix='/contrato')
app.register_blueprint(material_bp, url_prefix='/material')
app.register_blueprint(plano_conta_bp, url_prefix='/plano-conta')
app.register_blueprint(usuario_bp, url_prefix='/usuarios')
app.register_blueprint(cliente_bp, url_prefix='/clientes')
app.register_blueprint(tanque_bp, url_prefix='/tanques')
app.register_blueprint(peca, url_prefix='/pecas')
app.register_blueprint(concretagem, url_prefix='/concretagens')
app.register_blueprint(equipamento_bp, url_prefix='/equipamentos')
app.register_blueprint(colaborador_bp, url_prefix='/colaboradores')
# Registrar o blueprint unificado seguranca_bp e aliases
app.register_blueprint(seguranca_bp, url_prefix='/seguranca')
# app.register_blueprint(fornecedor_bp, url_prefix='/fornecedores')
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(usinagem_concreto, url_prefix='/usinagem-concreto')
app.register_blueprint(conversao_unidade_bp,url_prefix='/conversao-unidade')
app.register_blueprint(solicitacao_bp, url_prefix='/solicitacoes')
app.register_blueprint(cargo_bp, url_prefix='/cargos')
app.register_blueprint(departamento_bp, url_prefix='/departamentos')
app.register_blueprint(nota_fiscal_bp, url_prefix='/notas-fiscais')
app.register_blueprint(estoque_bp, url_prefix='/estoque')
app.register_blueprint(unidade_bp)
app.register_blueprint(produto_composto_bp, url_prefix='/produto-composto')
app.register_blueprint(dados_analiticos_bp, url_prefix='/dados-analiticos')
app.register_blueprint(relatorio_usinagem_bp)
app.register_blueprint(reembolso_bp, url_prefix='/reembolsos')
app.register_blueprint(relatorio_bp, url_prefix='/relatorios')
app.register_blueprint(acabamento_transporte_bp, url_prefix='/acabamento-transporte')
app.register_blueprint(upload_bp, url_prefix='/uploads')
logger.info("Blueprints registrados com sucesso!")

# Registrar comandos CLI
#logger.info("Registrando comandos CLI...")
#from commands.estoque_commands import register_commands as register_estoque_commands
#register_estoque_commands(app)
#logger.info("Comandos CLI registrados com sucesso!")

@app.route('/')
def index():
    return redirect(url_for('auth.login'))


@app.context_processor
def utility_processor():
    """
    Adiciona funções úteis ao contexto dos templates
    """
    def get_current_year():
        return datetime.now().year

    def is_active(route):
        if request.path.startswith(f'/{route}'):
            return 'active'
        return ''

    def formatcnpj(value):
        """Formata um CNPJ no padrão XX.XXX.XXX/XXXX-XX"""
        if not value:
            return ""
        # Remove caracteres não numéricos
        cnpj = ''.join(filter(str.isdigit, str(value)))
        if len(cnpj) != 14:
            return value
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

    return dict(
        get_current_year=get_current_year,
        is_active=is_active,
        formatcnpj=formatcnpj
    )


@app.errorhandler(400)
def bad_request(e):
    """
    Manipulador para erro 400 - Bad Request
    """
    if current_user.is_authenticated:
        return render_template('common/error.html', error_code=400,
                               error_title="Requisição Inválida",
                               error_message="O servidor não pode processar a requisição devido a um erro do cliente."), 400
    else:
        return render_template('common/error_public.html', error_code=400,
                               error_title="Requisição Inválida",
                               error_message="O servidor não pode processar a requisição devido a um erro do cliente."), 400


@app.errorhandler(401)
def unauthorized(e):
    """
    Manipulador para erro 401 - Unauthorized
    """
    return render_template('common/error_public.html', error_code=401,
                           error_title="Não Autorizado",
                           error_message="É necessário autenticar-se para acessar este recurso."), 401


@app.errorhandler(403)
def forbidden(e):
    """
    Manipulador para erro 403 - Forbidden
    """
    if current_user.is_authenticated:
        return render_template('common/403.html'), 403
    else:
        return render_template('common/error_public.html', error_code=403,
                               error_title="Acesso Proibido",
                               error_message="Você não tem permissão para acessar este recurso."), 403


@app.errorhandler(404)
def page_not_found(e):
    """
    Manipulador para erro 404 - Not Found
    """
    if current_user.is_authenticated:
        return render_template('common/404.html'), 404
    else:
        return render_template('common/error_public.html', error_code=404,
                               error_title="Página Não Encontrada",
                               error_message="O recurso solicitado não foi encontrado no servidor."), 404


@app.errorhandler(500)
def internal_server_error(e):
    """
    Manipulador para erro 500 - Internal Server Error
    """
    logger.error(f"Erro 500: {str(e)}")
    if current_user.is_authenticated:
        return render_template('common/500.html'), 500
    else:
        return render_template('common/error_public.html', error_code=500,
                               error_title="Erro Interno do Servidor",
                               error_message="O servidor encontrou uma situação inesperada que o impediu de atender à solicitação."), 500

# Manipulador genérico para outros erros HTTP


@app.errorhandler(Exception)
def handle_exception(e):
    """
    Manipulador genérico para outras exceções
    """
    # Se for um erro HTTP conhecido, obtém o código
    if isinstance(e, HTTPException):
        code = e.code
        name = e.name
        description = e.description
    else:
        # Para exceções não-HTTP, considera como 500
        code = 500
        name = "Erro Interno do Servidor"
        description = "Ocorreu um erro inesperado no servidor."
        # Logar o erro para análise posterior
        logger.error(f"Erro não tratado: {str(e)}", exc_info=True)

    # Verifica se o usuário está autenticado
    if current_user.is_authenticated:
        return render_template('common/error.html',
                               error_code=code,
                               error_title=name,
                               error_message=description), code
    else:
        return render_template('common/error_public.html',
                               error_code=code,
                               error_title=name,
                               error_message=description), code
def processar_arquivei():
    NotaFiscal.importar_arquivei(data_inicial=(datetime.now()-timedelta(days=1)).strftime('%Y-%m-%d'),data_final=(datetime.now()).strftime('%Y-%m-%d'))
    NotaFiscal.importar_arquivei(data_inicial=(datetime.now()-timedelta(days=1)).strftime('%Y-%m-%d'),data_final=(datetime.now()).strftime('%Y-%m-%d'),tipo='cte')
def job_email5min():
    with app.app_context():
        processar_emails()
        #processar_protocolos()
        #processar_reembolsos()
        #processar_notas_fiscais()

def job_email15min():
    with app.app_context():
        #processar_protocolos()
        #processar_reembolsos()
        pass
        
        #processar_notas_fiscais()
def job_diario():
    """
    Job que executa uma vez por dia
    """
    with app.app_context():
        logger.info("Executando job diário...")
        loop = asyncio.new_event_loop() 
        asyncio.set_event_loop(loop)
        logger.info("Iniciando extração de dados analíticos...")
        resultado = loop.run_until_complete(
                executar_importacao_async(0)
            )  
        logger.info(f"Resultado da extração: {resultado}")
        # Aqui você pode adicionar as funções que deseja executar diariamente
        # Por exemplo:
        # processar_relatorios_diarios()
        # enviar_relatorio_diario()
        # etc...

def job_semanal():
    """
    Job que executa uma vez por semana (todo domingo às 00:00)
    """
    with app.app_context():
        logger.info("Executando job semanal...")
        # Aqui você pode adicionar as funções que deseja executar semanalmente
        # Por exemplo:
        # processar_relatorios_semanais()
        # enviar_relatorio_semanal()
        # etc...

def job_hora():
    """
    Job que executa a cada hora
    """
    with app.app_context():
        logger.info("Executando job horário...")
        processar_arquivei()
        # Aqui você pode adicionar as funções que deseja executar a cada hora
        # Por exemplo:
        # verificar_status_sistema()
        # atualizar_cache()
        # etc...

def gerenciar_scheduler():
    """
    Gerencia os schedulers da aplicação, garantindo que não haja duplicatas
    """
    try:
        # Parar todos os schedulers existentes
        if hasattr(app, 'scheduler'):
            try:
                app.scheduler.shutdown()
                logger.info("Scheduler existente parado com sucesso")
            except:
                pass

        # Criar novo scheduler se não existir
        if not hasattr(app, 'scheduler'):
            app.scheduler = BackgroundScheduler(timezone='America/Sao_Paulo')
            
            # Adiciona o job de email (a cada 5 minutos)
            app.scheduler.add_job(job_email5min, 'cron', minute='*/5')
            logger.info("Job de email adicionado ao scheduler")

            # Adiciona o job de email (a cada 15 minutos)
            app.scheduler.add_job(job_email15min, 'cron', minute='*/15')
            logger.info("Job de email adicionado ao scheduler")
            
            # Adiciona o job diário (todos os dias às 00:00)
            app.scheduler.add_job(job_diario, 'cron', hour=0, minute=0)
            logger.info("Job diário adicionado ao scheduler")

            # Adiciona o job semanal (todo domingo às 00:00)
            app.scheduler.add_job(job_semanal, 'cron', day_of_week='sun', hour=0, minute=0)
            logger.info("Job semanal adicionado ao scheduler")

            # Adiciona o job horário (a cada hora)
            app.scheduler.add_job(job_hora, 'cron', hour='*')
            logger.info("Job horário adicionado ao scheduler")
            
            logger.info("Novo scheduler criado com sucesso")
        
        # Iniciar o scheduler se não estiver rodando
        if not app.scheduler.running:
            app.scheduler.start()
            logger.info("Scheduler iniciado com sucesso")
    except Exception as e:
        logger.error(f"Erro ao gerenciar scheduler: {str(e)}")

# Gerenciar o scheduler
#gerenciar_scheduler()

# Inicializa o banco de dados quando a aplicação é iniciada
with app.app_context():
    logger.info("Inicializando banco de dados...")
    print(os.getenv('DATABASE_URI'))
    try:
        init_db()
        logger.info("Banco de dados inicializado com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {str(e)}", exc_info=True)

app.jinja_env.filters['notas_json'] = notas_json
app.jinja_env.filters['avulsos_json'] = avulsos_json

