#!/usr/bin/env python3
"""
Script para migrar dados do banco MySQL para SQLite local
Permite funcionamento offline do sistema Fortanks
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Adicionar o diretório raiz ao path para importar os modelos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

# Carregar variáveis de ambiente
load_dotenv('.env')

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/migracao_sqlite.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MigradorSQLite:
    """
    Classe responsável pela migração de dados do MySQL para SQLite
    """
    
    def __init__(self):
        self.mysql_engine = None
        self.sqlite_engine = None
        self.mysql_session = None
        self.sqlite_session = None
        self.sqlite_path = 'instance/fortanks_offline.db'
        
    def conectar_mysql(self):
        """Conecta ao banco MySQL existente"""
        try:
            # Usar as mesmas configurações do config.py
            DB_password = os.environ.get('DB_PASSWORD') or ''
            sql_url = f'mysql+pymysql://remote:{quote_plus(DB_password)}@192.168.8.10:3306/sfortanks'
            
            self.mysql_engine = create_engine(sql_url, echo=False)
            Session = sessionmaker(bind=self.mysql_engine)
            self.mysql_session = Session()
            
            logger.info("Conexão com MySQL estabelecida com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao conectar com MySQL: {str(e)}")
            return False
    
    def conectar_sqlite(self):
        """Conecta ao banco SQLite local"""
        try:
            # Garantir que o diretório instance existe
            os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)
            
            # Criar engine SQLite
            self.sqlite_engine = create_engine(f'sqlite:///{self.sqlite_path}', echo=False)
            Session = sessionmaker(bind=self.sqlite_engine)
            self.sqlite_session = Session()
            
            logger.info(f"Conexão com SQLite estabelecida: {self.sqlite_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao conectar com SQLite: {str(e)}")
            return False
    
    def obter_tabelas_mysql(self):
        """Obtém lista de todas as tabelas do MySQL"""
        try:
            query = text("SHOW TABLES")
            result = self.mysql_session.execute(query)
            tabelas = [row[0] for row in result.fetchall()]
            logger.info(f"Encontradas {len(tabelas)} tabelas no MySQL")
            return tabelas
        except Exception as e:
            logger.error(f"Erro ao obter tabelas do MySQL: {str(e)}")
            return []
    
    def obter_estrutura_tabela(self, nome_tabela):
        """Obtém a estrutura de uma tabela específica"""
        try:
            query = text(f"DESCRIBE {nome_tabela}")
            result = self.mysql_session.execute(query)
            colunas = []
            for row in result.fetchall():
                colunas.append({
                    'Field': row[0],
                    'Type': row[1],
                    'Null': row[2],
                    'Key': row[3],
                    'Default': row[4],
                    'Extra': row[5]
                })
            return colunas
        except Exception as e:
            logger.error(f"Erro ao obter estrutura da tabela {nome_tabela}: {str(e)}")
            return []
    
    def criar_tabela_sqlite(self, nome_tabela, colunas):
        """Cria uma tabela no SQLite baseada na estrutura do MySQL"""
        try:
            # Mapear tipos MySQL para SQLite
            def mapear_tipo(tipo_mysql):
                tipo_mysql = tipo_mysql.lower()
                if 'int' in tipo_mysql:
                    return 'INTEGER'
                elif 'varchar' in tipo_mysql or 'char' in tipo_mysql or 'text' in tipo_mysql:
                    return 'TEXT'
                elif 'decimal' in tipo_mysql or 'float' in tipo_mysql or 'double' in tipo_mysql:
                    return 'REAL'
                elif 'datetime' in tipo_mysql or 'timestamp' in tipo_mysql:
                    return 'DATETIME'
                elif 'date' in tipo_mysql:
                    return 'DATE'
                elif 'time' in tipo_mysql:
                    return 'TIME'
                elif 'boolean' in tipo_mysql or 'bool' in tipo_mysql:
                    return 'BOOLEAN'
                elif 'enum' in tipo_mysql:
                    return 'TEXT'
                else:
                    return 'TEXT'
            
            # Construir SQL CREATE TABLE
            sql_colunas = []
            for coluna in colunas:
                nome = coluna['Field']
                tipo = mapear_tipo(coluna['Type'])
                null = '' if coluna['Null'] == 'YES' else ' NOT NULL'
                default = f" DEFAULT {coluna['Default']}" if coluna['Default'] is not None else ''
                extra = ''
                
                if coluna['Key'] == 'PRI':
                    extra = ' PRIMARY KEY'
                elif coluna['Key'] == 'UNI':
                    extra = ' UNIQUE'
                
                sql_colunas.append(f"{nome} {tipo}{null}{default}{extra}")
            
            sql = f"CREATE TABLE IF NOT EXISTS {nome_tabela} ({', '.join(sql_colunas)})"
            
            # Executar no SQLite
            self.sqlite_session.execute(text(sql))
            self.sqlite_session.commit()
            
            logger.info(f"Tabela {nome_tabela} criada no SQLite")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao criar tabela {nome_tabela} no SQLite: {str(e)}")
            return False
    
    def copiar_dados_tabela(self, nome_tabela):
        """Copia dados de uma tabela do MySQL para SQLite"""
        try:
            # Obter dados do MySQL
            query = text(f"SELECT * FROM {nome_tabela}")
            result = self.mysql_session.execute(query)
            dados = result.fetchall()
            
            if not dados:
                logger.info(f"Tabela {nome_tabela} está vazia")
                return True
            
            # Obter nomes das colunas
            colunas = [desc[0] for desc in result.description]
            
            # Preparar dados para inserção
            valores_placeholder = ', '.join(['?' for _ in colunas])
            sql_insert = f"INSERT OR REPLACE INTO {nome_tabela} ({', '.join(colunas)}) VALUES ({valores_placeholder})"
            
            # Conectar diretamente ao SQLite para inserção em lote
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            
            # Inserir dados em lotes
            batch_size = 1000
            for i in range(0, len(dados), batch_size):
                batch = dados[i:i + batch_size]
                cursor.executemany(sql_insert, batch)
                conn.commit()
                logger.info(f"Copiados {min(i + batch_size, len(dados))}/{len(dados)} registros da tabela {nome_tabela}")
            
            conn.close()
            logger.info(f"Dados da tabela {nome_tabela} copiados com sucesso ({len(dados)} registros)")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao copiar dados da tabela {nome_tabela}: {str(e)}")
            return False
    
    def migrar_todas_tabelas(self):
        """Migra todas as tabelas do MySQL para SQLite"""
        try:
            tabelas = self.obter_tabelas_mysql()
            if not tabelas:
                logger.error("Nenhuma tabela encontrada no MySQL")
                return False
            
            sucessos = 0
            falhas = 0
            
            for tabela in tabelas:
                logger.info(f"Migrando tabela: {tabela}")
                
                # Obter estrutura da tabela
                colunas = self.obter_estrutura_tabela(tabela)
                if not colunas:
                    logger.error(f"Não foi possível obter estrutura da tabela {tabela}")
                    falhas += 1
                    continue
                
                # Criar tabela no SQLite
                if not self.criar_tabela_sqlite(tabela, colunas):
                    logger.error(f"Falha ao criar tabela {tabela} no SQLite")
                    falhas += 1
                    continue
                
                # Copiar dados
                if not self.copiar_dados_tabela(tabela):
                    logger.error(f"Falha ao copiar dados da tabela {tabela}")
                    falhas += 1
                    continue
                
                sucessos += 1
            
            logger.info(f"Migração concluída: {sucessos} sucessos, {falhas} falhas")
            return falhas == 0
            
        except Exception as e:
            logger.error(f"Erro durante migração: {str(e)}")
            return False
    
    def criar_tabela_controle_sincronizacao(self):
        """Cria tabela para controle de sincronização"""
        try:
            sql = """
            CREATE TABLE IF NOT EXISTS controle_sincronizacao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tabela TEXT NOT NULL,
                ultima_sincronizacao DATETIME NOT NULL,
                registros_sincronizados INTEGER DEFAULT 0,
                status TEXT DEFAULT 'sucesso',
                erro TEXT,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            self.sqlite_session.execute(text(sql))
            self.sqlite_session.commit()
            logger.info("Tabela de controle de sincronização criada")
            return True
        except Exception as e:
            logger.error(f"Erro ao criar tabela de controle: {str(e)}")
            return False
    
    def fechar_conexoes(self):
        """Fecha todas as conexões"""
        try:
            if self.mysql_session:
                self.mysql_session.close()
            if self.sqlite_session:
                self.sqlite_session.close()
            if self.mysql_engine:
                self.mysql_engine.dispose()
            if self.sqlite_engine:
                self.sqlite_engine.dispose()
            logger.info("Conexões fechadas")
        except Exception as e:
            logger.error(f"Erro ao fechar conexões: {str(e)}")
    
    def executar_migracao_completa(self):
        """Executa a migração completa"""
        logger.info("Iniciando migração completa para SQLite...")
        
        try:
            # Conectar aos bancos
            if not self.conectar_mysql():
                return False
            
            if not self.conectar_sqlite():
                return False
            
            # Criar tabela de controle
            if not self.criar_tabela_controle_sincronizacao():
                return False
            
            # Migrar todas as tabelas
            sucesso = self.migrar_todas_tabelas()
            
            if sucesso:
                logger.info("Migração concluída com sucesso!")
                logger.info(f"Banco SQLite criado em: {self.sqlite_path}")
            else:
                logger.error("Migração concluída com erros")
            
            return sucesso
            
        except Exception as e:
            logger.error(f"Erro durante migração completa: {str(e)}")
            return False
        finally:
            self.fechar_conexoes()

def main():
    """Função principal"""
    print("=== Migrador MySQL para SQLite - Fortanks ===")
    print("Este script irá copiar todos os dados do banco MySQL para SQLite local")
    print("Permitindo funcionamento offline do sistema.")
    print()
    
    resposta = input("Deseja continuar? (s/N): ").lower().strip()
    if resposta not in ['s', 'sim', 'y', 'yes']:
        print("Migração cancelada pelo usuário.")
        return
    
    migrador = MigradorSQLite()
    sucesso = migrador.executar_migracao_completa()
    
    if sucesso:
        print("\n✅ Migração concluída com sucesso!")
        print(f"📁 Banco SQLite criado em: {migrador.sqlite_path}")
        print("🔄 O sistema agora pode funcionar offline")
    else:
        print("\n❌ Migração falhou. Verifique os logs para mais detalhes.")
        print("📋 Logs salvos em: logs/migracao_sqlite.log")

if __name__ == "__main__":
    main()


