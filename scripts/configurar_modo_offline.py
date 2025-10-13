#!/usr/bin/env python3
"""
Script para configurar o sistema para funcionar em modo offline
Altera as configurações para usar SQLite local em vez do MySQL
"""

import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def backup_config_original():
    """Faz backup da configuração original"""
    config_path = 'config/config.py'
    backup_path = f'config/config_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.py'
    
    if os.path.exists(config_path):
        shutil.copy2(config_path, backup_path)
        print(f"✅ Backup da configuração criado: {backup_path}")
        return backup_path
    else:
        print("❌ Arquivo de configuração não encontrado")
        return None

def criar_config_offline():
    """Cria configuração para modo offline"""
    config_offline = '''import os
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
    
    # Configurações do banco de dados - MODO OFFLINE
    # Usando SQLite local em vez do MySQL
    SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/fortanks_offline.db'
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
    
    # Configurações de e-mail (desabilitadas em modo offline)
    MAIL_SERVER = ''
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = ''
    MAIL_PASSWORD = ''
    MAIL_DEFAULT_SENDER = ''
    
    EMAILS_PDF_SOLICITACAO = ''
    
    # Configurações da API do Arquivei (desabilitadas em modo offline)
    ARQUIVEI_API_ID = ''
    ARQUIVEI_API_KEY = ''
    ARQUIVEI_API_URL = ''
    
    # Flag para indicar modo offline
    MODO_OFFLINE = True

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
'''
    
    with open('config/config.py', 'w', encoding='utf-8') as f:
        f.write(config_offline)
    
    print("✅ Configuração offline criada")

def criar_config_online():
    """Cria configuração para modo online (MySQL)"""
    config_online = '''import os
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
    
    # Configurações do banco de dados - MODO ONLINE
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
    
    # Configurações da API do Arquivei
    ARQUIVEI_API_ID = os.environ.get('ARQUIVEI_API_ID') or ''
    ARQUIVEI_API_KEY = os.environ.get('ARQUIVEI_API_KEY') or ''
    ARQUIVEI_API_URL = os.environ.get('ARQUIVEI_API_URL') or ''
    
    # Flag para indicar modo online
    MODO_OFFLINE = False

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
'''
    
    with open('config/config.py', 'w', encoding='utf-8') as f:
        f.write(config_online)
    
    print("✅ Configuração online criada")

def verificar_banco_sqlite():
    """Verifica se o banco SQLite existe"""
    sqlite_path = 'instance/fortanks_offline.db'
    if os.path.exists(sqlite_path):
        size = os.path.getsize(sqlite_path)
        print(f"✅ Banco SQLite encontrado: {sqlite_path} ({size:,} bytes)")
        return True
    else:
        print(f"❌ Banco SQLite não encontrado: {sqlite_path}")
        return False

def main():
    """Função principal"""
    print("=== Configurador de Modo Offline - Fortanks ===")
    print()
    
    while True:
        print("Escolha uma opção:")
        print("1. Configurar para modo OFFLINE (SQLite)")
        print("2. Configurar para modo ONLINE (MySQL)")
        print("3. Verificar status do banco SQLite")
        print("4. Sair")
        print()
        
        opcao = input("Digite sua opção (1-4): ").strip()
        
        if opcao == '1':
            print("\n🔄 Configurando para modo OFFLINE...")
            
            # Verificar se banco SQLite existe
            if not verificar_banco_sqlite():
                print("⚠️  Banco SQLite não encontrado!")
                print("Execute primeiro o script de migração: python scripts/migrar_para_sqlite.py")
                continue
            
            # Fazer backup da configuração atual
            backup_path = backup_config_original()
            
            # Criar configuração offline
            criar_config_offline()
            
            print("\n✅ Sistema configurado para modo OFFLINE!")
            print("📁 Banco SQLite: instance/fortanks_offline.db")
            print("🔄 Para voltar ao modo online, execute este script novamente e escolha opção 2")
            if backup_path:
                print(f"💾 Backup da configuração original: {backup_path}")
            
        elif opcao == '2':
            print("\n🔄 Configurando para modo ONLINE...")
            
            # Fazer backup da configuração atual
            backup_path = backup_config_original()
            
            # Criar configuração online
            criar_config_online()
            
            print("\n✅ Sistema configurado para modo ONLINE!")
            print("🗄️  Banco MySQL: 192.168.8.10:3306/sfortanks")
            print("🔄 Para voltar ao modo offline, execute este script novamente e escolha opção 1")
            if backup_path:
                print(f"💾 Backup da configuração anterior: {backup_path}")
            
        elif opcao == '3':
            print("\n🔍 Verificando status do banco SQLite...")
            verificar_banco_sqlite()
            
        elif opcao == '4':
            print("\n👋 Saindo...")
            break
            
        else:
            print("\n❌ Opção inválida! Tente novamente.")
        
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    main()


