# coding: utf-8
import os
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import mysql.connector
from mysql.connector import Error

from utils.db import get_db_connection
from utils.auth import verificar_permissao

# Configurar logger
logger = logging.getLogger('centros_custo')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.FileHandler('centros_custo.log')
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Criação do blueprint como submódulo
mod_centros_custo = Blueprint(
    'centros_custo', __name__, template_folder='templates')


def init_app(parent_blueprint):
    """Inicializa o módulo de centros de custo como submódulo de cadastros"""
    logger.info("Inicializando submódulo de centros de custo")
    return parent_blueprint

#
# Rotas para gerenciamento de centros de custo
#


@mod_centros_custo.route('/')
def index():
    """Página inicial do módulo de centros de custo"""
    return redirect(url_for('cadastros.centros_custo.listar'))


@mod_centros_custo.route('/listar')
def listar():
    """Lista todos os centros de custo cadastrados"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para acessar esta página', 'danger')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, codigo, nome, descricao, ativo, DATE_FORMAT(data_cadastro, '%d/%m/%Y') as data_cadastro 
            FROM centros_custo 
            ORDER BY codigo
        """)
        centros = cursor.fetchall()

        cursor.close()
        conn.close()

        # Verificar permissão para edição
        pode_editar = verificar_permissao('editar')

        return render_template('cadastros/centros_custo/listar.html',
                               centros=centros,
                               pode_editar=pode_editar)

    except Exception as e:
        logger.error(f"Erro ao listar centros de custo: {str(e)}")
        flash(f"Erro ao listar centros de custo: {str(e)}", "danger")
        return redirect(url_for('dashboard'))


@mod_centros_custo.route('/novo', methods=['GET', 'POST'])
def novo():
    """Cadastra um novo centro de custo"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para cadastrar centros de custo', 'danger')
        return redirect(url_for('cadastros.centros_custo.listar'))

    if request.method == 'POST':
        try:
            # Obter dados do formulário
            codigo = request.form.get('codigo')
            nome = request.form.get('nome')
            descricao = request.form.get('descricao')
            ativo = 'ativo' in request.form  # Checkbox

            # Validar campos obrigatórios
            if not codigo or not nome:
                flash('Preencha todos os campos obrigatórios', 'warning')
                return render_template('cadastros/centros_custo/novo.html')

            # Inserir no banco de dados
            conn = get_db_connection()
            cursor = conn.cursor()

            query = """
                INSERT INTO centros_custo (
                    codigo, nome, descricao, ativo, data_cadastro, usuario_cadastro
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """

            cursor.execute(query, (
                codigo, nome, descricao, ativo,
                datetime.now(), session.get('usuario_id')
            ))

            conn.commit()
            cursor.close()
            conn.close()

            flash('Centro de Custo cadastrado com sucesso!', 'success')
            return redirect(url_for('cadastros.centros_custo.listar'))

        except Exception as e:
            logger.error(f"Erro ao cadastrar centro de custo: {str(e)}")
            flash(f"Erro ao cadastrar centro de custo: {str(e)}", "danger")
            return render_template('cadastros/centros_custo/novo.html')

    # Método GET - exibir formulário
    return render_template('cadastros/centros_custo/novo.html')


@mod_centros_custo.route('/visualizar/<int:id>')
def visualizar(id):
    """Visualiza os detalhes de um centro de custo"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para visualizar centros de custo', 'danger')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT id, codigo, nome, descricao, ativo, 
                   data_cadastro, usuario_cadastro
            FROM centros_custo
            WHERE id = %s
        """

        cursor.execute(query, (id,))
        centro = cursor.fetchone()

        cursor.close()
        conn.close()

        if not centro:
            flash('Centro de Custo não encontrado', 'warning')
            return redirect(url_for('cadastros.centros_custo.listar'))

        # Verificar permissão para edição
        pode_editar = verificar_permissao('editar')

        return render_template('cadastros/centros_custo/visualizar.html',
                               centro=centro,
                               pode_editar=pode_editar)

    except Exception as e:
        logger.error(f"Erro ao visualizar centro de custo: {str(e)}")
        flash(f"Erro ao visualizar centro de custo: {str(e)}", "danger")
        return redirect(url_for('cadastros.centros_custo.listar'))


@mod_centros_custo.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """Edita um centro de custo existente"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para editar centros de custo', 'danger')
        return redirect(url_for('cadastros.centros_custo.listar'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if request.method == 'POST':
            # Obter dados do formulário
            codigo = request.form.get('codigo')
            nome = request.form.get('nome')
            descricao = request.form.get('descricao')
            ativo = 'ativo' in request.form  # Checkbox

            # Validar campos obrigatórios
            if not codigo or not nome:
                flash('Preencha todos os campos obrigatórios', 'warning')
                cursor.execute(
                    "SELECT * FROM centros_custo WHERE id = %s", (id,))
                centro = cursor.fetchone()
                return render_template('cadastros/centros_custo/editar.html', centro=centro)

            # Atualizar no banco de dados
            query = """
                UPDATE centros_custo SET
                    codigo = %s, nome = %s, descricao = %s, 
                    ativo = %s, data_atualizacao = %s
                WHERE id = %s
            """

            cursor.execute(query, (
                codigo, nome, descricao, ativo,
                datetime.now(), id
            ))

            conn.commit()
            flash('Centro de Custo atualizado com sucesso!', 'success')
            return redirect(url_for('cadastros.centros_custo.visualizar', id=id))

        else:
            # Método GET - exibir formulário com dados atuais
            cursor.execute("""
                SELECT id, codigo, nome, descricao, ativo, 
                       data_cadastro
                FROM centros_custo
                WHERE id = %s
            """, (id,))

            centro = cursor.fetchone()

            if not centro:
                flash('Centro de Custo não encontrado', 'warning')
                return redirect(url_for('cadastros.centros_custo.listar'))

            return render_template('cadastros/centros_custo/editar.html', centro=centro)

    except Exception as e:
        logger.error(f"Erro ao editar centro de custo: {str(e)}")
        flash(f"Erro ao editar centro de custo: {str(e)}", "danger")
        return redirect(url_for('cadastros.centros_custo.listar'))

    finally:
        cursor.close()
        conn.close()


@mod_centros_custo.route('/alternar-status/<int:id>')
def alternar_status(id):
    """Alterna o status de ativo/inativo de um centro de custo"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para alterar centros de custo', 'danger')
        return redirect(url_for('cadastros.centros_custo.listar'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Obter status atual
        cursor.execute("SELECT ativo FROM centros_custo WHERE id = %s", (id,))
        centro = cursor.fetchone()

        if not centro:
            flash('Centro de Custo não encontrado', 'warning')
            return redirect(url_for('cadastros.centros_custo.listar'))

        # Inverter o status
        novo_status = not centro['ativo']

        # Atualizar no banco de dados
        cursor.execute("""
            UPDATE centros_custo SET
                ativo = %s,
                data_atualizacao = %s
            WHERE id = %s
        """, (novo_status, datetime.now(), id))

        conn.commit()
        cursor.close()
        conn.close()

        status_texto = "ativado" if novo_status else "desativado"
        flash(f'Centro de Custo {status_texto} com sucesso!', 'success')

    except Exception as e:
        logger.error(f"Erro ao alternar status do centro de custo: {str(e)}")
        flash(
            f"Erro ao alternar status do centro de custo: {str(e)}", "danger")

    return redirect(url_for('cadastros.centros_custo.listar'))
