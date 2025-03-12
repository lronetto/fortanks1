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
        logging.FileHandler('solicitacao.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Criar o Blueprint
mod_solicitacao = Blueprint('solicitacao', __name__,
                            template_folder='templates',
                            url_prefix='/solicitacao')


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

# Rota principal - dashboard de solicitações


@mod_solicitacao.route('/')
def index():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    solicitacoes = []
    estatisticas = {
        'total': 0,
        'pendentes': 0,
        'aprovadas': 0,
        'rejeitadas': 0
    }

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar solicitações do usuário
            cursor.execute("""
                SELECT s.*, cc.nome as centro_custo_nome, u.nome as solicitante_nome
                FROM solicitacoes s
                LEFT JOIN centros_custo cc ON s.centro_custo_id = cc.id
                LEFT JOIN usuarios u ON s.solicitante_id = u.id
                WHERE s.solicitante_id = %s
                ORDER BY s.data_solicitacao DESC
                LIMIT 10
            """, [session['usuario_id']])
            solicitacoes = cursor.fetchall()

            # Buscar estatísticas
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pendente' THEN 1 ELSE 0 END) as pendentes,
                    SUM(CASE WHEN status = 'aprovada' THEN 1 ELSE 0 END) as aprovadas,
                    SUM(CASE WHEN status = 'rejeitada' THEN 1 ELSE 0 END) as rejeitadas
                FROM solicitacoes
                WHERE solicitante_id = %s
            """, [session['usuario_id']])
            stats = cursor.fetchone()

            if stats:
                estatisticas.update(stats)

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao carregar dashboard: {str(e)}")
            flash(f'Erro ao carregar dashboard: {str(e)}', 'danger')
        finally:
            connection.close()

    return render_template('solicitacao/index.html',
                           solicitacoes=solicitacoes,
                           estatisticas=estatisticas)

# Rota para criar nova solicitação


@mod_solicitacao.route('/nova', methods=['GET', 'POST'])
def nova_solicitacao():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        justificativa = request.form.get('justificativa')
        centro_custo_id = request.form.get('centro_custo_id')
        materiais = request.form.getlist('material_id[]')
        quantidades = request.form.getlist('quantidade[]')
        observacoes = request.form.getlist('observacao[]')

        if not justificativa or not centro_custo_id or not materiais:
            flash('Preencha todos os campos obrigatórios', 'warning')
            return redirect(request.url)

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()

                # Inserir solicitação
                cursor.execute("""
                    INSERT INTO solicitacoes 
                    (justificativa, solicitante_id, centro_custo_id, status, data_solicitacao)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (justificativa, session['usuario_id'], centro_custo_id, 'pendente'))

                solicitacao_id = cursor.lastrowid

                # Inserir itens
                for i in range(len(materiais)):
                    cursor.execute("""
                        INSERT INTO itens_solicitacao 
                        (solicitacao_id, material_id, quantidade, observacao)
                        VALUES (%s, %s, %s, %s)
                    """, (solicitacao_id, materiais[i], quantidades[i], observacoes[i]))

                connection.commit()
                flash('Solicitação criada com sucesso!', 'success')
                return redirect(url_for('solicitacao.index'))

            except Exception as e:
                connection.rollback()
                logger.error(f"Erro ao criar solicitação: {str(e)}")
                flash(f'Erro ao criar solicitação: {str(e)}', 'danger')
            finally:
                cursor.close()
                connection.close()

    # Buscar dados para o formulário
    connection = get_db_connection()
    materiais = []
    centros_custo = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar materiais disponíveis
            cursor.execute(
                "SELECT * FROM materiais WHERE ativo = TRUE ORDER BY nome")
            materiais = cursor.fetchall()

            # Buscar centros de custo
            cursor.execute(
                "SELECT * FROM centros_custo WHERE ativo = TRUE ORDER BY codigo")
            centros_custo = cursor.fetchall()

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao carregar dados do formulário: {str(e)}")
        finally:
            connection.close()

    return render_template('solicitacao/nova.html',
                           materiais=materiais,
                           centros_custo=centros_custo)

# Rota para visualizar solicitação


@mod_solicitacao.route('/<int:solicitacao_id>')
def visualizar(solicitacao_id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    solicitacao = None
    itens = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar dados da solicitação
            cursor.execute("""
                SELECT s.*, cc.nome as centro_custo_nome, u.nome as solicitante_nome
                FROM solicitacoes s
                LEFT JOIN centros_custo cc ON s.centro_custo_id = cc.id
                LEFT JOIN usuarios u ON s.solicitante_id = u.id
                WHERE s.id = %s
            """, [solicitacao_id])
            solicitacao = cursor.fetchone()

            if solicitacao:
                # Buscar itens da solicitação
                cursor.execute("""
                    SELECT i.*, m.nome as material_nome, m.codigo as material_codigo
                    FROM itens_solicitacao i
                    LEFT JOIN materiais m ON i.material_id = m.id
                    WHERE i.solicitacao_id = %s
                """, [solicitacao_id])
                itens = cursor.fetchall()

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao buscar solicitação: {str(e)}")
            flash(f'Erro ao buscar solicitação: {str(e)}', 'danger')
        finally:
            connection.close()

    if not solicitacao:
        flash('Solicitação não encontrada', 'warning')
        return redirect(url_for('solicitacao.index'))

    return render_template('solicitacao/visualizar.html',
                           solicitacao=solicitacao,
                           itens=itens)

# Rota para aprovar solicitação


@mod_solicitacao.route('/<int:solicitacao_id>/aprovar', methods=['POST'])
def aprovar(solicitacao_id):
    if 'usuario_id' not in session or session.get('cargo') != 'admin':
        return jsonify({'success': False, 'message': 'Não autorizado'}), 403

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()

            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes 
                SET status = 'aprovada',
                    aprovador_id = %s,
                    data_aprovacao = NOW()
                WHERE id = %s
            """, (session['usuario_id'], solicitacao_id))

            connection.commit()
            flash('Solicitação aprovada com sucesso!', 'success')
            return jsonify({'success': True})

        except Exception as e:
            connection.rollback()
            logger.error(f"Erro ao aprovar solicitação: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    return jsonify({'success': False, 'message': 'Erro de conexão'}), 500

# Rota para rejeitar solicitação


@mod_solicitacao.route('/<int:solicitacao_id>/rejeitar', methods=['POST'])
def rejeitar(solicitacao_id):
    if 'usuario_id' not in session or session.get('cargo') != 'admin':
        return jsonify({'success': False, 'message': 'Não autorizado'}), 403

    motivo = request.form.get('motivo')
    if not motivo:
        return jsonify({'success': False, 'message': 'Motivo é obrigatório'}), 400

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()

            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes 
                SET status = 'rejeitada',
                    aprovador_id = %s,
                    data_aprovacao = NOW(),
                    motivo_rejeicao = %s
                WHERE id = %s
            """, (session['usuario_id'], motivo, solicitacao_id))

            connection.commit()
            flash('Solicitação rejeitada com sucesso!', 'success')
            return jsonify({'success': True})

        except Exception as e:
            connection.rollback()
            logger.error(f"Erro ao rejeitar solicitação: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    return jsonify({'success': False, 'message': 'Erro de conexão'}), 500

# Função de inicialização do módulo


def init_app(app):
    """Função para inicializar o módulo com a aplicação Flask"""

    @app.context_processor
    def inject_menu_data():
        return {
            'modulo_solicitacao': True
        }

    return app
