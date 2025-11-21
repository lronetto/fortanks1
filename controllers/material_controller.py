from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import uuid
import pandas as pd
import tempfile
import openpyxl
from io import BytesIO
import logging
import json
from sqlalchemy import or_

from models.database import db
from models.material import Material
from models.plano_conta import PlanoConta
from models.conversao_unidade import ConversaoUnidade
from models.unidade import Unidade
from models.nota_fiscal import NotaFiscalItem

# Configurar o logger para o módulo
logger = logging.getLogger(__name__)

material_bp = Blueprint('material', __name__, url_prefix='/materiais')

# Middleware para verificar se o usuário tem permissão
#@material_bp.before_request
#@login_required
#def verificar_permissao():

#    if not current_user.is_gerente_ou_superior:
#        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
#        return redirect(url_for('dashboard.index'))

@material_bp.route('/')
@login_required
def index():
    """
    Lista materiais com filtros e paginação
    """
    #materiais = Material.query.all()
    #for material in materiais:
    #    if material.plano_conta:
    #        material.plano_conta_id = PlanoConta.query.filter_by(codigo=int(material.plano_conta)).first().id
    #db.session.commit()
    # Obter parâmetros de filtro e paginação
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    per_page = current_app.config.get('PER_PAGE', 20) # Aumentar padrão para 20

    # Construir a query base
    query = Material.query

    # Aplicar filtro de busca (nome ou código)
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.filter(or_(
            Material.nome.ilike(search_pattern),
            Material.codigo.ilike(search_pattern)
        ))

    # Aplicar filtro de categoria
    if category_filter:
        query = query.filter(Material.categoria == category_filter)

    # Ordenar (opcional, mas recomendado)
    query = query.order_by(Material.nome)

    # Paginar a query filtrada
    materiais_paginados = query.paginate(page=page, per_page=per_page, error_out=False)
    materiais = materiais_paginados.items
    
    # Buscar planos de conta para o modal de edição
    planos_conta = PlanoConta.query.filter_by(ativo=True).all()
    
    # Buscar todas as unidades ativas
    unidades = Unidade.query.filter_by(ativo=True).order_by(Unidade.nome).all()
    
    # Coleta todas as categorias distintas para o filtro (pode ser otimizado)
    todas_categorias = db.session.query(Material.categoria).distinct().order_by(Material.categoria).all()
    categorias_filtro = [cat[0] for cat in todas_categorias if cat[0]] # Lista de strings
    
    return render_template('materiais/index.html', 
                         materiais=materiais, 
                         pagination=materiais_paginados,
                         planos_conta=planos_conta,
                         unidades=unidades,
                         categorias_filtro=categorias_filtro, # Passa as categorias para o select
                         search_term=search_term,         # Mantém o valor da busca
                         category_filter=category_filter  # Mantém o valor do filtro de categoria
                         )

@material_bp.route('/novo', methods=['GET'])
@login_required
def novo_get():
    """
    Redireciona GET para index, pois agora usamos um modal
    """
    return redirect(url_for('material.index'))

@material_bp.route('/novo', methods=['POST'])
@login_required
def novo():
    """
    Cria um novo material
    """
    # Busca todos os planos de conta ativos para o formulário
    planos_conta = PlanoConta.query.filter_by(ativo=True).order_by(PlanoConta.indice).all()
    # Buscar todas as unidades ativas
    unidades = Unidade.query.filter_by(ativo=True).order_by(Unidade.nome).all()
    
    if request.method == 'POST':
        try:
            codigo = request.form.get('codigo')
            nome = request.form.get('nome')
            descricao = request.form.get('descricao')
            categoria = request.form.get('categoria')
            plano_conta = request.form.get('plano_conta')
            codigo_erp = request.form.get('codigo_erp')
            unidade = request.form.get('unidade')
            mascara = request.form.get('mascara')
            formula_calculo = request.form.get('formula_calculo', '').strip()
            print(f'request.form: {request.form}')
            
            # Verificar o campo alternativo de unidade
            unidade_texto = request.form.get('unidade_texto', '')
            if not unidade and unidade_texto:
                logger.info(f"Usando o campo alternativo de unidade: {unidade_texto}")
                unidade = unidade_texto
            
            logger.info(f"Valor final da unidade: {unidade}")
            
            # Verificar se a requisição vem do modal ou página normal
            from_modal = request.referrer and 'index' in request.referrer
            
            # Validar campos obrigatórios
            if not nome or not categoria:
                flash('Nome e categoria são campos obrigatórios!', 'danger')
                if from_modal:
                    return redirect(url_for('material.index'))
                return render_template('materiais/novo.html', planos_conta=planos_conta, unidades=unidades)
            
            # Verificar duplicidade de código
            if codigo and Material.query.filter_by(codigo=codigo).first():
                flash(f'Já existe um material com o código {codigo}!', 'danger')
                if from_modal:
                    return redirect(url_for('material.index'))
                return render_template('materiais/novo.html', planos_conta=planos_conta, unidades=unidades)
            
            # Criar nova instância
            material = Material(
                codigo=codigo,
                nome=nome,
                descricao=descricao,
                categoria=categoria,
                plano_conta=plano_conta,
                codigo_erp=codigo_erp,
                unidade_id=unidade,
                mascara=mascara,  # Novo campo com relacionamento
                formula_calculo=formula_calculo if formula_calculo else None
            )
            
            # Definir usuário que criou
            material.usuario_id = current_user.id
            
            # Salvar no banco
            material.save()
            
            flash('Material cadastrado com sucesso!', 'success')
            
            # Se vier do modal, redirecionar para a página de lista
            if from_modal:
                return redirect(url_for('material.index'))
            
            return redirect(url_for('material.index'))
        
        except Exception as e:
            flash(f'Erro ao cadastrar material: {str(e)}', 'danger')
            if 'from_modal' in locals() and from_modal:
                return redirect(url_for('material.index'))
    
    return render_template('materiais/index.html')

@material_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um material existente
    """
    logger.info(f"Acessando edição do material ID: {id}")
    
    # Verificar se é uma requisição AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    logger.info(f"É uma requisição AJAX: {is_ajax}")
    
    try:
        # Busca o material pelo ID
        material = Material.query.get_or_404(id)
        logger.info(f"Material encontrado: {material.nome}")
        
        # Buscar todas as unidades ativas
        unidades = Unidade.query.filter_by(ativo=True).order_by(Unidade.nome).all()
        
        # Para requisições GET AJAX, retornar dados JSON
        if request.method == 'GET' and is_ajax:
            logger.info(f"Retornando dados do material ID {id} em formato JSON")
            return jsonify({
                'id': material.id,
                'codigo': material.codigo or '',
                'nome': material.nome or '',
                'descricao': material.descricao or '',
                'categoria': material.categoria or '',
                'plano_conta': material.plano_conta or '',
                'codigo_erp': material.codigo_erp or '',
                'unidade': material.unidade or '',
                'unidade_id': material.unidade_id or 0,
                'mascara': material.mascara or '',
                'formula_calculo': material.formula_calculo or ''
            })
        
        # Para requisições POST
        if request.method == 'POST':
            form_data = request.form.to_dict()
            print(f"Dados recebidos do formulário: {form_data}")
            
            codigo = request.form.get('codigo', '')
            nome = request.form.get('nome', '')
            descricao = request.form.get('descricao', '')
            categoria = request.form.get('categoria', '')
            plano_conta = request.form.get('plano_conta', '')
            codigo_erp = request.form.get('codigo_erp', '')
            unidade = request.form.get('unidade', '')
            mascara = request.form.get('mascara', '')
            formula_calculo = request.form.get('formula_calculo', '').strip()
            
            # Validar campos obrigatórios
            if not nome or not categoria:
                logger.warning(f"Campos obrigatórios não preenchidos: nome={nome}, categoria={categoria}")
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'message': 'Nome e categoria são campos obrigatórios!'
                    })
                else:
                    flash('Nome e categoria são campos obrigatórios!', 'danger')
                    return render_template('materiais/editar.html', material=material, 
                                            planos_conta=PlanoConta.query.filter_by(ativo=True).all(),
                                            unidades=unidades)
            
            # Verificar duplicidade de código (se for alterado)
            if codigo and codigo != material.codigo and Material.query.filter_by(codigo=codigo).first():
                logger.warning(f"Tentativa de alterar código para um já existente: {codigo}")
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'message': f'Já existe um material com o código {codigo}!'
                    })
                else:
                    flash(f'Já existe um material com o código {codigo}!', 'danger')
                    return render_template('materiais/editar.html', material=material, 
                                            planos_conta=PlanoConta.query.filter_by(ativo=True).all(),
                                            unidades=unidades)
            
            logger.info(f"Atualizando material ID {id} de '{material.nome}' para '{nome}'")
            
            # Validação especial para o código (campo pode ser requerido no modelo)
            if not codigo:
                # Se o banco não aceitar NULL, gerar um código único temporário
                codigo = f"AUTO-{id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                logger.info(f"Código vazio: gerando código temporário '{codigo}'")
  
            # Atualizar dados
            material.codigo = codigo
            material.nome = nome
            material.descricao = descricao
            material.categoria = categoria
            material.plano_conta = plano_conta
            material.codigo_erp = codigo_erp
            material.unidade_id = unidade
            material.mascara = mascara
            material.formula_calculo = formula_calculo if formula_calculo else None
            try:
                # Salvar no banco
                db.session.add(material)
                db.session.commit()
                logger.info(f"Material ID {id} atualizado com sucesso")
                
                if is_ajax:
                    return jsonify({
                        'success': True,
                        'message': 'Material atualizado com sucesso!',
                        'material': {
                            'id': material.id,
                            'nome': material.nome,
                            'codigo': material.codigo,
                            'categoria': material.categoria,
                            'unidade': material.unidade,
                            'mascara': material.mascara
                        }
                    })
                else:
                    flash('Material atualizado com sucesso!', 'success')
                    return redirect(url_for('material.visualizar', id=material.id))
                    
            except Exception as db_error:
                db.session.rollback()
                error_msg = str(db_error)
                logger.error(f"Erro ao salvar material no banco: {error_msg}", exc_info=True)
                
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'message': f'Erro ao salvar material: {error_msg}'
                    })
                else:
                    flash(f'Erro ao salvar material: {error_msg}', 'danger')
                    return render_template('materiais/editar.html', material=material, planos_conta=PlanoConta.query.filter_by(ativo=True).all(), unidades=unidades)
        
        # Para requisições GET normais, renderizar o template
        planos_conta = PlanoConta.query.filter_by(ativo=True).all()
        return render_template('materiais/editar.html', material=material, planos_conta=planos_conta, unidades=unidades)
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Erro ao processar edição do material: {error_msg}", exc_info=True)
        
        if is_ajax:
            return jsonify({
                'success': False,
                'message': f'Erro ao atualizar material: {error_msg}'
            })
        else:
            flash(f'Erro ao atualizar material: {error_msg}', 'danger')
            return redirect(url_for('material.index'))

@material_bp.route('/visualizar/<int:id>')
@login_required
def visualizar(id):
    """
    Visualiza os detalhes de um material
    """
    material = Material.query.get_or_404(id)
    return render_template('materiais/visualizar.html', material=material)

@material_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um material
    """
    logger.info(f"Tentando excluir material ID: {id}")
    
    try:
        material = Material.query.get_or_404(id)
        logger.info(f"Material encontrado: {material.nome} (ID: {material.id})")
        
        # Verificar se o material está vinculado a alguma solicitação
        has_itens = False
        try:
            has_itens = len(material.itens_solicitacao) > 0
            logger.info(f"Material possui {len(material.itens_solicitacao)} itens de solicitação vinculados")
        except Exception as e:
            logger.error(f"Erro ao verificar itens de solicitação: {str(e)}", exc_info=True)
            has_itens = False
        
        if has_itens:
            logger.warning(f"Material ID {id} não pode ser excluído pois está vinculado a solicitações")
            flash('Este material não pode ser excluído pois está vinculado a solicitações!', 'danger')
            return redirect(url_for('material.visualizar', id=material.id))
        
        try:
            nome = material.nome
            logger.info(f"Excluindo material: {nome} (ID: {id})")
            
            # Usar sessão com rollback automático em caso de erro
            db.session.delete(material)
            db.session.commit()
            
            logger.info(f"Material excluído com sucesso: {nome} (ID: {id})")
            flash(f'Material "{nome}" excluído com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            error_msg = str(e)
            logger.error(f"Erro ao excluir material: {error_msg}", exc_info=True)
            flash(f'Erro ao excluir material: {error_msg}', 'danger')
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Erro ao processar exclusão de material: {error_msg}", exc_info=True)
        flash(f'Erro ao excluir material: {error_msg}', 'danger')
    
    return redirect(url_for('material.index'))

@material_bp.route('/importar', methods=['GET'])
@login_required
def importar():
    """
    Página de importação de materiais via arquivo Excel
    """
    # Redirecionar para index, pois agora usamos um modal
    return redirect(url_for('material.index'))

@material_bp.route('/importar/upload', methods=['POST'])
@login_required
def upload_arquivo():
    """
    Recebe upload do arquivo Excel e salva temporariamente para mapeamento
    """
    if 'arquivo' not in request.files:
        flash('Nenhum arquivo enviado', 'danger')
        return redirect(url_for('material.importar'))
    
    arquivo = request.files['arquivo']
    
    if arquivo.filename == '':
        flash('Nenhum arquivo selecionado', 'danger')
        return redirect(url_for('material.importar'))
    
    # Verificar se a extensão é válida
    if not arquivo.filename.endswith('.xlsx'):
        flash('Apenas arquivos Excel (.xlsx) são permitidos', 'danger')
        return redirect(url_for('material.importar'))
    
    # Verificar se a requisição vem do modal ou página normal
    from_modal = request.referrer and 'index' in request.referrer
    
    try:
        # Criar nome único para o arquivo
        nome_arquivo = f"{uuid.uuid4().hex}.xlsx"
        caminho_temp = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_arquivo)
        
        # Salvar o arquivo
        arquivo.save(caminho_temp)
        
        # Ler o arquivo com pandas para verificar se tem conteúdo válido
        df = pd.read_excel(caminho_temp)
        
        if df.empty or len(df.columns) == 0:
            os.remove(caminho_temp)  # Remover arquivo vazio
            flash('O arquivo enviado está vazio ou não contém dados válidos', 'danger')
            if from_modal:
                return redirect(url_for('material.index'))
            return redirect(url_for('material.importar'))
        
        # Se requisição vier do modal, redirecionar para a tela de mapeamento
        # com uma mensagem diferente
        if from_modal:
            flash('Arquivo recebido com sucesso. Por favor, verifique o mapeamento das colunas.', 'success')
            return redirect(url_for('material.selecionar_planilha', arquivo=nome_arquivo))
            
        # Tudo ok, redirecionar para a próxima etapa
        return redirect(url_for('material.selecionar_planilha', arquivo=nome_arquivo))
        
    except Exception as e:
        flash(f'Erro ao processar o arquivo: {str(e)}', 'danger')
        if 'from_modal' in locals() and from_modal:
            return redirect(url_for('material.index'))
        return redirect(url_for('material.importar'))

@material_bp.route('/importar/selecionar-planilha', methods=['GET'])
@login_required
def selecionar_planilha():
    """
    Carrega os dados de uma planilha específica para o mapeamento de colunas
    """
    try:
        # Obter parâmetros da URL
        temp_file = request.args.get('arquivo')
        planilha = request.args.get('planilha')
        
        logger.info(f"Selecionando planilha: {planilha}, arquivo: {temp_file}")
        print(f"DEBUG - Selecionando planilha: {planilha}, arquivo: {temp_file}")
        
        # Construir o caminho completo para o arquivo
        caminho_completo = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_file)
        
        # Verificar se o arquivo existe
        if not temp_file or not os.path.isfile(caminho_completo):
            flash("Arquivo temporário não encontrado. Por favor, faça o upload novamente.", "danger")
            return redirect(url_for('material.importar'))
        
        # Carregar o arquivo Excel com o pandas
        xls = pd.ExcelFile(caminho_completo)
        
        # Verificar se a planilha especificada existe
        planilhas = xls.sheet_names
        if planilha and planilha not in planilhas:
            flash(f"Planilha '{planilha}' não encontrada no arquivo. Planilhas disponíveis: {', '.join(planilhas)}", "danger")
            planilha = planilhas[0]  # Usar a primeira planilha como padrão
        
        # Se nenhuma planilha foi especificada, usar a primeira
        if not planilha:
            planilha = planilhas[0]
        
        # Ler os dados da planilha selecionada
        df = pd.read_excel(caminho_completo, sheet_name=planilha)
        
        # Obter as colunas disponíveis
        colunas = df.columns.tolist()
        
        # Obter os primeiros 5 registros para preview
        preview_data = df.head(5).values.tolist()
        
        # Renderizar o template com as informações
        return render_template('materiais/mapear_colunas.html', 
                              temp_file=caminho_completo,
                              colunas=colunas,
                              planilhas=planilhas,
                              planilha_atual=planilha,
                              preview_data=preview_data)
    
    except Exception as e:
        print(f"DEBUG - Erro ao processar planilha: {str(e)}")
        logger.error(f"Erro ao processar planilha: {str(e)}")
        flash(f"Erro ao processar a planilha: {str(e)}", "danger")
        return redirect(url_for('material.importar'))

@material_bp.route('/importar/confirmar', methods=['POST'])
@login_required
def confirmar_importacao():
    """
    Processa a importação dos materiais após o mapeamento de colunas
    """
    logger.info("Iniciando confirmação de importação de materiais")
    print("DEBUG - Iniciando confirmação de importação")
    
    # Obter os dados do formulário
    temp_file = request.form.get('temp_file')
    planilha = request.form.get('planilha')
    col_id = request.form.get('col_id')
    col_mascara = request.form.get('col_mascara')
    col_ncm = request.form.get('col_ncm')
    col_nome = request.form.get('col_nome')
    col_descricao = request.form.get('col_descricao')
    col_codigo = request.form.get('col_codigo')
    col_codigo_erp = request.form.get('col_codigo_erp')
    col_plano_conta = request.form.get('col_plano_conta')
    col_pc = request.form.get('col_pc')
    col_unidade = request.form.get('col_unidade')
    col_categoria = request.form.get('col_categoria')
    opcao_atualizacao = request.form.get('opcao_atualizacao', 'pular')
    
    print(f"DEBUG - Parâmetros recebidos: arquivo={temp_file}, planilha={planilha}")
    print(f"DEBUG - Colunas mapeadas: nome={col_nome}, descricao={col_descricao}, codigo={col_codigo}, codigo_erp={col_codigo_erp}, plano_conta={col_plano_conta}, pc={col_pc}, unidade={col_unidade}, categoria={col_categoria}, mascara={col_mascara}, ncm={col_ncm}, id={col_id}")
    print(f"DEBUG - Opção de atualização: {opcao_atualizacao}")
    
    # Validar dados obrigatórios
    if not temp_file or not planilha or not col_nome or not col_categoria:
        logger.error("Dados obrigatórios não fornecidos")
        flash('Por favor, preencha todos os campos obrigatórios', 'danger')
        return redirect(url_for('material.importar'))
    
    # Verificar se o caminho é absoluto ou apenas o nome do arquivo
    caminho_arquivo = temp_file
    if not os.path.isabs(temp_file):
        caminho_arquivo = os.path.join(current_app.config['UPLOAD_FOLDER'], os.path.basename(temp_file))
    
    # Verificar se o arquivo existe
    if not os.path.isfile(caminho_arquivo):
        logger.error(f"Arquivo não encontrado: {caminho_arquivo}")
        flash('Arquivo não encontrado. Por favor, faça o upload novamente.', 'danger')
        return redirect(url_for('material.importar'))
    
    # Contadores
    inseridos = 0
    atualizados = 0
    erros = 0
    registros_com_erro = []
    
    try:
        # Iniciar a transação
        db.session.begin_nested()
        
        # Carregar a planilha
        df = pd.read_excel(caminho_arquivo, sheet_name=planilha)
        
        # Validar se as colunas mapeadas existem na planilha
        colunas_planilha = df.columns.tolist()
        for col, nome in [
            (col_id, 'ID'),
            (col_nome, 'Nome'),
            (col_codigo, 'Código'),
            (col_codigo_erp, 'Código ERP'),
            (col_plano_conta, 'Plano de Conta'),
            (col_descricao, 'Descrição'),
            (col_pc, 'PC'),
            (col_unidade, 'Unidade'),
            (col_categoria, 'Categoria'),
            (col_mascara, 'Máscara'),
            (col_ncm, 'NCM')
        ]:
            if col and col not in colunas_planilha:
                logger.error(f"Coluna {nome} ({col}) não encontrada na planilha")
                flash(f"Coluna {nome} ({col}) não encontrada na planilha", 'danger')
                return redirect(url_for('material.importar'))
        
        # Processar cada linha
        for index, row in df.iterrows():
            try:
                # Obter dados da linha
                id = str(row[col_id]).strip() if col_id and not pd.isna(row[col_id]) else ""
                nome = str(row[col_nome]).strip() if not pd.isna(row[col_nome]) else ""
                codigo = str(row[col_codigo]).strip() if col_codigo and not pd.isna(row[col_codigo]) else ""
                codigo_erp = str(row[col_codigo_erp]).strip() if col_codigo_erp and not pd.isna(row[col_codigo_erp]) else ""
                plano_conta = str(row[col_plano_conta]).strip() if col_plano_conta and not pd.isna(row[col_plano_conta]) else ""
                descricao = str(row[col_descricao]).strip() if col_descricao and not pd.isna(row[col_descricao]) else ""
                unidade = str(row[col_unidade]).strip() if col_unidade and not pd.isna(row[col_unidade]) else ""
                categoria = str(row[col_categoria]).strip() if not pd.isna(row[col_categoria]) else ""
                mascara = str(row[col_mascara]).strip() if col_mascara and not pd.isna(row[col_mascara]) else ""
                ncm = str(row[col_ncm]).strip() if col_ncm and not pd.isna(row[col_ncm]) else ""
                # Validar dados obrigatórios
                if not nome or not categoria:
                    erros += 1
                    erro_msg = f"Linha {index+2}: Nome e Categoria são obrigatórios"
                    registros_com_erro.append(erro_msg)
                    logger.warning(erro_msg)
                    print(f"DEBUG - {erro_msg}")
                    continue
                
                # Verificar se o material já existe pelo código ou nome
                material_existente = None
                if id:
                    material_existente = Material.query.filter_by(id=id).first()
                
                if not material_existente and nome:
                    material_existente = Material.query.filter_by(nome=nome).first()
                
                # Decidir se vamos atualizar, ignorar ou criar um novo
                if material_existente:
                    if opcao_atualizacao == 'pular':
                        # Pular material existente
                        continue
                    elif opcao_atualizacao == 'atualizar':
                        # Atualizar material existente
                        material_existente.nome = nome
                        material_existente.codigo = codigo
                        if mascara:
                            material_existente.mascara = mascara
                        if ncm:
                            material_existente.ncm = ncm
                        if codigo_erp:
                            material_existente.codigo_erp = codigo_erp
                        if plano_conta:
                            material_existente.plano_conta = plano_conta
                        if descricao:
                            material_existente.descricao = descricao
                        if unidade:
                            material_existente.unidade = unidade
                        if categoria:
                            material_existente.categoria = categoria
                        
                        db.session.add(material_existente)
                        atualizados += 1
                else:
                    # Criar novo material
                    novo_material = Material(
                        nome=nome,
                        codigo=codigo if codigo else None,
                        codigo_erp=codigo_erp if codigo_erp else None,
                        plano_conta=plano_conta if plano_conta else None,
                        descricao=descricao if descricao else None,
                        unidade=unidade if unidade else None,
                        categoria=categoria,
                        mascara=mascara if mascara else None,
                        ncm=ncm if ncm else None
                    )
                    db.session.add(novo_material)
                    inseridos += 1
                
            except Exception as e:
                erros += 1
                erro_msg = f"Erro na linha {index+2}: {str(e)}"
                registros_com_erro.append(erro_msg)
                logger.error(erro_msg, exc_info=True)
                print(f"DEBUG - {erro_msg}")
        
        # Commit da transação se não houver erros
        if erros == 0 or inseridos > 0 or atualizados > 0:
            db.session.commit()
            logger.info(f"Importação concluída: {inseridos} inseridos, {atualizados} atualizados, {erros} erros")
            print(f"DEBUG - Commit realizado: {inseridos} inseridos, {atualizados} atualizados, {erros} erros")
            flash(f'Importação concluída com sucesso! {inseridos} materiais inseridos, {atualizados} atualizados.', 'success')
        else:
            db.session.rollback()
            logger.warning("Importação cancelada: nenhum registro processado com sucesso")
            print("DEBUG - Rollback: nenhum registro processado com sucesso")
            flash('Nenhum material foi importado devido a erros.', 'warning')
        
        # Se houver erros, mostrar detalhes
        if erros > 0:
            flash(f'{erros} registros não foram importados devido a erros.', 'warning')
            # Limitar a quantidade de erros mostrados para não sobrecarregar a tela
            for erro in registros_com_erro[:10]:
                flash(erro, 'warning')
            if len(registros_com_erro) > 10:
                flash(f'... e mais {len(registros_com_erro) - 10} erros.', 'warning')
        
        # Limpar o arquivo temporário após o processamento
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
            logger.info(f"Arquivo temporário removido: {caminho_arquivo}")
            print(f"DEBUG - Arquivo temporário removido: {caminho_arquivo}")
        
        # Redirecionar para a lista de materiais
        return redirect(url_for('material.index'))
        
    except Exception as e:
        # Em caso de erro, fazer rollback e informar o usuário
        db.session.rollback()
        logger.error(f"Erro durante a importação: {str(e)}", exc_info=True)
        print(f"DEBUG - Erro durante a importação: {str(e)}")
        flash(f'Erro durante a importação: {str(e)}', 'danger')
        
        # Limpar o arquivo temporário em caso de erro
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
            logger.info(f"Arquivo temporário removido após erro: {caminho_arquivo}")
            print(f"DEBUG - Arquivo temporário removido após erro: {caminho_arquivo}")
        
        return redirect(url_for('material.importar'))

@material_bp.route('/download-modelo')
@login_required
def download_modelo():
    """
    Gera um arquivo Excel modelo para importação de materiais
    """
    try:
        # Criar um writer do Excel com Pandas
        temp_file = os.path.join(tempfile.gettempdir(), 'modelo_importacao_materiais.xlsx')
        writer = pd.ExcelWriter(temp_file, engine='openpyxl')
        
        # Criar DataFrame com as colunas do modelo
        df_principal = pd.DataFrame(columns=[
            'ID',
            'Nome',
            'Categoria',
            'Código ERP',
            'Plano de Conta',
            'Unidade',
            'Máscara',
            'NCM'
        ])
        
        # Adicionar algumas linhas de exemplo na planilha principal
        df_principal.loc[0] = [
            '1',
            'Cimento Portland CP-II',
            'Matéria-prima',
            'ERP001',
            'Material Direto',
            'sc',
            '1234567890'
        ]
        df_principal.loc[1] = [
            '2',
            'Areia Média',
            'Matéria-prima',
            'ERP002',
            'Material Direto',
            'm³',
            '1234567890'
        ]
        
        # Criar uma segunda planilha para instruções
        df_instrucoes = pd.DataFrame(columns=['Campo', 'Descrição', 'Obrigatório'])
        
        # Adicionar informações de cada campo
        df_instrucoes.loc[0] = ['Nome', 'Nome do material', 'Sim']
        df_instrucoes.loc[1] = ['Categoria', 'Categoria do material (ex: Matéria-prima, Ferramenta, etc)', 'Sim']
        df_instrucoes.loc[2] = ['Código ERP', 'Código do material no sistema ERP', 'Não']
        df_instrucoes.loc[3] = ['Plano de Conta', 'Plano de contas contábil', 'Não']
        df_instrucoes.loc[4] = ['Unidade', 'Unidade de medida (ex: kg, m, un)', 'Não']
        
        # Salvar os DataFrames em diferentes planilhas
        df_principal.to_excel(writer, sheet_name='Materiais', index=False)
        df_instrucoes.to_excel(writer, sheet_name='Instruções', index=False)
        
        # Salvar e fechar o arquivo
        writer.close()
        
        return send_file(
            temp_file,
            as_attachment=True,
            download_name='modelo_importacao_materiais.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        logger.error(f"Erro ao gerar arquivo modelo: {str(e)}", exc_info=True)
        flash(f'Erro ao gerar arquivo modelo: {str(e)}', 'danger')
        return redirect(url_for('material.importar'))

@material_bp.route('/listar-json')
@login_required
def listar_json():
    """
    Retorna uma lista de materiais em formato JSON para ser usada em selects
    """
    materiais = Material.query.filter_by(ativo=True).all()
    resultado = []
    
    for material in materiais:
        resultado.append({
            'id': material.id,
            'codigo': material.codigo or '',
            'nome': material.nome or '',
            'unidade': material.unidade_obj.nome or ''
        })
    
    return jsonify(resultado)

@material_bp.route('/api/materiais')
@login_required
def api_materiais():
    """
    API para retornar materiais em formato JSON
    Suporta filtragem por plano de conta
    """
    query = Material.query

    # Filtro por plano de conta
    plano_conta = request.args.get('plano_conta')
    if plano_conta:
        query = query.filter_by(plano_conta=plano_conta)
    
    # Filtro por código ou nome
    search = request.args.get('q')
    if search:
        query = query.filter(
            db.or_(
                Material.codigo.like(f'%{search}%'),
                Material.nome.like(f'%{search}%')
            )
        )
    
    # Ordenação
    sort_by = request.args.get('sort_by', 'codigo')
    sort_dir = request.args.get('sort_dir', 'asc')
    
    if sort_by in ['codigo', 'nome', 'categoria', 'plano_conta']:
        if sort_dir == 'desc':
            query = query.order_by(db.desc(getattr(Material, sort_by)))
        else:
            query = query.order_by(getattr(Material, sort_by))
    
    # Limitar resultados
    limit = request.args.get('limit', 100, type=int)
    query = query.limit(limit)
    
    materiais = query.all()
    
    # Converter para dicionário
    result = []
    for m in materiais:
        result.append({
            'id': m.id,
            'codigo': m.codigo,
            'nome': m.nome,
            'descricao': m.descricao,
            'categoria': m.categoria,
            'plano_conta': m.plano_conta,
            'mascara': m.mascara,
            'unidade': m.unidade,
            'criado_em': m.criado_em.strftime('%d/%m/%Y %H:%M') if m.criado_em else None
        })
    
    return jsonify(result)

@material_bp.route('/editar-material-ajax/<int:id>', methods=['GET', 'POST'])
def editar_material_ajax(id):
    """
    Edita um material via AJAX (usado pelo modal de edição)
    """
    try:
        material = Material.query.get_or_404(id)
        logger.info(f"Acessando edição do material ID {id} via AJAX")
        
        if request.method == 'POST':
            # Verificar CSRF Token
            csrf_token = request.form.get('csrf_token')
            if not csrf_token:
                return jsonify({'success': False, 'message': 'CSRF token não fornecido'}), 400
            
            # Usar o FlaskForm para validar o token CSRF ou implementar sua própria validação
            # Esta é uma implementação simplificada
            
            data = request.form
            codigo = data.get('edit_codigo', '')
            nome = data.get('edit_nome', '')
            descricao = data.get('edit_descricao', '')
            categoria = data.get('edit_categoria', '')
            plano_conta = data.get('edit_plano_conta', '')
            codigo_erp = data.get('edit_codigo_erp', '')
            unidade = data.get('edit_unidade', '')
            mascara = data.get('edit_mascara', '')
            formula_calculo = data.get('edit_formula_calculo', '').strip()
            print(f'form_data: {data}')
            
            # Verificar o campo alternativo de unidade
           
            
            logger.info(f"Valor final da unidade para atualização: {unidade}")
            
            # Validar campos obrigatórios
            if not nome or not categoria:
                return jsonify({
                    'success': False,
                    'message': 'Nome e categoria são campos obrigatórios!'
                })
            
            # Verificar duplicidade de código (se for alterado)
            if codigo and codigo != material.codigo:
                existente = Material.query.filter_by(codigo=codigo).first()
                if existente and existente.id != material.id:
                    return jsonify({
                        'success': False,
                        'message': f'Já existe um material com o código {codigo}!'
                    })
            
            try:
                # Atualizar os campos
                material.codigo = codigo
                material.nome = nome
                material.descricao = descricao
                material.categoria = categoria
                material.plano_conta = plano_conta
                material.codigo_erp = codigo_erp
                material.unidade_id = unidade
                material.mascara = mascara
                material.formula_calculo = formula_calculo if formula_calculo else None
               
                    
                # Atualizar data e usuário
                from flask_login import current_user
                material.data_atualizacao = datetime.now()
                if hasattr(current_user, 'id'):
                    material.usuario_id = current_user.id
                
                # Salvar no banco
                db.session.commit()
                logger.info(f"Material ID {id} atualizado com sucesso")
                
                return jsonify({
                    'success': True,
                    'message': 'Material atualizado com sucesso!',
                    'redirect': url_for('material.index')
                })
            except Exception as db_error:
                db.session.rollback()
                logger.error(f"Erro ao salvar material no banco: {str(db_error)}", exc_info=True)
                return jsonify({
                    'success': False,
                    'message': f'Erro ao salvar material: {str(db_error)}'
                })
            
        # Para requisições GET, retornar os dados do material
        return jsonify({
            'id': material.id,
            'codigo': material.codigo or '',
            'nome': material.nome,
            'descricao': material.descricao or '',
            'categoria': material.categoria,
            'plano_conta': material.plano_conta or '',
            'codigo_erp': material.codigo_erp or '',
            'unidade': material.unidade_obj.nome or '',
            'mascara': material.mascara or '',
            'formula_calculo': material.formula_calculo or ''
        })
            
    except Exception as e:
        logger.error(f"Erro na edição AJAX: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Erro ao processar a solicitação: {str(e)}'
        }), 500

@material_bp.route('/obter/<int:id>', methods=['GET'])
@login_required
def obter_material(id):
    """
    Retorna os detalhes de um material em formato JSON
    """
    try:
        material = Material.query.get(id)
        if not material:
            return jsonify({
                'success': False,
                'error': 'Material não encontrado'
            })
        
        # Retornar apenas JSON, sem template HTML
        response = jsonify({
            'success': True,
            'material': {
                'id': material.id,
                'codigo': material.codigo or '',
                'codigo_erp': material.codigo_erp or '',
                'nome': material.nome or '',
                'descricao': material.descricao or '',
                'categoria': material.categoria or '',
                'plano_conta': material.plano_conta or '',
                'unidade': material.unidade or '',
                'mascara': material.mascara or '',
                'formula_calculo': material.formula_calculo or ''
            }
        })
        response.headers['Content-Type'] = 'application/json'
        return response
    except Exception as e:
        logger.error(f"Erro ao obter material ID {id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erro ao obter dados do material: {str(e)}'
        })

@material_bp.route('/obter-ajax/<int:id>', methods=['GET'])
@login_required
def obter_material_ajax(id):
    """
    Retorna os detalhes de um material em formato JSON para chamadas AJAX
    """
    try:
        material = Material.query.get(id)
        if not material:
            response = jsonify({
                'success': False,
                'error': 'Material não encontrado'
            })
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        
        # Retornar dados em formato JSON
        response = jsonify({
            'success': True,
            'material': {
                'id': material.id,
                'codigo': material.codigo or '',
                'codigo_erp': material.codigo_erp or '',
                'nome': material.nome or '',
                'descricao': material.descricao or '',
                'categoria': material.categoria or '',
                'plano_conta': material.plano_conta or '',
                'unidade': material.unidade or '',
                'mascara': material.mascara or '',
                'formula_calculo': material.formula_calculo or ''
            }
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    except Exception as e:
        logger.error(f"Erro ao obter material AJAX ID {id}: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Erro ao obter dados do material: {str(e)}'
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response 

@material_bp.route('/diagnostico/<int:id>', methods=['GET'])
def diagnostico_material(id):
    """
    Rota para diagnóstico de problemas com a API de materiais
    """
    try:
        material = Material.query.get(id)
        if not material:
            resposta = {
                'status': 'erro',
                'mensagem': f'Material com ID {id} não encontrado'
            }
        else:
            resposta = {
                'status': 'sucesso',
                'material_id': material.id,
                'material_nome': material.nome
            }
        
        # Enviar como texto simples para evitar problemas com JSON
        return f"""
        Diagnóstico do Material:
        
        {resposta}
        
        Cabeçalhos da requisição:
        {dict(request.headers)}
        
        URL da requisição:
        {request.url}
        
        Método da requisição:
        {request.method}
        
        Autenticação:
        {current_user.is_authenticated if current_user else False}
        """
    except Exception as e:
        return f"Erro no diagnóstico: {str(e)}" 


# Rota para exportar materiais para Excel
@material_bp.route('/exportar-excel')
@login_required
def exportar_excel():
    """
    Exporta a lista completa de materiais para um arquivo Excel.
    """
    try:
        # Buscar todos os materiais (sem paginação para exportação completa)
        materiais = Material.query.all()
        ncm_unico = None
        # Preparar os dados para o DataFrame
        dados_exportacao = []
        for mat in materiais:
            itens = NotaFiscalItem.query.filter_by(material_id=mat.id).all()
            
            # Verificar se todos os NCMs são iguais e agrupar por NCM
            if len(itens) == 0:
                ncm_iguais = 'N/A'
                ncms_validos = set()
                itens_por_ncm_json = '[]'
            else:
                # Coletar todos os NCMs únicos (filtrando valores None e strings vazias)
                ncms_unicos = set(item.ncm.strip() if item.ncm and item.ncm.strip() else None for item in itens)
                # Remover None do set se houver NCMs válidos
                ncms_validos = {ncm for ncm in ncms_unicos if ncm is not None}
                if len(ncms_validos) == 1:
                    ncm_unico = list(ncms_validos)[0]
                else:
                    ncm_unico = None
                # Se todos são None/vazios ou se há apenas um NCM único válido, são iguais
                ncm_iguais = 'Sim' if len(ncms_validos) <= 1 else 'Não'
                
                # Agrupar itens por NCM e criar JSON com informações da nota fiscal
                itens_por_ncm = {}
                for item in itens:
                    ncm_item = item.ncm.strip() if item.ncm and item.ncm.strip() else None
                    if ncm_item:
                        if ncm_item not in itens_por_ncm:
                            itens_por_ncm[ncm_item] = []
                        
                        # Coletar informações da nota fiscal
                        if item.nota_fiscal:
                            itens_por_ncm[ncm_item].append({
                                'numero_nf': item.nota_fiscal.numero_nf,
                                'fornecedor': item.nota_fiscal.nome_emitente,
                                'nome_item': item.descricao
                            })
                        else:
                            # Caso não tenha nota fiscal vinculada
                            itens_por_ncm[ncm_item].append({
                                'numero_nf': None,
                                'fornecedor': None,
                                'nome_item': item.descricao
                            })
                
                # Converter para JSON string
                itens_por_ncm_json = json.dumps(itens_por_ncm, ensure_ascii=False)
            
            dados_exportacao.append({
                'ID': mat.id,
                'Máscara': mat.mascara,
                'Código SOX': mat.codigo,
                'Nome': mat.nome,
                'Descrição': mat.descricao,
                'Categoria': mat.categoria,
                'Unidade': mat.unidade_obj.nome,
                'NCM': mat.ncm,
                'Plano de Conta': mat.plano_conta,
                'Código Alterdata': mat.codigo_erp,
                'Data Criação': mat.data_criacao.strftime('%Y-%m-%d %H:%M:%S') if mat.data_criacao else '',
                'Quantidade Importada': len(itens),
                'ncms' : [item.ncm+',' if i < len(itens)-1 else item.ncm for i,item in enumerate(itens)],
                'ncn iguais' : ncm_iguais,
                'ncm unicos' : len(ncms_validos),
                'ncms unico' : ncm_unico,
                'itens_por_ncm' : itens_por_ncm_json
                #'Data Atualização': mat.data_atualizacao.strftime('%Y-%m-%d %H:%M:%S') if mat.data_atualizacao else ''
                # Adicione mais campos se necessário
            })

        # Criar DataFrame com pandas
        df = pd.DataFrame(dados_exportacao)

        # Criar um arquivo Excel na memória
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Materiais')
        output.seek(0)

        # Nome do arquivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"materiais_{timestamp}.xlsx"

        # Enviar o arquivo para download
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Erro ao exportar materiais para Excel: {e}")
        flash('Ocorreu um erro ao gerar o arquivo Excel.', 'danger')
        return redirect(url_for('material.index'))

@material_bp.route('/exportar-mega')
@login_required
def exportar_mega():
    """
    Exporta materiais para o Mega, usando o template CADASTRO DE INSUMOS.xlsx
    e adicionando dados do banco a partir da linha 7.
    """
    try:
        # Caminho para o arquivo template (na raiz do projeto)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        template_path = os.path.join(base_path, 'CADASTRO DE INSUMOS.xlsx')
        
        if not os.path.exists(template_path):
            logger.error(f"Template não encontrado: {template_path}")
            flash('Arquivo template não encontrado. Entre em contato com o administrador.', 'danger')
            return redirect(url_for('material.index'))
        
        # Carregar o workbook template
        wb = openpyxl.load_workbook(template_path)
        ws = wb.active
        
        # Buscar todos os materiais do banco de dados
        materiais = Material.query.filter_by(ativo=True).order_by(Material.nome).all()
        
        # Linha inicial para inserção de dados (linha 7)
        linha_inicial = 7
        linha_atual = linha_inicial
        
        # Mapear campos do Material para as colunas do Excel
        # Coluna 1: GRU_IN_CODIGO - Código do grupo (usar código do material ou ID)
        # Coluna 2: PRO_ST_DESCRICAO - Descrição do item (nome do material)
        # Coluna 3: PRO_ST_DEFITEM - Definição do item (categoria ou padrão)
        # Coluna 4: PRO_BO_GENERICO - Item genérico (S/N, padrão 'N')
        # Coluna 5: UNIP_ST_UNIDADE - Unidade de processo (unidade do material)
        # Coluna 6: PRO_CH_DEFFISCALITEM - Definição fiscal (NCM)
        # Coluna 7: PRO_ST_ORIGEM - Origem (padrão 'Comprado')
        # Coluna 8: UNI_ST_UNIDADE - Unidade de estoque (unidade do material)
        # Coluna 9: PRO_IN_GERASOLICITACAO - Gera solicitação (EM/NC, padrão 'EM')
        # Coluna 10: PRO_IN_QTDECOMPRAR - Qtde a comprar (EM/NC, padrão 'NC')
        # Coluna 11: PRO_ST_ALTERNATIVO - Código alternativo (código ERP)
        # Coluna 12: PRO_ST_DESCRICAOPDV - Descrição abreviada (pode ser vazio)
        # Coluna 13: PRO_ST_DESCRICAONFE - Descrição NF-e (nome ou descrição)
        # Coluna 14: PRO_ST_NARRATIVA - Narrativa (descrição do material)
        # Coluna 15: PRO_BO_TOTALIZADOC - Totaliza documentos (S/N, padrão 'S')
        # Coluna 16: PRO_RE_PELIQUIDO - Peso líquido (vazio)
        # Coluna 17: PRO_RE_PEBRUTO - Peso bruto (vazio)
        # Coluna 18: PRO_ST_UTILIZACAO - Utilização (vazio)
        # Coluna 19: PRO_CH_REALIZADOORC - Controle de orçamento (vazio)
        
        for material in materiais:
            # Coluna 1: Código do grupo (usar código ou ID)
            codigo_grupo = material.mascara if material.mascara else ''
            ws.cell(row=linha_atual, column=1, value=codigo_grupo)
            
            # Coluna 2: Descrição do item (nome)
            ws.cell(row=linha_atual, column=2, value=material.nome or '')
            
            # Coluna 3: Definição do item (categoria ou padrão)
            # Se não houver categoria específica, usar um padrão
            def_item = 'MT'
            ws.cell(row=linha_atual, column=3, value=def_item)
            
            # Coluna 4: Item genérico (padrão 'N')
            ws.cell(row=linha_atual, column=4, value='N')
            
            # Coluna 5: Unidade de processo
            unidade = material.unidade_obj.nome if material.unidade_obj else 'UN'
            ws.cell(row=linha_atual, column=5, value=unidade)
            
            # Coluna 6: Definição fiscal (NCM)
            def_fiscal = "07" if (material.categoria == 'EPI' or 
                                  material.categoria == 'Insumo' or
                                material.categoria == 'EPP') else "08"
            ws.cell(row=linha_atual, column=6, value=def_fiscal)
            
            # Coluna 7: Origem (padrão 'Comprado')
            ws.cell(row=linha_atual, column=7, value='Comprado')
            
            # Coluna 8: Unidade de estoque
            ws.cell(row=linha_atual, column=8, value=unidade)
            
            # Coluna 9: Gera solicitação (padrão 'EM')
            ws.cell(row=linha_atual, column=9, value='EM')
            
            # Coluna 10: Qtde a comprar (padrão 'NC')
            ws.cell(row=linha_atual, column=10, value='NC')
            
            # Coluna 11: Código alternativo (código ERP)
            codigo_alternativo = material.id
            if codigo_alternativo:
                ws.cell(row=linha_atual, column=11, value=codigo_alternativo)
            
            # Coluna 12: Descrição abreviada (vazio por padrão)
            # ws.cell(row=linha_atual, column=12, value=None)  # Não precisa definir se vazio
            
            # Coluna 13: Descrição NF-e (usar nome ou descrição)
            ws.cell(row=linha_atual, column=13, value="")
            
            # Coluna 14: Narrativa (descrição do material)
            if material.descricao:
                ws.cell(row=linha_atual, column=14, value=material.descricao)
            
            # Coluna 15: Totaliza documentos (padrão 'S')
            ws.cell(row=linha_atual, column=15, value='S')
            
            # Colunas 16-19 ficam vazias por padrão
            
            linha_atual += 1
        
        # Criar arquivo em memória
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        # Nome do arquivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"CADASTRO_DE_INSUMOS_{timestamp}.xlsx"
        
        # Enviar o arquivo para download
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Erro ao exportar materiais para Mega: {e}", exc_info=True)
        flash(f'Ocorreu um erro ao gerar o arquivo Excel para o Mega: {str(e)}', 'danger')
        return redirect(url_for('material.index')) 