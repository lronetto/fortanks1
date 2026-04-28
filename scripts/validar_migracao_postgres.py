#!/usr/bin/env python3
"""
Valida migracao MySQL -> PostgreSQL por contagem de registros.

Uso:
  - Configure MIGRACAO_MYSQL_URI e MIGRACAO_POSTGRES_URI no .env
  - Execute: python scripts/validar_migracao_postgres.py
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


load_dotenv(".env")


def _normalizar_tabela(nome):
    return nome.lower()


def _contar(engine, tabela):
    quoted_table = engine.dialect.identifier_preparer.quote(tabela)
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {quoted_table}")).scalar_one()


def main():
    mysql_uri = os.getenv("MIGRACAO_MYSQL_URI") or os.getenv("DATABASE_URI")
    pg_uri = os.getenv("MIGRACAO_POSTGRES_URI")

    if not mysql_uri:
        print("ERRO: MIGRACAO_MYSQL_URI ou DATABASE_URI nao definido.")
        return 1
    if not pg_uri:
        print("ERRO: MIGRACAO_POSTGRES_URI nao definido.")
        return 1

    mysql_engine = create_engine(mysql_uri, pool_pre_ping=True)
    pg_engine = create_engine(pg_uri, pool_pre_ping=True)

    try:
        insp = inspect(mysql_engine)
        tabelas = [t for t in insp.get_table_names() if t != "alembic_version"]
        if not tabelas:
            print("Nenhuma tabela para validar.")
            return 1

        divergencias = []
        print(f"Validando {len(tabelas)} tabelas...")

        for tabela in tabelas:
            nome_pg = _normalizar_tabela(tabela)
            qtd_mysql = _contar(mysql_engine, tabela)
            qtd_pg = _contar(pg_engine, nome_pg)
            status = "OK" if qtd_mysql == qtd_pg else "DIVERGENTE"
            print(f"{tabela}: mysql={qtd_mysql} | postgres={qtd_pg} -> {status}")
            if qtd_mysql != qtd_pg:
                divergencias.append((tabela, qtd_mysql, qtd_pg))

        print("-" * 60)
        if divergencias:
            print(f"Validacao finalizou com {len(divergencias)} divergencia(s).")
            return 2

        print("Validacao concluida sem divergencias.")
        return 0
    finally:
        mysql_engine.dispose()
        pg_engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
