#!/usr/bin/env python3
"""
Script para adicionar a coluna configuracao_id à tabela erp_credenciais.

Este script verifica se a coluna já existe e, caso contrário, a adiciona.
Em seguida, migra os dados existentes da coluna usuario_id para configuracao_id.
"""

from utils.db import get_db_connection, execute_query
import os
import sys
import logging
from pathlib import Path
import argparse

# Adicionar o diretório raiz ao PATH para importar os módulos do sistema
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importar as funções de banco de dados

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def verificar_coluna_existe(connection, tabela, coluna):
    """
    Verifica se uma coluna específica existe em uma tabela.

    Args:
        connection: Conexão com o banco de dados
        tabela (str): Nome da tabela
        coluna (str): Nome da coluna

    Returns:
        bool: True se a coluna existir, False caso contrário
    """
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"SHOW COLUMNS FROM {tabela} LIKE '{coluna}'")
        resultado = cursor.fetchone()
        cursor.close()
        return resultado is not None
    except Exception as e:
        logger.error(
            f"Erro ao verificar coluna {coluna} na tabela {tabela}: {e}")
        return False


def adicionar_coluna(connection, tabela, coluna, definicao):
    """
    Adiciona uma coluna a uma tabela se ela não existir.

    Args:
        connection: Conexão com o banco de dados
        tabela (str): Nome da tabela
        coluna (str): Nome da coluna a ser adicionada
        definicao (str): Definição SQL da coluna (tipo, constraints, etc)

    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário
    """
    try:
        if not verificar_coluna_existe(connection, tabela, coluna):
            cursor = connection.cursor()
            sql = f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}"
            logger.info(f"Executando: {sql}")
            cursor.execute(sql)
            connection.commit()
            cursor.close()
            logger.info(
                f"Coluna {coluna} adicionada com sucesso à tabela {tabela}")
            return True
        else:
            logger.info(f"Coluna {coluna} já existe na tabela {tabela}")
            return True
    except Exception as e:
        logger.error(
            f"Erro ao adicionar coluna {coluna} à tabela {tabela}: {e}")
        return False


def migrar_dados(connection, dry_run=False):
    """
    Migra os dados da coluna usuario_id para configuracao_id.

    Args:
        connection: Conexão com o banco de dados
        dry_run (bool): Se True, apenas simula as operações sem fazer alterações

    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário
    """
    try:
        cursor = connection.cursor(dictionary=True)

        # Verificar se tem dados para migrar
        cursor.execute("""
            SELECT COUNT(*) as total 
            FROM erp_credenciais 
            WHERE usuario_id IS NOT NULL 
            AND (configuracao_id IS NULL OR configuracao_id = 0)
        """)
        result = cursor.fetchone()
        total = result['total'] if result else 0

        if total == 0:
            logger.info("Não há dados para migrar.")
            cursor.close()
            return True

        logger.info(f"Encontrados {total} registros para migrar.")

        if dry_run:
            logger.info("[DRY RUN] A migração não será executada.")
            cursor.close()
            return True

        # Migrar dados
        sql = """
            UPDATE erp_credenciais 
            SET configuracao_id = usuario_id 
            WHERE usuario_id IS NOT NULL 
            AND (configuracao_id IS NULL OR configuracao_id = 0)
        """
        logger.info(f"Executando: {sql}")
        cursor.execute(sql)
        connection.commit()
        rows_affected = cursor.rowcount
        cursor.close()

        logger.info(
            f"Migração concluída: {rows_affected} registros atualizados.")
        return True
    except Exception as e:
        logger.error(f"Erro ao migrar dados: {e}")
        if not dry_run:
            connection.rollback()
        return False


def adicionar_chave_estrangeira(connection, dry_run=False):
    """
    Adiciona uma chave estrangeira à coluna configuracao_id.

    Args:
        connection: Conexão com o banco de dados
        dry_run (bool): Se True, apenas simula as operações sem fazer alterações

    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário
    """
    try:
        cursor = connection.cursor(dictionary=True)

        # Verificar se a chave estrangeira já existe
        cursor.execute("""
            SELECT COUNT(*) as total
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'erp_credenciais'
            AND COLUMN_NAME = 'configuracao_id'
            AND REFERENCED_TABLE_NAME = 'erp_configuracoes'
        """)
        result = cursor.fetchone()
        fk_exists = result['total'] > 0 if result else False

        if fk_exists:
            logger.info("A chave estrangeira já existe.")
            cursor.close()
            return True

        if dry_run:
            logger.info("[DRY RUN] A chave estrangeira não será adicionada.")
            cursor.close()
            return True

        # Adicionar chave estrangeira
        sql = """
            ALTER TABLE erp_credenciais
            ADD CONSTRAINT fk_credenciais_configuracao
            FOREIGN KEY (configuracao_id) 
            REFERENCES erp_configuracoes(id)
            ON DELETE CASCADE
        """
        logger.info(f"Executando: {sql}")
        cursor.execute(sql)
        connection.commit()
        cursor.close()

        logger.info("Chave estrangeira adicionada com sucesso.")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar chave estrangeira: {e}")
        if not dry_run:
            connection.rollback()
        return False


def main():
    """Função principal do script"""
    parser = argparse.ArgumentParser(
        description="Adiciona e configura a coluna configuracao_id na tabela erp_credenciais")
    parser.add_argument('--dry-run', action='store_true',
                        help="Executa uma simulação sem fazer alterações no banco de dados")

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Executando em modo de simulação (dry run)")

    # Obter conexão com o banco de dados
    connection = get_db_connection()
    if not connection:
        logger.error("Não foi possível conectar ao banco de dados.")
        return 1

    try:
        # 1. Adicionar a coluna configuracao_id se ela não existir
        definicao_coluna = "INT UNSIGNED AFTER usuario_id"
        if not adicionar_coluna(connection, "erp_credenciais", "configuracao_id", definicao_coluna):
            logger.error(
                "Falha ao adicionar coluna configuracao_id. Abortando.")
            return 1

        # 2. Migrar dados da coluna usuario_id para configuracao_id
        if not migrar_dados(connection, args.dry_run):
            logger.error("Falha ao migrar dados. Abortando.")
            return 1

        # 3. Adicionar chave estrangeira
        if not adicionar_chave_estrangeira(connection, args.dry_run):
            logger.error("Falha ao adicionar chave estrangeira. Abortando.")
            return 1

        # Resultado final
        print("\n" + "="*60)
        print(" RESULTADO DA MIGRAÇÃO ".center(60, "="))
        print("="*60)
        print("✓ Coluna configuracao_id adicionada")
        print("✓ Dados migrados de usuario_id para configuracao_id")
        print("✓ Chave estrangeira adicionada")
        print("="*60)

        if args.dry_run:
            print(
                "\nEste foi apenas um teste. Execute sem a opção --dry-run para aplicar as mudanças.")

        return 0
    except Exception as e:
        logger.error(f"Erro não tratado: {e}")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
