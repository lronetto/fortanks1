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

# Criação do blueprint como submódulo
mod_equipamentos = Blueprint(
    'equipamentos', __name__, template_folder='templates')


def init_app(parent_blueprint):
    """Inicializa o módulo de equipamentos como submódulo de cadastros"""
    logger.info("Inicializando submódulo de equipamentos")
    return parent_blueprint

#
# Rotas para gerenciamento de equipamentos
#


@mod_equipamentos.route('/')
def index():
    """Página inicial do módulo de equipamentos"""
    return redirect(url_for('cadastros.equipamentos.listar'))


@mod_equipamentos.route('/listar')
def listar():
    """Lista todos os equipamentos cadastrados"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para acessar esta página', 'danger')
        return redirect(url_for('dashboard'))

    # Obter parâmetros de filtro
    tipo = request.args.get('tipo', '')
    status = request.args.get('status', '')
    nome = request.args.get('nome', '')
    local = request.args.get('local', '')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Construir a consulta SQL com filtros
        query = """
            SELECT id, codigo, nome, tipo, modelo, fabricante, status, local, 
                   data_aquisicao, valor_aquisicao, data_cadastro, foto_url
            FROM equipamentos
            WHERE 1=1
        """
        params = []

        if tipo:
            query += " AND tipo LIKE %s"
            params.append(f"%{tipo}%")

        if status:
            query += " AND status = %s"
            params.append(status)

        if nome:
            query += " AND nome LIKE %s"
            params.append(f"%{nome}%")

        if local:
            query += " AND local LIKE %s"
            params.append(f"%{local}%")

        query += " ORDER BY nome ASC"

        cursor.execute(query, params)
        equipamentos = cursor.fetchall()

        # Obter lista de tipos distintos para o filtro
        cursor.execute("SELECT DISTINCT tipo FROM equipamentos ORDER BY tipo")
        tipos = [row['tipo'] for row in cursor.fetchall()]

        # Obter lista de status distintos para o filtro
        cursor.execute(
            "SELECT DISTINCT status FROM equipamentos ORDER BY status")
        status_list = [row['status'] for row in cursor.fetchall()]

        # Obter lista de locais distintos para o filtro
        cursor.execute(
            "SELECT DISTINCT local FROM equipamentos WHERE local IS NOT NULL ORDER BY local")
        locais = [row['local'] for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        # Verificar permissão para edição
        pode_editar = verificar_permissao('editar')

        return render_template('cadastros/equipamentos/listar.html',
                               equipamentos=equipamentos,
                               tipos=tipos,
                               status_list=status_list,
                               locais=locais,
                               filtros={
                                   'tipo': tipo,
                                   'status': status,
                                   'nome': nome,
                                   'local': local
                               },
                               pode_editar=pode_editar)

    except Exception as e:
        logger.error(f"Erro ao listar equipamentos: {str(e)}")
        flash(f"Erro ao listar equipamentos: {str(e)}", "danger")
        return redirect(url_for('dashboard'))


@mod_equipamentos.route('/novo', methods=['GET', 'POST'])
def novo():
    """Cadastra um novo equipamento"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para cadastrar equipamentos', 'danger')
        return redirect(url_for('cadastros.equipamentos.listar'))

    if request.method == 'POST':
        try:
            # Obter dados do formulário
            codigo = request.form.get('codigo')
            nome = request.form.get('nome')
            descricao = request.form.get('descricao')
            tipo = request.form.get('tipo')
            modelo = request.form.get('modelo')
            fabricante = request.form.get('fabricante')
            data_aquisicao = request.form.get('data_aquisicao')
            valor_aquisicao = request.form.get('valor_aquisicao')
            local = request.form.get('local')
            status = request.form.get('status')
            observacoes = request.form.get('observacoes')

            # Validar campos obrigatórios
            if not codigo or not nome or not tipo or not status:
                flash('Preencha todos os campos obrigatórios', 'warning')
                return render_template('cadastros/equipamentos/novo.html')

            # Processar upload de foto, se houver
            foto_url = None
            if 'foto' in request.files and request.files['foto'].filename:
                foto = request.files['foto']
                if foto.filename:
                    # Gerar nome único para o arquivo
                    filename = secure_filename(foto.filename)
                    ext = os.path.splitext(filename)[1]
                    new_filename = f"{uuid.uuid4().hex}{ext}"

                    # Criar diretório de uploads se não existir
                    upload_folder = os.path.join(
                        current_app.static_folder, 'uploads', 'equipamentos')
                    os.makedirs(upload_folder, exist_ok=True)

                    # Salvar arquivo
                    filepath = os.path.join(upload_folder, new_filename)
                    foto.save(filepath)

                    # URL relativa para o arquivo
                    foto_url = f"/static/uploads/equipamentos/{new_filename}"

            # Inserir no banco de dados
            conn = get_db_connection()
            cursor = conn.cursor()

            query = """
                INSERT INTO equipamentos (
                    codigo, nome, descricao, tipo, modelo, fabricante, 
                    data_aquisicao, valor_aquisicao, local, status, 
                    observacoes, foto_url, data_cadastro, usuario_cadastro
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            cursor.execute(query, (
                codigo, nome, descricao, tipo, modelo, fabricante,
                data_aquisicao if data_aquisicao else None,
                valor_aquisicao if valor_aquisicao else None,
                local, status, observacoes, foto_url,
                datetime.now(), session.get('usuario_id')
            ))

            conn.commit()
            cursor.close()
            conn.close()

            flash('Equipamento cadastrado com sucesso!', 'success')
            return redirect(url_for('cadastros.equipamentos.listar'))

        except Exception as e:
            logger.error(f"Erro ao cadastrar equipamento: {str(e)}")
            flash(f"Erro ao cadastrar equipamento: {str(e)}", "danger")
            return render_template('cadastros/equipamentos/novo.html')

    # Método GET - exibir formulário
    return render_template('cadastros/equipamentos/novo.html')


@mod_equipamentos.route('/visualizar/<int:id>')
def visualizar(id):
    """Visualiza os detalhes de um equipamento"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para visualizar equipamentos', 'danger')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT id, codigo, nome, descricao, tipo, modelo, fabricante, 
                   data_aquisicao, valor_aquisicao, local, status, 
                   observacoes, foto_url, data_cadastro, usuario_cadastro
            FROM equipamentos
            WHERE id = %s
        """

        cursor.execute(query, (id,))
        equipamento = cursor.fetchone()

        cursor.close()
        conn.close()

        if not equipamento:
            flash('Equipamento não encontrado', 'warning')
            return redirect(url_for('cadastros.equipamentos.listar'))

        # Verificar permissão para edição
        pode_editar = verificar_permissao('editar')

        return render_template('cadastros/equipamentos/visualizar.html',
                               equipamento=equipamento,
                               pode_editar=pode_editar)

    except Exception as e:
        logger.error(f"Erro ao visualizar equipamento: {str(e)}")
        flash(f"Erro ao visualizar equipamento: {str(e)}", "danger")
        return redirect(url_for('cadastros.equipamentos.listar'))


@mod_equipamentos.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """Edita um equipamento existente"""
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if not verificar_permissao('editar'):
        flash('Você não tem permissão para editar equipamentos', 'danger')
        return redirect(url_for('cadastros.equipamentos.listar'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if request.method == 'POST':
            # Obter dados do formulário
            codigo = request.form.get('codigo')
            nome = request.form.get('nome')
            descricao = request.form.get('descricao')
            tipo = request.form.get('tipo')
            modelo = request.form.get('modelo')
            fabricante = request.form.get('fabricante')
            data_aquisicao = request.form.get('data_aquisicao')
            valor_aquisicao = request.form.get('valor_aquisicao')
            local = request.form.get('local')
            status = request.form.get('status')
            observacoes = request.form.get('observacoes')
            manter_foto = 'manter_foto' in request.form

            # Validar campos obrigatórios
            if not codigo or not nome or not tipo or not status:
                flash('Preencha todos os campos obrigatórios', 'warning')
                cursor.execute(
                    "SELECT * FROM equipamentos WHERE id = %s", (id,))
                equipamento = cursor.fetchone()
                return render_template('cadastros/equipamentos/editar.html', equipamento=equipamento)

            # Obter informações atuais do equipamento para a foto
            cursor.execute(
                "SELECT foto_url FROM equipamentos WHERE id = %s", (id,))
            equip_atual = cursor.fetchone()
            foto_url = equip_atual['foto_url'] if equip_atual and manter_foto else None

            # Processar upload de nova foto, se houver
            if 'foto' in request.files and request.files['foto'].filename:
                foto = request.files['foto']
                if foto.filename:
                    # Gerar nome único para o arquivo
                    filename = secure_filename(foto.filename)
                    ext = os.path.splitext(filename)[1]
                    new_filename = f"{uuid.uuid4().hex}{ext}"

                    # Criar diretório de uploads se não existir
                    upload_folder = os.path.join(
                        current_app.static_folder, 'uploads', 'equipamentos')
                    os.makedirs(upload_folder, exist_ok=True)

                    # Salvar arquivo
                    filepath = os.path.join(upload_folder, new_filename)
                    foto.save(filepath)

                    # URL relativa para o arquivo
                    foto_url = f"/static/uploads/equipamentos/{new_filename}"

                    # Remover foto antiga se existir e não for a mesma
                    if equip_atual and equip_atual['foto_url'] and not manter_foto:
                        try:
                            old_path = os.path.join(
                                current_app.static_folder,
                                equip_atual['foto_url'].replace('/static/', '')
                            )
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        except Exception as e:
                            logger.warning(
                                f"Erro ao remover foto antiga: {str(e)}")

            # Atualizar no banco de dados
            query = """
                UPDATE equipamentos SET
                    codigo = %s, nome = %s, descricao = %s, tipo = %s, 
                    modelo = %s, fabricante = %s, data_aquisicao = %s, 
                    valor_aquisicao = %s, local = %s, status = %s, 
                    observacoes = %s, foto_url = %s, data_atualizacao = %s
                WHERE id = %s
            """

            cursor.execute(query, (
                codigo, nome, descricao, tipo, modelo, fabricante,
                data_aquisicao if data_aquisicao else None,
                valor_aquisicao if valor_aquisicao else None,
                local, status, observacoes, foto_url,
                datetime.now(), id
            ))

            conn.commit()
            flash('Equipamento atualizado com sucesso!', 'success')
            return redirect(url_for('cadastros.equipamentos.visualizar', id=id))

        else:
            # Método GET - exibir formulário com dados atuais
            cursor.execute("""
                SELECT id, codigo, nome, descricao, tipo, modelo, fabricante, 
                       data_aquisicao, valor_aquisicao, local, status, 
                       observacoes, foto_url, data_cadastro
                FROM equipamentos
                WHERE id = %s
            """, (id,))

            equipamento = cursor.fetchone()

            if not equipamento:
                flash('Equipamento não encontrado', 'warning')
                return redirect(url_for('cadastros.equipamentos.listar'))

            return render_template('cadastros/equipamentos/editar.html', equipamento=equipamento)

    except Exception as e:
        logger.error(f"Erro ao editar equipamento: {str(e)}")
        flash(f"Erro ao editar equipamento: {str(e)}", "danger")
        return redirect(url_for('cadastros.equipamentos.listar'))

    finally:
        cursor.close()
        conn.close()
