from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import os
import logging
from datetime import datetime
import mysql.connector
from mysql.connector import Error

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
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    return render_template('cadastros/index.html')

# Rotas para Materiais


@mod_cadastros.route('/materiais')
def materiais():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    materiais = []
    connection = get_db_connection()

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM materiais 
                ORDER BY codigo
            """)
            materiais = cursor.fetchall()
            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao buscar materiais: {str(e)}")
            flash(f'Erro ao buscar materiais: {str(e)}', 'danger')
        finally:
            connection.close()

    return render_template('cadastros/materiais.html', materiais=materiais)


@mod_cadastros.route('/materiais/novo', methods=['GET', 'POST'])
def novo_material():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        codigo = request.form.get('codigo')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        unidade = request.form.get('unidade')

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    INSERT INTO materiais (codigo, nome, descricao, unidade, ativo, criado_em)
                    VALUES (%s, %s, %s, %s, TRUE, NOW())
                """, (codigo, nome, descricao, unidade))

                connection.commit()
                flash('Material cadastrado com sucesso!', 'success')
                return redirect(url_for('cadastros.materiais'))

            except Exception as e:
                connection.rollback()
                logger.error(f"Erro ao cadastrar material: {str(e)}")
                flash(f'Erro ao cadastrar material: {str(e)}', 'danger')
            finally:
                cursor.close()
                connection.close()

    return render_template('cadastros/material_form.html')

# Rotas para Centros de Custo


@mod_cadastros.route('/centros-custo')
def centros_custo():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    centros = []
    connection = get_db_connection()

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM centros_custo 
                ORDER BY codigo
            """)
            centros = cursor.fetchall()
            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao buscar centros de custo: {str(e)}")
            flash(f'Erro ao buscar centros de custo: {str(e)}', 'danger')
        finally:
            connection.close()

    return render_template('cadastros/centros_custo.html', centros=centros)


@mod_cadastros.route('/centros-custo/novo', methods=['GET', 'POST'])
def novo_centro_custo():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        codigo = request.form.get('codigo')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    INSERT INTO centros_custo (codigo, nome, descricao, ativo)
                    VALUES (%s, %s, %s, TRUE)
                """, (codigo, nome, descricao))

                connection.commit()
                flash('Centro de Custo cadastrado com sucesso!', 'success')
                return redirect(url_for('cadastros.centros_custo'))

            except Exception as e:
                connection.rollback()
                logger.error(f"Erro ao cadastrar centro de custo: {str(e)}")
                flash(f'Erro ao cadastrar centro de custo: {str(e)}', 'danger')
            finally:
                cursor.close()
                connection.close()

    return render_template('cadastros/centro_custo_form.html')

# Função de inicialização do módulo


def init_app(app):
    """Função para inicializar o módulo com a aplicação Flask"""
    return app
