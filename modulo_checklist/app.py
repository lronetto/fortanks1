# modulo_checklist/app.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
import os
import json
import logging
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import Error

# Configuração de logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('checklist.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('checklist')

# Configuração do Blueprint
mod_checklist = Blueprint('checklist', __name__,
                          template_folder='templates',
                          static_folder='static')

# Função para conectar ao banco de dados


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

# Verificar permissões de acesso


def verificar_permissao(permissao_necessaria):
    """
    Verifica se o usuário tem a permissão necessária
    permissao_necessaria pode ser: 'visualizar', 'editar', 'aprovar', 'admin'
    """
    if 'logado' not in session:
        return False

    # Permissões baseadas no cargo
    permissoes = {
        'colaborador': ['visualizar'],
        'gerente': ['visualizar', 'editar', 'aprovar'],
        'diretor': ['visualizar', 'editar', 'aprovar'],
        'admin': ['visualizar', 'editar', 'aprovar', 'admin']
    }

    cargo = session.get('cargo', 'colaborador')
    return permissao_necessaria in permissoes.get(cargo, [])

# Rota principal - dashboard de checklists


@mod_checklist.route('/')
def index():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    # Estatísticas
    connection = get_db_connection()
    estatisticas = {
        'total_modelos': 0,
        'checklists_pendentes': 0,
        'checklists_concluidos': 0,
        'checklists_hoje': 0
    }

    modelos_recentes = []
    checklists_recentes = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Total de modelos
            cursor.execute(
                "SELECT COUNT(*) as total FROM checklist_modelos WHERE ativo = TRUE")
            resultado = cursor.fetchone()
            estatisticas['total_modelos'] = resultado['total'] if resultado else 0

            # Checklists pendentes
            cursor.execute(
                "SELECT COUNT(*) as total FROM checklist_preenchidos WHERE status = 'em_andamento'")
            resultado = cursor.fetchone()
            estatisticas['checklists_pendentes'] = resultado['total'] if resultado else 0

            # Checklists concluídos
            cursor.execute(
                "SELECT COUNT(*) as total FROM checklist_preenchidos WHERE status IN ('concluido', 'aprovado')")
            resultado = cursor.fetchone()
            estatisticas['checklists_concluidos'] = resultado['total'] if resultado else 0

            # Checklists de hoje
            cursor.execute(
                "SELECT COUNT(*) as total FROM checklist_preenchidos WHERE DATE(data_preenchimento) = CURDATE()")
            resultado = cursor.fetchone()
            estatisticas['checklists_hoje'] = resultado['total'] if resultado else 0

            # Modelos recentes
            cursor.execute("""
                SELECT m.*, u.nome as criador_nome, 
                (SELECT COUNT(*) FROM checklist_itens WHERE modelo_id = m.id AND ativo = TRUE) as total_itens
                FROM checklist_modelos m
                JOIN usuarios u ON m.criado_por = u.id
                WHERE m.ativo = TRUE
                ORDER BY m.criado_em DESC
                LIMIT 5
            """)
            modelos_recentes = cursor.fetchall()

            # Checklists recentes
            cursor.execute("""
                SELECT c.*, m.nome as modelo_nome, 
                u1.nome as responsavel_nome, u2.nome as supervisor_nome
                FROM checklist_preenchidos c
                JOIN checklist_modelos m ON c.modelo_id = m.id
                JOIN usuarios u1 ON c.responsavel_id = u1.id
                LEFT JOIN usuarios u2 ON c.supervisor_id = u2.id
                ORDER BY c.data_preenchimento DESC
                LIMIT 10
            """)
            checklists_recentes = cursor.fetchall()

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
        finally:
            connection.close()

    return render_template('checklist/index.html',
                           estatisticas=estatisticas,
                           modelos_recentes=modelos_recentes,
                           checklists_recentes=checklists_recentes)

# Rotas para gerenciamento de modelos de checklist


@mod_checklist.route('/modelos')
def listar_modelos():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para acessar esta página', 'danger')
        return redirect(url_for('checklist.index'))

    filtro_tipo = request.args.get('tipo', '')
    filtro_frequencia = request.args.get('frequencia', '')
    filtro_nome = request.args.get('nome', '')

    connection = get_db_connection()
    modelos = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Construir query com filtros
            query = """
                SELECT m.*, u.nome as criador_nome, 
                (SELECT COUNT(*) FROM checklist_itens WHERE modelo_id = m.id AND ativo = TRUE) as total_itens
                FROM checklist_modelos m
                JOIN usuarios u ON m.criado_por = u.id
                WHERE m.ativo = TRUE
            """
            params = []

            if filtro_tipo:
                query += " AND m.tipo_equipamento = %s"
                params.append(filtro_tipo)

            if filtro_frequencia:
                query += " AND m.frequencia = %s"
                params.append(filtro_frequencia)

            if filtro_nome:
                query += " AND m.nome LIKE %s"
                params.append(f"%{filtro_nome}%")

            query += " ORDER BY m.nome"

            cursor.execute(query, params)
            modelos = cursor.fetchall()

            # Obter lista de tipos de equipamento para o filtro
            cursor.execute(
                "SELECT DISTINCT tipo_equipamento FROM checklist_modelos WHERE ativo = TRUE ORDER BY tipo_equipamento")
            tipos_equipamento = [row['tipo_equipamento']
                                 for row in cursor.fetchall()]

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao listar modelos: {e}")
            flash(f"Erro ao listar modelos: {str(e)}", 'danger')
        finally:
            connection.close()

    return render_template('checklist/modelos.html',
                           modelos=modelos,
                           filtros={
                               'tipo': filtro_tipo,
                               'frequencia': filtro_frequencia,
                               'nome': filtro_nome
                           },
                           tipos_equipamento=tipos_equipamento if 'tipos_equipamento' in locals() else [],
                           pode_editar=verificar_permissao('editar'),
                           pode_admin=verificar_permissao('admin'))


@mod_checklist.route('/modelos/novo', methods=['GET', 'POST'])
def novo_modelo():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para criar modelos de checklist', 'danger')
        return redirect(url_for('checklist.listar_modelos'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        tipo_equipamento = request.form.get('tipo_equipamento')
        frequencia = request.form.get('frequencia')

        if not all([nome, tipo_equipamento, frequencia]):
            flash('Preencha todos os campos obrigatórios', 'warning')
            return redirect(url_for('checklist.novo_modelo'))

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()

                # Inserir o modelo
                cursor.execute("""
                    INSERT INTO checklist_modelos 
                    (nome, descricao, tipo_equipamento, frequencia, criado_por)
                    VALUES (%s, %s, %s, %s, %s)
                """, [nome, descricao, tipo_equipamento, frequencia, session['id_usuario']])

                modelo_id = cursor.lastrowid
                connection.commit()
                flash('Modelo de checklist criado com sucesso', 'success')

                # Redirecionar para a página de edição de itens
                return redirect(url_for('checklist.editar_itens', modelo_id=modelo_id))

            except Exception as e:
                connection.rollback()
                logger.error(f"Erro ao criar modelo: {e}")
                flash(f"Erro ao criar modelo: {str(e)}", 'danger')
            finally:
                cursor.close()
                connection.close()

    return render_template('checklist/novo_modelo.html')


@mod_checklist.route('/modelos/<int:modelo_id>/editar', methods=['GET', 'POST'])
def editar_modelo(modelo_id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para editar modelos de checklist', 'danger')
        return redirect(url_for('checklist.listar_modelos'))

    connection = get_db_connection()
    modelo = None

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar o modelo
            cursor.execute(
                "SELECT * FROM checklist_modelos WHERE id = %s", [modelo_id])
            modelo = cursor.fetchone()

            if not modelo:
                flash('Modelo não encontrado', 'warning')
                return redirect(url_for('checklist.listar_modelos'))

            if request.method == 'POST':
                nome = request.form.get('nome')
                descricao = request.form.get('descricao')
                tipo_equipamento = request.form.get('tipo_equipamento')
                frequencia = request.form.get('frequencia')
                ativo = 'ativo' in request.form

                if not all([nome, tipo_equipamento, frequencia]):
                    flash('Preencha todos os campos obrigatórios', 'warning')
                    return redirect(url_for('checklist.editar_modelo', modelo_id=modelo_id))

                # Atualizar o modelo
                cursor.execute("""
                    UPDATE checklist_modelos 
                    SET nome = %s, descricao = %s, tipo_equipamento = %s, 
                        frequencia = %s, ativo = %s
                    WHERE id = %s
                """, [nome, descricao, tipo_equipamento, frequencia, ativo, modelo_id])

                connection.commit()
                flash('Modelo atualizado com sucesso', 'success')
                return redirect(url_for('checklist.listar_modelos'))

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao editar modelo: {e}")
            flash(f"Erro ao editar modelo: {str(e)}", 'danger')
        finally:
            connection.close()

    return render_template('checklist/editar_modelo.html', modelo=modelo)


@mod_checklist.route('/modelos/<int:modelo_id>/itens', methods=['GET', 'POST'])
def editar_itens(modelo_id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para editar itens de checklist', 'danger')
        return redirect(url_for('checklist.listar_modelos'))

    connection = get_db_connection()
    modelo = None
    itens = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar o modelo
            cursor.execute(
                "SELECT * FROM checklist_modelos WHERE id = %s", [modelo_id])
            modelo = cursor.fetchone()

            if not modelo:
                flash('Modelo não encontrado', 'warning')
                return redirect(url_for('checklist.listar_modelos'))

            # Buscar os itens do modelo
            cursor.execute("""
                SELECT * FROM checklist_itens 
                WHERE modelo_id = %s 
                ORDER BY ordem
            """, [modelo_id])
            itens = cursor.fetchall()

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao buscar itens do modelo: {e}")
            flash(f"Erro ao buscar itens do modelo: {str(e)}", 'danger')
        finally:
            connection.close()

    return render_template('checklist/editar_itens.html', modelo=modelo, itens=itens)


@mod_checklist.route('/modelos/<int:modelo_id>/item', methods=['POST'])
def adicionar_item(modelo_id):
    if 'logado' not in session:
        return jsonify({'success': False, 'message': 'Faça login para acessar o sistema'}), 401

    if not verificar_permissao('editar'):
        return jsonify({'success': False, 'message': 'Você não tem permissão para adicionar itens'}), 403

    try:
        data = request.get_json()

        texto = data.get('texto')
        tipo_resposta = data.get('tipo_resposta')
        ordem = data.get('ordem', 0)
        obrigatorio = data.get('obrigatorio', True)
        valores_possiveis = json.dumps(data.get('valores_possiveis', [])) if data.get(
            'valores_possiveis') else None
        valor_minimo = data.get('valor_minimo')
        valor_maximo = data.get('valor_maximo')
        unidade = data.get('unidade')

        if not all([texto, tipo_resposta]):
            return jsonify({'success': False, 'message': 'Preencha todos os campos obrigatórios'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'success': False, 'message': 'Erro de conexão com o banco de dados'}), 500

        try:
            cursor = connection.cursor()

            # Inserir o item
            cursor.execute("""
                INSERT INTO checklist_itens 
                (modelo_id, texto, tipo_resposta, ordem, obrigatorio, 
                valores_possiveis, valor_minimo, valor_maximo, unidade)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [modelo_id, texto, tipo_resposta, ordem, obrigatorio,
                  valores_possiveis, valor_minimo, valor_maximo, unidade])

            item_id = cursor.lastrowid
            connection.commit()

            # Buscar o item inserido
            cursor.execute(
                "SELECT * FROM checklist_itens WHERE id = %s", [item_id])
            item = cursor.fetchone()

            cursor.close()
            connection.close()

            return jsonify({'success': True, 'message': 'Item adicionado com sucesso', 'item': item})

        except Exception as e:
            connection.rollback()
            logger.error(f"Erro ao adicionar item: {e}")
            return jsonify({'success': False, 'message': f'Erro ao adicionar item: {str(e)}'}), 500
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()
    except Exception as e:
        logger.error(f"Erro ao processar requisição: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400


@mod_checklist.route('/modelos/item/<int:item_id>', methods=['PUT', 'DELETE'])
def gerenciar_item(item_id):
    if 'logado' not in session:
        return jsonify({'success': False, 'message': 'Faça login para acessar o sistema'}), 401

    if not verificar_permissao('editar'):
        return jsonify({'success': False, 'message': 'Você não tem permissão para editar itens'}), 403

    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'message': 'Erro de conexão com o banco de dados'}), 500

    try:
        cursor = connection.cursor(dictionary=True)

        # Verificar se o item existe
        cursor.execute(
            "SELECT * FROM checklist_itens WHERE id = %s", [item_id])
        item = cursor.fetchone()

        if not item:
            return jsonify({'success': False, 'message': 'Item não encontrado'}), 404

        if request.method == 'DELETE':
            # Excluir o item (ou apenas marcar como inativo)
            cursor.execute(
                "UPDATE checklist_itens SET ativo = FALSE WHERE id = %s", [item_id])
            connection.commit()
            return jsonify({'success': True, 'message': 'Item removido com sucesso'})

        elif request.method == 'PUT':
            data = request.get_json()

            texto = data.get('texto')
            tipo_resposta = data.get('tipo_resposta')
            ordem = data.get('ordem', 0)
            obrigatorio = data.get('obrigatorio', True)
            valores_possiveis = json.dumps(data.get('valores_possiveis', [])) if data.get(
                'valores_possiveis') else None
            valor_minimo = data.get('valor_minimo')
            valor_maximo = data.get('valor_maximo')
            unidade = data.get('unidade')

            if not all([texto, tipo_resposta]):
                return jsonify({'success': False, 'message': 'Preencha todos os campos obrigatórios'}), 400

            # Atualizar o item
            cursor.execute("""
                UPDATE checklist_itens 
                SET texto = %s, tipo_resposta = %s, ordem = %s, 
                    obrigatorio = %s, valores_possiveis = %s, 
                    valor_minimo = %s, valor_maximo = %s, unidade = %s
                WHERE id = %s
            """, [texto, tipo_resposta, ordem, obrigatorio,
                  valores_possiveis, valor_minimo, valor_maximo, unidade, item_id])

            connection.commit()

            # Buscar o item atualizado
            cursor.execute(
                "SELECT * FROM checklist_itens WHERE id = %s", [item_id])
            item_atualizado = cursor.fetchone()

            return jsonify({'success': True, 'message': 'Item atualizado com sucesso', 'item': item_atualizado})

    except Exception as e:
        connection.rollback()
        logger.error(f"Erro ao gerenciar item: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@mod_checklist.route('/modelos/<int:modelo_id>/reordenar', methods=['POST'])
def reordenar_itens(modelo_id):
    if 'logado' not in session:
        return jsonify({'success': False, 'message': 'Faça login para acessar o sistema'}), 401

    if not verificar_permissao('editar'):
        return jsonify({'success': False, 'message': 'Você não tem permissão para reordenar itens'}), 403

    try:
        data = request.get_json()
        item_ids = data.get('item_ids', [])

        if not item_ids:
            return jsonify({'success': False, 'message': 'Nenhum item para reordenar'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'success': False, 'message': 'Erro de conexão com o banco de dados'}), 500

        try:
            cursor = connection.cursor()

            # Atualizar a ordem dos itens
            for ordem, item_id in enumerate(item_ids, 1):
                cursor.execute("UPDATE checklist_itens SET ordem = %s WHERE id = %s", [
                               ordem, item_id])

            connection.commit()
            return jsonify({'success': True, 'message': 'Itens reordenados com sucesso'})

        except Exception as e:
            connection.rollback()
            logger.error(f"Erro ao reordenar itens: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    except Exception as e:
        logger.error(f"Erro ao processar requisição: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400

# Rotas para preenchimento de checklists


@mod_checklist.route('/checklists')
def listar_checklists():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    filtro_status = request.args.get('status', '')
    filtro_modelo = request.args.get('modelo_id', '')
    filtro_equipamento = request.args.get('equipamento', '')
    filtro_data_inicio = request.args.get('data_inicio', '')
    filtro_data_fim = request.args.get('data_fim', '')
    apenas_meus = 'apenas_meus' in request.args

    connection = get_db_connection()
    checklists = []
    modelos = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar modelos para o filtro
            cursor.execute(
                "SELECT id, nome FROM checklist_modelos WHERE ativo = TRUE ORDER BY nome")
            modelos = cursor.fetchall()

            # Construir query com filtros
            query = """
                SELECT c.*, m.nome as modelo_nome, 
                u1.nome as responsavel_nome, u2.nome as supervisor_nome
                FROM checklist_preenchidos c
                JOIN checklist_modelos m ON c.modelo_id = m.id
                JOIN usuarios u1 ON c.responsavel_id = u1.id
                LEFT JOIN usuarios u2 ON c.supervisor_id = u2.id
                WHERE 1=1
            """
            params = []

            if filtro_status:
                query += " AND c.status = %s"
                params.append(filtro_status)

            if filtro_modelo:
                query += " AND c.modelo_id = %s"
                params.append(filtro_modelo)

            if filtro_equipamento:
                query += " AND (c.equipamento_id LIKE %s OR c.equipamento_nome LIKE %s)"
                params.extend([f"%{filtro_equipamento}%",
                              f"%{filtro_equipamento}%"])

            if filtro_data_inicio:
                query += " AND DATE(c.data_preenchimento) >= %s"
                params.append(filtro_data_inicio)

            if filtro_data_fim:
                query += " AND DATE(c.data_preenchimento) <= %s"
                params.append(filtro_data_fim)

            if apenas_meus:
                query += " AND c.responsavel_id = %s"
                params.append(session['id_usuario'])

            query += " ORDER BY c.data_preenchimento DESC"

            cursor.execute(query, params)
            checklists = cursor.fetchall()

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao listar checklists: {e}")
            flash(f"Erro ao listar checklists: {str(e)}", 'danger')
        finally:
            connection.close()

    return render_template('checklist/checklists.html',
                           checklists=checklists,
                           modelos=modelos,
                           filtros={
                               'status': filtro_status,
                               'modelo_id': filtro_modelo,
                               'equipamento': filtro_equipamento,
                               'data_inicio': filtro_data_inicio,
                               'data_fim': filtro_data_fim,
                               'apenas_meus': apenas_meus
                           },
                           pode_aprovar=verificar_permissao('aprovar'))


@mod_checklist.route('/checklists/novo', methods=['GET', 'POST'])
def novo_checklist():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    connection = get_db_connection()
    modelos = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar modelos disponíveis
            cursor.execute("""
                SELECT m.*, 
                (SELECT COUNT(*) FROM checklist_itens WHERE modelo_id = m.id AND ativo = TRUE) as total_itens
                FROM checklist_modelos m
                WHERE m.ativo = TRUE
                ORDER BY m.nome
            """)
            modelos = cursor.fetchall()

            if request.method == 'POST':
                modelo_id = request.form.get('modelo_id')
                equipamento_id = request.form.get('equipamento_id')
                equipamento_nome = request.form.get('equipamento_nome')
                equipamento_local = request.form.get('equipamento_local')
                observacoes = request.form.get('observacoes')

                if not all([modelo_id, equipamento_id, equipamento_nome]):
                    flash('Preencha todos os campos obrigatórios', 'warning')
                    return redirect(url_for('checklist.novo_checklist'))

                # Criar novo checklist
                cursor.execute("""
                    INSERT INTO checklist_preenchidos 
                    (modelo_id, equipamento_id, equipamento_nome, equipamento_local, 
                    responsavel_id, observacoes, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, [
                    modelo_id, equipamento_id, equipamento_nome, equipamento_local,
                    session['id_usuario'], observacoes, 'em_andamento'
                ])

                checklist_id = cursor.lastrowid
                connection.commit()

                flash('Checklist criado com sucesso', 'success')
                return redirect(url_for('checklist.preencher_checklist', checklist_id=checklist_id))

            cursor.close()
        except Exception as e:
            if 'connection' in locals() and connection.is_connected():
                connection.rollback()
            logger.error(f"Erro ao criar checklist: {e}")
            flash(f"Erro ao criar checklist: {str(e)}", 'danger')
        finally:
            if 'connection' in locals() and connection.is_connected():
                connection.close()

    return render_template('checklist/novo_checklist.html', modelos=modelos)


@mod_checklist.route('/checklists/<int:checklist_id>/preencher', methods=['GET', 'POST'])
def preencher_checklist(checklist_id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    connection = get_db_connection()
    checklist = None
    itens = []
    respostas = {}

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar o checklist
            cursor.execute("""
                SELECT c.*, m.nome as modelo_nome 
                FROM checklist_preenchidos c
                JOIN checklist_modelos m ON c.modelo_id = m.id
                WHERE c.id = %s
            """, [checklist_id])
            checklist = cursor.fetchone()

            if not checklist:
                flash('Checklist não encontrado', 'warning')
                return redirect(url_for('checklist.listar_checklists'))

            # Verificar permissão - apenas o responsável pode preencher
            if checklist['responsavel_id'] != session['id_usuario'] and not verificar_permissao('admin'):
                flash('Você não tem permissão para preencher este checklist', 'danger')
                return redirect(url_for('checklist.listar_checklists'))

            # Verificar se o checklist já foi concluído
            if checklist['status'] not in ['em_andamento']:
                flash(
                    'Este checklist já foi concluído e não pode ser editado', 'warning')
                return redirect(url_for('checklist.visualizar_checklist', checklist_id=checklist_id))

            # Buscar itens do modelo
            cursor.execute("""
                SELECT i.* 
                FROM checklist_itens i
                WHERE i.modelo_id = %s AND i.ativo = TRUE
                ORDER BY i.ordem
            """, [checklist['modelo_id']])
            itens = cursor.fetchall()

            # Buscar respostas já preenchidas
            cursor.execute("""
                SELECT * FROM checklist_respostas
                WHERE checklist_id = %s
            """, [checklist_id])
            for resposta in cursor.fetchall():
                respostas[resposta['item_id']] = resposta

            # Processar submissão
            if request.method == 'POST' and request.form.get('acao') == 'salvar':
                # Processar as respostas
                for item in itens:
                    item_id = item['id']
                    prefix = f"item_{item_id}_"

                    resposta_texto = request.form.get(prefix + 'texto', '')
                    resposta_numerica = request.form.get(
                        prefix + 'numerica', None)
                    resposta_booleana = request.form.get(
                        prefix + 'booleana') == 'sim'
                    conformidade = request.form.get(
                        prefix + 'conformidade', 'conforme')
                    observacao = request.form.get(prefix + 'observacao', '')

                    # Converter valor numérico se aplicável
                    if resposta_numerica and resposta_numerica.strip():
                        try:
                            resposta_numerica = float(
                                resposta_numerica.replace(',', '.'))
                        except:
                            resposta_numerica = None
                    else:
                        resposta_numerica = None

                    # Verificar se já existe uma resposta para este item
                    if item_id in respostas:
                        # Atualizar resposta existente
                        cursor.execute("""
                            UPDATE checklist_respostas
                            SET resposta_texto = %s, resposta_numerica = %s, 
                                resposta_booleana = %s, conformidade = %s, 
                                observacao = %s, data_resposta = NOW()
                            WHERE id = %s
                        """, [
                            resposta_texto, resposta_numerica, resposta_booleana,
                            conformidade, observacao, respostas[item_id]['id']
                        ])
                    else:
                        # Inserir nova resposta
                        cursor.execute("""
                            INSERT INTO checklist_respostas
                            (checklist_id, item_id, resposta_texto, resposta_numerica, 
                            resposta_booleana, conformidade, observacao)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, [
                            checklist_id, item_id, resposta_texto, resposta_numerica,
                            resposta_booleana, conformidade, observacao
                        ])

                # Verificar se é para concluir o checklist
                concluir = request.form.get('concluir') == 'true'
                if concluir:
                    # Verificar se todos os itens obrigatórios foram respondidos
                    cursor.execute("""
                        SELECT COUNT(*) as total_obrigatorios
                        FROM checklist_itens
                        WHERE modelo_id = %s AND obrigatorio = TRUE AND ativo = TRUE
                    """, [checklist['modelo_id']])
                    total_obrigatorios = cursor.fetchone()[
                        'total_obrigatorios']

                    cursor.execute("""
                        SELECT COUNT(*) as total_respondidos
                        FROM checklist_respostas r
                        JOIN checklist_itens i ON r.item_id = i.id
                        WHERE r.checklist_id = %s AND i.obrigatorio = TRUE
                    """, [checklist_id])
                    total_respondidos = cursor.fetchone()['total_respondidos']

                    if total_respondidos < total_obrigatorios:
                        flash(
                            'Responda todos os itens obrigatórios antes de concluir o checklist', 'warning')
                    else:
                        # Atualizar status do checklist
                        cursor.execute("""
                            UPDATE checklist_preenchidos
                            SET status = 'concluido'
                            WHERE id = %s
                        """, [checklist_id])

                        # Registrar no histórico
                        cursor.execute("""
                            INSERT INTO checklist_historico
                            (checklist_id, usuario_id, acao, descricao)
                            VALUES (%s, %s, %s, %s)
                        """, [
                            checklist_id, session['id_usuario'], 'conclusao',
                            'Checklist concluído pelo responsável'
                        ])

                        flash('Checklist concluído com sucesso', 'success')

                        # Redirecionar para visualização
                        connection.commit()
                        return redirect(url_for('checklist.visualizar_checklist', checklist_id=checklist_id))

                # Registrar no histórico que houve atualização
                cursor.execute("""
                    INSERT INTO checklist_historico
                    (checklist_id, usuario_id, acao, descricao)
                    VALUES (%s, %s, %s, %s)
                """, [
                    checklist_id, session['id_usuario'], 'atualizacao',
                    'Checklist atualizado pelo responsável'
                ])

                connection.commit()
                flash('Respostas salvas com sucesso', 'success')

                # Atualizar as respostas
                cursor.execute("""
                    SELECT * FROM checklist_respostas
                    WHERE checklist_id = %s
                """, [checklist_id])
                respostas = {r['item_id']: r for r in cursor.fetchall()}

            cursor.close()
        except Exception as e:
            if 'connection' in locals() and connection.is_connected():
                connection.rollback()
            logger.error(f"Erro ao processar checklist: {e}")
            flash(f"Erro ao processar checklist: {str(e)}", 'danger')
        finally:
            if 'connection' in locals() and connection.is_connected():
                connection.close()

    return render_template('checklist/preencher_checklist.html',
                           checklist=checklist,
                           itens=itens,
                           respostas=respostas)


@mod_checklist.route('/checklists/<int:checklist_id>/visualizar')
def visualizar_checklist(checklist_id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    connection = get_db_connection()
    checklist = None
    itens = []
    respostas = {}
    historico = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar o checklist
            cursor.execute("""
                SELECT c.*, m.nome as modelo_nome, m.tipo_equipamento, m.frequencia,
                u1.nome as responsavel_nome, u2.nome as supervisor_nome
                FROM checklist_preenchidos c
                JOIN checklist_modelos m ON c.modelo_id = m.id
                JOIN usuarios u1 ON c.responsavel_id = u1.id
                LEFT JOIN usuarios u2 ON c.supervisor_id = u2.id
                WHERE c.id = %s
            """, [checklist_id])
            checklist = cursor.fetchone()

            if not checklist:
                flash('Checklist não encontrado', 'warning')
                return redirect(url_for('checklist.listar_checklists'))

            # Buscar itens do modelo
            cursor.execute("""
                SELECT i.* 
                FROM checklist_itens i
                WHERE i.modelo_id = %s AND i.ativo = TRUE
                ORDER BY i.ordem
            """, [checklist['modelo_id']])
            itens = cursor.fetchall()

            # Buscar respostas
            cursor.execute("""
                SELECT * FROM checklist_respostas
                WHERE checklist_id = %s
            """, [checklist_id])
            for resposta in cursor.fetchall():
                respostas[resposta['item_id']] = resposta

            # Buscar histórico
            cursor.execute("""
                SELECT h.*, u.nome as usuario_nome
                FROM checklist_historico h
                JOIN usuarios u ON h.usuario_id = u.id
                WHERE h.checklist_id = %s
                ORDER BY h.data_acao DESC
            """, [checklist_id])
            historico = cursor.fetchall()

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao visualizar checklist: {e}")
            flash(f"Erro ao visualizar checklist: {str(e)}", 'danger')
        finally:
            connection.close()

    return render_template('checklist/visualizar_checklist.html',
                           checklist=checklist,
                           itens=itens,
                           respostas=respostas,
                           historico=historico,
                           pode_aprovar=verificar_permissao('aprovar'))


@mod_checklist.route('/checklists/<int:checklist_id>/aprovar', methods=['POST'])
def aprovar_checklist(checklist_id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('aprovar'):
        flash('Você não tem permissão para aprovar checklists', 'danger')
        return redirect(url_for('checklist.listar_checklists'))

    connection = get_db_connection()

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar o checklist
            cursor.execute(
                "SELECT * FROM checklist_preenchidos WHERE id = %s", [checklist_id])
            checklist = cursor.fetchone()

            if not checklist:
                flash('Checklist não encontrado', 'warning')
                return redirect(url_for('checklist.listar_checklists'))

            # Verificar se o checklist está em status que pode ser aprovado
            if checklist['status'] != 'concluido':
                flash('Este checklist não está disponível para aprovação', 'warning')
                return redirect(url_for('checklist.visualizar_checklist', checklist_id=checklist_id))

            # Aprovar o checklist
            observacoes = request.form.get('observacoes', '')

            cursor.execute("""
                UPDATE checklist_preenchidos
                SET status = 'aprovado', 
                    supervisor_id = %s, 
                    data_aprovacao = NOW(),
                    observacoes = CONCAT(observacoes, '\n\nObservações do supervisor: ', %s)
                WHERE id = %s
            """, [session['id_usuario'], observacoes, checklist_id])

            # Registrar no histórico
            cursor.execute("""
                INSERT INTO checklist_historico
                (checklist_id, usuario_id, acao, descricao)
                VALUES (%s, %s, %s, %s)
            """, [
                checklist_id, session['id_usuario'], 'aprovacao',
                f'Checklist aprovado pelo supervisor: {observacoes}'
            ])

            connection.commit()
            flash('Checklist aprovado com sucesso', 'success')

        except Exception as e:
            connection.rollback()
            logger.error(f"Erro ao aprovar checklist: {e}")
            flash(f"Erro ao aprovar checklist: {str(e)}", 'danger')
        finally:
            cursor.close()
            connection.close()

    return redirect(url_for('checklist.visualizar_checklist', checklist_id=checklist_id))


@mod_checklist.route('/checklists/<int:checklist_id>/rejeitar', methods=['POST'])
def rejeitar_checklist(checklist_id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('aprovar'):
        flash('Você não tem permissão para rejeitar checklists', 'danger')
        return redirect(url_for('checklist.listar_checklists'))

    connection = get_db_connection()

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar o checklist
            cursor.execute(
                "SELECT * FROM checklist_preenchidos WHERE id = %s", [checklist_id])
            checklist = cursor.fetchone()

            if not checklist:
                flash('Checklist não encontrado', 'warning')
                return redirect(url_for('checklist.listar_checklists'))

            # Verificar se o checklist está em status que pode ser rejeitado
            if checklist['status'] != 'concluido':
                flash('Este checklist não está disponível para rejeição', 'warning')
                return redirect(url_for('checklist.visualizar_checklist', checklist_id=checklist_id))

            # Rejeitar o checklist
            motivo = request.form.get('motivo', '')

            if not motivo:
                flash('Informe o motivo da rejeição', 'warning')
                return redirect(url_for('checklist.visualizar_checklist', checklist_id=checklist_id))

            cursor.execute("""
                UPDATE checklist_preenchidos
                SET status = 'rejeitado', 
                    supervisor_id = %s, 
                    data_aprovacao = NOW(),
                    observacoes = CONCAT(observacoes, '\n\nMotivo da rejeição: ', %s)
                WHERE id = %s
            """, [session['id_usuario'], motivo, checklist_id])

            # Registrar no histórico
            cursor.execute("""
                INSERT INTO checklist_historico
                (checklist_id, usuario_id, acao, descricao)
                VALUES (%s, %s, %s, %s)
            """, [
                checklist_id, session['id_usuario'], 'rejeicao',
                f'Checklist rejeitado pelo supervisor. Motivo: {motivo}'
            ])

            connection.commit()
            flash('Checklist rejeitado', 'warning')

        except Exception as e:
            connection.rollback()
            logger.error(f"Erro ao rejeitar checklist: {e}")
            flash(f"Erro ao rejeitar checklist: {str(e)}", 'danger')
        finally:
            cursor.close()
            connection.close()

    return redirect(url_for('checklist.visualizar_checklist', checklist_id=checklist_id))

# Rotas para relatórios


@mod_checklist.route('/relatorios')
def relatorios():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    return render_template('checklist/relatorios.html')


@mod_checklist.route('/api/estatisticas')
def api_estatisticas():
    if 'logado' not in session:
        return jsonify({'success': False, 'message': 'Não autorizado'}), 401

    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'message': 'Erro de conexão com o banco de dados'}), 500

    try:
        cursor = connection.cursor(dictionary=True)

        # Dados de checklists por status
        cursor.execute("""
            SELECT status, COUNT(*) as total
            FROM checklist_preenchidos
            GROUP BY status
        """)
        checklists_por_status = cursor.fetchall()

        # Dados de checklists por tipo de equipamento
        cursor.execute("""
            SELECT m.tipo_equipamento, COUNT(*) as total
            FROM checklist_preenchidos c
            JOIN checklist_modelos m ON c.modelo_id = m.id
            GROUP BY m.tipo_equipamento
            ORDER BY total DESC
            LIMIT 10
        """)
        checklists_por_tipo = cursor.fetchall()

        # Dados de checklists por mês
        cursor.execute("""
            SELECT 
                DATE_FORMAT(data_preenchimento, '%Y-%m') as mes,
                COUNT(*) as total
            FROM checklist_preenchidos
            WHERE data_preenchimento >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY mes
            ORDER BY mes
        """)
        checklists_por_mes = cursor.fetchall()

        cursor.close()
        connection.close()

        return jsonify({
            'success': True,
            'data': {
                'por_status': checklists_por_status,
                'por_tipo': checklists_por_tipo,
                'por_mes': checklists_por_mes
            }
        })

    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        if connection.is_connected():
            cursor.close()
            connection.close()
        return jsonify({'success': False, 'message': str(e)}), 500

# Função para inicializar o módulo


def init_app(app):
    # Importar dependências necessárias
    import mysql.connector
    from mysql.connector import Error
    import json

    # Registrar o blueprint
    app.register_blueprint(mod_checklist, url_prefix='/checklist')

    # Adicionar filtro personalizado para converter JSON para Python
    @app.template_filter('from_json')
    def from_json(value):
        if not value:
            return []
        try:
            return json.loads(value)
        except Exception as e:
            logger.error(f"Erro ao converter JSON: {e}")
            return []

    # Adicionar item ao menu principal
    @app.context_processor
    def inject_menu_data():
        menu_items = []
        if 'logado' in session:
            menu_items = [
                {'name': 'Dashboard', 'url': url_for(
                    'dashboard'), 'icon': 'fas fa-tachometer-alt'},
                {'name': 'Solicitações', 'url': url_for(
                    'dashboard'), 'icon': 'fas fa-clipboard-list'},
                {'name': 'Notas Fiscais', 'url': url_for(
                    'importacao_nf.index'), 'icon': 'fas fa-file-invoice'},
                {'name': 'Checklists', 'url': url_for(
                    'checklist.index'), 'icon': 'fas fa-tasks'},
                {'name': 'Integração ERP', 'url': url_for(
                    'integracao_erp.index'), 'icon': 'fas fa-sync'},
                {'name': 'Relatórios', 'url': url_for(
                    'relatorios'), 'icon': 'fas fa-chart-bar'},
            ]
        return {'menu_items': menu_items}

    return app
