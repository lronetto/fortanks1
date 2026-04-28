#!/usr/bin/env python3
"""
Migracao de schema e dados de MySQL para PostgreSQL.

Uso:
  1) Configure no .env:
     MIGRACAO_MYSQL_URI=mysql+pymysql://usuario:senha@host:3306/banco
     MIGRACAO_POSTGRES_URI=postgresql+psycopg://usuario:senha@host:5432/banco
  2) Execute:
     python scripts/migrar_mysql_para_postgres.py
"""

import os
import sys
import logging
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError


load_dotenv(".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/migracao_postgres.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def _normalizar_tabela(nome):
    # Nome em minusculo reduz problema com identificador quoted no PostgreSQL.
    return nome.lower()


class MigradorMySQLParaPostgres:
    def __init__(self):
        self.mysql_uri = os.getenv("MIGRACAO_MYSQL_URI") or os.getenv("DATABASE_URI")
        self.pg_uri = os.getenv("MIGRACAO_POSTGRES_URI")

        if not self.mysql_uri:
            raise RuntimeError("MIGRACAO_MYSQL_URI ou DATABASE_URI nao definido.")
        if not self.pg_uri:
            raise RuntimeError("MIGRACAO_POSTGRES_URI nao definido.")

        self.mysql_engine = None
        self.pg_engine = None
        self.metadata_origem = MetaData()
        self.metadata_destino = MetaData()

    def conectar(self):
        logger.info("Conectando em MySQL e PostgreSQL...")
        self.mysql_engine = create_engine(self.mysql_uri, pool_pre_ping=True)
        self.pg_engine = create_engine(self.pg_uri, pool_pre_ping=True)

        with self.mysql_engine.connect() as c1:
            c1.execute(text("SELECT 1"))
        with self.pg_engine.connect() as c2:
            c2.execute(text("SELECT 1"))

        logger.info("Conexoes estabelecidas com sucesso.")

    def _listar_tabelas_origem(self):
        insp = inspect(self.mysql_engine)
        tabelas = insp.get_table_names()
        tabelas = [t for t in tabelas if t != "alembic_version"]
        return tabelas

    def criar_schema_destino(self):
        tabelas_origem = self._listar_tabelas_origem()
        if not tabelas_origem:
            raise RuntimeError("Nenhuma tabela encontrada na origem.")

        logger.info("Refletindo schema de origem (%s tabelas)...", len(tabelas_origem))

        for nome_tabela in tabelas_origem:
            tabela_origem = Table(
                nome_tabela,
                self.metadata_origem,
                autoload_with=self.mysql_engine,
            )
            colunas_destino = [col.copy() for col in tabela_origem.columns]
            Table(
                _normalizar_tabela(nome_tabela),
                self.metadata_destino,
                *colunas_destino,
            )

        logger.info("Criando schema no PostgreSQL...")
        self.metadata_destino.create_all(self.pg_engine, checkfirst=True)
        logger.info("Schema criado/atualizado no destino.")

    def copiar_dados(self, tamanho_lote=1000):
        total_tabelas = len(self.metadata_origem.tables)
        logger.info("Iniciando carga de dados (%s tabelas)...", total_tabelas)

        with self.mysql_engine.connect() as conn_origem, self.pg_engine.begin() as tx_destino:
            for idx, nome_tabela in enumerate(self.metadata_origem.sorted_tables, start=1):
                origem = self.metadata_origem.tables[nome_tabela.name]
                nome_destino = _normalizar_tabela(nome_tabela.name)
                destino = self.metadata_destino.tables[nome_destino]

                logger.info("[%s/%s] Copiando tabela %s", idx, total_tabelas, nome_tabela.name)

                tx_destino.execute(text(f'TRUNCATE TABLE "{nome_destino}" RESTART IDENTITY CASCADE'))

                resultado = conn_origem.execute(select(origem))
                copiados = 0
                lote = []

                for row in resultado.mappings():
                    lote.append(dict(row))
                    if len(lote) >= tamanho_lote:
                        tx_destino.execute(destino.insert(), lote)
                        copiados += len(lote)
                        lote.clear()

                if lote:
                    tx_destino.execute(destino.insert(), lote)
                    copiados += len(lote)

                logger.info("Tabela %s copiada: %s registros", nome_tabela.name, copiados)

        logger.info("Carga de dados concluida.")

    def executar(self):
        inicio = datetime.now()
        logger.info("=== Migracao MySQL -> PostgreSQL iniciada ===")
        try:
            self.conectar()
            self.criar_schema_destino()
            self.copiar_dados()
            elapsed = datetime.now() - inicio
            logger.info("=== Migracao concluida com sucesso em %s ===", elapsed)
            return True
        except SQLAlchemyError as exc:
            logger.exception("Erro de SQLAlchemy durante migracao: %s", exc)
            return False
        except Exception as exc:
            logger.exception("Erro inesperado durante migracao: %s", exc)
            return False
        finally:
            if self.mysql_engine:
                self.mysql_engine.dispose()
            if self.pg_engine:
                self.pg_engine.dispose()


def main():
    print("=== Migrador MySQL -> PostgreSQL (Fortanks) ===")
    print("Este processo recria tabelas (se necessario) e sobrescreve dados no destino.")
    resposta = input("Deseja continuar? (s/N): ").strip().lower()
    if resposta not in {"s", "sim", "y", "yes"}:
        print("Operacao cancelada.")
        return 0

    os.makedirs("logs", exist_ok=True)

    migrador = MigradorMySQLParaPostgres()
    ok = migrador.executar()

    if ok:
        print("Migracao concluida com sucesso.")
        print("Logs: logs/migracao_postgres.log")
        return 0

    print("Migracao falhou. Veja logs/migracao_postgres.log")
    return 1


if __name__ == "__main__":
    sys.exit(main())
