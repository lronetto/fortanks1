#!/usr/bin/env python3
"""
Script para sincronização incremental entre MySQL e SQLite
Permite manter o banco local atualizado com as mudanças do servidor
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Carregar variáveis de ambiente
load_dotenv('.env')

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/sincronizacao_sqlite.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SincronizadorSQLite:
    """
    Classe responsável pela sincronização incremental entre MySQL e SQLite
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
            DB_password = os.environ.get('DB_PASSWORD') or ''
            sql_url = f'mysql+pymysql://remote:{quote_plus(DB_password)}@192.168.8.10:3306/sfortanks'
            
            self.mysql_engine = create_engine(sql_url, echo=False)
            Session = sessionmaker(bind=self.mysql_engine)
            self.mysql_session = Session()
            
            logger.info("Conexão com MySQL estabelecida")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao conectar com MySQL: {str(e)}")
            return False
    
    def conectar_sqlite(self):
        """Conecta ao banco SQLite local"""
        try:
            if not os.path.exists(self.sqlite_path):
                logger.error(f"Banco SQLite não encontrado: {self.sqlite_path}")
                return False
            
            self.sqlite_engine = create_engine(f'sqlite:///{self.sqlite_path}', echo=False)
            Session = sessionmaker(bind=self.sqlite_engine)
            self.sqlite_session = Session()
            
            logger.info("Conexão com SQLite estabelecida")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao conectar com SQLite: {str(e)}")
            return False
    
    def obter_ultima_sincronizacao(self, tabela):
        """Obtém a data da última sincronização de uma tabela"""
        try:
            query = text("""
                SELECT ultima_sincronizacao 
                FROM controle_sincronizacao 
                WHERE tabela = :tabela 
                ORDER BY ultima_sincronizacao DESC 
                LIMIT 1
            """)
            result = self.sqlite_session.execute(query, {'tabela': tabela})
            row = result.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Erro ao obter última sincronização da tabela {tabela}: {str(e)}")
            return None
    
    def atualizar_controle_sincronizacao(self, tabela, registros_sincronizados, status='sucesso', erro=None):
        """Atualiza o controle de sincronização"""
        try:
            query = text("""
                INSERT INTO controle_sincronizacao 
                (tabela, ultima_sincronizacao, registros_sincronizados, status, erro)
                VALUES (:tabela, :ultima_sincronizacao, :registros_sincronizados, :status, :erro)
            """)
            
            self.sqlite_session.execute(query, {
                'tabela': tabela,
                'ultima_sincronizacao': datetime.now(),
                'registros_sincronizados': registros_sincronizados,
                'status': status,
                'erro': erro
            })
            self.sqlite_session.commit()
            
        except Exception as e:
            logger.error(f"Erro ao atualizar controle de sincronização: {str(e)}")
    
    def obter_registros_modificados(self, tabela, data_ultima_sincronizacao):
        """Obtém registros modificados desde a última sincronização"""
        try:
            # Tentar diferentes campos de data/hora comuns
            campos_data = ['atualizado_em', 'modificado_em', 'criado_em', 'updated_at', 'created_at']
            campo_data = None
            
            # Verificar qual campo de data existe na tabela
            query_estrutura = text(f"DESCRIBE {tabela}")
            result_estrutura = self.mysql_session.execute(query_estrutura)
            colunas = [row[0] for row in result_estrutura.fetchall()]
            
            for campo in campos_data:
                if campo in colunas:
                    campo_data = campo
                    break
            
            if not campo_data:
                logger.warning(f"Nenhum campo de data encontrado na tabela {tabela}")
                return []
            
            # Buscar registros modificados
            if data_ultima_sincronizacao:
                query = text(f"SELECT * FROM {tabela} WHERE {campo_data} > :data_ultima_sincronizacao")
                result = self.mysql_session.execute(query, {'data_ultima_sincronizacao': data_ultima_sincronizacao})
            else:
                # Se não há data de sincronização, buscar todos os registros
                query = text(f"SELECT * FROM {tabela}")
                result = self.mysql_session.execute(query)
            
            registros = result.fetchall()
            colunas = [desc[0] for desc in result.description]
            
            return registros, colunas
            
        except Exception as e:
            logger.error(f"Erro ao obter registros modificados da tabela {tabela}: {str(e)}")
            return [], []
    
    def sincronizar_tabela(self, tabela):
        """Sincroniza uma tabela específica"""
        try:
            logger.info(f"Sincronizando tabela: {tabela}")
            
            # Obter última sincronização
            ultima_sincronizacao = self.obter_ultima_sincronizacao(tabela)
            
            # Obter registros modificados
            registros, colunas = self.obter_registros_modificados(tabela, ultima_sincronizacao)
            
            if not registros:
                logger.info(f"Nenhum registro novo/modificado na tabela {tabela}")
                self.atualizar_controle_sincronizacao(tabela, 0)
                return True
            
            # Preparar SQL de inserção/atualização
            valores_placeholder = ', '.join(['?' for _ in colunas])
            sql_insert = f"INSERT OR REPLACE INTO {tabela} ({', '.join(colunas)}) VALUES ({valores_placeholder})"
            
            # Conectar diretamente ao SQLite para inserção em lote
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            
            # Inserir/atualizar registros
            cursor.executemany(sql_insert, registros)
            conn.commit()
            conn.close()
            
            # Atualizar controle de sincronização
            self.atualizar_controle_sincronizacao(tabela, len(registros))
            
            logger.info(f"Tabela {tabela} sincronizada: {len(registros)} registros")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao sincronizar tabela {tabela}: {str(e)}")
            self.atualizar_controle_sincronizacao(tabela, 0, 'erro', str(e))
            return False
    
    def obter_tabelas_para_sincronizar(self):
        """Obtém lista de tabelas que precisam ser sincronizadas"""
        try:
            # Obter todas as tabelas do MySQL
            query = text("SHOW TABLES")
            result = self.mysql_session.execute(query)
            tabelas_mysql = [row[0] for row in result.fetchall()]
            
            # Filtrar tabelas que não são de controle
            tabelas_excluidas = ['controle_sincronizacao', 'alembic_version']
            tabelas_para_sincronizar = [t for t in tabelas_mysql if t not in tabelas_excluidas]
            
            return tabelas_para_sincronizar
            
        except Exception as e:
            logger.error(f"Erro ao obter tabelas para sincronização: {str(e)}")
            return []
    
    def sincronizar_todas_tabelas(self):
        """Sincroniza todas as tabelas"""
        try:
            tabelas = self.obter_tabelas_para_sincronizar()
            if not tabelas:
                logger.error("Nenhuma tabela encontrada para sincronização")
                return False
            
            sucessos = 0
            falhas = 0
            
            for tabela in tabelas:
                if self.sincronizar_tabela(tabela):
                    sucessos += 1
                else:
                    falhas += 1
            
            logger.info(f"Sincronização concluída: {sucessos} sucessos, {falhas} falhas")
            return falhas == 0
            
        except Exception as e:
            logger.error(f"Erro durante sincronização: {str(e)}")
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
        except Exception as e:
            logger.error(f"Erro ao fechar conexões: {str(e)}")
    
    def executar_sincronizacao(self):
        """Executa a sincronização completa"""
        logger.info("Iniciando sincronização incremental...")
        
        try:
            # Conectar aos bancos
            if not self.conectar_mysql():
                return False
            
            if not self.conectar_sqlite():
                return False
            
            # Sincronizar todas as tabelas
            sucesso = self.sincronizar_todas_tabelas()
            
            if sucesso:
                logger.info("Sincronização concluída com sucesso!")
            else:
                logger.error("Sincronização concluída com erros")
            
            return sucesso
            
        except Exception as e:
            logger.error(f"Erro durante sincronização: {str(e)}")
            return False
        finally:
            self.fechar_conexoes()

def main():
    """Função principal"""
    print("=== Sincronizador MySQL -> SQLite - Fortanks ===")
    print("Este script irá sincronizar as mudanças do MySQL para SQLite local")
    print()
    
    sincronizador = SincronizadorSQLite()
    sucesso = sincronizador.executar_sincronizacao()
    
    if sucesso:
        print("\n✅ Sincronização concluída com sucesso!")
        print("🔄 Banco SQLite local atualizado")
    else:
        print("\n❌ Sincronização falhou. Verifique os logs para mais detalhes.")
        print("📋 Logs salvos em: logs/sincronizacao_sqlite.log")

if __name__ == "__main__":
    main()

