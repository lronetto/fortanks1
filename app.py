# app.py - Aplicativo principal
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_mysqldb import MySQL, cursors
from flask_wtf.csrf import CSRFProtect
import os
import tempfile
import pdfkit
import platform
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pathlib

# Importar os módulos
from modulos.importacao_nf import mod_importacao_nf, init_app as init_importacao_nf
from modulos.integracao_erp import mod_integracao_erp, init_app as init_integracao_erp
from modulos.checklist import mod_checklist, init_app as init_checklist
from modulos.solicitacao import mod_solicitacao, init_app as init_solicitacao
from modulos.cadastros import mod_cadastros, init_app as init_cadastros

# Limpar variáveis de ambiente existentes que possam interferir
for key in ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'SECRET_KEY', 'ARQUIVEI_API_ID', 'ARQUIVEI_API_KEY']:
    if key in os.environ:
        del os.environ[key]

# Obter o caminho absoluto do arquivo .env
current_dir = pathlib.Path(__file__).parent.absolute()
env_path = current_dir / '.env'

load_dotenv(dotenv_path=env_path, override=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sua_chave_secreta')

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

# Inicializa o CSRF Protection
csrf = CSRFProtect(app)

# Inicializa o MySQL
mysql = MySQL(app)

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

# Após as importações e antes das rotas


def get_db_connection():
    try:
        connection = mysql.connection
        return connection
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        return None

# Rotas para autenticação


@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM usuarios WHERE email = %s", [email])
        usuario = cur.fetchone()
        cur.close()

        if usuario:
            try:
                senha_correta = check_password_hash(usuario['senha'], senha)
                if senha_correta:
                    session['usuario_id'] = usuario['id']
                    session['nome'] = usuario['nome']
                    session['departamento'] = usuario['departamento']
                    session['cargo'] = usuario['cargo']
                    flash('Login realizado com sucesso', 'success')
                    return redirect(url_for('dashboard'))
            except ValueError:
                if usuario['senha'] == senha:  # Modo desenvolvimento
                    session['usuario_id'] = usuario['id']
                    session['nome'] = usuario['nome']
                    session['departamento'] = usuario['departamento']
                    session['cargo'] = usuario['cargo']
                    flash('Login realizado com sucesso', 'success')
                    return redirect(url_for('dashboard'))

        flash('Email ou senha inválidos', 'danger')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado com sucesso', 'success')
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    # Inicializa as variáveis
    minhas_solicitacoes = []
    solicitacoes_pendentes = []
    materiais = []
    centros_custo = []

    try:
        cur = mysql.connection.cursor()

        try:
            # Buscar solicitações do usuário
            cur.execute("""
                        SELECT s.*, cc.nome as centro_custo_nome 
                FROM solicitacoes s
                        LEFT JOIN centros_custo cc ON s.centro_custo_id = cc.id
                WHERE s.solicitante_id = %s
                ORDER BY s.data_solicitacao DESC
                        LIMIT 5
                    """, [session['usuario_id']])
            minhas_solicitacoes = cur.fetchall()
        except Exception as e:
            flash(f'Erro ao buscar suas solicitações: {str(e)}', 'danger')

        if session.get('cargo') == 'admin':
            try:
                # Buscar solicitações pendentes (apenas para admin)
                cur.execute("""
                            SELECT s.*, u.nome as solicitante_nome, cc.nome as centro_custo_nome
                    FROM solicitacoes s
                            LEFT JOIN usuarios u ON s.solicitante_id = u.id
                            LEFT JOIN centros_custo cc ON s.centro_custo_id = cc.id
                    WHERE s.status = 'pendente'
                            ORDER BY s.data_solicitacao DESC
                            LIMIT 5
                """)
                solicitacoes_pendentes = cur.fetchall()
            except Exception as e:
                flash(
                    f'Erro ao buscar solicitações pendentes: {str(e)}', 'danger')

            try:
                # Buscar materiais mais recentes
                cur.execute("""
                    SELECT * FROM materiais 
                    ORDER BY criado_em DESC 
                    LIMIT 5
                """)
                materiais = cur.fetchall()
            except Exception as e:
                flash(f'Erro ao buscar materiais: {str(e)}', 'danger')

            try:
                # Buscar centros de custo ativos
                cur.execute("""
                    SELECT * FROM centros_custo 
                    WHERE ativo = TRUE 
                    ORDER BY codigo
                """)
                centros_custo = cur.fetchall()
            except Exception as e:
                flash(f'Erro ao buscar centros de custo: {str(e)}', 'danger')

            cur.close()

            return render_template('dashboard.html',
                                   minhas_solicitacoes=minhas_solicitacoes,
                                   solicitacoes_pendentes=solicitacoes_pendentes,
                                   materiais=materiais,
                                   centros_custo=centros_custo)

    except Exception as e:
        flash(f'Erro ao carregar dashboard: {str(e)}', 'danger')
        return render_template('dashboard.html',
                               minhas_solicitacoes=[],
                               solicitacoes_pendentes=[],
                               materiais=[],
                               centros_custo=[])


@app.route('/perfil')
def perfil():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    usuario = None

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM usuarios WHERE id = %s",
                           (session['usuario_id'],))
            usuario = cursor.fetchone()
            cursor.close()
        finally:
            connection.close()

    return render_template('perfil.html', usuario=usuario)


@app.route('/alterar-senha', methods=['POST'])
def alterar_senha():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    senha_atual = request.form.get('senha_atual')
    nova_senha = request.form.get('nova_senha')
    confirmar_senha = request.form.get('confirmar_senha')

    if not all([senha_atual, nova_senha, confirmar_senha]):
        flash('Todos os campos são obrigatórios', 'danger')
        return redirect(url_for('perfil'))

    if nova_senha != confirmar_senha:
        flash('A nova senha e a confirmação não coincidem', 'danger')
        return redirect(url_for('perfil'))

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Verificar senha atual
            cursor.execute(
                "SELECT senha FROM usuarios WHERE id = %s", (session['usuario_id'],))
            usuario = cursor.fetchone()

            if not usuario or not check_password_hash(usuario['senha'], senha_atual):
                flash('Senha atual incorreta', 'danger')
                return redirect(url_for('perfil'))

            # Atualizar senha
            nova_senha_hash = generate_password_hash(nova_senha)
            cursor.execute("UPDATE usuarios SET senha = %s WHERE id = %s",
                           (nova_senha_hash, session['usuario_id']))

            connection.commit()
            flash('Senha alterada com sucesso!', 'success')

            cursor.close()
        except Error as e:
            flash(f'Erro ao alterar senha: {str(e)}', 'danger')
        finally:
            connection.close()

    return redirect(url_for('perfil'))


@app.route('/editar-perfil', methods=['POST'])
def editar_perfil():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    nome = request.form.get('nome')
    email = request.form.get('email')
    departamento = request.form.get('departamento')
    cargo = request.form.get('cargo')

    if not all([nome, email]):
        flash('Nome e email são obrigatórios', 'danger')
        return redirect(url_for('perfil'))

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Verificar se o email já está em uso por outro usuário
            cursor.execute("SELECT id FROM usuarios WHERE email = %s AND id != %s",
                           (email, session['usuario_id']))
            if cursor.fetchone():
                flash('Este email já está em uso por outro usuário', 'danger')
                return redirect(url_for('perfil'))

            # Atualizar dados do usuário
            cursor.execute("""
                UPDATE usuarios 
                SET nome = %s, email = %s, departamento = %s, cargo = %s 
                WHERE id = %s
            """, (nome, email, departamento, cargo, session['usuario_id']))

            connection.commit()

            # Atualizar dados da sessão
            session['nome'] = nome
            session['departamento'] = departamento
            session['cargo'] = cargo

            flash('Perfil atualizado com sucesso!', 'success')
            cursor.close()

        except Exception as e:
            flash(f'Erro ao atualizar perfil: {str(e)}', 'danger')
        finally:
            connection.close()

    return redirect(url_for('perfil'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
