# coding: utf-8
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import os
import logging
from datetime import datetime
import re
import pandas as pd

# Importações das funções centralizadas
from utils.db import get_db_connection, execute_query, get_single_result, insert_data, update_data
from utils.auth import login_obrigatorio, admin_obrigatorio, verificar_permissao
from utils.file_handlers import save_uploaded_file

# Configuração de logging
log_dir = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'materiais.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuração para upload de arquivos
UPLOAD_FOLDER = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# Criar diretório de uploads se não existir
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Verificar extensão de arquivo permitida


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Criar o Blueprint
mod_materiais = Blueprint('materiais', __name__, url_prefix='/materiais')

# Rota para redirecionar para a lista


@mod_materiais.route('/')
@login_obrigatorio
def index():
    return redirect(url_for('materiais.listar'))

# Rota para listar materiais


@mod_materiais.route('/listar')
@login_obrigatorio
def listar():
    # Verificar se o usuário tem permissão de visualização
    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para visualizar materiais.', 'warning')
        return redirect(url_for('dashboard'))

    # Obter materiais ativos e inativos
    try:
        # Obter materiais ativos
        query_ativos = """
            SELECT m.*, c.nome as centro_custo_nome
            FROM materiais m
            LEFT JOIN centros_custo c ON m.centro_custo_id = c.id
            WHERE m.ativo = 1
            ORDER BY m.descricao
        """
        materiais_ativos = execute_query(query_ativos)

        # Obter materiais inativos
        query_inativos = """
            SELECT m.*, c.nome as centro_custo_nome
            FROM materiais m
            LEFT JOIN centros_custo c ON m.centro_custo_id = c.id
            WHERE m.ativo = 0
            ORDER BY m.descricao
        """
        materiais_inativos = execute_query(query_inativos)

    except Exception as e:
        logger.error(f"Erro ao listar materiais: {str(e)}")
        flash('Ocorreu um erro ao carregar os materiais. Por favor, tente novamente.', 'danger')
        materiais_ativos = []
        materiais_inativos = []

    return render_template('cadastros/materiais/listar.html',
                           materiais_ativos=materiais_ativos or [],
                           materiais_inativos=materiais_inativos or [])

# Rota para visualizar material


@mod_materiais.route('/visualizar/<int:id>')
@login_obrigatorio
def visualizar(id):
    # Verificar se o usuário tem permissão de visualização
    if not verificar_permissao('visualizar'):
        flash('Você não tem permissão para visualizar materiais.', 'warning')
        return redirect(url_for('dashboard'))

    # Buscar material por ID
    try:
        query = """
            SELECT m.*, 
                   c.nome as centro_custo_nome,
                   u_criado.nome as criado_por_nome,
                   u_alterado.nome as alterado_por_nome
            FROM materiais m
            LEFT JOIN centros_custo c ON m.centro_custo_id = c.id
            LEFT JOIN usuarios u_criado ON m.criado_por = u_criado.id
            LEFT JOIN usuarios u_alterado ON m.alterado_por = u_alterado.id
            WHERE m.id = %s
        """
        material = get_single_result(query, [id])

        if not material:
            flash('Material não encontrado.', 'warning')
            return redirect(url_for('materiais.listar'))
    except Exception as e:
        logger.error(f"Erro ao buscar material {id}: {str(e)}")
        flash('Ocorreu um erro ao buscar o material. Por favor, tente novamente.', 'danger')
        return redirect(url_for('materiais.listar'))

    return render_template('cadastros/materiais/visualizar.html', material=material)

# Rota para cadastrar novo material


@mod_materiais.route('/novo', methods=['GET', 'POST'])
@login_obrigatorio
def novo():
    # Verificar se o usuário tem permissão de edição
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para cadastrar materiais.', 'warning')
        return redirect(url_for('materiais.listar'))

    # Obter lista de centros de custo para o formulário
    try:
        centros_custo = execute_query(
            "SELECT id, nome, codigo FROM centros_custo WHERE ativo = 1 ORDER BY nome"
        )
    except Exception as e:
        logger.error(f"Erro ao buscar centros de custo: {str(e)}")
        flash('Ocorreu um erro ao carregar os centros de custo. Por favor, tente novamente.', 'danger')
        centros_custo = []

    if request.method == 'POST':
        # Obter dados do formulário
        codigo = request.form.get('codigo', '').strip()
        descricao = request.form.get('descricao', '').strip()
        unidade = request.form.get('unidade', '').strip()
        centro_custo_id = request.form.get('centro_custo_id', '').strip()
        pc = request.form.get('pc', '').strip()
        codigo_erp = request.form.get('codigo_erp', '').strip()

        # Validar formulário
        erro = False
        if not codigo:
            flash('O código do material é obrigatório.', 'danger')
            erro = True
        if not descricao:
            flash('A descrição do material é obrigatória.', 'danger')
            erro = True
        if not unidade:
            flash('A unidade de medida é obrigatória.', 'danger')
            erro = True
        if not centro_custo_id:
            flash('O centro de custo é obrigatório.', 'danger')
            erro = True
        else:
            try:
                centro_custo_id = int(centro_custo_id)
            except ValueError:
                flash('Centro de custo inválido.', 'danger')
                erro = True

        # Verificar se código já existe
        if not erro:
            codigo_existe = get_single_result(
                "SELECT id FROM materiais WHERE codigo = %s",
                [codigo]
            )
            if codigo_existe:
                flash(f'O código {codigo} já está em uso.', 'danger')
                erro = True

        # Se não houver erros, salvar no banco
        if not erro:
            try:
                # Preparar dados para inserção
                now = datetime.now()
                data = {
                    'codigo': codigo,
                    'descricao': descricao,
                    'unidade': unidade,
                    'centro_custo_id': centro_custo_id,
                    'pc': pc,
                    'codigo_erp': codigo_erp,
                    'ativo': 1,
                    'criado_por': session['usuario_id'],
                    'criado_em': now,
                    'alterado_em': now
                }

                material_id = insert_data('materiais', data)

                logger.info(
                    f"Material {descricao} ({codigo}) cadastrado por {session['usuario_id']}")
                flash(
                    f'Material {descricao} cadastrado com sucesso!', 'success')
                return redirect(url_for('materiais.visualizar', id=material_id))
            except Exception as e:
                logger.error(f"Erro ao cadastrar material: {str(e)}")
                flash(
                    'Ocorreu um erro ao cadastrar o material. Por favor, tente novamente.', 'danger')

    return render_template('cadastros/materiais/form.html',
                           material=None,
                           centros_custo=centros_custo or [])

# Rota para editar material


@mod_materiais.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_obrigatorio
def editar(id):
    # Verificar se o usuário tem permissão de edição
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para editar materiais.', 'warning')
        return redirect(url_for('materiais.listar'))

    # Buscar material por ID
    try:
        material = get_single_result(
            "SELECT * FROM materiais WHERE id = %s", [id])

        if not material:
            flash('Material não encontrado.', 'warning')
            return redirect(url_for('materiais.listar'))
    except Exception as e:
        logger.error(f"Erro ao buscar material {id}: {str(e)}")
        flash('Ocorreu um erro ao buscar o material. Por favor, tente novamente.', 'danger')
        return redirect(url_for('materiais.listar'))

    # Obter lista de centros de custo para o formulário
    try:
        centros_custo = execute_query(
            "SELECT id, nome, codigo FROM centros_custo WHERE ativo = 1 ORDER BY nome"
        )
    except Exception as e:
        logger.error(f"Erro ao buscar centros de custo: {str(e)}")
        flash('Ocorreu um erro ao carregar os centros de custo. Por favor, tente novamente.', 'danger')
        centros_custo = []

    if request.method == 'POST':
        # Obter dados do formulário
        codigo = request.form.get('codigo', '').strip()
        descricao = request.form.get('descricao', '').strip()
        unidade = request.form.get('unidade', '').strip()
        centro_custo_id = request.form.get('centro_custo_id', '').strip()
        pc = request.form.get('pc', '').strip()
        codigo_erp = request.form.get('codigo_erp', '').strip()

        # Validar formulário
        erro = False
        if not codigo:
            flash('O código do material é obrigatório.', 'danger')
            erro = True
        if not descricao:
            flash('A descrição do material é obrigatória.', 'danger')
            erro = True
        if not unidade:
            flash('A unidade de medida é obrigatória.', 'danger')
            erro = True
        if not centro_custo_id:
            flash('O centro de custo é obrigatório.', 'danger')
            erro = True
        else:
            try:
                centro_custo_id = int(centro_custo_id)
            except ValueError:
                flash('Centro de custo inválido.', 'danger')
                erro = True

        # Verificar se código já existe (se foi alterado)
        if not erro and codigo != material['codigo']:
            codigo_existe = get_single_result(
                "SELECT id FROM materiais WHERE codigo = %s AND id != %s",
                [codigo, id]
            )
            if codigo_existe:
                flash(f'O código {codigo} já está em uso.', 'danger')
                erro = True

        # Se não houver erros, atualizar no banco
        if not erro:
            try:
                # Preparar dados para atualização
                data = {
                    'codigo': codigo,
                    'descricao': descricao,
                    'unidade': unidade,
                    'centro_custo_id': centro_custo_id,
                    'pc': pc,
                    'codigo_erp': codigo_erp,
                    'alterado_por': session['usuario_id'],
                    'alterado_em': datetime.now()
                }

                update_data('materiais', data, 'id', id)

                logger.info(
                    f"Material {id} ({descricao}) alterado por {session['usuario_id']}")
                flash(
                    f'Material {descricao} atualizado com sucesso!', 'success')
                return redirect(url_for('materiais.visualizar', id=id))
            except Exception as e:
                logger.error(f"Erro ao atualizar material {id}: {str(e)}")
                flash(
                    'Ocorreu um erro ao atualizar o material. Por favor, tente novamente.', 'danger')

    return render_template('cadastros/materiais/form.html',
                           material=material,
                           centros_custo=centros_custo or [])

# Rota para alternar status (ativar/desativar)


@mod_materiais.route('/alternar_status/<int:id>', methods=['POST'])
@login_obrigatorio
def alternar_status(id):
    # Verificar se o usuário tem permissão de edição
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para alterar o status de materiais.', 'warning')
        return redirect(url_for('materiais.listar'))

    try:
        # Buscar material atual
        material = get_single_result(
            "SELECT descricao, ativo FROM materiais WHERE id = %s", [id])

        if not material:
            flash('Material não encontrado.', 'warning')
            return redirect(url_for('materiais.listar'))

        # Alternar o status
        novo_status = 0 if material['ativo'] == 1 else 1
        status_texto = "ativado" if novo_status == 1 else "desativado"

        # Atualizar status no banco
        data = {
            'ativo': novo_status,
            'alterado_por': session['usuario_id'],
            'alterado_em': datetime.now()
        }

        update_data('materiais', data, 'id', id)

        logger.info(
            f"Material {id} ({material['descricao']}) {status_texto} por {session['usuario_id']}")
        flash(
            f"Material {material['descricao']} {status_texto} com sucesso!", 'success')
    except Exception as e:
        logger.error(f"Erro ao alternar status do material {id}: {str(e)}")
        flash('Ocorreu um erro ao alterar o status do material. Por favor, tente novamente.', 'danger')

    return redirect(url_for('materiais.listar'))

# Rota para a página de importação de material


@mod_materiais.route('/importar', methods=['GET', 'POST'])
@login_obrigatorio
def importar():
    # Verificar se o usuário tem permissão de edição
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para importar materiais.', 'warning')
        return redirect(url_for('materiais.listar'))

    if request.method == 'POST':
        # Verificar se um arquivo foi enviado
        if 'arquivo' not in request.files:
            flash('Nenhum arquivo selecionado.', 'warning')
            return redirect(request.url)

        arquivo = request.files['arquivo']

        # Se o usuário não selecionou um arquivo
        if arquivo.filename == '':
            flash('Nenhum arquivo selecionado.', 'warning')
            return redirect(request.url)

        # Verificar se o arquivo é Excel
        if not arquivo.filename.endswith(('.xlsx', '.xls')):
            flash('O arquivo deve ser um arquivo Excel (.xlsx ou .xls).', 'warning')
            return redirect(request.url)

        try:
            # Salvar o arquivo
            caminho_arquivo = salvar_arquivo_upload(
                arquivo, 'materiais_import')

            # Processar o arquivo Excel
            df = processar_arquivo_excel(caminho_arquivo)

            if df is None or df.empty:
                flash('O arquivo está vazio ou não contém dados válidos.', 'warning')
                return redirect(request.url)

            # Validar que as colunas necessárias existem
            colunas_necessarias = [
                'codigo', 'descricao', 'unidade', 'centro_custo']
            colunas_faltantes = [
                col for col in colunas_necessarias if col not in df.columns]

            if colunas_faltantes:
                flash(
                    f'O arquivo não contém as colunas necessárias: {", ".join(colunas_faltantes)}', 'warning')
                return redirect(request.url)

            # Preparar para importação
            resultados = importar_materiais_do_df(df)

            # Mensagem de sucesso
            flash(
                f'Importação concluída: {resultados["importados"]} materiais importados, {resultados["erros"]} erros.', 'success')
            return redirect(url_for('materiais.listar'))

        except Exception as e:
            logger.error(f"Erro ao importar materiais: {str(e)}")
            flash(f'Erro ao processar o arquivo: {str(e)}', 'danger')
            return redirect(request.url)

    return render_template('cadastros/materiais/importar.html')

# Função para importar materiais do DataFrame


def importar_materiais_do_df(df):
    """
    Importa materiais de um DataFrame para o banco de dados

    Args:
        df (pandas.DataFrame): DataFrame com os dados dos materiais

    Returns:
        dict: Dicionário com os resultados da importação
    """
    resultados = {
        "importados": 0,
        "erros": 0,
        "detalhes": []
    }

    # Para cada linha do DataFrame
    for index, row in df.iterrows():
        try:
            # Buscar centro de custo pelo código ou nome
            centro_custo_query = """
                SELECT id FROM centros_custo 
                WHERE codigo = %s OR nome = %s
                LIMIT 1
            """
            centro_custo = get_single_result(centro_custo_query, [
                row.get('centro_custo', ''),
                row.get('centro_custo', '')
            ])

            if not centro_custo:
                resultados["erros"] += 1
                resultados["detalhes"].append(
                    f"Linha {index+2}: Centro de custo não encontrado: {row.get('centro_custo', '')}")
                continue

            centro_custo_id = centro_custo['id']

            # Verificar se o material já existe pelo código
            material_existente = get_single_result(
                "SELECT id FROM materiais WHERE codigo = %s",
                [row.get('codigo', '')]
            )

            now = datetime.now()

            if material_existente:
                # Atualizar material existente
                data = {
                    'descricao': row.get('descricao', ''),
                    'unidade': row.get('unidade', ''),
                    'centro_custo_id': centro_custo_id,
                    'pc': row.get('pc', ''),
                    'codigo_erp': row.get('codigo_erp', ''),
                    'alterado_por': session['usuario_id'],
                    'alterado_em': now
                }

                update_data('materiais', data, 'id', material_existente['id'])

                resultados["importados"] += 1
                logger.info(
                    f"Material {row.get('codigo')} atualizado na importação")
            else:
                # Inserir novo material
                data = {
                    'codigo': row.get('codigo', ''),
                    'descricao': row.get('descricao', ''),
                    'unidade': row.get('unidade', ''),
                    'centro_custo_id': centro_custo_id,
                    'pc': row.get('pc', ''),
                    'codigo_erp': row.get('codigo_erp', ''),
                    'ativo': 1,
                    'criado_por': session['usuario_id'],
                    'criado_em': now,
                    'alterado_em': now
                }

                insert_data('materiais', data)

                resultados["importados"] += 1
                logger.info(
                    f"Material {row.get('codigo')} criado na importação")

        except Exception as e:
            resultados["erros"] += 1
            resultados["detalhes"].append(f"Linha {index+2}: {str(e)}")
            logger.error(f"Erro ao importar linha {index+2}: {str(e)}")

    return resultados

# Inicialização do módulo


def init_app(app):
    # Registrar o Blueprint no app principal
    app.register_blueprint(mod_materiais)
    logger.info("Módulo de materiais inicializado")
