# coding: utf-8
from .materiais import mod_materiais, init_app as init_materiais
from .equipamentos import mod_equipamentos, init_app as init_equipamentos
from .centros_custo import mod_centros_custo, init_app as init_centros_custo
from .plano_contas import mod_plano_contas, init_app as init_plano_contas
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import os
import logging
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from utils.auth import verificar_permissao

# Configuração de logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cadastros.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Criar o Blueprint
mod_cadastros = Blueprint('cadastros', __name__,
                          template_folder='templates',
                          url_prefix='/cadastros')

# Importação dos submódulos do blueprints

# Registrar os Blueprints dos submódulos
mod_cadastros.register_blueprint(mod_equipamentos, url_prefix='/equipamentos')
mod_cadastros.register_blueprint(
    mod_centros_custo, url_prefix='/centros-custo')
mod_cadastros.register_blueprint(mod_materiais, url_prefix='/materiais')


def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'sistema_solicitacoes'),
            user=os.environ.get('DB_USER', 'root'),
            password=os.environ.get('DB_PASSWORD', 'sua_senha')
        )
        return connection
    except Error as e:
        logger.error(f"Erro ao conectar ao MySQL: {e}")
        return None


# Rota principal - dashboard de cadastros
@mod_cadastros.route('/')
def index():
    """Página principal do módulo de cadastros"""
    # Verificar autenticação
    if 'usuario_id' not in session:
        flash('Você precisa fazer login para acessar esta página', 'warning')
        return redirect(url_for('login'))

    # Verificar se o usuário tem acesso ao módulo de cadastros
    if not verificar_permissao('cadastros'):
        flash('Você não tem permissão para acessar este módulo', 'danger')
        return redirect(url_for('index'))

    return render_template('cadastros/index.html')


# Função para inicializar o blueprint no app Flask principal
def init_app(app):
    # app.register_blueprint(mod_cadastros)
    return app
