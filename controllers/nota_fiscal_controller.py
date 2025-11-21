import time
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import logging
import zipfile
import requests
import base64
import xml.etree.ElementTree as ET
import json
from decimal import Decimal
from sqlalchemy import func, or_, case, distinct, and_, exists # Adicionar distinct e exists
from sqlalchemy.sql import func as sqlfunc # Alias para func
from flask import make_response
from models.database import db
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.material import Material
from models.centro_custo import CentroCusto
from models.unidade import Unidade
from models.conversao_unidade import ConversaoUnidade
from forms.nota_fiscal_forms import NotaFiscalImportForm # Import para formulário do modal
from utils.relatorio_financeiro import gerar_relatorio_financeiro
from models.arquivei import Arquivei
from scripts.processar_email1 import processar_emails
from models.conversao_unidade import comparar_unidades
from models.upload import Upload
from models.nota_fiscal import CNPJS_MATRIZ_FILIAIS,CNPJS_MATRIZ,CNPJS_FILIAIS
from models.dados_analiticos import DadoAnalitico
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from scripts.importar_cte import extrair_dados_cte
import pandas as pd
import io
from models.reembolso import ReembolsoDocumento
from models.plano_conta import PlanoConta

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

@nota_fiscal_bp.route('/teste2')
@login_required
def teste2():
    print('teste2')
    processar_emails()
    return redirect(url_for('nota_fiscal.index'))

@nota_fiscal_bp.route('/teste1')
@login_required
def teste1():
    xmls = Arquivei(data_inicial='2025-06-15', data_final='2025-06-16',tipo='cte')
    for xml in xmls.xml_datas:
        dados = extrair_dados_cte(xml)
        print(dados)
    #processar_protocolos()
    return redirect(url_for('nota_fiscal.index'))

@nota_fiscal_bp.route('/teste')
@login_required
def teste():
    print('teste')
    nota = NotaFiscal.query.get(33894)
    nota.analizar_xml_json()
    return redirect(url_for('nota_fiscal.index'))
@nota_fiscal_bp.route('/')
@login_required
def index():
    """
    Lista notas fiscais com paginação e filtros.
    """
    # Parâmetros de Paginação
    
    
    return render_template('notas_fiscais/index.html') # Passar novo filtro para o template

def nota_fiscal_busca(filtros):
    if not filtros:
        return jsonify({'error': 'Dados inválidos'}), 400

    print('Filtros recebidos:', filtros)
    
    page = int(filtros.get('page', 1))
    per_page = int(filtros.get('per_page', 10))
    ids = filtros.get('ids', [])
    pagamento_filtro = filtros.get('pagamento', '')
    valor_minimo = filtros.get('valor_minimo')
    valor_maximo = filtros.get('valor_maximo')
    valor_exato = filtros.get('valor_exato')
    notas_selecionadas = filtros.get('notas_selecionadas', [])
    from dateutil.relativedelta import relativedelta
    data_inicial = filtros.get('data_inicial') if filtros.get('data_inicial') else datetime.now() - relativedelta(months=12)
    data_final = filtros.get('data_final')
    fornecedor = filtros.get('fornecedor')
    busca = filtros.get('busca','')
    busca_prod = filtros.get('busca_prod','')
    cnpj_emitente = filtros.get('cnpj_emitente','')
    cnpj_destinatario = filtros.get('cnpj_destinatario','')
    cfop = filtros.get('cfop','')
    reembolso_id = filtros.get('reembolso_id','')
    tinicial = time.time()
    
    # Colunas virtuais usando funções de agregação para evitar duplicatas
    tem_pagamento_column = func.max(case((DadoAnalitico.id != None, 1), else_=0)).label('tem_pagamento')
    upload_column = func.max(case((Upload.tipo != None, 1), else_=0)).label('upload')
    upload_envio_column = func.max(case((Upload.tipo == 2, 1), else_=0)).label('upload_envio')
    upload_reembolso_column = func.max(case((Upload.tipo == 3, 1), else_=0)).label('upload_reembolso')

    query = db.session.query(
        NotaFiscal,
        tem_pagamento_column,
        upload_column,
        upload_envio_column,
        upload_reembolso_column,
        ReembolsoDocumento
    ).select_from(NotaFiscal).filter(NotaFiscal.status_processamento != 'cancelada')

    
    #query = query.join(NotaFiscalItem, NotaFiscalItem.nf_id == NotaFiscal.id)
    # Condições do Join para encontrar a correspondência de pagamento
    join_conditions_pagamento = and_(
        NotaFiscal.valor_total == DadoAnalitico.valor,
        DadoAnalitico.documento.like('%' + NotaFiscal.numero_nf + '%')
    )
    
    # Condições do Join para uploads
    join_conditions_upload = and_(
        Upload.pai_id == NotaFiscal.id,
        Upload.pai == 'NotaFiscal'
    )

    # Usar LEFT JOIN (outerjoin) para incluir todas as notas
    query = query.outerjoin(DadoAnalitico, join_conditions_pagamento)
    query = query.outerjoin(PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id)
    query = query.outerjoin(ReembolsoDocumento, ReembolsoDocumento.nota_fiscal_id == NotaFiscal.id)
    query = query.outerjoin(Upload, join_conditions_upload)
    
    if valor_minimo:
        query = query.filter(NotaFiscal.valor_total >= valor_minimo)
    if valor_maximo:
        query = query.filter(NotaFiscal.valor_total <= valor_maximo)
    if valor_exato:
        query = query.filter(NotaFiscal.valor_total == valor_exato)
    if data_inicial:
        query = query.filter(NotaFiscal.data_emissao >= data_inicial)
    if data_final:
        query = query.filter(NotaFiscal.data_emissao <= data_final)
    if fornecedor:
        query = query.filter(NotaFiscal.nome_emitente.ilike(f'%{fornecedor}%'))
    if busca:
        busca_like = f'%{busca}%'
        query = query.filter(
            or_(
                NotaFiscal.numero_nf.ilike(busca_like),
                NotaFiscal.nome_emitente.ilike(busca_like),
                NotaFiscal.chave_acesso.ilike(busca_like)
            )
        )
    if busca_prod:
        busca_prod_like = f'%{busca_prod}%'
        query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.descricao.ilike(busca_prod_like)))
    if cnpj_emitente:
        query = query.filter(NotaFiscal.cnpj_emitente.notin_(cnpj_emitente))
    if cnpj_destinatario:
        query = query.filter(NotaFiscal.cnpj_destinatario.notin_(cnpj_destinatario))
    if cfop:
        query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.notin_(cfop)))
    

    # Usar a nova coluna para o filtro de pagamento
    # Condições que atuam em colunas agregadas devem usar `having`
    if pagamento_filtro == '0':  # Não Pago
        query = query.having(tem_pagamento_column == 0)
    if pagamento_filtro == '1':  # Pago
        query = query.having(tem_pagamento_column == 1)
    if pagamento_filtro == '2':  # Sem upload de envio
        query = query.having(upload_envio_column == 0)
    if pagamento_filtro == '3':  # Com upload de reembolso
        query = query.having(upload_reembolso_column == 1)

    # Este filtro atua sobre uma coluna normal, então continua usando `filter`
    if pagamento_filtro == '4':
        query = query.filter(NotaFiscal.id.in_(ids))

    # Agrupar por ID da nota fiscal para evitar duplicatas (ESSENCIAL para o having funcionar)
    query = query.group_by(NotaFiscal.id)

    # Ordenar por data de emissão
    query = query.order_by(NotaFiscal.data_emissao.desc())

    tfinal = time.time()
    print(f'Tempo de execução1: {tfinal - tinicial} segundos')
    tinicial = time.time()
    #print(f'query: {query}')
    # Aplicar paginação
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    notas = pagination.items

    print('tempo de execução2: qtd='+str(pagination.total)+', tempo='+str(time.time()-tinicial))
    tinicial = time.time()
    # Processar notas para o JSON de resposta
    notas_filtradas = []
    for n in notas:
        try:
            nota_fiscal_obj = n.NotaFiscal
            notas_filtradas.append({
                'doc': '' if n.ReembolsoDocumento is None else {
                    'cc': n.ReembolsoDocumento.centro_custo_id,
                    'descricao': n.ReembolsoDocumento.descricao
                },
                'id': nota_fiscal_obj.id,
                'selecionada': nota_fiscal_obj.id in notas_selecionadas,
                'numero_nf': nota_fiscal_obj.numero_nf,
                'nome_emitente': nota_fiscal_obj.nome_emitente,
                'data_emissao': nota_fiscal_obj.data_emissao.isoformat(),
                'valor_total': float(nota_fiscal_obj.valor_total),
                'pagamento': n.tem_pagamento,
                'upload': n.upload,
                'upload_envio': n.upload_envio,
                'upload_reembolso': n.upload_reembolso,
                'chave_acesso': nota_fiscal_obj.chave_acesso,
            })
        except Exception as e:
            print(f'Erro ao processar nota {n.NotaFiscal.id}: {str(e)}')
            continue
    return notas_filtradas,pagination
def api_get_dados_notas_fiscais(request):
    # Obter parâmetros de filtro
    args = request.args
    busca = args.get('busca', '')
    item_nome = args.get('item_nome', '')
    status_importacao = args.get('status_importacao', '')
    emitente = args.get('emitente', '')
    destinatario = args.get('destinatario', '')
    status_pagamento = args.get('status_pagamento', '')
    data_emissao_inicio = args.get('data_emissao_inicio', '')
    data_emissao_fim = args.get('data_emissao_fim', '')
    tipo_nfe = args.get('tipo_nfe', '')
    origem = args.get('origem', '')  # Novo filtro para origem
    destino = args.get('destino', '')  # Novo filtro para destino
    remetente = args.get('remetente', '')  # Novo filtro para remetente
    status_upload = args.get('status_upload', '')  # Novo filtro de status upload
    # Novos filtros de CNPJ direto (valor exato)
    cnpj_emitente = args.get('cnpj_emitente', '').strip()
    cnpj_destinatario = args.get('cnpj_destinatario', '').strip()
    
    # Instanciar formulário de importação para o modal
    
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
    if emitente:
        if emitente == 'Terceiros':
            query = query.filter(~NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ_FILIAIS))
        elif emitente == 'Matriz':
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ))
        elif emitente == 'Filiais':
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_FILIAIS))
        elif emitente == 'Matriz_Filiais':
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ_FILIAIS))
    if destinatario:
        if destinatario == 'Terceiros':
            query = query.filter(~NotaFiscal.cnpj_destinatario.in_(CNPJS_MATRIZ_FILIAIS))
        if destinatario == 'Matriz':
            query = query.filter(NotaFiscal.cnpj_destinatario.in_(CNPJS_MATRIZ))
        elif destinatario == 'Filiais':
            query = query.filter(NotaFiscal.cnpj_destinatario.in_(CNPJS_FILIAIS))
        elif destinatario == 'Matriz_Filiais':
            query = query.filter(NotaFiscal.cnpj_destinatario.in_(CNPJS_MATRIZ_FILIAIS))
    # Aplicar filtros por CNPJ exato se informados
    if cnpj_emitente:
        query = query.filter(NotaFiscal.cnpj_emitente == cnpj_emitente)
    if cnpj_destinatario:
        query = query.filter(NotaFiscal.cnpj_destinatario == cnpj_destinatario)
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
    if tipo_nfe:
        if tipo_nfe == '0':
            tipo = [0,1]
        elif tipo_nfe == '2':
            tipo = [2]
        elif tipo_nfe == '3':
            tipo = [3]
        query = query.filter(NotaFiscal.tipo.in_(tipo))
        # Filtros extras para CTE
        if tipo_nfe == '2':
            if origem:
                query = query.filter(
                    db.cast(NotaFiscal.dados_adicionais, db.Text).ilike(f'%"municipio_inicio": "{origem}"%')
                )
            if destino:
                query = query.filter(
                    db.cast(NotaFiscal.dados_adicionais, db.Text).ilike(f'%"municipio_destino": "{destino}"%')
                )
            if remetente:
                query = query.filter(
                    db.cast(NotaFiscal.dados_adicionais, db.Text).ilike(f'%"remetente": %"nome": "%{remetente}%"%')
                )
    # Filtro de status de upload
    if status_upload:
        
        if status_upload == '1':
            # Notas com upload tipo arquivei
            query = query.filter(
                db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id, Upload.tipo == 1).exists()
            )
        elif status_upload == '2':
            # Notas com upload tipo protocolo
            query = query.filter(
                db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id, Upload.tipo == 2).exists()
            )
            # Notas com upload tipo 3 (reembolso)
        elif status_upload == '3':
           query = query.filter(
                db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id, Upload.tipo == 3).exists()
            )
        elif status_upload == '4':
            # Notas SEM upload tipo protocolo (tipo 2)
            query = query.filter(
                ~db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id, Upload.tipo == 2).exists()
            )
        
        elif status_upload == '5':
            query = query.filter(~db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id).exists())
    # Ordenar antes de paginar
    query = query.order_by(NotaFiscal.data_emissao.desc(),NotaFiscal.numero_nf.desc())
    
    return query
@nota_fiscal_bp.route('/api/notas-fiscais/ajax', methods=['GET','POST'])
@login_required
def api_get_ajax_notas_fiscais():   
    query = api_get_dados_notas_fiscais(request)
    return jsonify([nota.to_dict() for nota in query.all()])

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

 

    
@nota_fiscal_bp.route('/importar-arquivei', methods=['POST'])
@login_required
def importar_arquivei():
    """
    Importa notas fiscais da API do Arquivei
    """
    print(f'importando notas fiscais da API do Arquivei')
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
            
            # Log para auxiliar no diagnóstic            
            # Validar campos obrigatórios
            if not data_inicial or not data_final:
                flash('Datas inicial e final são obrigatórias!', 'danger')
                return redirect(url_for('nota_fiscal.index'))
            if tipo_documento == 'todos':
                print(f'importando notas fiscais do arquivei: {data_inicial} a {data_final}, tipo: nfe')
                NotaFiscal.importar_arquivei(data_inicial,data_final,'nfe')
                print(f'importando notas fiscais do arquivei: {data_inicial} a {data_final}, tipo: cte')
                NotaFiscal.importar_arquivei(data_inicial,data_final,'cte')
            else:
                print(f'importando notas fiscais do arquivei: {data_inicial} a {data_final}, tipo: {tipo_documento}')
                NotaFiscal.importar_arquivei(data_inicial,data_final,tipo_documento)

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
        upload = Upload.query.get_or_404(id)
        if upload:
            response = make_response(base64.b64decode(upload.blob))
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename=documento_{upload.id}.pdf'
            return response
        else:
            return 'PDF não encontrado para esta nota.', 404
    except Exception as e:
        logger.error(f"Erro ao gerar PDF: {str(e)}")
        flash(f'Erro ao gerar PDF: {str(e)}', 'danger')
        return redirect(url_for('nota_fiscal.index'))
   
@nota_fiscal_bp.route('/xml/<int:id>', methods=['GET'])
@login_required
def gerar_xml(id):
    """
    Gera um XML da nota fiscal para download
    """
    nota = NotaFiscal.query.get_or_404(id)
    return jsonify({'xml': base64.b64decode(nota.xml_data).decode('utf-8')})
   


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
            data = request.get_json()
            itens = data.get('itens')
            print(f"Itens: {itens}")
            # Importar os itens para o estoque
            for item_data in itens:
                
                item_id = item_data.get('item_id')
                material_id = item_data.get('material_id')
                fator_conversao = item_data.get('fator_conversao')
                print(f"Item ID: {item_id}")
                print(f"Material ID: {material_id}")
                print(f"Fator Conversão: {fator_conversao}")
                item1 = NotaFiscalItem.query.get_or_404(item_id)
                print(f"Item: {item1}")
                item1.material_id = material_id
                material = Material.query.get_or_404(material_id)
                
                # Aplicar fator de conversão se fornecido, senão verificar se as unidades são iguais
                if not fator_conversao or fator_conversao== None :
                    if comparar_unidades(item1.unidade, material.unidade_obj.nome):
                        fator_conversao = 1
                    else:
                        fator_conversao = None
                item1.vincular(fator_conversao,material_id)
                item1.vincular_e_importar_estoque_todos()
                
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
    print(f'vinculando material ao item: {item_id}')
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
        material.ncm = item.ncm
        material.save()
        cnpj_emitente = item.nota_fiscal.cnpj_emitente
        
        notas_fiscais = NotaFiscal.query.\
            filter(NotaFiscal.cnpj_emitente==cnpj_emitente).all()
        print(f'notas_fiscais: {len(notas_fiscais)}')
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

@nota_fiscal_bp.route('/api/desvincular-material/<int:item_id>', methods=['POST'])
@login_required
def api_desvincular_material(item_id):
    """
    API para desvincular um material de um item de nota fiscal
    Também exclui a movimentação de estoque gerada e procura outros itens iguais para fazer o mesmo
    """
    try:
        from models.estoque import MovimentacaoEstoque
        
        # Obter o item da nota fiscal
        item = NotaFiscalItem.query.get_or_404(item_id)
        
        # Verificar se há material vinculado
        if not item.material_id:
            return jsonify({
                'success': False,
                'message': 'Item não possui material vinculado'
            }), 400
        
        # Armazenar informações antes de desvincular (para buscar itens iguais)
        material_id = item.material_id
        material_nome = item.material.nome if item.material else 'Material'
        codigo_item = item.codigo
        descricao_item = item.descricao
        
        # Set para armazenar IDs de itens já encontrados (evitar duplicatas)
        ids_itens_encontrados = {item_id}
        itens_iguais = []
        
        # Buscar outros itens iguais (mesmo código ou descrição e mesmo material_id)
        # Buscar por código se existir
        if codigo_item:
            itens_por_codigo = NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo_item,
                NotaFiscalItem.material_id == material_id,
                NotaFiscalItem.id != item_id
            ).all()
            for item_encontrado in itens_por_codigo:
                if item_encontrado.id not in ids_itens_encontrados:
                    itens_iguais.append(item_encontrado)
                    ids_itens_encontrados.add(item_encontrado.id)
        
        # Buscar por descrição (evitar duplicatas)
        if descricao_item:
            itens_por_descricao = NotaFiscalItem.query.filter(
                NotaFiscalItem.descricao == descricao_item,
                NotaFiscalItem.material_id == material_id,
                NotaFiscalItem.id != item_id
            ).all()
            # Adicionar apenas itens que não estão na lista de código
            for item_desc in itens_por_descricao:
                if item_desc.id not in ids_itens_encontrados:
                    itens_iguais.append(item_desc)
                    ids_itens_encontrados.add(item_desc.id)
        
        # Processar o item atual e os itens iguais
        todos_itens = [item] + itens_iguais
        itens_processados = []
        
        for item_processar in todos_itens:
            # Excluir movimentação de estoque se existir
            if item_processar.movimentacao_estoque_id:
                movimentacao = MovimentacaoEstoque.query.get(item_processar.movimentacao_estoque_id)
                if movimentacao:
                    try:
                        # Reverter a movimentação no estoque manualmente (sem commit)
                        if movimentacao.estoque:
                            if movimentacao.tipo_movimento == 'entrada':
                                movimentacao.estoque.quantidade -= movimentacao.quantidade
                            elif movimentacao.tipo_movimento == 'saida':
                                movimentacao.estoque.quantidade += movimentacao.quantidade
                            
                            # Garante que a quantidade nunca será negativa
                            if movimentacao.estoque.quantidade < 0:
                                movimentacao.estoque.quantidade = 0
                            
                            db.session.add(movimentacao.estoque)
                        
                        # Marcar movimentação para exclusão
                        db.session.delete(movimentacao)
                        logger.info(f'Movimentação {movimentacao.id} marcada para exclusão e estoque revertido')
                    except Exception as e:
                        logger.error(f'Erro ao processar movimentação {item_processar.movimentacao_estoque_id}: {str(e)}')
                        raise
            
            # Desvincular o material
            item_processar.material_id = None
            item_processar.fator_conversao_aplicado = None
            item_processar.movimentacao_estoque_id = None
            item_processar.importado_estoque = False
            item_processar.data_importacao_estoque = None
            item_processar.usuario_importacao_id = None
            item_processar.status_importacao = 'Pendente'
            db.session.add(item_processar)
            itens_processados.append(item_processar.id)
        
        # Fazer commit de todas as alterações de uma vez
        db.session.commit()
        
        # Montar mensagem de sucesso
        total_itens = len(itens_processados)
        if total_itens == 1:
            mensagem = f'Material {material_nome} desvinculado com sucesso do item'
        else:
            mensagem = f'Material {material_nome} desvinculado de {total_itens} item(ns) e movimentações de estoque excluídas'
            
        return jsonify({
            'success': True,
            'message': mensagem,
            'itens_processados': total_itens
        })
    
    except Exception as e:
        logger.error(f'Erro ao desvincular material: {str(e)}')
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erro ao desvincular material: {str(e)}'
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
                'material_unidade': Material.query.get(material_id).unidade_obj.nome if material_id else None,
                'material_nome': Material.query.get(material_id).nome if material_id else None,
                'importado_estoque': item.importado_estoque,
                'data_importacao_estoque': item.data_importacao_estoque.isoformat() if item.data_importacao_estoque else None,
                'vinculacao_automatica': vinculacao_automatica,
                'importacao_automatica': importacao_automatica,
                'fator_conversao_aplicado': item.fator_conversao_aplicado
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
        data = request.get_json()
        logger.info(f'API para aplicar conversão de unidades ao vincular material a item de nota fiscal')
        logger.info(f'request.form: {data}')
        
        # Obter dados do formulário
        item_id = data.get('item_id')
        material_id = data.get('material_id')
        fator_conversao = data.get('fator_conversao')
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
                                                NotaFiscal.data_emissao>=datetime.now()-relativedelta(months=3))\
                                                .all()
        
        itens_importados = 0
        notas_processadas = 0
        notas_importadas = 0
        notas_canceladas = 0
        # Para cada nota fiscal
        total_notas = len(notas_fiscais)
        print(f'total_notas: {total_notas}')
        for nota_fiscal in notas_fiscais:
            notas_processadas += 1
            if False: #(Arquivei(chave_acesso=nota_fiscal.chave_acesso,cancelamento=True).cancelada):
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
        query = query.group_by(Material.id, Material.nome, Material.unidade_id)
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
            unidade_referencia = material_obj.unidade_obj.nome
            logger.debug(f"Buscando histórico para Material ID: {material_id}, Unidade Padrão: {unidade_referencia}")

        # Query base para buscar itens individuais e dados da NF
        query = db.session.query(
            NotaFiscalItem.quantidade,
            NotaFiscalItem.valor_unitario,
            NotaFiscalItem.valor_total, # Necessário para recalcular valor unitário
            NotaFiscalItem.unidade.label('unidade_item_nf'), # Renomear para clareza
            NotaFiscalItem.fator_conversao_aplicado,
            NotaFiscal.data_emissao,
            NotaFiscal.numero_nf,
            NotaFiscal.nome_emitente,
            NotaFiscal.id.label('nota_id'), # ID da nota fiscal para visualizar documentos
            NotaFiscalItem.material_id # Selecionar para referência
        ).join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)

        if data_inicio_str:
            try:
                data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
                query = query.filter(NotaFiscal.data_emissao >= data_inicio)
            except ValueError:
                return jsonify({"error": "Formato de data inválido para Data Início."}), 400
        if data_fim_str:    
            try:
                data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
                query = query.filter(NotaFiscal.data_emissao <= data_fim)
            except ValueError:
                return jsonify({"error": "Formato de data inválido para Data Fim."}), 400
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
            if tipo == 'material' and item.fator_conversao_aplicado is not None:
                logger.debug(f"Tentando conversão: De {item.unidade_item_nf} para {unidade_referencia} para Material {material_id}")
               
                try:
                    fator = Decimal(item.fator_conversao_aplicado)
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
                
            
            # Adicionar ao resultado formatado
            historico_formatado.append({
                "quantidade": float(quantidade_final) if quantidade_final is not None else 0,
                "valor_unitario": float(valor_unitario_final) if valor_unitario_final is not None else 0,
                "unidade": unidade_final,
                "data_emissao": item.data_emissao.strftime('%Y-%m-%d') if item.data_emissao else None,
                "numero_nf": item.numero_nf,
                "nome_emitente": item.nome_emitente,
                "nota_id": item.nota_id, # ID da nota fiscal para visualizar documentos
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
    Exibe análise de transferências de itens (notas fiscais) com filtros de data, código, nome do item, CNPJ emitente e destinatário (permitindo múltiplos).
    """
    from sqlalchemy import and_
    from models.nota_fiscal import NotaFiscal, NotaFiscalItem
    page = request.args.get('page', 1, type=int)
    per_page = 25
    filtro_data_inicio = request.args.get('data_inicio', '')
    filtro_data_fim = request.args.get('data_fim', '')
    filtro_codigo_item = request.args.get('codigo_item', '')
    filtro_nome_item = request.args.get('nome_item', '')
    filtro_cnpj_emitente = request.args.get('cnpj_emitente', '')
    filtro_cnpj_destinatario = request.args.get('cnpj_destinatario', '')

    # Receber os filtros de CNPJ como arrays (para múltipla seleção do select2)
    cnpjs_emitente = request.args.getlist('cnpj_emitente')
    cnpjs_destinatario = request.args.getlist('cnpj_destinatario')

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
    if cnpjs_emitente:
        query = query.filter(NotaFiscal.cnpj_emitente.in_(cnpjs_emitente))
    if cnpjs_destinatario:
        query = query.filter(NotaFiscal.cnpj_destinatario.in_(cnpjs_destinatario))

    query = query.order_by(NotaFiscal.data_emissao.desc())
    paginacao = query.paginate(page=page, per_page=per_page, error_out=False)
    transferencias = paginacao.items

    # Buscar CNPJs distintos para os dropdowns
    cnpjs_emitentes_lista = db.session.query(NotaFiscal.cnpj_emitente).distinct().order_by(NotaFiscal.cnpj_emitente).all()
    cnpjs_destinatarios_lista = db.session.query(NotaFiscal.cnpj_destinatario).distinct().order_by(NotaFiscal.cnpj_destinatario).all()
    cnpjs_emitentes = [c[0] for c in cnpjs_emitentes_lista if c[0]]
    cnpjs_destinatarios = [c[0] for c in cnpjs_destinatarios_lista if c[0]]

    return render_template(
        'notas_fiscais/analise_transferencias.html',
        transferencias=transferencias,
        paginacao=paginacao,
        filtro_data_inicio=filtro_data_inicio,
        filtro_data_fim=filtro_data_fim,
        filtro_codigo_item=filtro_codigo_item,
        filtro_nome_item=filtro_nome_item,
        filtro_cnpj_emitente=cnpjs_emitente,
        filtro_cnpj_destinatario=cnpjs_destinatario,
        cnpjs_emitentes=cnpjs_emitentes,
        cnpjs_destinatarios=cnpjs_destinatarios
    )

@nota_fiscal_bp.route('/api/documentos/<int:nota_id>', methods=['GET'])
@login_required
def api_listar_documentos(nota_id):
    """
    API para listar documentos de uma nota fiscal
    """
    try:
        documentos = db.session.query(Upload.id,Upload.filename,Upload.tipo,Upload.uploaded_at).filter_by(pai='NotaFiscal', pai_id=nota_id).all()
        resultado = []
        nota = NotaFiscal.query.get(nota_id)
        if nota:
            resultado.append({
                'id': nota.id,
                'filename': f'nf {nota.numero_nf}.xml',
                'tipo': 10,
                'uploaded_at': nota.data_importacao.isoformat()
            })
        if not documentos:
                nota.get_pdf()
                
        for doc in documentos:
            resultado.append({
                'id': doc[0],
                'filename': doc[1],
                'tipo': doc[2],
                'uploaded_at': doc[3].isoformat()
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

@nota_fiscal_bp.route('/api/documentos/<int:doc_id>/download')
@login_required
def api_download_documento(doc_id):
    """
    API para fazer download de um documento
    """
    try:
        documento = Upload.query.filter(Upload.id==doc_id).first()
        response = make_response(base64.b64decode(documento.blob))
        response.headers['Content-Type'] = documento.mimetype
        response.headers['Content-Disposition'] = f'attachment; filename={documento.filename}'
        return response
    except Exception as e:
        logger.error(f'Erro ao fazer download do documento: {str(e)}')
        return jsonify({'error': f'Erro ao fazer download do documento: {str(e)}'}), 500

@nota_fiscal_bp.route('/exportar-excel')
@login_required
def exportar_excel():
    """
    Exporta as notas fiscais filtradas para um arquivo Excel.
    """
    # Obter filtros da query string 
    busca = request.args.get('busca', '')
    item_nome = request.args.get('item_nome', '')
    status_importacao = request.args.get('status_importacao', '')
    cnpj_emitente = request.args.get('cnpj_emitente', '')
    cnpj_emitente_val = request.args.get('cnpj_emitente_val', '').strip()
    cnpj_destinatario_val = request.args.get('cnpj_destinatario_val', '').strip()
    status_pagamento = request.args.get('status_pagamento', '')
    data_emissao_inicio = request.args.get('data_emissao_inicio', '')
    data_emissao_fim = request.args.get('data_emissao_fim', '')
    tipo_nfe = request.args.get('tipo_nfe', '')
    status_upload = request.args.get('status_upload', '')
    print("request: ", request.args)
    print("exportando excel")

    query = NotaFiscal.query
    if busca:
        busca_like = f'%{busca}%'
        query = query.filter(
            or_(
                NotaFiscal.numero_nf.ilike(busca_like),
                NotaFiscal.nome_emitente.ilike(busca_like),
                NotaFiscal.chave_acesso.ilike(busca_like)
            )
        )
    if item_nome:
        query = query.join(NotaFiscalItem).filter(
            NotaFiscalItem.descricao.ilike(f'%{item_nome}%')
        )
    if status_importacao == 'pendentes':
        query = query.filter(~NotaFiscal.itens.any(NotaFiscalItem.importado_estoque == True))
    if cnpj_emitente:
        if cnpj_emitente == 'proprio':
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS))
        elif cnpj_emitente == 'terceiros':
            query = query.filter(~NotaFiscal.cnpj_emitente.in_(CNPJS))
    # Novos filtros diretos de CNPJ
    if cnpj_emitente_val:
        query = query.filter(NotaFiscal.cnpj_emitente == cnpj_emitente_val)
    if cnpj_destinatario_val:
        query = query.filter(NotaFiscal.cnpj_destinatario == cnpj_destinatario_val)
    if data_emissao_inicio:
        data_inicio = datetime.strptime(data_emissao_inicio, '%Y-%m-%d')
        query = query.filter(NotaFiscal.data_emissao >= data_inicio)

    if data_emissao_fim:

        data_fim = datetime.strptime(data_emissao_fim, '%Y-%m-%d')
        query = query.filter(NotaFiscal.data_emissao <= data_fim)
    if tipo_nfe:
        if tipo_nfe == '0':
            tipo = [0,1]
        elif tipo_nfe == '2':
            tipo = [2]
        elif tipo_nfe == '3':
            tipo = [3]
        query = query.filter(NotaFiscal.tipo.in_(tipo))
    if status_upload:
        if status_upload == '1':
            query = query.filter(
                db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id, Upload.tipo == 1).exists()
            )
        elif status_upload == '2':
            query = query.filter(
                db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id, Upload.tipo == 2).exists()
            )
        elif status_upload == '3':
            query = query.filter(
                db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id, Upload.tipo == 3).exists()
            )
        elif status_upload == '4':
            query = query.filter(~db.session.query(Upload.id).filter(Upload.pai == 'NotaFiscal', Upload.pai_id == NotaFiscal.id).exists())
    query = query.order_by(NotaFiscal.data_emissao.desc(),NotaFiscal.numero_nf.desc())
    notas = query.all()
    # Montar os dados para o DataFrame
    dados = []
    print("montando dados tamanho", len(notas))
    for nf in notas:
        # Determinar status de upload
        uploads = db.session.query(Upload.pai_id,Upload.pai,Upload.tipo).filter_by(pai_id=nf.id, pai='NotaFiscal').all()
        status_upload = []
        if uploads:
            if any(u[2] == 1 for u in uploads):
                status_upload.append('Arquivei')
            if any(u[2] == 2 for u in uploads):
                status_upload.append('Protocolo')
            if any(u[2] == 3 for u in uploads):
                status_upload.append('Reembolso')
        else:
            status_upload.append('Nenhum')
        dados.append({
            'Fornecedor': nf.nome_emitente,
            'Número': nf.numero_nf,
            'Tipo': 'NFe' if nf.tipo in [0,1] else ('CTE' if nf.tipo == 2 else 'NFSe'),
            'Chave de Acesso': nf.chave_acesso,
            'Data': nf.data_emissao.strftime('%d/%m/%Y') if nf.data_emissao else '',
            'Valor': float(nf.valor_total) if nf.valor_total is not None else 0.0,
            'Status Upload': ', '.join(status_upload)
        })
    print("montando dataframe")
    df = pd.DataFrame(dados)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Notas Fiscais')
    output.seek(0)
    return send_file(output, download_name='notas_fiscais.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@nota_fiscal_bp.route('/analise-transferencias/ajax')
@login_required
def analise_transferencias_ajax():
    """
    Retorna apenas a tabela de transferências (HTML) para uso com AJAX.
    """
    from sqlalchemy import and_
    from models.nota_fiscal import NotaFiscal, NotaFiscalItem
    page = request.args.get('page', 1, type=int)
    per_page = 25
    filtro_data_inicio = request.args.get('data_inicio', '').strip() or ''
    filtro_data_fim = request.args.get('data_fim', '').strip() or ''
    filtro_codigo_item = request.args.get('codigo_item', '')
    filtro_nome_item = request.args.get('nome_item', '')
    cnpjs_emitente = request.args.getlist('cnpj_emitente')
    cnpjs_destinatario = request.args.getlist('cnpj_destinatario')

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
    if cnpjs_emitente:
        query = query.filter(NotaFiscal.cnpj_emitente.in_(cnpjs_emitente))
    if cnpjs_destinatario:
        query = query.filter(NotaFiscal.cnpj_destinatario.in_(cnpjs_destinatario))

    query = query.order_by(NotaFiscal.data_emissao.desc())
    paginacao = query.paginate(page=page, per_page=per_page, error_out=False)
    transferencias = paginacao.items

    return render_template(
        'notas_fiscais/_tabela_transferencias.html',
        transferencias=transferencias,
        paginacao=paginacao,
        filtro_data_inicio=filtro_data_inicio,
        filtro_data_fim=filtro_data_fim,
        filtro_codigo_item=filtro_codigo_item,
        filtro_nome_item=filtro_nome_item,
        filtro_cnpj_emitente=cnpjs_emitente,
        filtro_cnpj_destinatario=cnpjs_destinatario
    )

@nota_fiscal_bp.route('/exportar-zip', methods=['GET'])
@login_required
def exportar_zip():
    print('exportar zip')
    query = api_get_dados_notas_fiscais(request)
    notas = query.all()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        excel_data = []
        for nota in notas:
            if nota.tipo < 2:
                chave_acesso, dados_nota = nota.extrair_dados_xml_nfe()
                tipo = 'NFe'
            elif nota.tipo == 2:
                chave_acesso, dados_nota = nota.extrair_dados_xml_cte()
                tipo = 'CTe'
            xml_bytes = base64.b64decode(nota.xml_data)
            data_emissao = nota.data_emissao.strftime('%d_%m_%Y') if nota.data_emissao else ''
            zipf.writestr(f'{tipo} {data_emissao}_{nota.nome_emitente}_{nota.numero_nf}.xml', xml_bytes)
            
            excel_data.append({
                'Data': nota.data_emissao.strftime('%d/%m/%Y') if nota.data_emissao else '',
                'Fornecedor': nota.nome_emitente,
                'Número': nota.numero_nf,
                'Tipo': 'NFe' if nota.tipo in [0,1] else ('CTE' if nota.tipo == 2 else 'NFSe'),
                'CST': dados_nota['impostos']['CST'] if 'CST' in dados_nota['impostos'] else '',
                'vIPI': dados_nota['impostos']['vIPI'] if 'vIPI' in dados_nota['impostos'] else '',
                'vPIS': dados_nota['impostos']['vPIS'] if 'vPIS' in dados_nota['impostos'] else '',
                'vCOFINS': dados_nota['impostos']['vCOFINS'] if 'vCOFINS' in dados_nota['impostos'] else '',
                'vICMS': dados_nota['impostos']['vICMS'] if 'vICMS' in dados_nota['impostos'] else '',
                'Valor': float(nota.valor_total) if nota.valor_total is not None else 0.0,
                'Chave de Acesso': nota.chave_acesso,
                'tipo': dados_nota['tipo'],
                'cnpj_emitente': nota.cnpj_emitente,
                'cnpj_destinatario': nota.cnpj_destinatario,
                })
        df = pd.DataFrame(excel_data)
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, sheet_name='Notas Fiscais')
        excel_buffer.seek(0)
        zipf.writestr('notas_fiscais.xlsx', excel_buffer.read())

    zip_buffer.seek(0)
    return send_file(zip_buffer, download_name='notas_fiscais.zip', as_attachment=True, mimetype='application/zip')

@nota_fiscal_bp.route('/total-notas', methods=['GET'])
@login_required
def total_notas():
    """Retorna o total de notas fiscais com os filtros aplicados"""
    try:
        # Obter query com filtros aplicados
        query = api_get_dados_notas_fiscais(request)
        
        # Contar total de notas
        total = query.count()
        
        return jsonify({
            'total_notas': total
        })
    except Exception as e:
        logger.error(f'Erro ao obter total de notas: {str(e)}')
        return jsonify({'error': 'Erro ao obter total de notas', 'total_notas': 0}), 500

@nota_fiscal_bp.route('/estatisticas-pdfs', methods=['GET'])
@login_required
def estatisticas_pdfs():
    """Retorna estatísticas de PDFs das notas fiscais com os filtros aplicados"""
    try:
        inicio = time.time()
        # Obter query com filtros aplicados
        query = api_get_dados_notas_fiscais(request)
        
        # Obter apenas os IDs das notas filtradas
        nota_ids = [nf.id for nf in query.with_entities(NotaFiscal.id).all()]
        print(f'query ids: {time.time() - inicio}')
        
        if not nota_ids:
            return jsonify({
                'total_pdfs_originais': 0,
                'total_pdfs_protocolo': 0,
                'total_sem_protocolo': 0,
                'total_pdfs_reembolso': 0,
                'total_notas': 0,
                'notas_sem_original_ids': []
            })
        
        # Contar todos os tipos de PDFs em uma única query usando CASE WHEN
        stats = db.session.query(
            func.sum(case((Upload.tipo == 1, 1), else_=0)).label('total_pdfs_originais'),
            func.sum(case((Upload.tipo == 2, 1), else_=0)).label('total_pdfs_protocolo'),
            func.sum(case((Upload.tipo == 3, 1), else_=0)).label('total_pdfs_reembolso'),
            func.count(func.distinct(case((Upload.tipo == 2, Upload.pai_id), else_=None))).label('notas_com_protocolo')
        ).filter(
            Upload.pai == 'NotaFiscal',
            Upload.pai_id.in_(nota_ids)
        ).first()
        
        total_pdfs_originais = stats.total_pdfs_originais or 0
        total_pdfs_protocolo = stats.total_pdfs_protocolo or 0
        total_pdfs_reembolso = stats.total_pdfs_reembolso or 0
        notas_com_protocolo = stats.notas_com_protocolo or 0
        total_notas = len(nota_ids)
        total_sem_protocolo = total_notas - notas_com_protocolo
        
        # Buscar IDs das notas sem PDFs originais usando NOT EXISTS
        notas_sem_original = db.session.query(NotaFiscal.id).filter(
            NotaFiscal.id.in_(nota_ids),
            ~db.session.query(Upload.id).filter(
                Upload.pai == 'NotaFiscal',
                Upload.pai_id == NotaFiscal.id,
                Upload.tipo == 1
            ).exists()
        ).all()
        
        # Converter para lista de IDs
        notas_sem_original_ids = [row[0] for row in notas_sem_original]
        
        print(f'query estatisticas: {time.time() - inicio}')
        
        return jsonify({
            'total_pdfs_originais': total_pdfs_originais,
            'total_pdfs_protocolo': total_pdfs_protocolo,
            'total_sem_protocolo': total_sem_protocolo,
            'total_pdfs_reembolso': total_pdfs_reembolso,
            'total_notas': total_notas,
            'notas_sem_original_ids': notas_sem_original_ids
        })
    except Exception as e:
        logger.error(f'Erro ao obter estatísticas de PDFs: {str(e)}')
        return jsonify({'error': 'Erro ao obter estatísticas'}), 500

@nota_fiscal_bp.route('/download-pdfs-sem-protocolo', methods=['GET'])
@login_required
def download_pdfs_sem_protocolo():
    """Faz download de um ZIP com os PDFs originais que não têm protocolo, baixando do Arquivei se necessário"""
    try:
        # Obter query com filtros aplicados
        query = api_get_dados_notas_fiscais(request)
        notas = query.all()
        
        # Criar buffer para o ZIP
        zip_buffer = io.BytesIO()
        
        pdfs_adicionados = 0
        pdfs_baixados = 0
        erros = []
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for nota in notas:
                try:
                    # Verificar se não tem protocolo (tipo 2)
                    tem_protocolo = db.session.query(Upload.id).filter(
                        Upload.pai == 'NotaFiscal',
                        Upload.pai_id == nota.id,
                        Upload.tipo == 2
                    ).first() is not None
                    
                    # Se tem protocolo, pular esta nota
                    if tem_protocolo:
                        continue
                    
                    # Buscar PDF original (tipo 1) no banco
                    upload_original = db.session.query(Upload).filter(
                        Upload.pai == 'NotaFiscal',
                        Upload.pai_id == nota.id,
                        Upload.tipo == 1
                    ).first()
                    
                    pdf_bytes = None
                    
                    # Se não tem PDF original no banco, baixar do Arquivei
                    if not upload_original:
                        if not nota.chave_acesso:
                            logger.warning(f'Nota {nota.id} não tem chave de acesso para baixar PDF')
                            erros.append(f'Nota {nota.numero_nf}: sem chave de acesso')
                            continue
                        
                        try:
                            # Baixar PDF do Arquivei (detecta automaticamente se é NFe ou CTE pela chave de acesso)
                            arquivei = Arquivei(chave_acesso=nota.chave_acesso)
                            
                            if arquivei.pdf:
                                # Decodificar o PDF base64
                                pdf_bytes = base64.b64decode(arquivei.pdf)
                                
                                # Salvar no banco de dados
                                filename = f'{nota.chave_acesso}.pdf'
                                upload_original = Upload(
                                    pai='NotaFiscal',
                                    pai_id=nota.id,
                                    tipo=1,
                                    filename=filename,
                                    mimetype='application/pdf',
                                    blob=arquivei.pdf  # Já está em base64
                                )
                                db.session.add(upload_original)
                                db.session.commit()
                                
                                pdfs_baixados += 1
                                logger.info(f'PDF baixado e salvo no banco para nota {nota.id} - {nota.chave_acesso}')
                            else:
                                logger.warning(f'PDF não encontrado no Arquivei para nota {nota.id} - {nota.chave_acesso}')
                                erros.append(f'Nota {nota.numero_nf}: PDF não encontrado no Arquivei')
                                continue
                        except Exception as e:
                            logger.error(f'Erro ao baixar PDF do Arquivei para nota {nota.id}: {str(e)}')
                            erros.append(f'Nota {nota.numero_nf}: Erro ao baixar PDF - {str(e)}')
                            db.session.rollback()
                            continue
                    else:
                        # Se já tem PDF no banco, decodificar
                        try:
                            pdf_bytes = base64.b64decode(upload_original.blob)
                        except Exception as e:
                            logger.error(f'Erro ao decodificar PDF da nota {nota.id}: {str(e)}')
                            erros.append(f'Nota {nota.numero_nf}: Erro ao decodificar PDF')
                            continue
                    
                    # Adicionar ao ZIP
                    if pdf_bytes:
                        data_emissao = nota.data_emissao.strftime('%Y%m%d') if nota.data_emissao else 'semdata'
                        nome_arquivo = f'{nota.numero_nf}_{data_emissao}_{nota.chave_acesso}.pdf'
                        zipf.writestr(nome_arquivo, pdf_bytes)
                        pdfs_adicionados += 1
                        
                except Exception as e:
                    logger.error(f'Erro ao processar PDF da nota {nota.id}: {str(e)}')
                    erros.append(f'Nota {nota.numero_nf}: {str(e)}')
                    continue
        
        if pdfs_adicionados == 0:
            mensagem = 'Nenhum PDF original sem protocolo foi encontrado com os filtros aplicados.'
            if erros:
                mensagem += f' Erros: {", ".join(erros[:5])}'  # Mostrar até 5 erros
            flash(mensagem, 'warning')
            return redirect(url_for('nota_fiscal.index'))
        
        mensagem_sucesso = f'{pdfs_adicionados} PDF(s) adicionado(s) ao ZIP.'
        if pdfs_baixados > 0:
            mensagem_sucesso += f' {pdfs_baixados} PDF(s) baixado(s) do Arquivei e salvos no banco.'
        if erros:
            mensagem_sucesso += f' {len(erros)} erro(s) durante o processamento.'
        flash(mensagem_sucesso, 'success')
        
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            download_name=f'pdfs_sem_protocolo_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
            as_attachment=True,
            mimetype='application/zip'
        )
    except Exception as e:
        logger.error(f'Erro ao gerar ZIP de PDFs: {str(e)}')
        flash('Erro ao gerar arquivo ZIP. Por favor, tente novamente.', 'danger')
        return redirect(url_for('nota_fiscal.index'))

@nota_fiscal_bp.route('/tabela-notas-fiscais')
@login_required
def tabela_notas_fiscais():
    inicio = time.time()
    print("tabela notas fiscais")
    page = request.args.get('page', 1, type=int)
    per_page = 50
    query = api_get_dados_notas_fiscais(request)
    print(f'query {time.time() - inicio}')
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    notas_fiscais_pagina = pagination.items
    notas_fiscais_pagina_upload = []
    print(f'notas_fiscais_pagina len:{len(notas_fiscais_pagina)} {time.time() - inicio}')
    for nota in notas_fiscais_pagina:
        nota.upload = None
        nota.pago = False
        nota.emitente = ('Matriz' if nota.cnpj_emitente in CNPJS_MATRIZ else 'Filiais' if nota.cnpj_emitente in CNPJS_FILIAIS else 'Terceiros')
        nota.destinatario = ('Matriz' if nota.cnpj_destinatario in CNPJS_MATRIZ else 'Filiais' if nota.cnpj_destinatario in CNPJS_FILIAIS else 'Terceiros')
        dadosAnaliticos = db.session.query(DadoAnalitico.id).filter(DadoAnalitico.data_pagamento >= nota.data_emissao,\
                                                           DadoAnalitico.documento.ilike(f'%{nota.numero_nf}%'),\
                                                           DadoAnalitico.valor == nota.valor_total).first()
        if dadosAnaliticos:
            nota.pago = True
        nota.uploads = {'arquivei':False,'protocolo':False,'reembolso':False,'total':0}
        uploads = db.session.query(Upload.pai_id,Upload.pai,Upload.tipo).filter(Upload.pai_id==nota.id, Upload.pai=='NotaFiscal').all()
        if uploads:
            nota.uploads['arquivei'] = any(u[2] == 1 for u in uploads)
            nota.uploads['protocolo'] = any(u[2] == 2 for u in uploads)
            nota.uploads['reembolso'] = any(u[2] == 3 for u in uploads)
            nota.uploads['total'] = len(uploads)
        notas_fiscais_pagina_upload.append(nota)

    print(f'tabela notas fiscais {time.time() - inicio}')
    return render_template('notas_fiscais/notas_tabela.html', pagination=pagination, notas_fiscais=notas_fiscais_pagina_upload,total_resultados=len(notas_fiscais_pagina_upload))