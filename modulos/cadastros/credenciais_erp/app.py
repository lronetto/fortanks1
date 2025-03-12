# coding: utf-8
# modulos/cadastros/credenciais_erp/app.py

from flask import render_template, request, redirect, url_for, flash, session
import os
import logging
from datetime import datetime
from flask import Blueprint

# Importações das funções centralizadas
from utils.db import get_db_connection, execute_query, get_single_result, insert_data, update_data
from utils.auth import login_obrigatorio, admin_obrigatorio, verificar_permissao, get_user_id
from utils.crypto import encrypt_password, decrypt_password

# Configuração de logging
log_dir = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'credenciais_erp.log')

logger = logging.getLogger(__name__)

# Criar Blueprint
mod_credenciais_erp = Blueprint(
    'credenciais_erp', __name__, template_folder='templates')


def init_app(app):
    """Inicializa o submódulo credenciais_erp"""
    return app

# Rota para listar credenciais


@mod_credenciais_erp.route('/')
@login_obrigatorio
def listar():
    """Lista todas as credenciais do ERP"""
    try:
        # Verificar permissão
        if not verificar_permissao('visualizar'):
            flash('Você não tem permissão para visualizar credenciais', 'danger')
            return redirect(url_for('dashboard'))

        # Buscar todas as credenciais
        query = """
        SELECT 
            ec.id, 
            ec.nome, 
            ec.url_login, 
            ec.url_relatorio, 
            ec.periodo, 
            ec.ativo, 
            ec.criado_por, 
            ec.criado_em,
            er.usuario as usuario_usuario,
            er.data_atualizacao,
            u.nome as usuario_nome,
            u.email as usuario_email,
            u.cargo as usuario_cargo
        FROM 
            erp_configuracoes ec
        LEFT JOIN 
            erp_credenciais er ON ec.criado_por = er.id
        LEFT JOIN
            usuarios u ON ec.criado_por = u.id
        ORDER BY 
            ec.nome
        """
        credenciais = execute_query(query)

        return render_template('cadastros/credenciais_erp/listar.html', credenciais=credenciais)

    except Exception as e:
        logger.error(f"Erro ao listar credenciais: {str(e)}")
        flash(f'Erro ao listar credenciais: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

# Rota para nova credencial


@mod_credenciais_erp.route('/novo', methods=['GET'])
@login_obrigatorio
def novo():
    """Exibe o formulário para nova credencial"""
    try:
        # Verificar permissão
        if not verificar_permissao('editar'):
            flash('Você não tem permissão para cadastrar credenciais', 'danger')
            return redirect(url_for('cadastros.credenciais_erp.listar'))

        # Buscar usuários para o select
        usuarios = execute_query(
            "SELECT id, nome, email FROM usuarios ORDER BY nome")

        return render_template('cadastros/credenciais_erp/form.html', usuarios=usuarios)

    except Exception as e:
        logger.error(f"Erro ao exibir formulário de nova credencial: {str(e)}")
        flash(f'Erro ao exibir formulário: {str(e)}', 'danger')
        return redirect(url_for('cadastros.credenciais_erp.listar'))

# Rota para salvar nova credencial


@mod_credenciais_erp.route('/novo', methods=['POST'])
@login_obrigatorio
def salvar():
    """Processa o formulário de nova credencial"""
    # Verificar permissão
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para cadastrar credenciais', 'danger')
        return redirect(url_for('cadastros.credenciais_erp.listar'))

    try:
        # Obter dados do formulário
        nome = request.form.get('nome', '').strip()
        usuario_sistema = request.form.get('usuario_sistema', '').strip()
        usuario = request.form.get('usuario', '').strip()
        senha = request.form.get('senha', '').strip()

        # Validar dados
        if not nome or not usuario_sistema or not usuario or not senha:
            flash('Todos os campos marcados com * são obrigatórios', 'danger')
            # Buscar lista de usuários do sistema para reexibir o formulário
            usuarios = execute_query(
                "SELECT id, nome, email FROM usuarios ORDER BY nome")

            # Criar um objeto credencial a partir dos dados do formulário
            # Não incluímos um ID para que o template saiba que é um novo cadastro
            form_data = {
                'nome': nome,
                'usuario': usuario,
                'usuario_sistema': usuario_sistema
            }

            return render_template('cadastros/credenciais_erp/form.html',
                                   credencial=form_data,
                                   usuarios=usuarios)

        # Criptografar a senha
        senha_criptografada = encrypt_password(senha)

        # Usar valores padrão para os campos opcionais que foram removidos do formulário
        url_login = 'https://www.sox.com.br/'
        url_relatorio = ''
        periodo = 'atual'
        ativo = True

        # Inserir configuração
        configuracao_id = insert_data('erp_configuracoes', {
            'nome': nome,
            'url_login': url_login,
            'url_relatorio': url_relatorio,
            'periodo': periodo,
            'tipo_relatorio': 0,
            'ativo': 1 if ativo else 0,
            'criado_por': usuario_sistema,  # Agora usamos o ID do usuário selecionado
            'criado_em': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        if configuracao_id:
            # Inserir credenciais
            insert_data('erp_credenciais', {
                'usuario_id': configuracao_id,
                'usuario': usuario,
                'senha_encriptada': senha_criptografada
            })

            flash('Credencial cadastrada com sucesso!', 'success')
            return redirect(url_for('cadastros.credenciais_erp.listar'))
        else:
            flash('Erro ao cadastrar credencial', 'danger')
            # Buscar lista de usuários do sistema para reexibir o formulário
            usuarios = execute_query(
                "SELECT id, nome, email FROM usuarios ORDER BY nome")

            # Criar um objeto credencial a partir dos dados do formulário
            form_data = {
                'nome': nome,
                'usuario': usuario,
                'usuario_sistema': usuario_sistema
            }

            return render_template('cadastros/credenciais_erp/form.html',
                                   credencial=form_data,
                                   usuarios=usuarios)

    except Exception as e:
        logger.error(f"Erro ao salvar credencial: {str(e)}")
        flash(f'Erro ao salvar credencial: {str(e)}', 'danger')
        # Buscar lista de usuários do sistema para reexibir o formulário
        usuarios = execute_query(
            "SELECT id, nome, email FROM usuarios ORDER BY nome")

        # Criar um objeto credencial a partir dos dados do formulário
        form_data = {
            'nome': request.form.get('nome', ''),
            'usuario': request.form.get('usuario', ''),
            'usuario_sistema': request.form.get('usuario_sistema', '')
        }

        return render_template('cadastros/credenciais_erp/form.html',
                               credencial=form_data,
                               usuarios=usuarios)

# Rota para editar credencial


@mod_credenciais_erp.route('/editar/<int:id>', methods=['GET'])
@login_obrigatorio
def editar(id):
    """Exibe formulário para edição de credencial"""
    # Verificar permissão
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para editar credenciais', 'danger')
        return redirect(url_for('cadastros.credenciais_erp.listar'))

    try:
        # Obter credencial
        credencial = get_single_result("""
            SELECT c.*, cr.usuario
            FROM erp_configuracoes c
            JOIN erp_credenciais cr ON c.id = cr.configuracao_id
            WHERE c.id = %s
        """, [id])

        if not credencial:
            flash('Credencial não encontrada', 'warning')
            return redirect(url_for('cadastros.credenciais_erp.listar'))

        # Verificar se o usuário tem permissão para editar esta credencial específica
        usuario_id = get_user_id()
        if session.get('cargo') != 'admin' and credencial['criado_por'] != usuario_id:
            flash('Você não tem permissão para editar esta credencial', 'danger')
            return redirect(url_for('cadastros.credenciais_erp.listar'))

        # Buscar lista de usuários do sistema
        usuarios = execute_query(
            "SELECT id, nome, email FROM usuarios ORDER BY nome")

        return render_template('cadastros/credenciais_erp/form.html', credencial=credencial, usuarios=usuarios)

    except Exception as e:
        logger.error(f"Erro ao buscar credencial para edição: {str(e)}")
        flash(f'Erro ao carregar credencial: {str(e)}', 'danger')
        return redirect(url_for('cadastros.credenciais_erp.listar'))

# Rota para atualizar credencial


@mod_credenciais_erp.route('/editar/<int:id>', methods=['POST'])
@login_obrigatorio
def atualizar(id):
    """Processa o formulário de edição de credencial"""
    # Verificar permissão
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para editar credenciais', 'danger')
        return redirect(url_for('cadastros.credenciais_erp.listar'))

    try:
        # Verificar se o usuário tem permissão para editar esta credencial específica
        usuario_id = get_user_id()
        credencial_atual = get_single_result(
            "SELECT * FROM erp_configuracoes WHERE id = %s", [id])

        if not credencial_atual:
            flash('Credencial não encontrada', 'warning')
            return redirect(url_for('cadastros.credenciais_erp.listar'))

        if session.get('cargo') != 'admin' and credencial_atual['criado_por'] != usuario_id:
            flash('Você não tem permissão para editar esta credencial', 'danger')
            return redirect(url_for('cadastros.credenciais_erp.listar'))

        # Obter dados do formulário
        nome = request.form.get('nome', '').strip()
        usuario_sistema = request.form.get('usuario_sistema', '').strip()
        usuario = request.form.get('usuario', '').strip()
        senha = request.form.get('senha', '').strip()

        # Validar dados
        if not nome or not usuario_sistema or not usuario:
            flash('Nome, usuário do sistema e usuário do ERP são obrigatórios', 'danger')

            # Buscar lista de usuários do sistema
            usuarios = execute_query(
                "SELECT id, nome, email FROM usuarios ORDER BY nome")

            # Criar um objeto credencial com os dados do formulário e o ID original
            form_data = {
                'id': id,
                'nome': nome,
                'usuario': usuario,
                'usuario_sistema': usuario_sistema,
                'criado_por': usuario_sistema
            }

            return render_template('cadastros/credenciais_erp/form.html',
                                   credencial=form_data,
                                   usuarios=usuarios)

        # Atualizar configuração - mantendo os campos opcionais anteriores inalterados
        update_data('erp_configuracoes', {
            'nome': nome,
            'criado_por': usuario_sistema  # Agora podemos alterar o usuário associado
        }, 'id', id)

        # Atualizar credenciais
        update_data('erp_credenciais', {
            'usuario': usuario,
        }, 'configuracao_id', id)

        # Se uma nova senha foi fornecida, atualizar
        if senha:
            senha_criptografada = encrypt_password(senha)
            update_data('erp_credenciais', {
                'senha_encriptada': senha_criptografada,
            }, 'configuracao_id', id)

        flash('Credencial atualizada com sucesso!', 'success')
        return redirect(url_for('cadastros.credenciais_erp.listar'))

    except Exception as e:
        logger.error(f"Erro ao atualizar credencial: {str(e)}")
        flash(f'Erro ao atualizar credencial: {str(e)}', 'danger')

        # Buscar lista de usuários do sistema
        usuarios = execute_query(
            "SELECT id, nome, email FROM usuarios ORDER BY nome")

        # Criar um objeto credencial com os dados do formulário e o ID original
        form_data = {
            'id': id,
            'nome': request.form.get('nome', ''),
            'usuario': request.form.get('usuario', ''),
            'usuario_sistema': request.form.get('usuario_sistema', '')
        }

        return render_template('cadastros/credenciais_erp/form.html',
                               credencial=form_data,
                               usuarios=usuarios)

# Rota para excluir credencial


@mod_credenciais_erp.route('/excluir/<int:id>', methods=['POST'])
@login_obrigatorio
def excluir(id):
    """Exclui uma credencial"""
    # Verificar permissão
    if not verificar_permissao('editar'):
        flash('Você não tem permissão para excluir credenciais', 'danger')
        return redirect(url_for('cadastros.credenciais_erp.listar'))

    try:
        # Verificar se o usuário tem permissão para excluir esta credencial específica
        usuario_id = get_user_id()
        credencial = get_single_result(
            "SELECT criado_por FROM erp_configuracoes WHERE id = %s", [id])

        if not credencial:
            flash('Credencial não encontrada', 'warning')
            return redirect(url_for('cadastros.credenciais_erp.listar'))

        if session.get('cargo') != 'admin' and credencial['criado_por'] != usuario_id:
            flash('Você não tem permissão para excluir esta credencial', 'danger')
            return redirect(url_for('cadastros.credenciais_erp.listar'))

        # Excluir primeiro as credenciais (chave estrangeira)
        execute_query(
            "DELETE FROM erp_credenciais WHERE configuracao_id = %s", [id])

        # Excluir a configuração
        execute_query("DELETE FROM erp_configuracoes WHERE id = %s", [id])

        flash('Credencial excluída com sucesso!', 'success')
        return redirect(url_for('cadastros.credenciais_erp.listar'))

    except Exception as e:
        logger.error(f"Erro ao excluir credencial: {str(e)}")
        flash(f'Erro ao excluir credencial: {str(e)}', 'danger')
        return redirect(url_for('cadastros.credenciais_erp.listar'))
