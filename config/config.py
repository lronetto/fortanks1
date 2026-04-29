import os
import secrets
import logging
from datetime import timedelta
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv('.env')

logger = logging.getLogger(__name__)


def _get_secret_key():
    key = os.environ.get('SECRET_KEY')
    if not key:
        if os.environ.get('FLASK_ENV') == 'production':
            raise RuntimeError(
                "SECRET_KEY não configurada em produção! "
                "Defina SECRET_KEY no arquivo .env antes de iniciar a aplicação."
            )
        logger.warning(
            "SECRET_KEY nao definida via variavel de ambiente! "
            "Gerando chave aleatoria (sessoes serao perdidas ao reiniciar). "
            "Defina SECRET_KEY no .env para persistir sessoes."
        )
        key = secrets.token_hex(32)
    return key


def _build_db_uri():
    uri = os.environ.get('DATABASE_URI')
    if uri:
        return uri
    db_password = os.environ.get('DB_MYSQL_PASSWORD', '')
    db_host = os.environ.get('DB_MYSQL_HOST', '192.168.8.10')
    db_port = os.environ.get('DB_MYSQL_PORT', '3306')
    db_name = os.environ.get('DB_MYSQL_NAME', 'sfortanks')
    db_user = os.environ.get('DB_MYSQL_USER', 'remote')
    return f'mysql+pymysql://{db_user}:{quote_plus(db_password)}@{db_host}:{db_port}/{db_name}'


class Config:
    SECRET_KEY = _get_secret_key()
    DEBUG = False
    STATIC_FOLDER = 'static'
    TEMPLATES_FOLDER = 'templates'

    SQLALCHEMY_DATABASE_URI = _build_db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    PERMANENT_SESSION_LIFETIME = timedelta(hours=6)

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or _get_secret_key()
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {
        'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp',
        'xls', 'xlsx', 'csv', 'doc', 'docx',
        'xml', 'zip', 'rar', 'txt',
    }

    ITEMS_PER_PAGE = 10

    PASSWORD_MIN_LENGTH = 10
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = True

    MAIL_SERVER = os.environ.get('MAIL_SERVER') or ''
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or ''

    EMAILS_PDF_SOLICITACAO = os.environ.get('EMAILS_PDF_SOLICITACAO') or ''
    EMAILS_RELATORIO_TANQUES = os.environ.get('EMAILS_RELATORIO_TANQUES') or ''

    ARQUIVEI_API_ID = os.environ.get('ARQUIVEI_API_ID') or ''
    ARQUIVEI_API_KEY = os.environ.get('ARQUIVEI_API_KEY') or ''
    ARQUIVEI_API_URL = os.environ.get('ARQUIVEI_API_URL') or ''


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
