from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import pandas as pd
import os
from werkzeug.utils import secure_filename

from models.database import db
from models.plano_conta import PlanoConta

# Configuração para upload de arquivos
UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

plano_conta_bp = Blueprint('plano_conta', __name__)

# Verificar se a extensão do arquivo é permitida
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Middleware para verificar se o usuário tem permissão
@plano_conta_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_gerente_ou_superior:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@plano_conta_bp.route('/')
@login_required
def index():
    """
    Lista todos os planos de conta
    """
    planos_conta = PlanoConta.query.order_by(PlanoConta.codigo).all()
    return render_template('admin/cadastros/planos_conta/index.html', 
                          planos_conta=planos_conta)

@plano_conta_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cria um novo plano de conta
    """
    if request.method == 'POST':
        codigo = request.form.get('codigo')
        descricao = request.form.get('descricao')
        indice = request.form.get('indice', '')
        ativo = True if request.form.get('ativo') == 'on' else False
        
        # Validação básica
        if not codigo or not descricao:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('admin/cadastros/planos_conta/novo.html')
        
        # Verificar se o código já existe
        plano_existente = PlanoConta.query.filter_by(codigo=codigo).first()
        if plano_existente:
            flash(f'Um plano de conta com o código {codigo} já existe!', 'danger')
            return render_template('admin/cadastros/planos_conta/novo.html')
        
        # Criar novo plano de conta
        novo_plano = PlanoConta(
            codigo=codigo,
            descricao=descricao,
            indice=indice,
            ativo=ativo
        )
        
        try:
            novo_plano.save()
            flash('Plano de conta cadastrado com sucesso!', 'success')
            return redirect(url_for('plano_conta.index'))
        except Exception as e:
            flash(f'Erro ao cadastrar plano de conta: {str(e)}', 'danger')
            
    return render_template('admin/cadastros/planos_conta/novo.html')

@plano_conta_bp.route('/visualizar/<int:id>')
@login_required
def visualizar(id):
    """
    Visualiza os detalhes de um plano de conta
    """
    plano_conta = PlanoConta.query.get_or_404(id)
    return render_template('admin/cadastros/planos_conta/visualizar.html', plano_conta=plano_conta)

@plano_conta_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um plano de conta existente
    """
    plano_conta = PlanoConta.query.get_or_404(id)
    
    if request.method == 'POST':
        codigo = request.form.get('codigo')
        descricao = request.form.get('descricao')
        indice = request.form.get('indice', '')
        ativo = True if request.form.get('ativo') == 'on' else False
        
        # Validação básica
        if not codigo or not descricao:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('admin/cadastros/planos_conta/editar.html', 
                                  plano_conta=plano_conta)
        
        # Verificar se o código já existe (exceto para o plano atual)
        plano_existente = PlanoConta.query.filter(
            PlanoConta.codigo == codigo,
            PlanoConta.id != id
        ).first()
        
        if plano_existente:
            flash(f'Um plano de conta com o código {codigo} já existe!', 'danger')
            return render_template('admin/cadastros/planos_conta/editar.html', 
                                  plano_conta=plano_conta)
        
        # Atualizar o plano de conta
        plano_conta.codigo = codigo
        plano_conta.descricao = descricao
        plano_conta.indice = indice
        plano_conta.ativo = ativo
        
        try:
            plano_conta.save()
            flash('Plano de conta atualizado com sucesso!', 'success')
            return redirect(url_for('plano_conta.index'))
        except Exception as e:
            flash(f'Erro ao atualizar plano de conta: {str(e)}', 'danger')
    
    return render_template('admin/cadastros/planos_conta/editar.html', 
                          plano_conta=plano_conta)

@plano_conta_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um plano de conta
    """
    plano_conta = PlanoConta.query.get_or_404(id)
    
    try:
        plano_conta.delete()
        flash('Plano de conta excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir plano de conta: {str(e)}', 'danger')
    
    return redirect(url_for('plano_conta.index'))

@plano_conta_bp.route('/api/planos-conta')
@login_required
def api_planos_conta():
    """
    Retorna os planos de conta em formato JSON (para uso em APIs)
    """
    query = PlanoConta.query
    
    # Filtragem por status (ativo/inativo)
    status = request.args.get('ativo')
    if status is not None:
        is_active = status.lower() == 'true'
        query = query.filter_by(ativo=is_active)
    
    # Filtragem por índice
    indice = request.args.get('indice')
    if indice:
        query = query.filter_by(indice=indice)
    
    # Busca por texto
    search = request.args.get('q')
    if search:
        query = query.filter(
            db.or_(
                PlanoConta.codigo.like(f'%{search}%'),
                PlanoConta.descricao.like(f'%{search}%'),
                PlanoConta.indice.like(f'%{search}%')
            )
        )
    
    # Ordenação
    sort_by = request.args.get('sort_by', 'codigo')
    sort_dir = request.args.get('sort_dir', 'asc')
    
    if sort_dir == 'desc':
        query = query.order_by(db.desc(getattr(PlanoConta, sort_by)))
    else:
        query = query.order_by(getattr(PlanoConta, sort_by))
    
    planos_conta = query.all()
    return jsonify([plano.to_dict() for plano in planos_conta])

@plano_conta_bp.route('/importar', methods=['GET', 'POST'])
@login_required
def importar():
    """
    Importa planos de conta a partir de um arquivo Excel
    """
    resultados = None
    
    if request.method == 'POST':
        # Verificar se o arquivo foi enviado
        if 'arquivo_excel' not in request.files:
            flash('Nenhum arquivo enviado', 'danger')
            return render_template('admin/cadastros/planos_conta/importar.html')
        
        arquivo = request.files['arquivo_excel']
        
        # Verificar se o arquivo está vazio
        if arquivo.filename == '':
            flash('Nenhum arquivo selecionado', 'danger')
            return render_template('admin/cadastros/planos_conta/importar.html')
        
        # Verificar se a extensão é permitida
        if not allowed_file(arquivo.filename):
            flash('Formato de arquivo não permitido. Use apenas .xlsx ou .xls', 'danger')
            return render_template('admin/cadastros/planos_conta/importar.html')
        
        # Obter os parâmetros de mapeamento
        nome_planilha = request.form.get('planilha')
        coluna_codigo = request.form.get('coluna_codigo')
        coluna_descricao = request.form.get('coluna_descricao')
        coluna_indice = request.form.get('coluna_indice')
        primeira_linha_cabecalho = 'primeira_linha_cabecalho' in request.form
        
        # Validar os parâmetros necessários
        if not nome_planilha or not coluna_codigo or not coluna_descricao:
            flash('É necessário selecionar a planilha e mapear os campos obrigatórios', 'danger')
            return render_template('admin/cadastros/planos_conta/importar.html')
        
        try:
            coluna_codigo = int(coluna_codigo)
            coluna_descricao = int(coluna_descricao)
            if coluna_indice:
                coluna_indice = int(coluna_indice)
        except ValueError:
            flash('Mapeamento de colunas inválido', 'danger')
            return render_template('admin/cadastros/planos_conta/importar.html')
        
        try:
            # Verificar se o diretório de upload existe, senão criar
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
            
            # Salvar o arquivo temporariamente
            filename = secure_filename(arquivo.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            arquivo.save(filepath)
            
            # Ler o arquivo Excel com a planilha especificada
            if primeira_linha_cabecalho:
                df = pd.read_excel(filepath, sheet_name=nome_planilha)
            else:
                df = pd.read_excel(filepath, sheet_name=nome_planilha, header=None)
            
            # Inicializar contadores para o resultado
            total = len(df)
            sucesso = 0
            ignorados = 0
            erros = 0
            erros_detalhes = []
            
            # Processar cada linha do arquivo
            for index, row in df.iterrows():
                linha_atual = index + 2 if primeira_linha_cabecalho else index + 1
                
                try:
                    # Obter valores das colunas mapeadas
                    # Para linhas com cabeçalho, o pandas usa os nomes das colunas
                    # Para linhas sem cabeçalho, usamos os índices numéricos das colunas
                    if primeira_linha_cabecalho:
                        # Usar o índice de coluna (número)
                        codigo = str(row.iloc[coluna_codigo]).strip()
                        descricao = str(row.iloc[coluna_descricao]).strip()
                        indice = str(row.iloc[coluna_indice]).strip() if coluna_indice is not None else ''
                    else:
                        # Usar o índice de coluna (número)
                        codigo = str(row.iloc[coluna_codigo]).strip()
                        descricao = str(row.iloc[coluna_descricao]).strip()
                        indice = str(row.iloc[coluna_indice]).strip() if coluna_indice is not None else ''
                    
                    # Validar dados obrigatórios
                    if not codigo or pd.isna(codigo) or codigo == 'nan':
                        raise ValueError("Código não pode ser vazio")
                    
                    if not descricao or pd.isna(descricao) or descricao == 'nan':
                        raise ValueError("Descrição não pode ser vazia")
                    
                    # Verificar se já existe um plano com este código
                    plano_existente = PlanoConta.query.filter_by(codigo=codigo).first()
                    if plano_existente:
                        ignorados += 1
                        continue
                    
                    # Criar novo plano de conta
                    novo_plano = PlanoConta(
                        codigo=codigo,
                        descricao=descricao,
                        indice=indice,
                        ativo=True
                    )
                    
                    db.session.add(novo_plano)
                    sucesso += 1
                    
                except Exception as e:
                    erros += 1
                    erro_detalhe = {
                        'linha': linha_atual,
                        'codigo': codigo if 'codigo' in locals() else '',
                        'descricao': descricao if 'descricao' in locals() else '',
                        'erro': str(e)
                    }
                    erros_detalhes.append(erro_detalhe)
            
            # Confirmar as alterações no banco de dados
            db.session.commit()
            
            # Remover o arquivo temporário
            if os.path.exists(filepath):
                os.remove(filepath)
            
            # Preparar resultados para exibição
            resultados = {
                'total': total,
                'sucesso': sucesso,
                'ignorados': ignorados,
                'erros': erros,
                'erros_detalhes': erros_detalhes
            }
            
            if sucesso > 0:
                flash(f'{sucesso} planos de conta importados com sucesso!', 'success')
            else:
                flash('Nenhum plano de conta foi importado.', 'warning')
            
        except Exception as e:
            flash(f'Erro ao processar o arquivo: {str(e)}', 'danger')
            # Se houver algum erro, remover o arquivo temporário
            if 'filepath' in locals() and os.path.exists(filepath):
                os.remove(filepath)
    
    return render_template('admin/cadastros/planos_conta/importar.html', resultados=resultados) 