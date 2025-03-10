# app.py - Aplicativo principal
from modulo_importacao_nf.app import mod_importacao_nf
from modulo_integracao_erp import mod_integracao_erp, init_app
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_mysqldb import MySQL
import os
import tempfile
import pdfkit
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['MYSQL_HOST'] = os.getenv('DB_HOST')
app.config['MYSQL_USER'] = os.getenv('DB_USER')
app.config['MYSQL_PASSWORD'] = os.getenv(
    'DB_PASSWORD')  # Altere para sua senha do MySQL
app.config['MYSQL_DB'] = os.getenv('DB_NAME')
app.config['ARQUIVEI_API_ID'] = os.getenv('ARQUIVEI_API_ID')
app.config['ARQUIVEI_API_KEY'] = os.getenv('ARQUIVEI_API_KEY')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# Configurações
# app.config['SECRET_KEY'] = os.urandom(24)
# app.config['MYSQL_HOST'] = '192.168.8.150'
# app.config['MYSQL_USER'] = 'remote'
# app.config['MYSQL_PASSWORD'] = '8225Le@28'  # Altere para sua senha do MySQL
# app.config['MYSQL_DB'] = 'sistema_solicitacoes'
# app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
# app.config['ARQUIVEI_API_ID'] = '34bbd6ea3d83eb093e48b0f8ece693667540c603'
# app.config['ARQUIVEI_API_KEY'] = '6c3ec74c9c40511b8b32541ed231d26328c356a4'

# Configurações
# app.config['SECRET_KEY'] = os.urandom(24)
# app.config['MYSQL_HOST'] = db_host
# app.config['MYSQL_USER'] = db_user
# app.config['MYSQL_PASSWORD'] = db_password  # Altere para sua senha do MySQL
# app.config['MYSQL_DB'] = db_name
# app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# Inicializa o MySQL
mysql = MySQL(app)

# Context processor para disponibilizar a variável 'now' em todos os templates


@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Função para gerar PDF


# Importar o Blueprint do módulo de importação de NF

# Registrar o Blueprint
app.register_blueprint(mod_importacao_nf, url_prefix='/importacao_nf')
app.register_blueprint(mod_integracao_erp, url_prefix='/integracao_erp')

# Atualizar o menu no context processor


@app.context_processor
def inject_menu_data():
    return {
        'menu_items': [
            {'name': 'Dashboard', 'url': url_for(
                'dashboard'), 'icon': 'fas fa-tachometer-alt'},
            {'name': 'Solicitações', 'url': url_for(
                'dashboard'), 'icon': 'fas fa-clipboard-list'},
            {'name': 'Notas Fiscais', 'url': url_for(
                'importacao_nf.index'), 'icon': 'fas fa-file-invoice'},
            {'name': 'Relatórios', 'url': url_for(
                'relatorio_centro_custo'), 'icon': 'fas fa-chart-bar'},
            {'name': 'Integração ERP', 'url': url_for(
                'integracao_erp.index'), 'icon': 'fas fa-sync'},
        ] if 'logado' in session else []
    }


def generate_pdf(html_content, filename):
    # Configuração para o wkhtmltopdf (ajuste o caminho conforme sua instalação)
    # No Linux geralmente é: /usr/bin/wkhtmltopdf
    # No Windows geralmente é: C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe
    # No Mac geralmente é: /usr/local/bin/wkhtmltopdf
    config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')

    # Crie um arquivo temporário
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp:
        temp_filename = temp.name

    # Gere o PDF
    pdfkit.from_string(html_content, temp_filename, configuration=config)

    return temp_filename

# Rotas para autenticação


@app.route('/')
def index():
    if 'logado' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM usuarios WHERE email = %s", [email])
        usuario = cur.fetchone()
        cur.close()

        if usuario:
            # Verificação de senha com tratamento de erro
            try:
                senha_correta = check_password_hash(usuario['senha'], senha)
                if senha_correta:
                    session['logado'] = True
                    session['id_usuario'] = usuario['id']
                    session['nome'] = usuario['nome']
                    session['departamento'] = usuario['departamento']
                    session['cargo'] = usuario['cargo']

                    flash('Login realizado com sucesso', 'success')
                    return redirect(url_for('dashboard'))
            except ValueError:
                # Se o hash estiver em formato inválido, tente comparação direta
                # (usado apenas para facilitar desenvolvimento ou testes)
                if usuario['senha'] == senha:
                    session['logado'] = True
                    session['id_usuario'] = usuario['id']
                    session['nome'] = usuario['nome']
                    session['departamento'] = usuario['departamento']
                    session['cargo'] = usuario['cargo']

                    flash(
                        'Login realizado com sucesso (modo desenvolvimento)', 'success')
                    return redirect(url_for('dashboard'))

        flash('Email ou senha incorretos', 'danger')

    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema', 'info')
    return redirect(url_for('index'))

# Rotas do dashboard


# Atualizar a rota dashboard para suportar múltiplos itens
@app.route('/dashboard')
def dashboard():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()

    # Obter solicitações do usuário com seus itens
    cur.execute("""
        SELECT s.*, c.codigo as centro_custo_codigo, c.nome as centro_custo_nome,
        (SELECT nome FROM usuarios WHERE id = s.aprovador_id) as aprovador_nome,
        (SELECT COUNT(*) FROM itens_solicitacao WHERE solicitacao_id = s.id) as total_itens,
        (SELECT SUM(quantidade) FROM itens_solicitacao WHERE solicitacao_id = s.id) as quantidade_total
        FROM solicitacoes s
        LEFT JOIN centros_custo c ON s.centro_custo_id = c.id
        WHERE s.solicitante_id = %s
        ORDER BY s.data_solicitacao DESC
    """, [session['id_usuario']])

    minhas_solicitacoes = cur.fetchall()

    # Verificar se é aprovador e obter solicitações pendentes
    solicitacoes_pendentes = []
    if session['cargo'] == 'gerente' or session['cargo'] == 'diretor':
        cur.execute("""
            SELECT s.*, c.codigo as centro_custo_codigo, c.nome as centro_custo_nome,
            (SELECT nome FROM usuarios WHERE id = s.solicitante_id) as solicitante_nome,
            (SELECT departamento FROM usuarios WHERE id = s.solicitante_id) as departamento_solicitante,
            (SELECT COUNT(*) FROM itens_solicitacao WHERE solicitacao_id = s.id) as total_itens,
            (SELECT SUM(quantidade) FROM itens_solicitacao WHERE solicitacao_id = s.id) as quantidade_total
            FROM solicitacoes s
            LEFT JOIN centros_custo c ON s.centro_custo_id = c.id
            WHERE s.status = 'pendente'
            ORDER BY s.data_solicitacao ASC
        """)
        solicitacoes_pendentes = cur.fetchall()

    # Obter lista de materiais disponíveis
    cur.execute("SELECT * FROM materiais ORDER BY nome")
    materiais = cur.fetchall()

    # Obter lista de centros de custo
    cur.execute("SELECT * FROM centros_custo WHERE ativo = TRUE ORDER BY codigo")
    centros_custo = cur.fetchall()

    cur.close()

    return render_template('dashboard.html',
                           minhas_solicitacoes=minhas_solicitacoes,
                           solicitacoes_pendentes=solicitacoes_pendentes,
                           materiais=materiais,
                           centros_custo=centros_custo)


@app.route('/solicitar', methods=['POST'])
def solicitar_material():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Dados da solicitação
        justificativa = request.form['justificativa']
        centro_custo_id = request.form['centro_custo_id']
        data_solicitacao = datetime.now()

        # Obter os itens do formulário
        materiais_ids = request.form.getlist('material_id[]')
        quantidades = request.form.getlist('quantidade[]')
        observacoes = request.form.getlist('observacao_item[]')

        # Verificar se há pelo menos um item
        if not materiais_ids or len(materiais_ids) == 0:
            flash('Adicione pelo menos um item à solicitação', 'danger')
            return redirect(url_for('dashboard'))

        cur = mysql.connection.cursor()
        try:
            # Iniciar transação
            cur.execute("""
                INSERT INTO solicitacoes 
                (justificativa, solicitante_id, centro_custo_id, status, data_solicitacao)
                VALUES (%s, %s, %s, %s, %s)
            """, [justificativa, session['id_usuario'], centro_custo_id, 'pendente', data_solicitacao])

            # Obter o ID da solicitação inserida
            solicitacao_id = cur.lastrowid

            # Inserir os itens da solicitação
            for i in range(len(materiais_ids)):
                material_id = materiais_ids[i]
                quantidade = quantidades[i]
                observacao = observacoes[i] if i < len(observacoes) else ''

                cur.execute("""
                    INSERT INTO itens_solicitacao
                    (solicitacao_id, material_id, quantidade, observacao)
                    VALUES (%s, %s, %s, %s)
                """, [solicitacao_id, material_id, quantidade, observacao])

            # Commit da transação
            mysql.connection.commit()
            flash('Solicitação enviada com sucesso', 'success')

        except Exception as e:
            # Em caso de erro, desfaz a transação
            mysql.connection.rollback()
            flash(f'Erro ao processar a solicitação: {str(e)}', 'danger')
        finally:
            cur.close()

    return redirect(url_for('dashboard'))


@app.route('/solicitacao/<int:id>')
def visualizar_solicitacao(id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()

    # Obter dados da solicitação
    cur.execute("""
        SELECT s.*, 
        c.codigo as centro_custo_codigo, c.nome as centro_custo_nome,
        u_sol.nome as solicitante_nome, u_sol.email as solicitante_email, u_sol.departamento as solicitante_departamento,
        u_apr.nome as aprovador_nome, u_apr.email as aprovador_email, u_apr.departamento as aprovador_departamento
        FROM solicitacoes s
        LEFT JOIN centros_custo c ON s.centro_custo_id = c.id
        JOIN usuarios u_sol ON s.solicitante_id = u_sol.id
        LEFT JOIN usuarios u_apr ON s.aprovador_id = u_apr.id
        WHERE s.id = %s
    """, [id])

    solicitacao = cur.fetchone()

    # Verificar se a solicitação existe e se o usuário tem permissão
    if not solicitacao or (solicitacao['solicitante_id'] != session['id_usuario'] and
                           session['cargo'] not in ['gerente', 'diretor', 'admin']):
        flash('Solicitação não encontrada ou sem permissão para acessá-la', 'danger')
        return redirect(url_for('dashboard'))

    # Obter itens da solicitação
    cur.execute("""
        SELECT i.*, m.nome as material_nome, m.descricao as material_descricao, m.categoria as material_categoria
        FROM itens_solicitacao i
        JOIN materiais m ON i.material_id = m.id
        WHERE i.solicitacao_id = %s
        ORDER BY i.id
    """, [id])

    itens = cur.fetchall()
    cur.close()

    return render_template('visualizar_solicitacao.html',
                           solicitacao=solicitacao,
                           itens=itens)


@app.route('/aprovar/<int:id>', methods=['POST'])
def aprovar_solicitacao(id):
    if 'logado' not in session or (session['cargo'] != 'gerente' and session['cargo'] != 'diretor'):
        flash('Você não tem permissão para aprovar solicitações', 'danger')
        return redirect(url_for('dashboard'))

    observacao = request.form.get('observacao', '')

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE solicitacoes 
        SET status = 'aprovada', 
            aprovador_id = %s, 
            data_aprovacao = %s,
            observacao = %s
        WHERE id = %s
    """, [session['id_usuario'], datetime.now(), observacao, id])

    mysql.connection.commit()
    cur.close()

    flash('Solicitação aprovada com sucesso', 'success')
    return redirect(url_for('dashboard'))


@app.route('/rejeitar/<int:id>', methods=['POST'])
def rejeitar_solicitacao(id):
    if 'logado' not in session or (session['cargo'] != 'gerente' and session['cargo'] != 'diretor'):
        flash('Você não tem permissão para rejeitar solicitações', 'danger')
        return redirect(url_for('dashboard'))

    motivo = request.form['motivo']

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE solicitacoes 
        SET status = 'rejeitada', 
            aprovador_id = %s, 
            data_aprovacao = %s,
            observacao = %s
        WHERE id = %s
    """, [session['id_usuario'], datetime.now(), motivo, id])

    mysql.connection.commit()
    cur.close()

    flash('Solicitação rejeitada', 'warning')
    return redirect(url_for('dashboard'))

# Rotas para gerenciamento de materiais (somente admin)


@app.route('/materiais')
def listar_materiais():
    if 'logado' not in session or session['cargo'] != 'admin':
        flash('Acesso restrito para administradores', 'danger')
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM materiais ORDER BY nome")
    materiais = cur.fetchall()
    cur.close()

    return render_template('materiais.html', materiais=materiais)


@app.route('/adicionar_material', methods=['POST'])
def adicionar_material():
    if 'logado' not in session or session['cargo'] != 'admin':
        flash('Acesso restrito para administradores', 'danger')
        return redirect(url_for('dashboard'))

    nome = request.form['nome']
    descricao = request.form['descricao']
    categoria = request.form['categoria']

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO materiais (nome, descricao, categoria) VALUES (%s, %s, %s)",
                [nome, descricao, categoria])
    mysql.connection.commit()
    cur.close()

    flash('Material adicionado com sucesso', 'success')
    return redirect(url_for('listar_materiais'))

# Rotas para administração de usuários (somente admin)


@app.route('/usuarios')
def listar_usuarios():
    if 'logado' not in session or session['cargo'] != 'admin':
        flash('Acesso restrito para administradores', 'danger')
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id, nome, email, departamento, cargo FROM usuarios ORDER BY nome")
    usuarios = cur.fetchall()
    cur.close()

    return render_template('usuarios.html', usuarios=usuarios)


@app.route('/adicionar_usuario', methods=['POST'])
def adicionar_usuario():
    if 'logado' not in session or session['cargo'] != 'admin':
        flash('Acesso restrito para administradores', 'danger')
        return redirect(url_for('dashboard'))

    nome = request.form['nome']
    email = request.form['email']
    # Gere um hash válido com método especificado (sha256)
    senha = generate_password_hash(
        request.form['senha'], method='pbkdf2:sha256')
    departamento = request.form['departamento']
    cargo = request.form['cargo']

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO usuarios (nome, email, senha, departamento, cargo) VALUES (%s, %s, %s, %s, %s)",
                [nome, email, senha, departamento, cargo])
    mysql.connection.commit()
    cur.close()

    flash('Usuário adicionado com sucesso', 'success')
    return redirect(url_for('listar_usuarios'))

# Rotas para centros de custo


@app.route('/centros_custo')
def listar_centros_custo():
    if 'logado' not in session or session['cargo'] != 'admin':
        flash('Acesso restrito para administradores', 'danger')
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM centros_custo ORDER BY codigo")
    centros_custo = cur.fetchall()
    cur.close()

    return render_template('centros_custo.html', centros_custo=centros_custo)


@app.route('/adicionar_centro_custo', methods=['POST'])
def adicionar_centro_custo():
    if 'logado' not in session or session['cargo'] != 'admin':
        flash('Acesso restrito para administradores', 'danger')
        return redirect(url_for('dashboard'))

    codigo = request.form['codigo']
    nome = request.form['nome']
    descricao = request.form['descricao']

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO centros_custo (codigo, nome, descricao) VALUES (%s, %s, %s)",
                [codigo, nome, descricao])
    mysql.connection.commit()
    cur.close()

    flash('Centro de custo adicionado com sucesso', 'success')
    return redirect(url_for('listar_centros_custo'))

# Rota para exportar PDF


# Atualizar a rota para exportar PDF
@app.route('/exportar_pdf/<int:id>')
def exportar_pdf(id):
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()

    # Obter dados da solicitação
    cur.execute("""
        SELECT s.*, 
        c.codigo as centro_custo_codigo, c.nome as centro_custo_nome,
        u_sol.nome as solicitante_nome, u_sol.email as solicitante_email, u_sol.departamento as solicitante_departamento,
        u_apr.nome as aprovador_nome, u_apr.email as aprovador_email, u_apr.departamento as aprovador_departamento
        FROM solicitacoes s
        LEFT JOIN centros_custo c ON s.centro_custo_id = c.id
        JOIN usuarios u_sol ON s.solicitante_id = u_sol.id
        LEFT JOIN usuarios u_apr ON s.aprovador_id = u_apr.id
        WHERE s.id = %s
    """, [id])

    solicitacao = cur.fetchone()

    # Verificar se a solicitação existe e se o usuário tem permissão
    if not solicitacao or (solicitacao['solicitante_id'] != session['id_usuario'] and
                           session['cargo'] not in ['gerente', 'diretor', 'admin']):
        flash('Solicitação não encontrada ou sem permissão para acessá-la', 'danger')
        return redirect(url_for('dashboard'))

    # Obter itens da solicitação
    cur.execute("""
        SELECT i.*, m.nome as material_nome, m.descricao as material_descricao, m.categoria as material_categoria
        FROM itens_solicitacao i
        JOIN materiais m ON i.material_id = m.id
        WHERE i.solicitacao_id = %s
        ORDER BY i.id
    """, [id])

    itens = cur.fetchall()
    cur.close()

    # Renderizar o template para o PDF
    html_content = render_template('solicitacao_pdf.html',
                                   solicitacao=solicitacao,
                                   itens=itens)

    # Gerar o PDF
    pdf_file = generate_pdf(html_content, f'solicitacao_{id}.pdf')

    # Enviar o arquivo para download
    return_data = send_file(pdf_file,
                            mimetype='application/pdf',
                            as_attachment=True,
                            download_name=f'solicitacao_{id}.pdf')

    # Programar a remoção do arquivo temporário após o download
    @return_data.call_on_close
    def delete_file():
        if os.path.exists(pdf_file):
            os.remove(pdf_file)

    return return_data


@app.route('/relatorios/centro_custo')
def relatorio_centro_custo():
    if 'logado' not in session or session['cargo'] not in ['gerente', 'diretor', 'admin']:
        flash('Acesso restrito', 'danger')
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor()

    # Totais por centro de custo
    cur.execute("""
        SELECT c.codigo, c.nome, COUNT(s.id) as total_solicitacoes, 
               SUM(s.quantidade) as total_itens,
               (SELECT COUNT(*) FROM solicitacoes WHERE centro_custo_id = c.id AND status = 'aprovada') as aprovadas,
               (SELECT COUNT(*) FROM solicitacoes WHERE centro_custo_id = c.id AND status = 'rejeitada') as rejeitadas,
               (SELECT COUNT(*) FROM solicitacoes WHERE centro_custo_id = c.id AND status = 'pendente') as pendentes
        FROM centros_custo c
        LEFT JOIN solicitacoes s ON c.id = s.centro_custo_id
        GROUP BY c.id
        ORDER BY total_solicitacoes DESC
    """)

    resumo_centros = cur.fetchall()
    cur.close()

    return render_template('relatorio_centro_custo.html', resumo_centros=resumo_centros)

# Rota para os dados do gráfico


@app.route('/dados_grafico')
def dados_grafico():
    if 'logado' not in session:
        return jsonify({'error': 'Não autorizado'}), 401

    cur = mysql.connection.cursor()

    # Total de solicitações por status
    cur.execute("""
        SELECT status, COUNT(*) as total 
        FROM solicitacoes 
        GROUP BY status
    """)

    dados = cur.fetchall()
    cur.close()

    labels = [d['status'] for d in dados]
    valores = [d['total'] for d in dados]

    return jsonify({
        'labels': labels,
        'valores': valores
    })


@app.route('/buscar_material', methods=['GET', 'POST'])
def buscar_material():
    if 'logado' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('index'))

    termo_busca = request.args.get('termo', '')

    if termo_busca:
        cur = mysql.connection.cursor()
        # Busca por nome, descrição ou categoria usando LIKE
        cur.execute("""
            SELECT * FROM materiais 
            WHERE nome LIKE %s OR descricao LIKE %s OR categoria LIKE %s
            ORDER BY nome
        """, [f'%{termo_busca}%', f'%{termo_busca}%', f'%{termo_busca}%'])

        resultados = cur.fetchall()
        cur.close()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Se for uma requisição AJAX, retorna JSON
            return jsonify(resultados)
        else:
            # Se for acesso direto, renderiza template
            return render_template('busca_materiais.html',
                                   resultados=resultados,
                                   termo=termo_busca)

    return render_template('busca_materiais.html', termo=termo_busca, resultados=[])


# Iniciar o aplicativo
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
# Adicione estas rotas ao seu app.py

# Rota para busca de materiais
