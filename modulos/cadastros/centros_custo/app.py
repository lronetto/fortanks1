# coding: utf-8
import os
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import mysql.connector
from mysql.connector import Error

from utils.db import get_db_connection, execute_query, get_single_result, insert_data, update_data
from utils.auth import login_obrigatorio, admin_obrigatorio, verificar_permissao

# Configurar logger
log_dir = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'centros_custo.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
@login_obrigatorio
def index():
    """Página inicial do módulo de centros de custo"""
    return redirect(url_for('centros_custo.listar'))


@mod_centros_custo.route('/listar')
@login_obrigatorio
def listar():
    """Lista todos os centros de custo cadastrados"""
    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para visualizar centros de custo.', 'warning')
        return redirect(url_for('dashboard'))

    try:
        # Obter centros de custo ativos
        query_ativos = """
            SELECT cc.*, u.nome as criado_por_nome
            FROM centros_custo cc
            LEFT JOIN usuarios u ON cc.criado_por = u.id
            WHERE cc.ativo = 1
            ORDER BY cc.nome
        """
        centros_custo_ativos = execute_query(query_ativos)

        # Obter centros de custo inativos
        query_inativos = """
            SELECT cc.*, u.nome as criado_por_nome
            FROM centros_custo cc
            LEFT JOIN usuarios u ON cc.criado_por = u.id
            WHERE cc.ativo = 0
            ORDER BY cc.nome
        """
        centros_custo_inativos = execute_query(query_inativos)

    except Exception as e:
        logger.error(f"Erro ao listar centros de custo: {str(e)}")
        flash('Ocorreu um erro ao carregar os centros de custo. Por favor, tente novamente.', 'danger')
        centros_custo_ativos = []
        centros_custo_inativos = []

    return render_template('cadastros/centros_custo/listar.html',
                           centros_custo_ativos=centros_custo_ativos or [],
                           centros_custo_inativos=centros_custo_inativos or [])


@mod_centros_custo.route('/novo', methods=['GET', 'POST'])
@login_obrigatorio
def novo():
    """Cadastra um novo centro de custo"""
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para cadastrar centros de custo.', 'warning')
        return redirect(url_for('centros_custo.listar'))

    if request.method == 'POST':
        try:
            # Obter dados do formulário
            codigo = request.form.get('codigo', '').strip()
            nome = request.form.get('nome', '').strip()
            descricao = request.form.get('descricao', '').strip()

            # Validar campos obrigatórios
            if not codigo or not nome:
                flash('Preencha todos os campos obrigatórios', 'warning')
                return render_template('cadastros/centros_custo/novo.html')

            # Verificar se código já existe
            codigo_existe = get_single_result(
                "SELECT id FROM centros_custo WHERE codigo = %s",
                [codigo]
            )
            if codigo_existe:
                flash(f'O código {codigo} já está em uso.', 'danger')
                return render_template('cadastros/centros_custo/novo.html')

            # Inserir no banco de dados
            now = datetime.now()
            data = {
                'codigo': codigo,
                'nome': nome,
                'descricao': descricao,
                'ativo': 1,
                'criado_por': session['usuario_id'],
                'criado_em': now,
                'alterado_em': now
            }

            insert_data('centros_custo', data)

            logger.info(
                f"Centro de custo {nome} ({codigo}) cadastrado por {session['usuario_id']}")
            flash('Centro de Custo cadastrado com sucesso!', 'success')
            return redirect(url_for('centros_custo.listar'))

        except Exception as e:
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
