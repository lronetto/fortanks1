from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import logging
import requests
import base64
import xml.etree.ElementTree as ET
import json
from decimal import Decimal
from sqlalchemy import func, or_, case, distinct # Adicionar distinct
from sqlalchemy.sql import func as sqlfunc # Alias para func
from flask import make_response
from models.database import db
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.material import Material
from models.centro_custo import CentroCusto
from models.unidade import Unidade
from models.conversao_unidade import ConversaoUnidade
from forms.nota_fiscal_forms import NotaFiscalImportForm # Import para formulário do modal
from scripts.robo_email_nf import processar_emails
from utils.relatorio_financeiro import gerar_relatorio_financeiro
from scripts.verificar_cancelamento import verificar
from models.arquivei import Arquivei
from scripts.processar_email import processar_emails
from models.conversao_unidade import comparar_unidades
from models.upload import Upload
from models.nota_fiscal import CNPJS
from models.dados_analiticos import DadoAnalitico
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
# Configurar o logger para o módulo
logger = logging.getLogger(__name__)

nota_fiscal_bp = Blueprint('nota_fiscal', __name__)

# Middleware para verificar se o usuário tem permissão
@nota_fiscal_bp.before_request
@login_required
def verificar_permissao():
    pass
    # if not current_user.is_gerente_ou_superior:
    #     flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
    #     return redirect(url_for('dashboard.index'))

@nota_fiscal_bp.route('/teste1')
@login_required
def teste1():
    processar_emails()
    #processar_protocolos()
    return redirect(url_for('nota_fiscal.index'))

@nota_fiscal_bp.route('/teste')
@login_required
def teste():
    print('teste')
    notas = Arquivei(data_inicial='2024-06-01', data_final='2025-05-31')
    #notas = Arquivei(send=True)
    tamanho = len(notas.xml_datas)
    print('tamanho: ',tamanho)
    if tamanho > 0:
        i=0
        for xml_data in notas.xml_datas:
            nf = NotaFiscal(xml_data=xml_data)
            print(f'id: {nf.id} numero_nf: {nf.numero_nf} {i}/{tamanho} ')
            i+=1
           
    return redirect(url_for('nota_fiscal.index'))
@nota_fiscal_bp.route('/')
@login_required
def index():
    """
    Lista notas fiscais com paginação e filtros.
    """
    # Parâmetros de Paginação
    page = request.args.get('page', 1, type=int)
    per_page = 100 # Pegar da config ou usar 20
    
    # Obter parâmetros de filtro
    busca = request.args.get('busca', '')
    item_nome = request.args.get('item_nome', '')
    status_importacao = request.args.get('status_importacao', '')
    cnpj_emitente = request.args.get('cnpj_emitente', '')
    data_emissao_inicio = request.args.get('data_emissao_inicio', '')
    data_emissao_fim = request.args.get('data_emissao_fim', '')
    
    # Instanciar formulário de importação para o modal
    import_form = NotaFiscalImportForm()
    
    # Construir query base
    query = NotaFiscal.query
    
    # Aplicar filtros
    if busca:
        busca_like = f'%{busca}%'
        query = query.filter(
            or_(
                NotaFiscal.numero_nf.ilike(busca_like),
                NotaFiscal.nome_emitente.ilike(busca_like),
                NotaFiscal.chave_acesso.ilike(busca_like)
            )
        )
    
    # Aplicar filtro de nome de item (Código ou Descrição do Item)
    if item_nome:
        query = query.join(NotaFiscalItem).filter(
            NotaFiscalItem.descricao.ilike(f'%{item_nome}%')
        )
    
    # Aplicar filtro de status de importação (Simplificado para paginação)
    if status_importacao == 'pendentes':
        # Notas sem NENHUM item importado
        query = query.filter(~NotaFiscal.itens.any(NotaFiscalItem.importado_estoque == True))
        flash("Filtrando por notas pendentes (sem itens importados). Filtros 'Importadas' e 'Parciais' estão desativados com paginação.", "info")
    elif status_importacao == 'importadas' or status_importacao == 'parciais':
        # Avisar que estes filtros complexos estão desativados por enquanto
        flash(f"Filtro por status '{status_importacao}' não está otimizado para paginação e foi desativado. Mostrando todos os status.", "warning")
        status_importacao = '' # Resetar para não quebrar a lógica do template
    
    # Filtro por data de emissão
    data_emissao_inicio = request.args.get('data_emissao_inicio', '')
    data_emissao_fim = request.args.get('data_emissao_fim', '')
    if cnpj_emitente:
        if cnpj_emitente == 'proprio':
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS))
        elif cnpj_emitente == 'terceiros':
            query = query.filter(~NotaFiscal.cnpj_emitente.in_(CNPJS))
    if data_emissao_inicio:
        try:
            data_inicio = datetime.strptime(data_emissao_inicio, '%Y-%m-%d')
            query = query.filter(NotaFiscal.data_emissao >= data_inicio)
        except Exception:
            flash('Data de início inválida.', 'warning')
    if data_emissao_fim:
        try:
            data_fim = datetime.strptime(data_emissao_fim, '%Y-%m-%d')
            query = query.filter(NotaFiscal.data_emissao <= data_fim)
        except Exception:
            flash('Data final inválida.', 'warning')
    
    # Ordenar antes de paginar
    query = query.order_by(NotaFiscal.data_emissao.desc())
    
    # Executar a paginação
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    notas_fiscais_pagina = pagination.items # Itens para a página atual
    notas_fiscais_pagina_upload = []
    for nota in notas_fiscais_pagina:
        nota.upload = None
        nota.pago = False
        dadosAnaliticos = DadoAnalitico.query.filter(DadoAnalitico.data_pagamento >= nota.data_emissao,\
                                                       DadoAnalitico.documento.ilike(f'%{nota.numero_nf}%'),\
                                                       DadoAnalitico.valor == nota.valor_total).first()
        if dadosAnaliticos:
            nota.pago = True
        if Upload.query.filter_by(pai_id=nota.id, pai='NotaFiscal').first():
            nota.upload = Upload.query.filter_by(pai_id=nota.id, pai='NotaFiscal').first()
        notas_fiscais_pagina_upload.append(nota)
        
    
    return render_template('notas_fiscais/index.html', 
                          pagination=pagination, # Passar objeto de paginação
                          notas_fiscais=notas_fiscais_pagina_upload, # Manter para compatibilidade ou remover e usar pagination.items no template
                          status_importacao=status_importacao,
                          busca=busca,
                          item_nome=item_nome,
                          data_emissao_inicio=data_emissao_inicio,
                          data_emissao_fim=data_emissao_fim,
                          import_form=import_form) # Passar formulário do modal

@nota_fiscal_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cadastra uma nova nota fiscal
    """
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            numero_nf = request.form.get('numero_nf')
            chave_acesso = request.form.get('chave_acesso')
            data_emissao = request.form.get('data_emissao')
            valor_total = request.form.get('valor_total')
            cnpj_emitente = request.form.get('cnpj_emitente')
            nome_emitente = request.form.get('nome_emitente')
            cnpj_destinatario = request.form.get('cnpj_destinatario')
            nome_destinatario = request.form.get('nome_destinatario')
            status_processamento = request.form.get('status_processamento')
            xml_data = request.form.get('xml_data')
            
            # Validar campos obrigatórios
            if not numero_nf or not chave_acesso or not data_emissao or not valor_total:
                flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
                return redirect(url_for('nota_fiscal.novo'))
            
            # Conversão de tipos
            data_emissao = datetime.strptime(data_emissao, '%Y-%m-%d')
            valor_total = float(valor_total)
            
            # Criar nova nota fiscal
            nota_fiscal = NotaFiscal(
                numero_nf=numero_nf,
                chave_acesso=chave_acesso,
                data_emissao=data_emissao,
                valor_total=valor_total,
                cnpj_emitente=cnpj_emitente,
                nome_emitente=nome_emitente,
                cnpj_destinatario=cnpj_destinatario,
                nome_destinatario=nome_destinatario,
                status_processamento=status_processamento,
                xml_data=xml_data
            )
            
            # Salvar no banco
            nota_fiscal.save()
            
            # Após salvar, aplicar vinculação automática para eventuais itens
            vincular_automaticamente_materiais_nota_fiscal(nota_fiscal.id)
            
            flash('Nota fiscal cadastrada com sucesso!', 'success')
            return redirect(url_for('nota_fiscal.index'))
        
        except Exception as e:
            flash(f'Erro ao cadastrar nota fiscal: {str(e)}', 'danger')
            logger.error(f'Erro ao cadastrar nota fiscal: {str(e)}')
    
    return render_template('notas_fiscais/novo.html')

@nota_fiscal_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita uma nota fiscal existente
    """
    # Busca a nota fiscal pelo ID
    nota_fiscal = NotaFiscal.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            nota_fiscal.numero_nf = request.form.get('numero_nf')
            nota_fiscal.chave_acesso = request.form.get('chave_acesso')
            nota_fiscal.data_emissao = datetime.strptime(request.form.get('data_emissao'), '%Y-%m-%d')
            nota_fiscal.valor_total = request.form.get('valor_total')
            nota_fiscal.cnpj_emitente = request.form.get('cnpj_emitente')
            nota_fiscal.nome_emitente = request.form.get('nome_emitente')
            nota_fiscal.cnpj_destinatario = request.form.get('cnpj_destinatario')
            nota_fiscal.nome_destinatario = request.form.get('nome_destinatario')
            nota_fiscal.xml_data = request.form.get('xml_data')
            nota_fiscal.status_processamento = request.form.get('status_processamento')
            
            # Validar campos obrigatórios
            if not nota_fiscal.numero_nf or not nota_fiscal.chave_acesso or not nota_fiscal.data_emissao or not nota_fiscal.valor_total:
                flash('Todos os campos marcados com * são obrigatórios!', 'danger')
                return render_template('notas_fiscais/editar.html', nota_fiscal=nota_fiscal)
            
            # Verificar se a chave de acesso já existe em outra nota fiscal
            existente = NotaFiscal.query.filter_by(chave_acesso=nota_fiscal.chave_acesso).first()
            if existente and existente.id != id:
                flash(f'Já existe uma nota fiscal com a chave de acesso {nota_fiscal.chave_acesso}!', 'danger')
                return render_template('notas_fiscais/editar.html', nota_fiscal=nota_fiscal)
            
            # Atualizar data de atualização
            nota_fiscal.data_atualizacao = datetime.now()
            
            # Salvar alterações
            nota_fiscal.save()
            
            flash('Nota fiscal atualizada com sucesso!', 'success')
            return redirect(url_for('nota_fiscal.index'))
        
        except Exception as e:
            flash(f'Erro ao atualizar nota fiscal: {str(e)}', 'danger')
            logger.error(f'Erro ao atualizar nota fiscal: {str(e)}')
    
    return render_template('notas_fiscais/editar.html', nota_fiscal=nota_fiscal)

@nota_fiscal_bp.route('/visualizar/<int:id>')
@login_required
def visualizar(id):
    """
    Visualiza detalhes de uma nota fiscal em formato HTML
    """
    nota_fiscal = NotaFiscal.query.get_or_404(id)
    materiais = Material.query.order_by(Material.codigo).all()
    centros_custo = CentroCusto.query.order_by(CentroCusto.codigo).all()
    
    return render_template(
        'notas_fiscais/visualizar.html', 
        nota_fiscal=nota_fiscal, 
        materiais=materiais,
        centros_custo=centros_custo,
        pode_editar=current_user.is_gerente_ou_superior
    )

@nota_fiscal_bp.route('/api/visualizar/<int:id>')
@login_required
def api_visualizar(id):
    """
    Retorna os detalhes de uma nota fiscal em formato JSON
    """
    try:
        # Log para debug
        logger.info(f"API: Visualizando nota fiscal {id}")
        
        # Buscar a nota fiscal
        nota_fiscal = NotaFiscal.query.get_or_404(id)
        
        # Verificar se a nota fiscal foi carregada corretamente
        if not nota_fiscal:
            logger.error(f"Nota fiscal {id} não encontrada")
            return jsonify({"error": "Nota fiscal não encontrada"}), 404
        
        # Obter itens da nota fiscal
        itens = []
        for item in nota_fiscal.itens:
            itens.append({
                'id': item.id,
                'codigo': item.codigo,
                'descricao': item.descricao,
                'quantidade': float(item.quantidade),
                'valor_unitario': float(item.valor_unitario),
                'valor_total': float(item.valor_total),
                'ncm': item.ncm,
                'cfop': item.cfop,
                'unidade': item.unidade
            })
        
        # Retorna dados em formato JSON
        data = {
            'id': nota_fiscal.id,
            'numero_nf': nota_fiscal.numero_nf,
            'chave_acesso': nota_fiscal.chave_acesso,
            'data_emissao': nota_fiscal.data_emissao.strftime('%d/%m/%Y'),
            'valor_total': float(nota_fiscal.valor_total),
            'cnpj_emitente': nota_fiscal.cnpj_emitente,
            'nome_emitente': nota_fiscal.nome_emitente,
            'cnpj_destinatario': nota_fiscal.cnpj_destinatario,
            'nome_destinatario': nota_fiscal.nome_destinatario,
            'status_processamento': nota_fiscal.status_processamento,
            'xml_data': nota_fiscal.xml_data,
            'data_importacao': nota_fiscal.data_importacao.strftime('%d/%m/%Y %H:%M:%S'),
            'data_atualizacao': nota_fiscal.data_atualizacao.strftime('%d/%m/%Y %H:%M:%S') if nota_fiscal.data_atualizacao else None,
            'itens': itens
        }
        
        # Log para debug
        logger.info(f"API: Dados da nota fiscal {id} retornados com sucesso")
        
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Erro ao processar API de visualização da nota fiscal {id}: {str(e)}")
        return jsonify({"error": f"Erro ao processar nota fiscal: {str(e)}"}), 500

@nota_fiscal_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui uma nota fiscal do banco de dados
    """
    nota_fiscal = NotaFiscal.query.get_or_404(id)
    
    try:
        # Excluir a nota fiscal e seus itens (via cascata)
        nota_fiscal.delete()
        
        flash('Nota fiscal excluída com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir nota fiscal: {str(e)}', 'danger')
        logger.error(f'Erro ao excluir nota fiscal: {str(e)}')
    
    return redirect(url_for('nota_fiscal.index'))

@nota_fiscal_bp.route('/items/<int:nf_id>', methods=['GET'])
@login_required
def listar_itens(nf_id):
    """
    Lista os itens de uma nota fiscal
    """
    nota_fiscal = NotaFiscal.query.get_or_404(nf_id)
    materiais = Material.query.order_by(Material.codigo).all()
    centros_custo = CentroCusto.query.order_by(CentroCusto.codigo).all()
    
    return render_template(
        'notas_fiscais/itens.html', 
        nota_fiscal=nota_fiscal,
        materiais=materiais,
        centros_custo=centros_custo
    )

@nota_fiscal_bp.route('/items/novo/<int:nf_id>', methods=['GET', 'POST'])
@login_required
def novo_item(nf_id):
    """
    Adiciona um novo item à nota fiscal
    """
    nota_fiscal = NotaFiscal.query.get_or_404(nf_id)
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            codigo = request.form.get('codigo')
            descricao = request.form.get('descricao')
            quantidade = request.form.get('quantidade')
            valor_unitario = request.form.get('valor_unitario')
            valor_total = request.form.get('valor_total')
            ncm = request.form.get('ncm')
            cfop = request.form.get('cfop')
            unidade = request.form.get('unidade')
            
            # Validar campos obrigatórios
            if not descricao or not quantidade or not valor_unitario or not valor_total:
                flash('Todos os campos marcados com * são obrigatórios!', 'danger')
                return redirect(url_for('nota_fiscal.listar_itens', nf_id=nf_id))
            
            # Criar novo item
            item = NotaFiscalItem(
                nf_id=nf_id,
                codigo=codigo,
                descricao=descricao,
                quantidade=quantidade,
                valor_unitario=valor_unitario,
                valor_total=valor_total,
                ncm=ncm,
                cfop=cfop,
                unidade=unidade
            )
            
            # Salvar no banco
            item.save()
            
            flash('Item adicionado com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro ao adicionar item: {str(e)}', 'danger')
            logger.error(f'Erro ao adicionar item: {str(e)}')
    
    return redirect(url_for('nota_fiscal.listar_itens', nf_id=nf_id))

@nota_fiscal_bp.route('/items/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_item(id):
    """
    Edita um item de nota fiscal
    """
    item = NotaFiscalItem.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            item.codigo = request.form.get('codigo')
            item.descricao = request.form.get('descricao')
            item.quantidade = request.form.get('quantidade')
            item.valor_unitario = request.form.get('valor_unitario')
            item.valor_total = request.form.get('valor_total')
            item.ncm = request.form.get('ncm')
            item.cfop = request.form.get('cfop')
            item.unidade = request.form.get('unidade')
            
            # Validar campos obrigatórios
            if not item.descricao or not item.quantidade or not item.valor_unitario or not item.valor_total:
                flash('Todos os campos marcados com * são obrigatórios!', 'danger')
                return redirect(url_for('nota_fiscal.listar_itens', nf_id=item.nf_id))
            
            # Atualizar data de atualização
            item.ultima_atualizacao = datetime.now()
            
            # Salvar alterações
            item.save()
            
            flash('Item atualizado com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro ao atualizar item: {str(e)}', 'danger')
            logger.error(f'Erro ao atualizar item: {str(e)}')
    
    return redirect(url_for('nota_fiscal.listar_itens', nf_id=item.nf_id))

@nota_fiscal_bp.route('/items/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_item(id):
    """
    Exclui um item de nota fiscal
    """
    item = NotaFiscalItem.query.get_or_404(id)
    nf_id = item.nf_id
    
    try:
        # Excluir o item
        item.delete()
        
        flash('Item excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir item: {str(e)}', 'danger')
        logger.error(f'Erro ao excluir item: {str(e)}')
    
    return redirect(url_for('nota_fiscal.listar_itens', nf_id=nf_id))

@nota_fiscal_bp.route('/api/buscar', methods=['GET'])
@login_required
def api_buscar():
    """
    API para buscar notas fiscais por número, chave ou CNPJ
    """
    termo = request.args.get('termo', '')
    
    if not termo:
        return jsonify([])
    
    # Busca por número, chave de acesso ou CNPJ emitente/destinatário
    notas = NotaFiscal.query.filter(
        (NotaFiscal.numero_nf.like(f'%{termo}%')) |
        (NotaFiscal.chave_acesso.like(f'%{termo}%')) |
        (NotaFiscal.cnpj_emitente.like(f'%{termo}%')) |
        (NotaFiscal.cnpj_destinatario.like(f'%{termo}%')) |
        (NotaFiscal.nome_emitente.like(f'%{termo}%')) |
        (NotaFiscal.nome_destinatario.like(f'%{termo}%'))
    ).limit(10).all()
    
    resultado = []
    for nota in notas:
        resultado.append({
            'id': nota.id,
            'numero_nf': nota.numero_nf,
            'chave_acesso': nota.chave_acesso,
            'data_emissao': nota.data_emissao.strftime('%d/%m/%Y'),
            'valor_total': float(nota.valor_total),
            'cnpj_emitente': nota.cnpj_emitente,
            'nome_emitente': nota.nome_emitente
        })
    
    return jsonify(resultado)


@nota_fiscal_bp.route('/importar-arquivei', methods=['POST'])
@login_required
def importar_arquivei():
    """
    Importa notas fiscais da API do Arquivei
    """
    if request.method == 'POST':
        try:
            # Verificar CSRF token
            csrf_token = request.form.get('csrf_token')
            if not csrf_token:
                flash('Token CSRF não fornecido', 'danger')
                return redirect(url_for('nota_fiscal.index'))
                
            # Obter parâmetros da requisição
            data_inicial = request.form.get('data_inicial')
            data_final = request.form.get('data_final')
            tipo_documento = request.form.get('tipo_documento', 'nfe')
            cnpj_consulta = request.form.get('cnpj_consulta', '')
            
            # Log para auxiliar no diagnóstico
            logger.info(f"Importando notas do Arquivei: {data_inicial} a {data_final}, tipo: {tipo_documento}, CNPJ: {cnpj_consulta or 'todos'}")
            
            # Validar campos obrigatórios
            if not data_inicial or not data_final:
                flash('Datas inicial e final são obrigatórias!', 'danger')
                return redirect(url_for('nota_fiscal.index'))
            
            notas = Arquivei(data_inicial=data_inicial, data_final=data_final)
            #notas = Arquivei(send=True)
            tamanho = len(notas.xml_datas)
            print('tamanho: ',tamanho)
            if tamanho > 0:
                i=0
                for xml_data in notas.xml_datas:
                    nf = NotaFiscal(xml_data=xml_data)
                    print(f'id: {nf.id} numero_nf: {nf.numero_nf} {i}/{tamanho} ')
                    i+=1
                
        except Exception as e:
            logger.error(f"Erro ao importar notas fiscais: {str(e)}", exc_info=True)
            flash(f'Erro ao importar notas fiscais: {str(e)}', 'danger')
        
        return jsonify({'success': True, 'message': 'Notas fiscais importadas com sucesso!'})
    
    # Se for GET, redirecionar para index
    return jsonify({'success': False, 'message': 'Método inválido'}), 405




@nota_fiscal_bp.route('/pdf/<int:id>', methods=['GET'])
@login_required
def gerar_pdf(id):
    """
    Gera um PDF da nota fiscal para download
    """
    try:
        nota = NotaFiscal(id=id)
        print(f'nota: {nota.get_chave_acesso()}')
        pdf = nota.get_pdf()
        print('pdf: ',pdf)
        if pdf:
            response = make_response(base64.b64decode(pdf.blob))
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename=nota_fiscal_{nota.numero_nf}.pdf'
            return response
        else:
            return 'PDF não encontrado para esta nota.', 404
    except Exception as e:
        logger.error(f"Erro ao gerar PDF: {str(e)}")
        flash(f'Erro ao gerar PDF: {str(e)}', 'danger')
        return redirect(url_for('nota_fiscal.index'))
   

@nota_fiscal_bp.route('/api/importar_itens', methods=['GET', 'POST'])
@login_required
def importar_itens():
    """
    Interface para importar itens da nota fiscal para estoque
    """
    if request.method == 'POST':
       # try:
           # print(f"Request form: {request.form}")
            # Processar os itens selecionados
            itens = json.loads(request.form.get('itens'))
            print(f"Itens: {itens}")
            # Importar os itens para o estoque
            for item in itens:
                
                item_id = item.get('item_id')
                material_id = item.get('material_id')
                print(f"Item ID: {item_id}")
                print(f"Material ID: {material_id}")
                item1 = NotaFiscalItem.query.get_or_404(item_id)
                print(f"Item: {item1}")
                item1.material_id = material_id
                material = Material.query.get_or_404(material_id)
                if comparar_unidades(item1.unidade, material.unidade_obj.nome):
                    item1.fator_conversao_aplicado = 1
                item1.save()
                db.session.refresh(item1)
                cnpj_emitente = NotaFiscal.query.\
                    join(NotaFiscalItem, NotaFiscalItem.nf_id == NotaFiscal.id).\
                    filter(NotaFiscalItem.id==item_id).first().cnpj_emitente
        
                notas_fiscais = NotaFiscal.query.\
                    filter(NotaFiscal.cnpj_emitente==cnpj_emitente).all()
                for nota_fiscal in notas_fiscais:
                    nota_fiscal.vincular_automaticamente()
                    nota_fiscal.importar_itens_para_estoque()
                
            return jsonify({'success': True, 'message': f'Item {item_id} importado com sucesso!'})
       # except Exception as e:
       #     logger.error(f"Erro ao importar itens: {str(e)}")
       #     return jsonify({'success': False, 'message': f'Erro ao importar itens: {str(e)}'}), 500
    return jsonify({'success': False, 'message': 'Método inválido'}), 405
def importar_estoque(id):
    """
    Interface para vincular itens da nota fiscal com materiais do sistema e importar para estoque
    """
    # Buscar a nota fiscal
    nota_fiscal = NotaFiscal.query.get_or_404(id)
    
    # Buscar todos os materiais para o select
    materiais = Material.query.filter_by(ativo=True).order_by(Material.nome).all()
    
    # Buscar todos os centros de custo para o select
    centros_custo = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.nome).all()
    
    # Processar o formulário de importação
    if request.method == 'POST':
        centro_custo_id = request.form.get('centro_custo_id')
        observacao = request.form.get('observacao')
        
        # Itens marcados para importação
        itens_para_importar = []
        mensagens = []
        
        # Log para rastreamento
        logger.info(f"Iniciando importação de itens da NF {nota_fiscal.numero_nf} para estoque")
        lista_itens = request.form.getlist('itens[]')
        print(f"Lista de itens: {lista_itens}")
        print(f'lista 0: {lista_itens[0]}')
        # Percorrer todos os itens da nota fiscal
        for item in nota_fiscal.itens:
            # Verificar se o item foi marcado para importação
            checkbox_name = f'importar_item_{item.id}'
            print(f"Checkbox name: {checkbox_name}")
            print(f"Request form: {request.form.getlist('itens[]')}")
            #print(f"Item ID: {item.id}")
            if str(item.id) in lista_itens:
                # Obter o material selecionado para este item
                print(f'form: {request.form}')
                print(f'form hidden: {request.form.get("formhidden")}')
                print(f"Item ID: {item.id}")
                material_id = request.form.get(f'material_id_{item.id}')
                
                logger.info(f"Processando item {item.id} - {item.descricao} - Material ID: {material_id}")
                print(f"Processando item {item.id} - {item.descricao} - Material ID: {material_id}")
                if material_id:
                    # Atualizar o material do item
                    item.material_id = material_id
                    item.importado_estoque = True
                    item.save()
                    
                    # Verificar estado atual do estoque antes da importação
                    from models.estoque import Estoque
                    estoque_atual = Estoque.query.filter_by(material_id=material_id, tipo_item='material').first()
                    qtd_atual = estoque_atual.quantidade if estoque_atual else 0
                    
                    logger.info(f"Estoque atual para material {material_id}: {qtd_atual}")
                    
                    # Importar para estoque
                    success, message = item.importar_para_estoque(
                        usuario_id=current_user.id,
                        centro_custo_id=centro_custo_id,
                        observacao=observacao
                    )
                    
                    # Verificar estado do estoque depois da importação
                    db.session.refresh(estoque_atual) if estoque_atual else None
                    estoque_depois = Estoque.query.filter_by(material_id=material_id, tipo_item='material').first()
                    qtd_depois = estoque_depois.quantidade if estoque_depois else 0
                    
                    logger.info(f"Estoque após importação para material {material_id}: {qtd_depois} (Diferença: {float(qtd_depois) - float(qtd_atual)})")
                    
                    # Adicionar log de diagnóstico
                    if float(qtd_depois) <= float(qtd_atual):
                        logger.warning(f"ALERTA: A quantidade não aumentou após a importação! Material: {material_id}, Antes: {qtd_atual}, Depois: {qtd_depois}")
                        
                        # Tentar forçar a atualização do estoque
                        if estoque_depois:
                            try:
                                estoque_depois.quantidade = float(qtd_atual) + float(item.quantidade)
                                estoque_depois.save()
                                logger.info(f"Estoque atualizado forçadamente. Nova quantidade: {estoque_depois.quantidade}")
                                
                                # Atualizar a mensagem
                                message += f" (Atualização forçada realizada)"
                            except Exception as e:
                                logger.error(f"Erro ao forçar atualização do estoque: {str(e)}")
                    
                    # Adicionar mensagem do resultado
                    mensagens.append({
                        'tipo': 'success' if success else 'danger',
                        'texto': f"Item {item.codigo}: {message}"
                    })
                else:
                    mensagens.append({
                        'tipo': 'warning',
                        'texto': f"Item {item.codigo}: Material não selecionado, este item não foi importado."
                    })
        
        # Flash as mensagens
        for msg in mensagens:
            flash(msg['texto'], msg['tipo'])
            
        # Redirecionar para a mesma página para mostrar as mudanças
        return jsonify({'success': True, 'message': 'Itens importados com sucesso!'})
    
    return render_template(
        'notas_fiscais/index.html', 
        nota_fiscal=nota_fiscal, 
        materiais=materiais,
        centros_custo=centros_custo
    )

@nota_fiscal_bp.route('/api/vincular-material/<int:item_id>', methods=['POST'])
@login_required
def api_vincular_material(item_id):
    """
    API para vincular um material do sistema a um item de nota fiscal
    """
    try:
        # Obter o item da nota fiscal
        item = NotaFiscalItem.query.get_or_404(item_id)
        
        # Obter o material_id do formulário
        material_id = request.form.get('material_id')
        
        if not material_id:
            return jsonify({
                'success': False,
                'message': 'ID do material não fornecido'
            }), 400
        
        # Verificar se o material existe
        material = Material.query.get(material_id)
        if not material:
            return jsonify({
                'success': False,
                'message': f'Material com ID {material_id} não encontrado'
            }), 404
        
        if comparar_unidades(item.unidade, material.unidade.nome):
            item.fator_conversao_aplicado = 1
            print(f'fator_conversao_aplicado: {item.fator_conversao_aplicado}')
        # Atualizar o item da nota fiscal
        item.material_id = material_id
        item.save()

        cnpj_emitente = NotaFiscal.query.\
            join(NotaFiscalItem, NotaFiscalItem.nf_id == NotaFiscal.id).\
            filter(NotaFiscalItem.id==item_id).first().cnpj_emitente
        
        notas_fiscais = NotaFiscal.query.\
            filter(NotaFiscal.cnpj_emitente==cnpj_emitente).all()
        for nota_fiscal in notas_fiscais:
            nota_fiscal.vincular_automaticamente()
            nota_fiscal.importar_itens_para_estoque(usuario_id=current_user.id)
            
        return jsonify({
            'success': True,
            'message': f'Material {material.nome} vinculado com sucesso ao item'
        })
    
    except Exception as e:
        logger.error(f'Erro ao vincular material: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Erro ao vincular material: {str(e)}'
        }), 500

@nota_fiscal_bp.route('/api/reimportar_notas')
@login_required
def api_reimportar_notas():
    """
    API para reimportar todas as notas fiscais
    """
    try:
        print(processar_arquivei('2025-01-01', '2025-01-31'))
        return redirect(url_for('nota_fiscal.index'))
    except Exception as e:
        logger.error(f'Erro ao reimportar notas fiscais: {str(e)}')
        return jsonify({'error': f'Erro ao reimportar notas fiscais: {str(e)}'}), 500

        # Buscar todas as notas fiscais
@nota_fiscal_bp.route('/api/itens/<int:nf_id>', methods=['GET'])
@login_required
def api_itens(nf_id):
    """
    API para listar os itens de uma nota fiscal
    """
    try:
        # Buscar a nota fiscal
        nota_fiscal = NotaFiscal.query.get_or_404(nf_id)
        
        # Listar os itens
        items = []
        items_importados_automaticamente = 0
        
        for item in nota_fiscal.itens:
            vinculacao_automatica = False
            importacao_automatica = False
            
            # Verificar se o item foi importado automaticamente
            if item.dados_adicionais:
                try:
                    dados_json = json.loads(item.dados_adicionais)
                    if dados_json.get('importacao_automatica'):
                        importacao_automatica = True
                except (json.JSONDecodeError, AttributeError):
                    pass
            
            # Verificar se já existe um material vinculado ou buscar vinculação anterior
            material_id = item.material_id
            
            # Se não tem material vinculado, buscar vinculação anterior
            if False:
                material_id = buscar_material_vinculado_anteriormente(item.codigo, item.descricao)
                
                # Se encontrou uma vinculação anterior, atualizar o item
                if material_id:
                    item.material_id = material_id
                    vinculacao_automatica = True
                    
                    # Importar automaticamente para o estoque se material foi vinculado
                    if not item.importado_estoque:
                        sucesso, mensagem = item.importar_para_estoque(
                            usuario_id=current_user.id,
                            centro_custo_id=None,
                            observacao=f"Importação automática da NF {nota_fiscal.numero_nf} de {nota_fiscal.nome_emitente}"
                        )
                        if sucesso:
                            importacao_automatica = True
                            items_importados_automaticamente += 1
                            # Registrar que foi uma importação automática
                            item.dados_adicionais = json.dumps({
                                "importacao_automatica": True,
                                "data_importacao_automatica": datetime.now().isoformat()
                            })
                            logger.info(f"Item {item.id} importado automaticamente para o estoque via API")
                    
                    item.save()
            
            items.append({
                'id': item.id,
                'codigo': item.codigo,
                'cfop': item.cfop,
                'descricao': item.descricao,
                'quantidade': float(item.quantidade),
                'unidade': item.unidade,
                'valor_unitario': float(item.valor_unitario),
                'valor_total': float(item.valor_total),
                'material_id': material_id,
                'material_nome': Material.query.get(material_id).nome if material_id else None,
                'importado_estoque': item.importado_estoque,
                'data_importacao_estoque': item.data_importacao_estoque.isoformat() if item.data_importacao_estoque else None,
                'vinculacao_automatica': vinculacao_automatica,
                'importacao_automatica': importacao_automatica
            })
        
        # Se houve importações automáticas, adicionar um flash message
        if items_importados_automaticamente > 0:
            flash(f"{items_importados_automaticamente} item(s) importado(s) automaticamente para o estoque.", "success")
        
        return jsonify({'itens': items, 'success': True})
    
    except Exception as e:
        logger.error(f'Erro ao listar itens da nota fiscal: {str(e)}')
        return jsonify({'error': f'Erro ao listar itens: {str(e)}'}), 500

@nota_fiscal_bp.route('/api/materiais', methods=['GET'])
@login_required
def api_materiais():
    """API para listar materiais ativos para seleção com filtro"""
    try:
        # Obter o termo de busca da query string
        termo = request.args.get('termo', '')
        
        # Aplicar filtro se o termo de busca foi fornecido
        if termo and len(termo) >= 3:
            # Buscar materiais que correspondem ao termo em código ou descrição
            termo_busca = f"%{termo}%"
            materiais = Material.query.filter(
                Material.ativo == True,
                db.or_(
                    Material.codigo.ilike(termo_busca),
                    Material.descricao.ilike(termo_busca),
                    Material.nome.ilike(termo_busca)
                )
            ).order_by(Material.nome).all()
        else:
            # Se nenhum termo foi fornecido ou é muito curto, retornar lista vazia
            materiais = []
        
        resultado = []
        for material in materiais:
            # Verificar se tem conversões
            tem_conversoes = False
            if hasattr(material, 'tem_conversoes') and callable(getattr(material, 'tem_conversoes')):
                tem_conversoes = material.tem_conversoes()
            
            # Determinar a unidade do material
            if hasattr(material, 'get_unidade_nome'):
                unidade = material.get_unidade_nome()
            elif hasattr(material, 'unidade') and material.unidade:
                unidade = material.unidade
            else:
                unidade = '-'
                
            # Determinar a sigla da unidade
            if hasattr(material, 'get_unidade_sigla'):
                unidade_sigla = material.get_unidade_sigla()
            elif hasattr(material, 'unidade_sigla') and material.unidade_sigla:
                unidade_sigla = material.unidade_sigla
            else:
                unidade_sigla = '-'
            
            resultado.append({
                'id': material.id,
                'nome': material.nome,
                'codigo': material.codigo or '',
                'descricao': material.descricao or '',
                'unidade': unidade,
                'unidade_sigla': unidade_sigla,
                'tem_conversoes': tem_conversoes
            })
        
        return jsonify({'materiais': resultado, 'success': True})
        
    except Exception as e:
        logger.error(f'Erro ao listar materiais: {str(e)}')
        return jsonify({'error': f'Erro ao listar materiais: {str(e)}', 'materiais': []}), 500

@nota_fiscal_bp.route('/api/centros-custo', methods=['GET'])
@login_required
def api_centros_custo():
    """
    API para listar centros de custo para o select
    """
    try:
        # Buscar todos os centros de custo ativos
        centros = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.codigo).all()
        
        # Formatar para JSON
        items = []
        for centro in centros:
            items.append({
                'id': centro.id,
                'codigo': centro.codigo,
                'nome': centro.nome
            })
        
        # Retornar no formato esperado pelo front-end: objeto com propriedade centros_custo
        return jsonify({'centros_custo': items, 'success': True})
    
    except Exception as e:
        logger.error(f'Erro ao listar centros de custo: {str(e)}')
        return jsonify({'error': f'Erro ao listar centros de custo: {str(e)}', 'centros_custo': [], 'success': False}), 500

@nota_fiscal_bp.route('/api/unidades_conversao/<int:material_id>', methods=['GET'])
@login_required
def api_unidades_conversao(material_id):
    """API para listar conversões de unidades para um material"""
    try:
        # Buscar o material
        material = Material.query.get_or_404(material_id)
        
        # Verificar se existe modelo de conversão de unidades
        # Ajustar conforme a estrutura do seu modelo
        conversoes = []
        
        # Se existir modelo de UnidadeConversao, buscar as conversões
        if 'UnidadeConversao' in globals():
            conversoes_db = ConversaoUnidade.query.filter_by(material_id=material_id).all()
            for c in conversoes_db:
                conversoes.append({
                    'id': c.id,
                    'descricao': c.descricao,
                    'unidade_origem': c.unidade_origem,
                    'unidade_destino': c.unidade_destino,
                    'fator': c.fator
                })
        
        return jsonify({'conversoes': conversoes})
        
    except Exception as e:
        logger.error(f'Erro ao buscar conversões de unidades: {str(e)}')
        return jsonify({'error': f'Erro ao buscar conversões: {str(e)}', 'conversoes': []}), 500

@nota_fiscal_bp.route('/api/unidades', methods=['GET'])
@login_required
def api_unidades():
    """
    API para listar todas as unidades disponíveis no sistema
    """
    try:
        # Buscar todas as unidades
        unidades = Unidade.query.order_by(Unidade.nome).all()
        
        # Formatar para JSON
        items = []
        for unidade in unidades:
            items.append({
                'id': unidade.id,
                'codigo': unidade.codigo,
                'nome': unidade.nome,
                'simbolo': unidade.simbolo
            })
        
        return jsonify(items)
    
    except Exception as e:
        logger.error(f'Erro ao listar unidades: {str(e)}')
        return jsonify({'error': f'Erro ao listar unidades: {str(e)}'}), 500

@nota_fiscal_bp.route('/api/aplicar_conversao', methods=['POST'])
@login_required
def api_aplicar_conversao():
    """API para aplicar conversão de unidades ao vincular material a item de nota fiscal"""
    try:
        # Obter dados do formulário
        item_id = request.form.get('item_id')
        material_id = request.form.get('material_id')
        fator_conversao = request.form.get('fator_conversao')
        unidade_conversao_id = request.form.get('unidade_conversao_id')
        
        if not item_id or not material_id or not fator_conversao:
            return jsonify({
                'success': False,
                'message': 'Dados incompletos para conversão'
            }), 400
        
        # Validar fator de conversão
        try:
            fator_conversao = float(fator_conversao)
            if fator_conversao <= 0:
                return jsonify({
                    'success': False,
                    'message': 'Fator de conversão deve ser maior que zero'
                }), 400
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Fator de conversão inválido'
            }), 400
        
        # Buscar o item
        item = NotaFiscalItem.query.get_or_404(item_id)
       
        item.fator_conversao_aplicado = fator_conversao
        item.material_id = material_id  
        item.save()
        
        # Criar ou atualizar a conversão no sistema, se necessário
        # Implementar conforme seu modelo de dados
        
        return jsonify({
            'success': True,
            'message': 'Conversão aplicada com sucesso'
        })
        
    except Exception as e:
        logger.error(f'Erro ao aplicar conversão: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Erro ao aplicar conversão: {str(e)}'
        }), 500

@nota_fiscal_bp.route('/importar-todas-pendentes', methods=['GET'])
@login_required
def importar_todas_pendentes():
    """
    Importa automaticamente para o estoque todos os itens de notas fiscais
    que não foram importados e que já possuem material vinculado
    """
    try:
        # Buscar todas as notas fiscais
        notas_fiscais = NotaFiscal.query.filter(NotaFiscal.status_processamento!='cancelada',
                                                NotaFiscal.data_emissao<=datetime.now()-relativedelta(months=3))\
                                                .all()
        
        itens_importados = 0
        notas_processadas = 0
        notas_importadas = 0
        notas_canceladas = 0
        # Para cada nota fiscal
        total_notas = len(notas_fiscais)
        for nota_fiscal in notas_fiscais:
            notas_processadas += 1
            if(Arquivei(chave_acesso=nota_fiscal.chave_acesso,cancelamento=True).cancelada):
                nota_fiscal.status_processamento = 'cancelada'
                nota_fiscal.save()
                notas_canceladas+=1
            else:
                nota_teve_importacao = False
                itens_vinculados = nota_fiscal.vincular_automaticamente()
                if itens_vinculados > 0:
                    nota_fiscal.importar_itens_para_estoque()
                    notas_importadas+=1
                
        
            print(f'{notas_processadas} - {notas_importadas} - {notas_canceladas} - {total_notas}')

        if itens_importados > 0:
            flash(f"{itens_importados} itens de {notas_processadas} notas fiscais foram importados automaticamente para o estoque.", "success")
        else:
            flash("Não foram encontrados itens pendentes com materiais vinculados para importação.", "info")
        
        return redirect(url_for('nota_fiscal.index'))
        
    except Exception as e:
        logger.error(f"Erro ao importar notas pendentes: {str(e)}")
        flash(f"Erro ao processar importação automática: {str(e)}", "danger")
        return redirect(url_for('nota_fiscal.index'))

@nota_fiscal_bp.route('/api/material/<int:id>', methods=['GET'])
@login_required
def api_material_por_id(id):
    """API para buscar material por ID"""
    try:
        # Buscar o material pelo ID
        material = Material.query.get(id)
        
        if not material:
            return jsonify({'error': f'Material com ID {id} não encontrado', 'material': None}), 404
        
        # Verificar se tem conversões
        tem_conversoes = False
        if hasattr(material, 'tem_conversoes') and callable(getattr(material, 'tem_conversoes')):
            tem_conversoes = material.tem_conversoes()
        
        # Determinar a unidade do material
        if hasattr(material, 'get_unidade_nome'):
            unidade = material.get_unidade_nome()
        elif hasattr(material, 'unidade') and material.unidade:
            unidade = material.unidade
        else:
            unidade = '-'
            
        # Determinar a sigla da unidade
        if hasattr(material, 'get_unidade_sigla'):
            unidade_sigla = material.get_unidade_sigla()
        elif hasattr(material, 'unidade_sigla') and material.unidade_sigla:
            unidade_sigla = material.unidade_sigla
        else:
            unidade_sigla = '-'
        
        # Montar o objeto de resposta
        resultado = {
            'id': material.id,
            'nome': material.nome,
            'codigo': material.codigo or '',
            'descricao': material.descricao or '',
            'unidade': unidade,
            'unidade_sigla': unidade_sigla,
            'tem_conversoes': tem_conversoes
        }
        
        return jsonify({'material': resultado})
        
    except Exception as e:
        logger.error(f'Erro ao buscar material por ID: {str(e)}')
        return jsonify({'error': f'Erro ao buscar material: {str(e)}', 'material': None}), 500


@nota_fiscal_bp.route('/api/comparar-unidades', methods=['POST'])
@login_required
def api_comparar_unidades():
    """
    API para comparar unidades de nota fiscal e material
    """
    try:
        unidade_nota = request.json.get('unidadeNota')
        unidade_material = request.json.get('unidadeMaterial')

        if comparar_unidades(unidade_nota, unidade_material):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False})
    except Exception as e:
        logger.error(f'Erro ao comparar unidades: {str(e)}')
        return jsonify({'error': f'Erro ao comparar unidades: {str(e)}', 'success': False}), 500

@nota_fiscal_bp.route('/api/importar-item-estoque/<int:item_id>', methods=['POST'])
@login_required
def api_importar_item_estoque(item_id):
    """
    API para importar um item de nota fiscal para o estoque
    """
    try:
        # Obter o item da nota fiscal
        item = NotaFiscalItem.query.get_or_404(item_id)
        
        # Verificar se o item já foi importado
        if item.importado_estoque:
            return jsonify({
                'success': False,
                'message': 'Este item já foi importado para o estoque'
            }), 400
        
        # Verificar se o material está vinculado
        if not item.material_id:
            return jsonify({
                'success': False,
                'message': 'Este item não está vinculado a um material do sistema'
            }), 400
        
        # Obter parâmetros adicionais
        centro_custo_id = request.form.get('centro_custo_id')
        observacao = request.form.get('observacao')
        importacao_automatica = request.form.get('importacao_automatica', 'false') == 'true'
        
        # Se for importação automática, ajusta a observação
        if importacao_automatica and not observacao:
            observacao = f"Importação automática da NF {item.nota_fiscal.numero_nf} de {item.nota_fiscal.nome_emitente}"
        
        # Verificar estado atual do estoque antes da importação
        from models.estoque import Estoque
        estoque_atual = Estoque.query.filter_by(material_id=item.material_id, tipo_item='material').first()
        qtd_atual = float(estoque_atual.quantidade) if estoque_atual else 0
        
        logger.info(f"API: Estoque atual para material {item.material_id}: {qtd_atual}")
        
        # Realizar a importação para o estoque
        sucesso, mensagem = item.importar_para_estoque(
            usuario_id=current_user.id,
            centro_custo_id=centro_custo_id if centro_custo_id else None,
            observacao=observacao
        )
        
        # Verificar estado do estoque depois da importação
        db.session.refresh(estoque_atual) if estoque_atual else None
        estoque_depois = Estoque.query.filter_by(material_id=item.material_id, tipo_item='material').first()
        qtd_depois = float(estoque_depois.quantidade) if estoque_depois else 0
        
        logger.info(f"API: Estoque após importação para material {item.material_id}: {qtd_depois}")
        
        if sucesso:
            # Registrar se foi importação automática
            if importacao_automatica:
                item.dados_adicionais = json.dumps({
                    "importacao_automatica": True,
                    "data_importacao_automatica": datetime.now().isoformat()
                })
                item.save()
            
            # Se foi bem-sucedido, retornar sucesso
            return jsonify({
                'success': True,
                'message': mensagem,
                'quantidade_anterior': qtd_atual,
                'quantidade_atual': qtd_depois,
                'importacao_automatica': importacao_automatica
            })
        else:
            # Se houve erro, retornar o erro
            return jsonify({
                'success': False,
                'message': mensagem
            }), 400
        
    except Exception as e:
        logger.error(f'Erro ao importar item para estoque: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Erro ao importar item para estoque: {str(e)}'
        }), 500


# Rota para análise de notas fiscais
@nota_fiscal_bp.route('/analise')
@login_required
def analise():
    """
    Exibe análise de itens de notas fiscais com filtros, opção de agrupamento e paginação.
    """
    # Parâmetros de Paginação e Agrupamento
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ANALISE_ITENS_PER_PAGE', 25) 
    agrupar_por = request.args.get('agrupar_por', 'item_nf') # 'item_nf' ou 'material'

    # Obter filtros da requisição
    fornecedor = request.args.get('fornecedor', '')
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    termo_item = request.args.get('termo_item', '')
    filtro_material = request.args.get('filtro_material', '') 
    
    # --- Construção da Query Base (Seleção e Joins) --- 
    if agrupar_por == 'material':
        # Agrupar por Material Vinculado
        query = db.session.query(
            Material.id.label('material_id'),
            Material.nome.label('material_nome'),
            Unidade.nome.label('material_unidade'), # Usar unidade do material
            sqlfunc.sum(NotaFiscalItem.quantidade).label('quantidade_total'),
            sqlfunc.sum(NotaFiscalItem.valor_total).label('valor_total_agregado'),
            sqlfunc.group_concat(distinct(NotaFiscal.nome_emitente)).label('fornecedores')
        ).join(NotaFiscalItem, Material.id == NotaFiscalItem.material_id).join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id).join(Unidade, Unidade.id == Material.unidade_id)
        # Adicionar filtro para garantir que material_id não é nulo (redundante com INNER JOIN)
        # query = query.filter(NotaFiscalItem.material_id != None) 
    else: 
        # Agrupar por Item da Nota Fiscal (lógica anterior)
        query = db.session.query(
            NotaFiscalItem.codigo,
            NotaFiscalItem.descricao,
            sqlfunc.sum(NotaFiscalItem.quantidade).label('quantidade_total'),
            sqlfunc.sum(NotaFiscalItem.valor_total).label('valor_total_agregado'),
            sqlfunc.group_concat(distinct(NotaFiscal.nome_emitente)).label('fornecedores'), 
            sqlfunc.group_concat(distinct(NotaFiscalItem.unidade)).label('unidades'),
            sqlfunc.group_concat(distinct(Material.nome)).label('materiais_vinculados') 
        ).join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id) \
         .outerjoin(Material, Material.id == NotaFiscalItem.material_id) # OUTER JOIN aqui

    # --- Aplicação de Filtros (Comum para ambos agrupamentos) ---
    if fornecedor:
        query = query.filter(NotaFiscal.nome_emitente == fornecedor)
    if data_inicio:
        try: dt_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date(); query = query.filter(NotaFiscal.data_emissao >= dt_inicio)
        except ValueError: flash('Formato de data inválido para Data Início', 'warning')
    if data_fim:
        try: dt_fim = datetime.strptime(data_fim, '%Y-%m-%d').date(); query = query.filter(NotaFiscal.data_emissao <= dt_fim)
        except ValueError: flash('Formato de data inválido para Data Fim', 'warning')
    if termo_item: 
        termo_like = f'%{termo_item}%'
        query = query.filter(or_(NotaFiscalItem.codigo.ilike(termo_like), NotaFiscalItem.descricao.ilike(termo_like)))
    if filtro_material: 
        # Este filtro só faz sentido se o join com Material existir (ambos os casos agora)
        material_like = f'%{filtro_material}%'
        query = query.filter(Material.nome.ilike(material_like))
        # Se agrupar por material, este filtro é aplicado antes do group by, filtrando quais materiais considerar
        # Se agrupar por item_nf, filtra os itens cujo material vinculado bate com o filtro.

    # --- Calcular Total Geral ANTES de agrupar (Query separada) --- 
    # Query base para o total
    total_geral_query_base = db.session.query(NotaFiscalItem.valor_total)
    total_geral_query_base = total_geral_query_base.join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
    
    # Adicionar outerjoin com Material ANTES dos filtros que dependem dele
    total_geral_query_base = total_geral_query_base.outerjoin(Material, Material.id == NotaFiscalItem.material_id)

    # Aplicar filtro para incluir apenas itens vinculados se agrupando por material
    if agrupar_por == 'material':
        total_geral_query_base = total_geral_query_base.filter(NotaFiscalItem.material_id != None)

    # Reaplicar filtros principais à query base do total geral
    if fornecedor: 
        total_geral_query_base = total_geral_query_base.filter(NotaFiscal.nome_emitente == fornecedor)
    if data_inicio: 
        try: 
            dt_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            total_geral_query_base = total_geral_query_base.filter(NotaFiscal.data_emissao >= dt_inicio)
        except ValueError: pass # Erro já notificado antes
    if data_fim: 
        try: 
            dt_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            total_geral_query_base = total_geral_query_base.filter(NotaFiscal.data_emissao <= dt_fim)
        except ValueError: pass # Erro já notificado antes
    if termo_item: 
        termo_like = f'%{termo_item}%'
        total_geral_query_base = total_geral_query_base.filter(or_(NotaFiscalItem.codigo.ilike(termo_like), NotaFiscalItem.descricao.ilike(termo_like)))
    if filtro_material: 
        material_like = f'%{filtro_material}%'
        # O outerjoin já permite filtrar aqui
        total_geral_query_base = total_geral_query_base.filter(Material.nome.ilike(material_like))
    
    # Calcular a soma total
    total_geral_scalar = total_geral_query_base.with_entities(sqlfunc.sum(NotaFiscalItem.valor_total)).scalar()
    total_geral = total_geral_scalar if total_geral_scalar is not None else Decimal(0)
    # ----------------------------------------------

    # --- Agrupamento e Ordenação (Condicional) --- 
    if agrupar_por == 'material':
        query = query.group_by(Material.id, Material.nome, Material.unidade)
        query = query.order_by(sqlfunc.sum(NotaFiscalItem.valor_total).desc()) # Ordenar por valor total
    else: # agrupar_por == 'item_nf'
        query = query.group_by(NotaFiscalItem.codigo, NotaFiscalItem.descricao)
         # A query já seleciona as colunas extras (unidades, materiais_vinculados)
        query = query.order_by(sqlfunc.sum(NotaFiscalItem.valor_total).desc())

    # --- Paginação --- 
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    resultados_pagina = pagination.items 
    
    # --- LOG PARA DEBUG --- 
    logger.debug(f"Resultados Agregados Pagina {page} (Agrupar por: {agrupar_por}):")
    for idx, row in enumerate(resultados_pagina):
        try:
            # O resultado é um objeto KeyedTuple (similar a um objeto nomeado)
            logger.debug(f"  Linha {idx}: {row._asdict()}") 
        except Exception as e_log:
             logger.error(f"Erro ao logar linha {idx}: {e_log}")
    # ---------------------

    # --- Obter Fornecedores para Filtro (Inalterado) --- 
    fornecedores_lista = db.session.query(NotaFiscal.nome_emitente).distinct().order_by(NotaFiscal.nome_emitente).all()
    fornecedores = [f[0] for f in fornecedores_lista if f[0]] 

    # --- Renderizar Template --- 
    return render_template(
        'notas_fiscais/analise.html',
        pagination=pagination, 
        resultados=resultados_pagina, 
        fornecedores=fornecedores, 
        total_geral=total_geral, 
        # Passar filtros e opção de agrupamento para o template
        filtro_fornecedor=fornecedor,
        filtro_data_inicio=data_inicio,
        filtro_data_fim=data_fim,
        filtro_termo_item=termo_item,
        filtro_material=filtro_material,
        agrupar_por=agrupar_por # Passar a opção de agrupamento
    )

@nota_fiscal_bp.route('/api/historico-preco')
@login_required
def api_historico_preco():
    """
    API para buscar o histórico de preços de um item, com conversão opcional para unidade padrão do material.
    """
    try:
        tipo = request.args.get('tipo', 'item_nf')
        material_id = request.args.get('material_id', type=int)
        codigo = request.args.get('codigo', '')
        descricao = request.args.get('descricao', '')
        
        fornecedor = request.args.get('fornecedor', '')
        data_inicio_str = request.args.get('data_inicio', '')
        data_fim_str = request.args.get('data_fim', '')

        unidade_referencia = None
        material_obj = None
        
        if tipo == 'material' and material_id:
            material_obj = Material.query.get(material_id)
            if not material_obj:
                 return jsonify({"error": "Material não encontrado."}), 404
            unidade_referencia = material_obj.unidade.nome
            logger.debug(f"Buscando histórico para Material ID: {material_id}, Unidade Padrão: {unidade_referencia}")

        # Query base para buscar itens individuais e dados da NF
        query = db.session.query(
            NotaFiscalItem.quantidade,
            NotaFiscalItem.valor_unitario,
            NotaFiscalItem.valor_total, # Necessário para recalcular valor unitário
            NotaFiscalItem.unidade.label('unidade_item_nf'), # Renomear para clareza
            NotaFiscal.data_emissao,
            NotaFiscal.numero_nf,
            NotaFiscal.nome_emitente,
            NotaFiscalItem.material_id # Selecionar para referência
        ).join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)

        # Filtrar pelo item/material específico
        if tipo == 'material' and material_id:
            query = query.filter(NotaFiscalItem.material_id == material_id)
        elif tipo == 'item_nf':
            if codigo:
                 query = query.filter(NotaFiscalItem.codigo == codigo)
            query = query.filter(NotaFiscalItem.descricao == descricao)
            # Se tipo é item_nf, não temos unidade_referencia definida ainda
        else:
            return jsonify({"error": "Parâmetros inválidos para tipo de histórico."}), 400

        # Aplicar filtros adicionais de contexto
        # ... (aplicar filtros de fornecedor, data_inicio, data_fim) ...

        # Ordenar pelo mais recente
        query = query.order_by(NotaFiscal.data_emissao.desc())

        # Executar a query
        historico_cru = query.all()
        logger.debug(f"Encontrados {len(historico_cru)} registros de histórico bruto.")

        # Formatar resultado para JSON com conversão opcional
        historico_formatado = []
        for item in historico_cru:
            quantidade_final = item.quantidade
            valor_unitario_final = item.valor_unitario
            unidade_final = item.unidade_item_nf
            conversao_aplicada = False

            # Tentar conversão apenas se agrupando por material e unidade de referência conhecida
            if tipo == 'material' and unidade_referencia and item.unidade_item_nf and item.unidade_item_nf != unidade_referencia:
                logger.debug(f"Tentando conversão: De {item.unidade_item_nf} para {unidade_referencia} para Material {material_id}")
                conversao = ConversaoUnidade.query.filter_by(
                    material_id=material_id, 
                    unidade_entrada=item.unidade_item_nf, 
                    unidade_saida=unidade_referencia
                ).first()
                
                if conversao:
                    try:
                        fator = conversao.fator_conversao
                        logger.debug(f"Conversão encontrada: Fator {fator}")
                        if fator is not None and fator > 0 and item.quantidade is not None and item.valor_total is not None:
                            quantidade_conv = Decimal(item.quantidade) * Decimal(fator)
                            if quantidade_conv > 0:
                                valor_unitario_conv = Decimal(item.valor_total) / quantidade_conv
                                
                                quantidade_final = quantidade_conv
                                valor_unitario_final = valor_unitario_conv
                                unidade_final = unidade_referencia
                                conversao_aplicada = True
                                logger.debug(f"  Convertido: Qtd={quantidade_final}, VU={valor_unitario_final}, Unid={unidade_final}")
                            else:
                                logger.warning("  Quantidade convertida resultou em zero ou negativa. Usando valores originais.")
                        else:
                             logger.warning("  Fator de conversão inválido ou quantidade/valor total nulos. Usando valores originais.")
                             unidade_final = f"{item.unidade_item_nf} (Conv. Inválida)"

                    except Exception as e_conv:
                         logger.error(f"  Erro durante cálculo da conversão: {e_conv}")
                         unidade_final = f"{item.unidade_item_nf} (Erro Conv.)"
                else:
                    logger.warning(f"  Conversão de {item.unidade_item_nf} para {unidade_referencia} não encontrada para Material {material_id}. Usando valores originais.")
                    unidade_final = f"{item.unidade_item_nf} (N/C)" # N/C = Não Convertido / Não Cadastrado
            
            # Adicionar ao resultado formatado
            historico_formatado.append({
                "quantidade": float(quantidade_final) if quantidade_final is not None else 0,
                "valor_unitario": float(valor_unitario_final) if valor_unitario_final is not None else 0,
                "unidade": unidade_final,
                "data_emissao": item.data_emissao.strftime('%Y-%m-%d') if item.data_emissao else None,
                "numero_nf": item.numero_nf,
                "nome_emitente": item.nome_emitente,
                "conversao_aplicada": conversao_aplicada # Flag para info
            })
        
        logger.debug(f"Histórico formatado final: {len(historico_formatado)} itens.")
        return jsonify({"historico": historico_formatado})

    except Exception as e:
        logger.error(f"Erro na API de histórico de preço: {str(e)}", exc_info=True)
        return jsonify({"error": "Erro interno ao buscar histórico de preços."}), 500

@nota_fiscal_bp.route('/importar-xml', methods=['POST'])
@login_required
def importar_xml():
    """
    Importa notas fiscais a partir de arquivos XML ou ZIP enviados pelo modal.
    """
    from werkzeug.utils import secure_filename
    import zipfile
    import io
    import base64
    mensagens = []
    total_importadas = 0
    try:
        # Verificar CSRF token
        csrf_token = request.form.get('csrf_token')
        if not csrf_token:
            return jsonify({'success': False, 'message': 'Token CSRF não fornecido.'})
        arquivos = request.files.getlist('xml_zip_files')
        if not arquivos:
            return jsonify({'success': False, 'message': 'Nenhum arquivo enviado.'})
        for arquivo in arquivos:
            filename = secure_filename(arquivo.filename)
            if filename.lower().endswith('.zip'):
                # Processar ZIP
                with zipfile.ZipFile(arquivo) as z:
                    total_arquivos = len(z.infolist())
                    print('zipinfo: ',total_arquivos)
                    for i, zipinfo in enumerate(z.infolist()):
                        print(f'arq {total_importadas}/{total_arquivos}')
                        if zipinfo.filename.lower().endswith('.xml'):
                            with z.open(zipinfo) as xmlfile:
                                xml_bytes = xmlfile.read()
                                xml_b64 = base64.b64encode(xml_bytes).decode('utf-8')
                                nf = NotaFiscal(xml_data=xml_b64)
                                if nf and nf.id:
                                    total_importadas += 1
                                else:
                                    mensagens.append(f'Erro ao importar {zipinfo.filename}')
            elif filename.lower().endswith('.xml'):
                # Processar XML individual
                xml_bytes = arquivo.read()
                xml_b64 = base64.b64encode(xml_bytes).decode('utf-8')
                nf = NotaFiscal(xml_data=xml_b64)
                if nf and nf.id:
                    total_importadas += 1
                else:
                    mensagens.append(f'Erro ao importar {filename}')
            else:
                mensagens.append(f'Arquivo ignorado: {filename}')
        if total_importadas > 0:
            return jsonify({'success': True, 'message': f'{total_importadas} nota(s) fiscal(is) importada(s) com sucesso!'}), 200
        else:
            return jsonify({'success': False, 'message': 'Nenhuma nota fiscal foi importada.\n' + '\n'.join(mensagens)}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao importar XML: {str(e)}'}), 500

@nota_fiscal_bp.route('/analise-transferencias')
@login_required
def analise_transferencias():
    """
    Exibe análise de transferências de itens (notas fiscais) com filtros de data, código e nome do item.
    """
    from sqlalchemy import and_
    from models.nota_fiscal import NotaFiscal, NotaFiscalItem
    page = request.args.get('page', 1, type=int)
    per_page = 25
    filtro_data_inicio = request.args.get('data_inicio', '')
    filtro_data_fim = request.args.get('data_fim', '')
    filtro_codigo_item = request.args.get('codigo_item', '')
    filtro_nome_item = request.args.get('nome_item', '')

    # Query base
    query = db.session.query(
        NotaFiscal.numero_nf.label('numero_nf'),
        NotaFiscalItem.descricao.label('nome_item'),
        NotaFiscalItem.codigo.label('codigo_item'),
        NotaFiscal.cnpj_emitente,
        NotaFiscal.cnpj_destinatario,
        NotaFiscal.nome_emitente,
        NotaFiscal.nome_destinatario,
        NotaFiscal.tipo.label('tipo_nota'),
        NotaFiscalItem.quantidade,
        NotaFiscalItem.valor_total.label('valor'),
        NotaFiscal.data_emissao.label('data')
    ).join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
    query = query.filter(NotaFiscal.status_processamento !='cancelada')

    # Filtros
    if filtro_data_inicio:
        try:
            from datetime import datetime
            data_inicio = datetime.strptime(filtro_data_inicio, '%Y-%m-%d')
            query = query.filter(NotaFiscal.data_emissao >= data_inicio)
        except Exception:
            pass
    if filtro_data_fim:
        try:
            from datetime import datetime
            data_fim = datetime.strptime(filtro_data_fim, '%Y-%m-%d')
            query = query.filter(NotaFiscal.data_emissao <= data_fim)
        except Exception:
            pass
    if filtro_codigo_item:
        query = query.filter(NotaFiscalItem.codigo.ilike(f'%{filtro_codigo_item}%'))
    if filtro_nome_item:
        query = query.filter(NotaFiscalItem.descricao.ilike(f'%{filtro_nome_item}%'))

    query = query.order_by(NotaFiscal.data_emissao.desc())
    paginacao = query.paginate(page=page, per_page=per_page, error_out=False)
    transferencias = paginacao.items

    return render_template(
        'notas_fiscais/analise_transferencias.html',
        transferencias=transferencias,
        paginacao=paginacao,
        filtro_data_inicio=filtro_data_inicio,
        filtro_data_fim=filtro_data_fim,
        filtro_codigo_item=filtro_codigo_item,
        filtro_nome_item=filtro_nome_item
    )

@nota_fiscal_bp.route('/api/documentos/<int:nota_id>', methods=['GET'])
@login_required
def api_listar_documentos(nota_id):
    """
    API para listar documentos de uma nota fiscal
    """
    try:
        documentos = Upload.query.filter_by(pai='NotaFiscal', pai_id=nota_id).all()
        resultado = []
        for doc in documentos:
            resultado.append({
                'id': doc.id,
                'filename': doc.filename,
                'tipo': doc.tipo,
                'uploaded_at': doc.uploaded_at.isoformat()
            })
        return jsonify({'documentos': resultado, 'success': True})
    except Exception as e:
        logger.error(f'Erro ao listar documentos: {str(e)}')
        return jsonify({'error': f'Erro ao listar documentos: {str(e)}', 'success': False}), 500

@nota_fiscal_bp.route('/api/documentos', methods=['POST'])
@login_required
def api_adicionar_documento():
    """
    API para adicionar um documento a uma nota fiscal
    """
    try:
        nota_id = request.form.get('nota_fiscal_id')
        tipo = request.form.get('tipo')
        arquivo = request.files.get('arquivo')
        
        if not nota_id or not tipo or not arquivo:
            return jsonify({'success': False, 'message': 'Dados incompletos'}), 400
            
        # Verificar se a nota fiscal existe
        nota = NotaFiscal.query.get(nota_id)
        if not nota:
            return jsonify({'success': False, 'message': 'Nota fiscal não encontrada'}), 404
            
        # Ler o arquivo e converter para base64
        arquivo_bytes = arquivo.read()
        arquivo_b64 = base64.b64encode(arquivo_bytes).decode('utf-8')
        
        # Criar novo upload
        upload = Upload(
            pai='nota_fiscal',
            pai_id=nota_id,
            tipo=tipo,
            filename=arquivo.filename,
            mimetype=arquivo.content_type,
            blob=arquivo_b64
        )
        
        upload.save()
        
        return jsonify({'success': True, 'message': 'Documento adicionado com sucesso'})
    except Exception as e:
        logger.error(f'Erro ao adicionar documento: {str(e)}')
        return jsonify({'success': False, 'message': f'Erro ao adicionar documento: {str(e)}'}), 500

@nota_fiscal_bp.route('/api/documentos/<int:doc_id>', methods=['DELETE'])
@login_required
def api_excluir_documento(doc_id):
    """
    API para excluir um documento
    """
    try:
        documento = Upload.query.get_or_404(doc_id)
        documento.delete()
        return jsonify({'success': True, 'message': 'Documento excluído com sucesso'})
    except Exception as e:
        logger.error(f'Erro ao excluir documento: {str(e)}')
        return jsonify({'success': False, 'message': f'Erro ao excluir documento: {str(e)}'}), 500

@nota_fiscal_bp.route('/api/documentos/<int:doc_id>/visualizar')
@login_required
def api_visualizar_documento(doc_id):
    """
    API para visualizar um documento
    """
    try:
        documento = Upload.query.get_or_404(doc_id)
        response = make_response(base64.b64decode(documento.blob))
        response.headers['Content-Type'] = documento.mimetype
        response.headers['Content-Disposition'] = f'inline; filename={documento.filename}'
        return response
    except Exception as e:
        logger.error(f'Erro ao visualizar documento: {str(e)}')
        return jsonify({'error': f'Erro ao visualizar documento: {str(e)}'}), 500