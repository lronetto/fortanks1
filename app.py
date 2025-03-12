# app.py - Aplicativo principal
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, send_from_directory
from flask_wtf.csrf import CSRFProtect
import os
import tempfile
import pdfkit
import platform
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pathlib
import logging
import secrets

# Importar os módulos
from modulos.importacao_nf import mod_importacao_nf, init_app as init_importacao_nf
from modulos.integracao_erp import mod_integracao_erp, init_app as init_integracao_erp
from modulos.checklist import mod_checklist, init_app as init_checklist
from modulos.solicitacao import mod_solicitacao, init_app as init_solicitacao
from modulos.cadastros import mod_cadastros, init_app as init_cadastros

# Importações das funções centralizadas
from utils.db import get_db_connection, execute_query, get_single_result, insert_data, update_data, init_app as init_db
from utils.auth import login_obrigatorio, admin_obrigatorio, verificar_permissao, get_user_id

# Limpar variáveis de ambiente existentes que possam interferir
for key in ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'SECRET_KEY', 'ARQUIVEI_API_ID', 'ARQUIVEI_API_KEY']:
    if key in os.environ:
        del os.environ[key]

# Obter o caminho absoluto do arquivo .env
current_dir = pathlib.Path(__file__).parent.absolute()
env_path = current_dir / '.env'

load_dotenv(dotenv_path=env_path, override=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Configurações do banco de dados e segurança
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['MYSQL_HOST'] = os.getenv('DB_HOST')
app.config['MYSQL_USER'] = os.getenv('DB_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('DB_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('DB_NAME')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
app.config['WTF_CSRF_ENABLED'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# Aumentar os limites de upload de arquivos
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
app.config['UPLOAD_EXTENSIONS'] = ['.xml', '.zip']
app.config['MAX_CONTENT_PATH'] = None

# Configuração de logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'app.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Inicializa o CSRF Protection
csrf = CSRFProtect(app)

# Inicializa o módulo de banco de dados
init_db(app)

# Registrar os Blueprints
app.register_blueprint(mod_importacao_nf)
app.register_blueprint(mod_integracao_erp, url_prefix='/integracao_erp')
app.register_blueprint(mod_checklist, url_prefix='/checklist')
app.register_blueprint(mod_solicitacao, url_prefix='/solicitacao')
app.register_blueprint(mod_cadastros, url_prefix='/cadastros')

# Inicializar funções de configuração dos módulos
init_importacao_nf(app)
init_integracao_erp(app)
init_checklist(app)
init_solicitacao(app)
init_cadastros(app)

# Context processor para disponibilizar a variável 'now' em todos os templates


@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Context processor para o menu


@app.context_processor
def inject_menu_data():
    return {'menu_items': []}

# Rotas para autenticação


@app.route('/')
def index():
    """Página inicial do sistema"""
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    # Renderizar diretamente a página de login
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Tela e processamento de login"""
    # Se já está logado, redireciona para o dashboard
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))

    # Processar o formulário de login
    if request.method == 'POST':
        email = request.form.get('email', '')
        senha = request.form.get('senha', '')

        try:
            # Buscar usuário por email
            usuario = get_single_result(
                "SELECT * FROM usuarios WHERE email = %s", [email])

            if usuario:
                try:
                    # Verificar senha
                    senha_correta = check_password_hash(
                        usuario['senha'], senha)
                    if senha_correta:
                        # Guardar dados na sessão
                        session['usuario_id'] = usuario['id']
                        session['nome'] = usuario['nome']
                        session['departamento'] = usuario['departamento']
                        session['cargo'] = usuario['cargo']

                        # Registrar o login no log
                        logger.info(f"Login realizado com sucesso: {email}")

                        flash('Login realizado com sucesso', 'success')
                        return redirect(url_for('dashboard'))
                except ValueError:
                    # Modo alternativo para desenvolvimento
                    if usuario['senha'] == senha:
                        session['usuario_id'] = usuario['id']
                        session['nome'] = usuario['nome']
                        session['departamento'] = usuario['departamento']
                        session['cargo'] = usuario['cargo']

                        logger.warning(
                            f"Login em modo desenvolvimento: {email}")
                        flash(
                            'Login realizado com sucesso (modo desenvolvimento)', 'success')
                        return redirect(url_for('dashboard'))

            # Se chegou aqui, login falhou
            logger.warning(f"Tentativa de login falhou: {email}")
            flash('Email ou senha inválidos', 'danger')

        except Exception as e:
            logger.error(f"Erro no processo de login: {str(e)}")
            flash('Ocorreu um erro ao processar o login. Tente novamente.', 'danger')

    # Renderizar a página de login (GET ou POST com erro)
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Encerra a sessão do usuário"""
    # Registrar o logout no log
    if 'usuario_id' in session:
        logger.info(f"Logout do usuário ID: {session.get('usuario_id')}")

    session.clear()
    flash('Você foi desconectado com sucesso', 'success')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_obrigatorio
def dashboard():
    """Dashboard principal do sistema"""
    try:
        # Obter estatísticas para o dashboard
        stats = {
            'solicitacoes_abertas': 0,
            'solicitacoes_finalizadas': 0,
            'materiais_cadastrados': 0,
            'solicitacoes_mes': 0
        }

        # Obter solicitações abertas
        result = get_single_result(
            "SELECT COUNT(*) as total FROM solicitacoes WHERE status IN ('aberta', 'em_analise', 'aprovada')")
        if result:
            stats['solicitacoes_abertas'] = result['total']

        # Obter solicitações finalizadas
        result = get_single_result(
            "SELECT COUNT(*) as total FROM solicitacoes WHERE status = 'finalizada'")
        if result:
            stats['solicitacoes_finalizadas'] = result['total']

        # Obter total de materiais cadastrados
        result = get_single_result(
            "SELECT COUNT(*) as total FROM materiais WHERE ativo = 1")
        if result:
            stats['materiais_cadastrados'] = result['total']

        # Obter solicitações do mês atual
        result = get_single_result("""
            SELECT COUNT(*) as total FROM solicitacoes 
            WHERE MONTH(data_solicitacao) = MONTH(CURRENT_DATE()) 
            AND YEAR(data_solicitacao) = YEAR(CURRENT_DATE())
        """)
        if result:
            stats['solicitacoes_mes'] = result['total']

        # Filtrar estatísticas por permissão
        cargo = session.get('cargo', '')
        nivel_acesso = {
            'admin': 3,
            'gerente': 2,
            'supervisor': 1,
            'técnico': 0
        }.get(cargo, 0)

        # Ajustar estatísticas com base no nível de acesso
        if nivel_acesso < 1:  # Técnico
            # Mostrar apenas as solicitações do próprio usuário
            user_id = get_user_id()
            result = get_single_result("""
                SELECT COUNT(*) as total FROM solicitacoes 
                WHERE status IN ('aberta', 'em_analise', 'aprovada') AND usuario_id = %s
            """, [user_id])
            if result:
                stats['solicitacoes_abertas'] = result['total']

            result = get_single_result("""
                SELECT COUNT(*) as total FROM solicitacoes 
                WHERE status = 'finalizada' AND usuario_id = %s
            """, [user_id])
            if result:
                stats['solicitacoes_finalizadas'] = result['total']

            result = get_single_result("""
                SELECT COUNT(*) as total FROM solicitacoes 
                WHERE MONTH(data_solicitacao) = MONTH(CURRENT_DATE()) 
                AND YEAR(data_solicitacao) = YEAR(CURRENT_DATE())
                AND usuario_id = %s
            """, [user_id])
            if result:
                stats['solicitacoes_mes'] = result['total']

        return render_template('dashboard.html', stats=stats)

    except Exception as e:
        logger.error(f"Erro ao carregar dashboard: {str(e)}")
        flash(
            'Ocorreu um erro ao carregar o dashboard. Por favor, tente novamente.', 'danger')
        return render_template('dashboard.html', stats={})


@app.route('/perfil')
@login_obrigatorio
def perfil():
    """Exibe e permite editar o perfil do usuário logado"""
    try:
        # Buscar dados do usuário
        user_id = get_user_id()
        user = get_single_result("""
            SELECT id, nome, usuario, email, cargo, departamento,
                   DATE_FORMAT(ultimo_acesso, '%d/%m/%Y %H:%i') as ultimo_acesso
            FROM usuarios 
            WHERE id = %s
        """, [user_id])

        if not user:
            flash('Erro ao carregar perfil de usuário', 'danger')
            return redirect(url_for('dashboard'))

        # Buscar estatísticas do usuário
        stats = {
            'total_solicitacoes': 0,
            'total_aprovacoes': 0,
            'ultimo_acesso': user.get('ultimo_acesso', 'Nunca')
        }

        # Total de solicitações feitas pelo usuário
        result = get_single_result("""
            SELECT COUNT(*) as total 
            FROM solicitacoes 
            WHERE usuario_id = %s
        """, [user_id])
        if result:
            stats['total_solicitacoes'] = result['total']

        # Total de aprovações (apenas para cargos que podem aprovar)
        if user['cargo'] in ['admin', 'gerente', 'supervisor']:
            result = get_single_result("""
                SELECT COUNT(*) as total 
                FROM solicitacoes 
                WHERE aprovado_por = %s
            """, [user_id])
            if result:
                stats['total_aprovacoes'] = result['total']

        return render_template('perfil.html', user=user, stats=stats)

    except Exception as e:
        logger.error(f"Erro ao carregar perfil: {str(e)}")
        flash(
            'Ocorreu um erro ao carregar seu perfil. Por favor, tente novamente.', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/alterar-senha', methods=['POST'])
@login_obrigatorio
def alterar_senha():
    """Altera a senha do usuário"""
    senha_atual = request.form.get('senha_atual')
    nova_senha = request.form.get('nova_senha')
    confirmar_senha = request.form.get('confirmar_senha')

    if not all([senha_atual, nova_senha, confirmar_senha]):
        flash('Todos os campos são obrigatórios', 'danger')
        return redirect(url_for('perfil'))

    if nova_senha != confirmar_senha:
        flash('A nova senha e a confirmação não coincidem', 'danger')
        return redirect(url_for('perfil'))

    try:
        # Verificar senha atual
        user_id = get_user_id()
        usuario = get_single_result(
            "SELECT senha FROM usuarios WHERE id = %s", [user_id])

        if not usuario or not check_password_hash(usuario['senha'], senha_atual):
            flash('Senha atual incorreta', 'danger')
            return redirect(url_for('perfil'))

        # Atualizar senha
        nova_senha_hash = generate_password_hash(nova_senha)
        update_data('usuarios', {'senha': nova_senha_hash}, 'id', user_id)

        logger.info(f"Senha alterada com sucesso para o usuário ID: {user_id}")
        flash('Senha alterada com sucesso!', 'success')

    except Exception as e:
        logger.error(f"Erro ao alterar senha: {str(e)}")
        flash('Ocorreu um erro ao alterar sua senha. Por favor, tente novamente.', 'danger')

    return redirect(url_for('perfil'))


@app.route('/editar-perfil', methods=['POST'])
@login_obrigatorio
def editar_perfil():
    """Atualiza os dados do perfil do usuário"""
    nome = request.form.get('nome')
    email = request.form.get('email')
    departamento = request.form.get('departamento')
    cargo = request.form.get('cargo')

    if not all([nome, email]):
        flash('Nome e email são obrigatórios', 'danger')
        return redirect(url_for('perfil'))

    try:
        user_id = get_user_id()

        # Verificar se o email já está em uso por outro usuário
        email_existe = get_single_result(
            "SELECT id FROM usuarios WHERE email = %s AND id != %s",
            [email, user_id]
        )

        if email_existe:
            flash('Este email já está em uso por outro usuário', 'danger')
            return redirect(url_for('perfil'))

        # Atualizar dados do usuário
        data = {
            'nome': nome,
            'email': email,
            'departamento': departamento
        }

        # O cargo só pode ser alterado por administradores
        if session.get('cargo') == 'admin' and cargo:
            data['cargo'] = cargo

        update_data('usuarios', data, 'id', user_id)

        # Atualizar dados da sessão
        session['nome'] = nome
        session['departamento'] = departamento

        logger.info(f"Perfil atualizado para o usuário ID: {user_id}")
        flash('Perfil atualizado com sucesso!', 'success')

    except Exception as e:
        logger.error(f"Erro ao atualizar perfil: {str(e)}")
        flash(
            'Ocorreu um erro ao atualizar seu perfil. Por favor, tente novamente.', 'danger')

    return redirect(url_for('perfil'))

# Rota para acessar uploads


@app.route('/uploads/<path:filename>')
@login_obrigatorio
def uploads(filename):
    """Serve arquivos de uploads com autenticação"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Handler para erros 404


@app.errorhandler(404)
def pagina_nao_encontrada(e):
    """Página para erro 404"""
    return render_template('errors/404.html'), 404

# Handler para erros 500


@app.errorhandler(500)
def erro_interno(e):
    """Página para erro 500"""
    logger.error(f"Erro 500: {str(e)}")
    return render_template('errors/500.html'), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
