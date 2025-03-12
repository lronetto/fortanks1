# coding: utf-8
import os
import logging
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from werkzeug.utils import secure_filename

from utils.db import get_db_connection
from utils.auth import verificar_permissao

# Configurar logger
logger = logging.getLogger('equipamentos')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.FileHandler('equipamentos.log')
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Criação do blueprint
mod_equipamentos = Blueprint(
    'equipamentos', __name__, url_prefix='/equipamentos')


def init_app(app):
    return app

#
# Rotas para gerenciamento de equipamentos
#


@mod_equipamentos.route('/')
def index():
    """Página inicial do módulo de equipamentos"""
    return redirect(url_for('equipamentos.listar'))


@mod_equipamentos.route('/listar')
def listar():
    """Lista todos os equipamentos cadastrados"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para acessar esta página', 'danger')
        return redirect(url_for('dashboard'))

    filtro_tipo = request.args.get('tipo', '')
    filtro_status = request.args.get('status', '')
    filtro_nome = request.args.get('nome', '')
    filtro_local = request.args.get('local', '')

    connection = get_db_connection()
    equipamentos = []
    tipos_equipamento = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Construir query com filtros
            query = """
                SELECT e.*, u.nome as responsavel_nome,
                (SELECT COUNT(*) FROM checklist_preenchidos WHERE equipamento_cadastrado_id = e.id) as total_checklists
                FROM checklist_equipamentos e
                JOIN usuarios u ON e.criado_por = u.id
                WHERE 1=1
            """
            params = []

            if filtro_tipo:
                query += " AND e.tipo = %s"
                params.append(filtro_tipo)

            if filtro_status:
                query += " AND e.status = %s"
                params.append(filtro_status)

            if filtro_nome:
                query += " AND (e.nome LIKE %s OR e.codigo LIKE %s)"
                params.extend([f"%{filtro_nome}%", f"%{filtro_nome}%"])

            if filtro_local:
                query += " AND e.local LIKE %s"
                params.append(f"%{filtro_local}%")

            query += " ORDER BY e.nome"

            cursor.execute(query, params)
            equipamentos = cursor.fetchall()

            # Obter lista de tipos de equipamento para o filtro
            cursor.execute(
                "SELECT DISTINCT tipo FROM checklist_equipamentos ORDER BY tipo")
            tipos_equipamento = [row['tipo'] for row in cursor.fetchall()]

            # Obter lista de locais para o filtro
            cursor.execute(
                "SELECT DISTINCT local FROM checklist_equipamentos WHERE local IS NOT NULL AND local != '' ORDER BY local")
            locais = [row['local'] for row in cursor.fetchall()]

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao listar equipamentos: {e}")
            flash(f"Erro ao listar equipamentos: {str(e)}", 'danger')
        finally:
            connection.close()

    return render_template('equipamentos/listar.html',
                           equipamentos=equipamentos,
                           filtros={
                               'tipo': filtro_tipo,
                               'status': filtro_status,
                               'nome': filtro_nome,
                               'local': filtro_local
                           },
                           tipos_equipamento=tipos_equipamento,
                           locais=locais if 'locais' in locals() else [],
                           pode_editar=verificar_permissao('editar'),
                           pode_admin=verificar_permissao('admin'))


@mod_equipamentos.route('/novo', methods=['GET', 'POST'])
def novo():
    """Cadastra um novo equipamento"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para cadastrar equipamentos', 'danger')
        return redirect(url_for('equipamentos.listar'))

    if request.method == 'POST':
        # Obter dados do formulário
        codigo = request.form.get('codigo', '')
        nome = request.form.get('nome', '')
        descricao = request.form.get('descricao', '')
        tipo = request.form.get('tipo', '')
        modelo = request.form.get('modelo', '')
        fabricante = request.form.get('fabricante', '')
        data_aquisicao = request.form.get('data_aquisicao', '')
        valor_aquisicao = request.form.get('valor_aquisicao', '')
        local = request.form.get('local', '')
        status = request.form.get('status', '')
        observacoes = request.form.get('observacoes', '')

        # Processar arquivo de foto, se existir
        foto = ''
        if 'foto' in request.files and request.files['foto'].filename:
            arquivo = request.files['foto']
            extensao = os.path.splitext(arquivo.filename)[1].lower()

            if extensao in ['.jpg', '.jpeg', '.png', '.gif']:
                # Gerar nome único para o arquivo
                nome_arquivo = f"{uuid.uuid4()}{extensao}"
                diretorio_upload = os.path.join(
                    current_app.root_path, 'static', 'uploads', 'equipamentos')

                # Criar diretório se não existir
                os.makedirs(diretorio_upload, exist_ok=True)

                # Salvar arquivo
                caminho_arquivo = os.path.join(diretorio_upload, nome_arquivo)
                arquivo.save(caminho_arquivo)

                # Caminho relativo para salvar no banco
                foto = f"uploads/equipamentos/{nome_arquivo}"
            else:
                flash(
                    'Formato de arquivo não suportado. Use JPG, PNG ou GIF.', 'warning')

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()

                cursor.execute("""
                INSERT INTO checklist_equipamentos
                (codigo, nome, descricao, tipo, modelo, fabricante, data_aquisicao, 
                valor_aquisicao, local, status, observacoes, foto, criado_por, data_criacao)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, [
                    codigo, nome, descricao, tipo, modelo, fabricante,
                    data_aquisicao or None, valor_aquisicao or None,
                    local, status, observacoes, foto, session['usuario_id']
                ])

                connection.commit()
                flash('Equipamento cadastrado com sucesso!', 'success')
                return redirect(url_for('equipamentos.listar'))
            except Exception as e:
                connection.rollback()
                logger.error(f"Erro ao cadastrar equipamento: {e}")
                flash(f"Erro ao cadastrar equipamento: {str(e)}", 'danger')
            finally:
                connection.close()

    return render_template('equipamentos/novo.html')


@mod_equipamentos.route('/<int:equipamento_id>/editar', methods=['GET', 'POST'])
def editar(equipamento_id):
    """Edita um equipamento existente"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para editar equipamentos', 'danger')
        return redirect(url_for('equipamentos.listar'))

    connection = get_db_connection()
    if not connection:
        flash('Erro ao conectar ao banco de dados', 'danger')
        return redirect(url_for('equipamentos.listar'))

    try:
        cursor = connection.cursor(dictionary=True)

        # Obter dados do equipamento
        cursor.execute(
            "SELECT * FROM checklist_equipamentos WHERE id = %s", [equipamento_id])
        equipamento = cursor.fetchone()

        if not equipamento:
            flash('Equipamento não encontrado', 'warning')
            return redirect(url_for('equipamentos.listar'))

        if request.method == 'POST':
            # Obter dados do formulário
            codigo = request.form.get('codigo', '')
            nome = request.form.get('nome', '')
            descricao = request.form.get('descricao', '')
            tipo = request.form.get('tipo', '')
            modelo = request.form.get('modelo', '')
            fabricante = request.form.get('fabricante', '')
            data_aquisicao = request.form.get('data_aquisicao', '')
            valor_aquisicao = request.form.get('valor_aquisicao', '')
            local = request.form.get('local', '')
            status = request.form.get('status', '')
            observacoes = request.form.get('observacoes', '')

            # Processar arquivo de foto, se existir
            foto = equipamento['foto']  # Manter a foto existente por padrão
            if 'foto' in request.files and request.files['foto'].filename:
                arquivo = request.files['foto']
                extensao = os.path.splitext(arquivo.filename)[1].lower()

                if extensao in ['.jpg', '.jpeg', '.png', '.gif']:
                    # Gerar nome único para o arquivo
                    nome_arquivo = f"{uuid.uuid4()}{extensao}"
                    diretorio_upload = os.path.join(
                        current_app.root_path, 'static', 'uploads', 'equipamentos')

                    # Criar diretório se não existir
                    os.makedirs(diretorio_upload, exist_ok=True)

                    # Salvar arquivo
                    caminho_arquivo = os.path.join(
                        diretorio_upload, nome_arquivo)
                    arquivo.save(caminho_arquivo)

                    # Caminho relativo para salvar no banco
                    foto = f"uploads/equipamentos/{nome_arquivo}"
                else:
                    flash(
                        'Formato de arquivo não suportado. Use JPG, PNG ou GIF.', 'warning')

            # Atualizar no banco
            cursor.execute("""
            UPDATE checklist_equipamentos
            SET codigo=%s, nome=%s, descricao=%s, tipo=%s, modelo=%s, 
                fabricante=%s, data_aquisicao=%s, valor_aquisicao=%s, 
                local=%s, status=%s, observacoes=%s, foto=%s,
                atualizado_por=%s, data_atualizacao=NOW()
            WHERE id=%s
            """, [
                codigo, nome, descricao, tipo, modelo, fabricante,
                data_aquisicao or None, valor_aquisicao or None,
                local, status, observacoes, foto,
                session['usuario_id'], equipamento_id
            ])

            connection.commit()
            flash('Equipamento atualizado com sucesso!', 'success')
            return redirect(url_for('equipamentos.listar'))

        return render_template('equipamentos/editar.html', equipamento=equipamento)
    except Exception as e:
        connection.rollback()
        logger.error(f"Erro ao processar equipamento: {e}")
        flash(f"Erro ao processar equipamento: {str(e)}", 'danger')
        return redirect(url_for('equipamentos.listar'))
    finally:
        connection.close()


@mod_equipamentos.route('/<int:equipamento_id>/visualizar')
def visualizar(equipamento_id):
    """Visualiza detalhes de um equipamento"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    connection = get_db_connection()
    if not connection:
        flash('Erro ao conectar ao banco de dados', 'danger')
        return redirect(url_for('equipamentos.listar'))

    try:
        cursor = connection.cursor(dictionary=True)

        # Obter dados do equipamento com nome do responsável
        cursor.execute("""
        SELECT e.*, u.nome as criado_por_nome, u2.nome as atualizado_por_nome
        FROM checklist_equipamentos e
        LEFT JOIN usuarios u ON e.criado_por = u.id
        LEFT JOIN usuarios u2 ON e.atualizado_por = u2.id
        WHERE e.id = %s
        """, [equipamento_id])

        equipamento = cursor.fetchone()

        if not equipamento:
            flash('Equipamento não encontrado', 'warning')
            return redirect(url_for('equipamentos.listar'))

        # Obter histórico de manutenções
        cursor.execute("""
        SELECT m.*, u.nome as responsavel_nome
        FROM checklist_manutencoes m
        LEFT JOIN usuarios u ON m.responsavel_id = u.id
        WHERE m.equipamento_id = %s
        ORDER BY m.data_manutencao DESC
        """, [equipamento_id])

        manutencoes = cursor.fetchall()

        # Obter histórico de checklists
        cursor.execute("""
        SELECT c.*, cp.data_preenchimento, u.nome as preenchido_por_nome, 
               m.nome as modelo_nome
        FROM checklist_preenchidos cp
        JOIN checklist c ON cp.checklist_id = c.id
        JOIN checklist_modelos m ON c.modelo_id = m.id
        JOIN usuarios u ON cp.preenchido_por = u.id
        WHERE cp.equipamento_cadastrado_id = %s
        ORDER BY cp.data_preenchimento DESC
        LIMIT 10
        """, [equipamento_id])

        checklists = cursor.fetchall()

        return render_template('equipamentos/visualizar.html',
                               equipamento=equipamento,
                               manutencoes=manutencoes,
                               checklists=checklists,
                               pode_editar=verificar_permissao('editar'))
    except Exception as e:
        logger.error(f"Erro ao visualizar equipamento: {e}")
        flash(f"Erro ao visualizar equipamento: {str(e)}", 'danger')
        return redirect(url_for('equipamentos.listar'))
    finally:
        connection.close()


@mod_equipamentos.route('/manutencao')
def manutencao():
    """Lista todas as manutenções cadastradas"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para acessar esta página', 'danger')
        return redirect(url_for('dashboard'))

    connection = get_db_connection()
    manutencoes = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
            SELECT m.*, e.nome as equipamento_nome, e.codigo as equipamento_codigo,
                  u.nome as responsavel_nome
            FROM checklist_manutencoes m
            JOIN checklist_equipamentos e ON m.equipamento_id = e.id
            LEFT JOIN usuarios u ON m.responsavel_id = u.id
            ORDER BY m.data_manutencao DESC
            """)

            manutencoes = cursor.fetchall()
            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao listar manutenções: {e}")
            flash(f"Erro ao listar manutenções: {str(e)}", 'danger')
        finally:
            connection.close()

    return render_template('equipamentos/manutencoes.html',
                           manutencoes=manutencoes,
                           pode_editar=verificar_permissao('editar'))


@mod_equipamentos.route('/<int:equipamento_id>/registrar-manutencao', methods=['GET', 'POST'])
def registrar_manutencao(equipamento_id):
    """Registra uma nova manutenção para um equipamento"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para registrar manutenções', 'danger')
        return redirect(url_for('equipamentos.listar'))

    connection = get_db_connection()
    if not connection:
        flash('Erro ao conectar ao banco de dados', 'danger')
        return redirect(url_for('equipamentos.listar'))

    try:
        cursor = connection.cursor(dictionary=True)

        # Obter dados do equipamento
        cursor.execute(
            "SELECT * FROM checklist_equipamentos WHERE id = %s", [equipamento_id])
        equipamento = cursor.fetchone()

        if not equipamento:
            flash('Equipamento não encontrado', 'warning')
            return redirect(url_for('equipamentos.listar'))

        if request.method == 'POST':
            # Obter dados do formulário
            tipo = request.form.get('tipo', '')
            data_manutencao = request.form.get('data_manutencao', '')
            descricao = request.form.get('descricao', '')
            responsavel_externo = request.form.get('responsavel_externo', '')
            custo = request.form.get('custo', '')
            resultado = request.form.get('resultado', '')
            observacoes = request.form.get('observacoes', '')

            # Inserir no banco
            cursor.execute("""
            INSERT INTO checklist_manutencoes 
            (equipamento_id, tipo, data_manutencao, descricao, responsavel_id, 
            responsavel_externo, custo, resultado, observacoes, criado_em)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, [
                equipamento_id, tipo, data_manutencao, descricao,
                session['usuario_id'], responsavel_externo,
                custo or 0, resultado, observacoes
            ])

            # Atualizar status do equipamento se for preventiva
            if tipo == 'Preventiva' or tipo == 'Corretiva':
                cursor.execute("""
                UPDATE checklist_equipamentos
                SET status = 'Operacional', data_ultima_manutencao = %s,
                    atualizado_por = %s, data_atualizacao = NOW()
                WHERE id = %s
                """, [data_manutencao, session['usuario_id'], equipamento_id])

            connection.commit()
            flash('Manutenção registrada com sucesso!', 'success')
            return redirect(url_for('equipamentos.visualizar', equipamento_id=equipamento_id))

        return render_template('equipamentos/registrar_manutencao.html',
                               equipamento=equipamento)
    except Exception as e:
        connection.rollback()
        logger.error(f"Erro ao registrar manutenção: {e}")
        flash(f"Erro ao registrar manutenção: {str(e)}", 'danger')
        return redirect(url_for('equipamentos.visualizar', equipamento_id=equipamento_id))
    finally:
        connection.close()
