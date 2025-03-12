from flask import current_app
import mysql.connector
from mysql.connector import Error
import os
import logging
from contextlib import contextmanager
from flask import g

logger = logging.getLogger('db')


def get_db_connection():
    """
    Cria e retorna uma conexão com o banco de dados MySQL.

    Returns:
        Connection: Objeto de conexão MySQL ou None se houver erro.
    """
    # Verifica se já existe uma conexão no contexto da aplicação
    if 'db' in g:
        return g.db

    try:
        # Usar configuração do Flask se disponível
        if current_app.config.get('MYSQL_HOST'):
            connection = mysql.connector.connect(
                host=current_app.config.get('MYSQL_HOST'),
                database=current_app.config.get('MYSQL_DB'),
                user=current_app.config.get('MYSQL_USER'),
                password=current_app.config.get('MYSQL_PASSWORD')
            )
        else:
            # Fallback para variáveis de ambiente
            connection = mysql.connector.connect(
                host=os.environ.get('DB_HOST', 'localhost'),
                database=os.environ.get('DB_NAME', 'sistema_solicitacoes'),
                user=os.environ.get('DB_USER', 'root'),
                password=os.environ.get('DB_PASSWORD', 'sua_senha')
            )

        # Armazenar a conexão no contexto da aplicação
        if 'g' in globals() or 'g' in locals():
            g.db = connection

        return connection
    except Error as e:
        logger.error(f"Erro ao conectar ao MySQL: {e}")
        return None


@contextmanager
def db_cursor(dictionary=True, commit=True):
    """
    Gerenciador de contexto para trabalhar com cursor do banco de dados.
    Fecha automaticamente o cursor e a conexão, e faz commit se necessário.

    Args:
        dictionary (bool): Se True, retorna os resultados como dicionários.
        commit (bool): Se True, faz commit da transação ao final.

    Yields:
        Cursor: Objeto cursor para executar consultas.

    Uso:
        with db_cursor() as cursor:
            cursor.execute("SELECT * FROM tabela")
            resultados = cursor.fetchall()
    """
    connection = get_db_connection()
    if not connection:
        logger.error("Não foi possível obter conexão com o banco de dados")
        raise Exception("Erro de conexão com o banco de dados")

    cursor = None
    try:
        # Simplificar a criação do cursor
        if dictionary:
            cursor = connection.cursor(dictionary=True)
        else:
            cursor = connection.cursor()

        yield cursor

        if commit:
            connection.commit()
    except Error as e:
        if connection.is_connected():
            connection.rollback()
        logger.error(f"Erro na operação do banco de dados: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        # Não fechar a conexão se ela estiver armazenada no contexto da aplicação
        if 'g' not in globals() and 'g' not in locals() or 'db' not in g:
            connection.close()


def execute_query(query, params=None, dictionary=True, commit=True):
    """
    Executa uma consulta SQL com tratamento de erros e retorna os resultados.

    Args:
        query (str): Consulta SQL a ser executada.
        params (tuple, dict, list): Parâmetros para a consulta.
        dictionary (bool): Se True, retorna os resultados como dicionários.
        commit (bool): Se True, faz commit da transação ao final.

    Returns:
        list: Lista de resultados da consulta ou None em caso de erro.
    """
    try:
        with db_cursor(dictionary=dictionary, commit=commit) as cursor:
            cursor.execute(query, params or ())

            # Verificar se é uma consulta SELECT ou similar
            if query.strip().upper().startswith(('SELECT', 'SHOW', 'DESCRIBE')):
                return cursor.fetchall()
            else:
                # Para INSERT, UPDATE, DELETE retorna o número de linhas afetadas e o último ID
                return {
                    'rowcount': cursor.rowcount,
                    'lastrowid': cursor.lastrowid
                }
    except Exception as e:
        logger.error(
            f"Erro ao executar consulta SQL: {e}\nConsulta: {query}\nParâmetros: {params}")
        return None


def execute_many(query, params_list, commit=True):
    """
    Executa uma consulta SQL várias vezes com diferentes conjuntos de parâmetros.
    Útil para inserções ou atualizações em massa.

    Args:
        query (str): Consulta SQL a ser executada.
        params_list (list): Lista de conjuntos de parâmetros.
        commit (bool): Se True, faz commit da transação ao final.

    Returns:
        int: Número de linhas afetadas ou None em caso de erro.
    """
    if not params_list:
        return 0

    try:
        with db_cursor(dictionary=False, commit=commit) as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount
    except Exception as e:
        logger.error(
            f"Erro ao executar consulta em massa: {e}\nConsulta: {query}")
        return None


def get_single_result(query, params=None, dictionary=True):
    """
    Executa uma consulta e retorna apenas o primeiro resultado.

    Args:
        query (str): Consulta SQL a ser executada.
        params (tuple, dict, list): Parâmetros para a consulta.
        dictionary (bool): Se True, retorna o resultado como dicionário.

    Returns:
        dict/tuple: Primeiro resultado da consulta ou None.
    """
    try:
        with db_cursor(dictionary=dictionary) as cursor:
            cursor.execute(query, params or ())
            return cursor.fetchone()
    except Exception as e:
        logger.error(
            f"Erro ao buscar resultado único: {e}\nConsulta: {query}\nParâmetros: {params}")
        return None


def insert_data(table, data):
    """
    Insere dados em uma tabela de forma simplificada.

    Args:
        table (str): Nome da tabela.
        data (dict): Dicionário com os dados a serem inseridos no formato {coluna: valor}.

    Returns:
        int: ID do registro inserido ou None em caso de erro.
    """
    if not data:
        return None

    try:
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        with db_cursor() as cursor:
            cursor.execute(query, list(data.values()))
            return cursor.lastrowid
    except Exception as e:
        logger.error(
            f"Erro ao inserir dados: {e}\nTabela: {table}\nDados: {data}")
        return None


def update_data(table, data, condition_column, condition_value):
    """
    Atualiza dados em uma tabela de forma simplificada.

    Args:
        table (str): Nome da tabela.
        data (dict): Dicionário com os dados a serem atualizados no formato {coluna: valor}.
        condition_column (str): Nome da coluna para a condição WHERE.
        condition_value: Valor para a condição WHERE.

    Returns:
        int: Número de linhas afetadas ou None em caso de erro.
    """
    if not data:
        return 0

    try:
        set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {condition_column} = %s"

        params = list(data.values())
        params.append(condition_value)

        with db_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
    except Exception as e:
        logger.error(
            f"Erro ao atualizar dados: {e}\nTabela: {table}\nDados: {data}\nCondição: {condition_column}={condition_value}")
        return None


def close_db_connection(e=None):
    """
    Fecha a conexão com o banco de dados armazenada no contexto da aplicação.
    Esta função deve ser registrada como teardown_appcontext.
    """
    try:
        db = g.pop('db', None)
        if db is not None:
            try:
                if hasattr(db, 'is_connected') and db.is_connected():
                    db.close()
                    logger.debug(
                        "Conexão com o banco de dados fechada com sucesso")
            except Exception as e:
                logger.error(
                    f"Erro ao fechar conexão com o banco de dados: {e}")
    except Exception as e:
        logger.error(f"Erro no teardown do contexto da aplicação: {e}")


def init_app(app):
    """
    Inicializa as funções de banco de dados com a aplicação Flask.
    """
    app.teardown_appcontext(close_db_connection)
