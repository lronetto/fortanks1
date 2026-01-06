import os
from datetime import timedelta
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv('.env')

class Config:
    # Configurações básicas
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'chave-secreta-padrao-deve-ser-alterada'
    DEBUG = True
    STATIC_FOLDER = 'static'
    TEMPLATES_FOLDER = 'templates'
    
    # Configurações do banco de dados
    DB_password = os.environ.get('DB_PASSWORD') or ''
    sql = 'mysql+pymysql://remote:%s@192.168.8.10:3306/sfortanks' % quote_plus(DB_password)
    #sql = 'mysql+pymysql://remote:%s@179.105.90.127:33066/sistema_solicitacoes?charset=utf8mb4' % quote_plus("8225Le@28")
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI') or sql
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Defina como True para debug de SQL
    
    # Configurações de sessão
    PERMANENT_SESSION_LIFETIME = timedelta(hours=6)
    
    # Configurações de upload
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 16MB
    
    # Configurações de paginação
    ITEMS_PER_PAGE = 10
    
    # Configurações de segurança
    PASSWORD_MIN_LENGTH = 8
    SESSION_COOKIE_SECURE = False  # Alterar para True em produção com HTTPS
    SESSION_COOKIE_HTTPONLY = True
    
    # Configurações de e-mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or ''
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or ''

   #EMAILS_PDF_SOLICITACAO = 'leandro.netto@fortanks.ind.br'
    EMAILS_PDF_SOLICITACAO = os.environ.get('EMAILS_PDF_SOLICITACAO') or ''
    EMAILS_RELATORIO_TANQUES = os.environ.get('EMAILS_RELATORIO_TANQUES') or ''
    
    # Configurações da API do Arquivei
    ARQUIVEI_API_ID = os.environ.get('ARQUIVEI_API_ID') or ''
    ARQUIVEI_API_KEY = os.environ.get('ARQUIVEI_API_KEY') or ''
    ARQUIVEI_API_URL = os.environ.get('ARQUIVEI_API_URL') or ''

class DevelopmentConfig(Config):
    DEBUG = True
    
class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    # Em produção, use uma chave secreta forte
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False 
