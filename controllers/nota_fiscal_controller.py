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
import sqlalchemy
from sqlalchemy import func, or_, case, distinct, and_, exists, select, text, Integer # Adicionar distinct, exists e select
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
from models.nota_fiscal import CNPJS_MATRIZ_FILIAIS,CNPJS_MATRIZ,CNPJS_FILIAIS,CFOPS_COMPRA,CFOPS_VENDA,CFOPS_TRANSFERENCIA
from models.dados_analiticos import DadoAnalitico
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import pandas as pd
import io
from models.reembolso import ReembolsoDocumento
from models.plano_conta import PlanoConta

# Import WeasyPrint para geração de PDF
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

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

def atualizar_dados_adicionais():
    """
    Atualiza dados adicionais das notas fiscais processando em blocos de 100 registros.
    """
    TAMANHO_BLOCO = 500
    total_notas = NotaFiscal.query.count()
    total_processadas = 0
    
    logger.info(f'Iniciando atualização de dados adicionais. Total de notas: {total_notas}')
    
    # Processa em blocos de 100
    offset = 0
    while offset < total_notas:
        # Busca bloco de 100 notas
        notas = NotaFiscal.query.offset(offset).limit(TAMANHO_BLOCO).all()
        
        if not notas:
            break
        
        # Processa cada nota do bloco
        for nota in notas:
            try:
                if nota.tipo == 2:
                    chave_acesso, dados = nota.extrair_dados_xml_cte()
                    nota.dados_adicionais = json.dumps(dados.get('dados_adicionais'), ensure_ascii=False)
                    #print(f'dados_adicionais: {nota.dados_adicionais}')
                    nota.save()
                elif nota.tipo < 2:
                    chave_acesso, dados = nota.extrair_dados_xml_nfe()
                    nota.dados_adicionais = json.dumps(dados.get('dados_adicionais'), ensure_ascii=False)
                    #print(f'dados_adicionais: {nota.dados_adicionais}')
                    nota.save()
                total_processadas += 1
            except Exception as e:
                logger.error(f'Erro ao processar nota ID {nota.id}: {e}')
                continue
        
        # Commit do bloco
        try:
            db.session.commit()
            logger.info(f'Bloco processado: {total_processadas}/{total_notas} notas (offset: {offset})')
        except Exception as e:
            logger.error(f'Erro ao fazer commit do bloco (offset: {offset}): {e}')
            db.session.rollback()
        
        offset += TAMANHO_BLOCO
    
    logger.info(f'Atualização concluída. Total processado: {total_processadas}/{total_notas} notas')

@nota_fiscal_bp.route('/teste2')
@login_required
def teste2():
    print('teste2')
    processar_emails()
    return redirect(url_for('nota_fiscal.index'))

@nota_fiscal_bp.route('/teste3')
@login_required
def rota_atualizar_dados_adicionais():
    print('atualizar_dados_adicionais')
    atualizar_dados_adicionais()
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
    # Normalizar documento para comparação (remover pontos e zeros à esquerda)
    # Isso é usado apenas como referência, pois não usamos mais OUTER JOIN
    # Mas mantido para compatibilidade caso seja usado em outro lugar
    documento_normalizado_join = func.ltrim(
        func.replace(DadoAnalitico.documento, '.', ''),
        '0'
    )
    numero_nf_normalizado_join = func.ltrim(NotaFiscal.numero_nf, '0')
    
    join_conditions_pagamento = and_(
        NotaFiscal.valor_total == DadoAnalitico.valor,
        documento_normalizado_join.like(func.concat(numero_nf_normalizado_join, '%'))
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
    tipo_operacao = args.get('tipo_operacao', '')  # Novo filtro de tipo de operação (Compra, Venda, Transferência)
    # Novos filtros de CNPJ direto (valor exato)
    cnpj_emitente = args.get('cnpj_emitente', '').strip()
    cnpj_destinatario = args.get('cnpj_destinatario', '').strip()
    
    # Instanciar formulário de importação para o modal

    # OTIMIZAÇÃO: Usar subqueries ao invés de OUTER JOINs para evitar multiplicação de linhas
    # Isso evita que uma nota com múltiplos DadoAnalitico ou Uploads crie múltiplas linhas
    
    # Subquery para verificar se tem pagamento (retorna 1 se existe, 0 se não existe)
    # Usa subquery escalar com CASE e EXISTS - mais eficiente que OUTER JOIN
    # EXISTS retorna True/False, então usamos CASE para converter para 1/0
    # Normalizar documento: remover pontos e zeros à esquerda para comparação
    # Exemplo: "000.123" ou "000123" deve comparar com "123"
    documento_normalizado = func.cast(
        func.replace(DadoAnalitico.documento, ".", ""),
        Integer
    )

    # Número da NF convertido para inteiro (remove zeros à esquerda)
    numero_nf_normalizado = func.cast(NotaFiscal.numero_nf, Integer)

    
    subquery_pagamento_exists = exists(
        select(1).select_from(DadoAnalitico).where(
            and_(
                NotaFiscal.data_emissao <= DadoAnalitico.data_pagamento,
                DadoAnalitico.valor == NotaFiscal.valor_total,
                # Comparar documentos normalizados (sem pontos e zeros à esquerda)
                documento_normalizado == numero_nf_normalizado
            )
        )
    )
    subquery_pagamento = case((subquery_pagamento_exists, 1), else_=0)
    
    # Subqueries para uploads usando EXISTS (mais eficiente que MAX)
    # EXISTS retorna True/False, então usamos CASE para converter para 1/0
    subquery_upload_arquivei_exists = exists(
        select(1).select_from(Upload).where(
            and_(
                Upload.pai_id == NotaFiscal.id,
                Upload.pai == 'NotaFiscal',
                Upload.tipo == 1
            )
        )
    )
    subquery_upload_arquivei = case((subquery_upload_arquivei_exists, 1), else_=0)
    
    subquery_upload_protocolo_exists = exists(
        select(1).select_from(Upload).where(
            and_(
                Upload.pai_id == NotaFiscal.id,
                Upload.pai == 'NotaFiscal',
                Upload.tipo == 2
            )
        )
    )
    subquery_upload_protocolo = case((subquery_upload_protocolo_exists, 1), else_=0)
    
    subquery_upload_reembolso_exists = exists(
        select(1).select_from(Upload).where(
            and_(
                Upload.pai_id == NotaFiscal.id,
                Upload.pai == 'NotaFiscal',
                Upload.tipo == 3
            )
        )
    )
    subquery_upload_reembolso = case((subquery_upload_reembolso_exists, 1), else_=0)
    
    # Subquery para verificar se tem qualquer upload
    subquery_upload_qualquer_exists = exists(
        select(1).select_from(Upload).where(
            and_(
                Upload.pai_id == NotaFiscal.id,
                Upload.pai == 'NotaFiscal'
            )
        )
    )
    subquery_upload_qualquer = case((subquery_upload_qualquer_exists, 1), else_=0)
    
    # Colunas calculadas usando subqueries EXISTS (sem JOINs, sem multiplicação de linhas)
    pagamento_column = subquery_pagamento.label('pagamento')
    upload_column = subquery_upload_qualquer.label('upload')
    upload_arquivei_column = subquery_upload_arquivei.label('upload_arquivei')
    upload_protocolo_column = subquery_upload_protocolo.label('upload_protocolo')
    upload_reembolso_column = subquery_upload_reembolso.label('upload_reembolso')
    
    # Construir query base SEM OUTER JOINs - isso evita multiplicação de linhas
    query = db.session.query(
        NotaFiscal,
        pagamento_column,
        upload_column,
        upload_protocolo_column,
        upload_reembolso_column,
        upload_arquivei_column
    ).select_from(NotaFiscal).filter(NotaFiscal.status_processamento != 'cancelada')
    
    # REMOVIDO: OUTER JOINs que causavam multiplicação de linhas
    # As subqueries acima já calculam os valores necessários
    
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
    
    # Aplicar filtro de tipo de operação (Compra, Venda, Transferência) baseado em CFOP
    if tipo_operacao:
        # Converter CFOPs para string para comparação (CFOP é armazenado como String no banco)
        if tipo_operacao == 'compra':
            cfops_lista = [str(cfop) for cfop in CFOPS_COMPRA]
            query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(cfops_lista)))
        elif tipo_operacao == 'venda':
            cfops_lista = [str(cfop) for cfop in CFOPS_VENDA]
            query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(cfops_lista)))
        elif tipo_operacao == 'transferencia':
            cfops_lista = [str(cfop) for cfop in CFOPS_TRANSFERENCIA]
            query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(cfops_lista)))
    
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
        # Filtros extras para CTE - Otimizado para usar json_extract ao invés de ILIKE
        if tipo_nfe == '2':
            if origem:
                # Usar json_extract é mais eficiente que ILIKE em JSON
                query = query.filter(
                    func.json_extract(NotaFiscal.dados_adicionais, '$.municipio_inicio') == origem
                )
            if destino:
                query = query.filter(
                    func.json_extract(NotaFiscal.dados_adicionais, '$.municipio_destino') == destino
                )
            if remetente:
                # Para remetente, ainda precisa de LIKE pois está aninhado
                query = query.filter(
                    func.json_extract(NotaFiscal.dados_adicionais, '$.remetente.nome').ilike(f'%{remetente}%')
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
    
    # OTIMIZAÇÃO: Não precisamos mais de GROUP BY pois as subqueries retornam apenas 1 valor por nota
    # As subqueries correlacionadas já garantem uma linha por NotaFiscal (sem multiplicação de linhas)
    
    # Filtros de status de pagamento - agora usando WHERE pois são subqueries, não funções agregadas
    if status_pagamento:
        if status_pagamento == 'pago':
            query = query.having(pagamento_column == 1)
        elif status_pagamento == 'nao_pago':
            query = query.having(pagamento_column == 0)
        elif status_pagamento == 'com_faturamento':
            query = query.filter(NotaFiscal.vencimento.isnot(None))
        elif status_pagamento == 'vencido':
            # Comparar string JSON diretamente (formato 'YYYY-MM-DD')
            hoje_str = datetime.now().date().strftime('%Y-%m-%d')
            query = query.filter(
                NotaFiscal.vencimento.isnot(None),
                NotaFiscal.vencimento < hoje_str
            )
        elif status_pagamento == 'vencido_nao_pago':
            # Comparar string JSON diretamente (formato 'YYYY-MM-DD')
            hoje_str = datetime.now().date().strftime('%Y-%m-%d')
            query = query.filter(
                NotaFiscal.vencimento.isnot(None),
                NotaFiscal.vencimento < hoje_str,
                pagamento_column == 0
            )
    
    # Ordenar antes de paginar
    # Obter parâmetros de ordenação
    order_by = args.get('order_by', 'data_emissao')
    order_dir = args.get('order_dir', 'desc')
    
    # Mapear colunas para ordenação
    order_mapping = {
        'numero_nf': NotaFiscal.numero_nf,
        'data_emissao': NotaFiscal.data_emissao,
        'vencimento': NotaFiscal.vencimento,
        'valor_total': NotaFiscal.valor_total,
        'nome_emitente': NotaFiscal.nome_emitente,
        'cnpj_emitente': NotaFiscal.cnpj_emitente,
        'cnpj_destinatario': NotaFiscal.cnpj_destinatario,
    }
    
    # Aplicar ordenação
    if order_by in order_mapping:
        order_column = order_mapping[order_by]
        if order_dir == 'asc':
            query = query.order_by(order_column.asc(), NotaFiscal.id.asc())
        else:
            query = query.order_by(order_column.desc(), NotaFiscal.id.desc())
    else:
        # Ordenação padrão
        query = query.order_by(NotaFiscal.data_emissao.desc(), NotaFiscal.numero_nf.desc())
    
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
            centro_custo_id = data.get('centro_custo_id')
            observacao = data.get('observacao')
            
            if not itens:
                return jsonify({
                    'success': False,
                    'message': 'Nenhum item selecionado para importação.'
                }), 400
            
            # Contar itens antes da operação
            itens_ja_importados = 0
            itens_importados = 0
            itens_com_erro = []
            total_itens_selecionados = len(itens)
            
            # Importar os itens para o estoque
            for item_data in itens:
                item_id = item_data.get('item_id')
                material_id = item_data.get('material_id')
                fator_conversao = item_data.get('fator_conversao')
                
                item1 = NotaFiscalItem.query.get_or_404(item_id)
                
                # Verificar se já estava importado
                if item1.importado_estoque:
                    itens_ja_importados += 1
                    continue
                
                # Verificar se tem material vinculado
                if not material_id:
                    itens_com_erro.append({
                        'item_id': item_id,
                        'descricao': item1.descricao,
                        'erro': 'Item não possui material vinculado'
                    })
                    continue
                
                material = Material.query.get_or_404(material_id)
                
                # Aplicar fator de conversão se fornecido, senão verificar se as unidades são iguais
                if not fator_conversao or fator_conversao == None:
                    if comparar_unidades(item1.unidade, material.unidade_obj.nome):
                        fator_conversao = 1
                    else:
                        fator_conversao = None
                
                # Vincular material se necessário
                if not item1.material_id:
                    item1.vincular(fator_conversao, material_id)
                
                # Importar para o estoque
                try:
                    sucesso, mensagem = item1.importar_para_estoque(
                        usuario_id=current_user.id,
                        centro_custo_id=centro_custo_id if centro_custo_id else None,
                        observacao=observacao or f"Importação da NF {item1.nota_fiscal.numero_nf if item1.nota_fiscal else 'N/A'}"
                    )
                    if sucesso:
                        itens_importados += 1
                    else:
                        itens_com_erro.append({
                            'item_id': item_id,
                            'descricao': item1.descricao,
                            'erro': mensagem
                        })
                except Exception as e:
                    logger.error(f'Erro ao importar item {item_id}: {str(e)}')
                    itens_com_erro.append({
                        'item_id': item_id,
                        'descricao': item1.descricao,
                        'erro': str(e)
                    })
            
            # Montar mensagem com estatísticas
            mensagem = f'Importação concluída!\n\n'
            mensagem += f'• Itens já importados: {itens_ja_importados}\n'
            mensagem += f'• Itens importados agora: {itens_importados}'
            if itens_com_erro:
                mensagem += f'\n• Itens com erro: {len(itens_com_erro)}'
            
            return jsonify({
                'success': True,
                'message': mensagem,
                'itens_importados': itens_importados,
                'itens_ja_importados': itens_ja_importados,
                'itens_com_erro': len(itens_com_erro),
                'total_itens_selecionados': total_itens_selecionados
            })
       # except Exception as e:
       #     logger.error(f"Erro ao importar itens: {str(e)}")
       #     return jsonify({'success': False, 'message': f'Erro ao importar itens: {str(e)}'}), 500
    return jsonify({'success': False, 'message': 'Método inválido'}), 405

def _buscar_itens_similares_todas_notas(codigo, descricao):
    """
    Busca todos os itens similares em todas as notas fiscais baseado em código e/ou descrição.
    
    Args:
        codigo: Código do item
        descricao: Descrição do item
    
    Returns:
        Lista de NotaFiscalItem encontrados
    """
    if codigo and descricao:
        return NotaFiscalItem.query.filter(
            NotaFiscalItem.codigo == codigo,
            NotaFiscalItem.descricao == descricao
        ).all()
    elif codigo:
        return NotaFiscalItem.query.filter(
            NotaFiscalItem.codigo == codigo
        ).all()
    elif descricao:
        return NotaFiscalItem.query.filter(
            NotaFiscalItem.descricao == descricao
        ).all()
    return []


def _aplicar_fator_conversao(item, material, fator_conversao):
    """
    Aplica o fator de conversão ao item baseado no material e fator fornecido.
    
    Args:
        item: NotaFiscalItem
        material: Material
        fator_conversao: Fator de conversão a ser aplicado
    """
    if fator_conversao:
        try:
            item.fator_conversao_aplicado = float(fator_conversao)
        except (ValueError, TypeError):
            if comparar_unidades(item.unidade, material.unidade_obj.nome):
                item.fator_conversao_aplicado = 1
            else:
                item.fator_conversao_aplicado = None
    elif comparar_unidades(item.unidade, material.unidade_obj.nome):
        item.fator_conversao_aplicado = 1
    else:
        item.fator_conversao_aplicado = None


def _vincular_material_a_itens_similares(item_original, material, itens_sem_material, itens_processados):
    """
    Vincula o material aos itens similares que não têm material vinculado.
    
    Args:
        item_original: Item original que já tem material vinculado
        material: Material a ser vinculado
        itens_sem_material: Lista de itens similares sem material
        itens_processados: Set de IDs de itens já processados
    
    Returns:
        Número de itens vinculados
    """
    itens_vinculados = 0
    fator_conversao = item_original.fator_conversao_aplicado
    
    for item_similar in itens_sem_material:
        if item_similar.id in itens_processados:
            continue
        
        _aplicar_fator_conversao(item_similar, material, fator_conversao)
        item_similar.material_id = item_original.material_id
        item_similar.save()
        
        itens_vinculados += 1
        itens_processados.add(item_similar.id)
        logger.info(f'Item {item_similar.id} vinculado ao material {material.nome} na nota {item_similar.nota_fiscal.numero_nf}')
    
    return itens_vinculados


def _importar_item_para_estoque(item, usuario_id, centro_custo_id, observacao, nota_fiscal):
    """
    Importa um item para o estoque.
    
    Args:
        item: NotaFiscalItem a ser importado
        usuario_id: ID do usuário
        centro_custo_id: ID do centro de custo
        observacao: Observação para a importação
        nota_fiscal: NotaFiscal relacionada
    
    Returns:
        Tupla (sucesso: bool, mensagem: str)
    """
    try:
        sucesso, mensagem = item.importar_para_estoque(
            usuario_id=usuario_id,
            centro_custo_id=centro_custo_id,
            observacao=observacao or f"Importação automática da NF {nota_fiscal.numero_nf} de {nota_fiscal.nome_emitente}"
        )
        if sucesso:
            logger.info(f'Item {item.id} importado para o estoque')
        else:
            logger.error(f'Erro ao importar item {item.id}: {mensagem}')
        return sucesso, mensagem
    except Exception as e:
        logger.error(f'Erro ao importar item {item.id}: {str(e)}')
        return False, str(e)


def _vincular_similares_para_item(item, material, itens_processados, grupos_processados, estatisticas):
    """
    Vincula itens similares em todas as notas para um item específico.
    
    Args:
        item: Item a ser processado
        material: Material vinculado ao item
        itens_processados: Set de IDs de itens já processados
        grupos_processados: Set de chaves de grupos já processados
        estatisticas: Dicionário com estatísticas da operação
    
    Returns:
        Lista de todos os itens similares encontrados (incluindo o original)
    """
    codigo = item.codigo.strip() if item.codigo else ''
    descricao = item.descricao.strip() if item.descricao else ''
    
    # Criar chave única para o grupo de itens similares
    chave_grupo = f"{codigo}|{descricao}"
    if chave_grupo in grupos_processados:
        return []  # Já processamos este grupo
    
    grupos_processados.add(chave_grupo)
    
    # 1. Buscar TODOS os itens similares em TODAS as notas fiscais
    logger.info(f'Buscando itens similares para código="{codigo}", descrição="{descricao}" em TODAS as notas fiscais')
    itens_similares_todos = _buscar_itens_similares_todas_notas(codigo, descricao)
    logger.info(f'Encontrados {len(itens_similares_todos)} itens similares em todas as notas')
    
    # Separar itens já vinculados dos que não têm material
    itens_ja_vinculados_local = [i for i in itens_similares_todos if i.material_id]
    itens_sem_material = [i for i in itens_similares_todos if not i.material_id]
    logger.info(f'Dos {len(itens_similares_todos)} itens similares: {len(itens_ja_vinculados_local)} já vinculados, {len(itens_sem_material)} sem material')
    
    # 2. Vincular material aos itens que não têm material vinculado
    itens_vinculados_local = _vincular_material_a_itens_similares(
        item, material, itens_sem_material, itens_processados
    )
    estatisticas['total_itens_vinculados'] += itens_vinculados_local
    estatisticas['total_itens_ja_vinculados'] += len(itens_ja_vinculados_local)
    
    # Retornar todos os itens similares (incluindo o original)
    return [item] + itens_similares_todos


def _importar_itens(itens_para_importar, nota_fiscal, centro_custo_id, observacao, 
                    itens_processados, estatisticas):
    """
    Importa uma lista de itens para o estoque.
    
    Args:
        itens_para_importar: Lista de itens para importar
        nota_fiscal: Nota fiscal relacionada
        centro_custo_id: ID do centro de custo
        observacao: Observação para importação
        itens_processados: Set de IDs de itens já processados
        estatisticas: Dicionário com estatísticas da operação
    """
    for item_para_importar in itens_para_importar:
        if item_para_importar.id in itens_processados:
            if item_para_importar.importado_estoque:
                estatisticas['total_itens_ja_importados'] += 1
            continue
        
        if item_para_importar.material_id:
            if not item_para_importar.importado_estoque:
                sucesso, mensagem = _importar_item_para_estoque(
                    item_para_importar, current_user.id, centro_custo_id, observacao, nota_fiscal
                )
                if sucesso:
                    estatisticas['total_itens_importados'] += 1
                else:
                    estatisticas['itens_com_erro'].append({
                        'item_id': item_para_importar.id,
                        'descricao': item_para_importar.descricao,
                        'erro': mensagem
                    })
            else:
                estatisticas['total_itens_ja_importados'] += 1
        
        itens_processados.add(item_para_importar.id)


@nota_fiscal_bp.route('/api/importar-pendentes-com-material', methods=['POST'])
@login_required
def api_importar_pendentes_com_material():
    """
    API para importar e vincular itens pendentes que já têm material vinculado.
    Para cada item já vinculado:
    1. Vincula itens similares em outras notas
    2. Importa o item atual e todos os similares encontrados
    """
    try:
        data = request.get_json()
        if not data:
            logger.error('Dados JSON não fornecidos na requisição')
            return jsonify({
                'success': False,
                'message': 'Dados não fornecidos na requisição'
            }), 400
        
        nf_id = data.get('nf_id')
        centro_custo_id = data.get('centro_custo_id')
        observacao = data.get('observacao')
        
        logger.info(f'Recebida requisição para importar pendentes: nf_id={nf_id}, centro_custo_id={centro_custo_id}')
        
        if not nf_id:
            logger.error('ID da nota fiscal não fornecido')
            return jsonify({
                'success': False,
                'message': 'ID da nota fiscal não fornecido'
            }), 400
        
        # Buscar a nota fiscal
        try:
            nf_id_int = int(nf_id)
        except (ValueError, TypeError):
            logger.error(f'ID da nota fiscal inválido: {nf_id}')
            return jsonify({
                'success': False,
                'message': f'ID da nota fiscal inválido: {nf_id}'
            }), 400
        
        nota_fiscal = NotaFiscal.query.get(nf_id_int)
        if not nota_fiscal:
            logger.error(f'Nota fiscal com ID {nf_id_int} não encontrada')
            return jsonify({
                'success': False,
                'message': f'Nota fiscal com ID {nf_id_int} não encontrada'
            }), 404
        
        # Contar itens antes da operação
        itens_ja_importados = [item for item in nota_fiscal.itens 
                              if item.importado_estoque and item.material_id]
        itens_pendentes_com_material = [item for item in nota_fiscal.itens 
                                       if not item.importado_estoque and item.material_id]
        total_pendentes = len(itens_pendentes_com_material)
        
        # Verificar se há itens para processar:
        # 1. Itens pendentes na nota atual (já têm material mas não foram importados)
        # 2. Itens similares em outras notas que podem ser vinculados e importados
        tem_itens_para_processar = total_pendentes > 0
        
        # Se não há pendentes na nota atual, verificar se há itens similares em outras notas
        # que podem ser vinculados (mesmo que todos os itens da nota atual já estejam importados)
        if not tem_itens_para_processar:
            logger.info('Nenhum item pendente na nota atual. Verificando itens similares em outras notas...')
            
            # Buscar todos os itens da nota atual que têm material vinculado
            # (mesmo que já estejam importados, podem ter similares em outras notas)
            itens_com_material = [item for item in nota_fiscal.itens if item.material_id]
            
            # Para cada item com material, verificar se há similares em outras notas sem material
            grupos_verificados = set()
            for item in itens_com_material:
                codigo = item.codigo.strip() if item.codigo else ''
                descricao = item.descricao.strip() if item.descricao else ''
                chave_grupo = f"{codigo}|{descricao}"
                
                # Evitar verificar o mesmo grupo múltiplas vezes
                if chave_grupo in grupos_verificados:
                    continue
                grupos_verificados.add(chave_grupo)
                
                # Buscar itens similares em todas as notas
                itens_similares = _buscar_itens_similares_todas_notas(codigo, descricao)
                
                # Verificar se há algum item similar sem material vinculado
                itens_similares_sem_material = [i for i in itens_similares if not i.material_id]
                
                if itens_similares_sem_material:
                    tem_itens_para_processar = True
                    logger.info(f'Encontrados {len(itens_similares_sem_material)} itens similares sem material em outras notas para processar')
                    break
        
        if not tem_itens_para_processar:
            return jsonify({
                'success': False,
                'message': 'Nenhum item pendente com material vinculado encontrado na nota atual e nenhum item similar sem material encontrado em outras notas.'
            }), 400
        
        # Inicializar estatísticas e estruturas de controle
        estatisticas = {
            'total_itens_vinculados': 0,
            'total_itens_ja_vinculados': 0,
            'total_itens_importados': 0,
            'total_itens_ja_importados': 0,
            'itens_com_erro': []
        }
        itens_processados = set()  # Para evitar processar o mesmo item múltiplas vezes
        grupos_processados = set()  # Para evitar processar o mesmo grupo de itens similares múltiplas vezes
        
        # ETAPA 1: Vincular similares em todas as notas
        # Coletar todos os itens que serão processados (originais + similares)
        todos_itens_para_importar = []
        
        # Processar cada item já vinculado na nota atual
        # Processar tanto itens pendentes quanto itens já importados (que podem ter similares em outras notas)
        for item in nota_fiscal.itens:
            # Processar se tiver material vinculado (mesmo que já esteja importado, pode ter similares em outras notas)
            if item.material_id and item.id not in itens_processados:
                material = Material.query.get(item.material_id)
                if not material:
                    continue
                
                # Vincular similares em todas as notas
                itens_similares = _vincular_similares_para_item(
                    item=item,
                    material=material,
                    itens_processados=itens_processados,
                    grupos_processados=grupos_processados,
                    estatisticas=estatisticas
                )
                
                # Adicionar à lista de itens para importar (sem duplicatas)
                for item_similar in itens_similares:
                    if item_similar.id not in [i.id for i in todos_itens_para_importar]:
                        todos_itens_para_importar.append(item_similar)
        
        # ETAPA 2: Importar todos os itens (originais + similares recém-vinculados)
        logger.info(f'Iniciando importação de {len(todos_itens_para_importar)} itens para o estoque')
        _importar_itens(
            itens_para_importar=todos_itens_para_importar,
            nota_fiscal=nota_fiscal,
            centro_custo_id=centro_custo_id,
            observacao=observacao,
            itens_processados=itens_processados,
            estatisticas=estatisticas
        )
        
        # Montar mensagem de resposta
        mensagens = []
        if estatisticas['total_itens_vinculados'] > 0:
            mensagens.append(f'{estatisticas["total_itens_vinculados"]} item(ns) vinculado(s) em outras notas.')
        if estatisticas['total_itens_importados'] > 0:
            mensagens.append(f'{estatisticas["total_itens_importados"]} item(ns) importado(s) para o estoque.')
        if estatisticas['itens_com_erro']:
            mensagens.append(f'{len(estatisticas["itens_com_erro"])} item(ns) com erro na importação.')
        
        mensagem_final = ' '.join(mensagens) if mensagens else 'Nenhum item foi processado.'
        
        return jsonify({
            'success': True,
            'message': mensagem_final,
            'itens_vinculados': estatisticas['total_itens_vinculados'],
            'itens_ja_vinculados': estatisticas['total_itens_ja_vinculados'],
            'itens_importados': estatisticas['total_itens_importados'],
            'itens_ja_importados': estatisticas['total_itens_ja_importados'],
            'itens_com_erro': len(estatisticas['itens_com_erro']),
            'total_pendentes': total_pendentes
        })
    
    except Exception as e:
        logger.error(f'Erro ao importar e vincular pendentes: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Erro ao processar: {str(e)}'
        }), 500

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
        material_id_str = request.form.get('material_id')
        fator_conversao_fornecido = request.form.get('fator_conversao')
        
        if not material_id_str:
            return jsonify({
                'success': False,
                'message': 'ID do material não fornecido'
            }), 400
        
        # Converter material_id para inteiro
        try:
            material_id = int(material_id_str)
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'message': f'ID do material inválido: {material_id_str}'
            }), 400
        
        # Verificar se o material existe
        material = Material.query.get(material_id)
        if not material:
            return jsonify({
                'success': False,
                'message': f'Material com ID {material_id} não encontrado'
            }), 404
        
        # Aplicar fator de conversão se fornecido, senão verificar se as unidades são iguais
        if fator_conversao_fornecido:
            try:
                item.fator_conversao_aplicado = float(fator_conversao_fornecido)
            except (ValueError, TypeError):
                item.fator_conversao_aplicado = None
        else:
            # Obter nome da unidade do material
            material_unidade_nome = None
            if hasattr(material, 'unidade_obj') and material.unidade_obj:
                material_unidade_nome = material.unidade_obj.nome
            elif hasattr(material, 'get_unidade_nome'):
                material_unidade_nome = material.get_unidade_nome()
            
            # Comparar unidades se ambas existirem
            if item.unidade and material_unidade_nome:
                if comparar_unidades(item.unidade, material_unidade_nome):
                    item.fator_conversao_aplicado = 1
                else:
                    item.fator_conversao_aplicado = None
            else:
                item.fator_conversao_aplicado = None
        
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
            nota_fiscal.importar_itens_para_estoque()
            
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

@nota_fiscal_bp.route('/api/buscar-materiais-outras-notas', methods=['GET'])
@login_required
def api_buscar_materiais_outras_notas():
    """
    API para buscar materiais que foram vinculados em outras notas fiscais
    baseado no código ou descrição do item
    """
    try:
        codigo = request.args.get('codigo', '').strip()
        descricao = request.args.get('descricao', '').strip()
        
        if not codigo and not descricao:
            return jsonify({
                'success': False,
                'message': 'Código ou descrição do item é obrigatório'
            }), 400
        
        materiais_encontrados = []
        
        # Buscar por código (prioridade 1)
        if codigo:
            itens_por_codigo = NotaFiscalItem.query.join(NotaFiscal, NotaFiscalItem.nf_id == NotaFiscal.id).filter(
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.material_id.isnot(None),
                NotaFiscalItem.importado_estoque == True
            ).order_by(NotaFiscalItem.data_importacao_estoque.desc()).limit(10).all()
            
            for item in itens_por_codigo:
                if item.material_id and item.material:
                    # Verificar se já não foi adicionado
                    if not any(m['material_id'] == item.material_id for m in materiais_encontrados):
                        materiais_encontrados.append({
                            'material_id': item.material_id,
                            'material_nome': item.material.nome if item.material else 'N/A',
                            'unidade': item.material.unidade_obj.nome if item.material and item.material.unidade_obj else 'N/A',
                            'fator_conversao': str(item.fator_conversao_aplicado) if item.fator_conversao_aplicado else '1',
                            'nota_fiscal_numero': item.nota_fiscal.numero_nf if item.nota_fiscal else 'N/A',
                            'data_importacao': item.data_importacao_estoque.strftime('%d/%m/%Y') if item.data_importacao_estoque else 'N/A'
                        })
        
        # Buscar por descrição (prioridade 2) se não encontrou por código ou para adicionar mais opções
        if descricao:
            itens_por_descricao = NotaFiscalItem.query.filter(
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.material_id.isnot(None),
                NotaFiscalItem.importado_estoque == True
            ).order_by(NotaFiscalItem.data_importacao_estoque.desc()).limit(10).all()
            
            for item in itens_por_descricao:
                if item.material_id and item.material:
                    # Verificar se já não foi adicionado
                    if not any(m['material_id'] == item.material_id for m in materiais_encontrados):
                        materiais_encontrados.append({
                            'material_id': item.material_id,
                            'material_nome': item.material.nome if item.material else 'N/A',
                            'unidade': item.material.unidade_obj.nome if item.material and item.material.unidade_obj else 'N/A',
                            'fator_conversao': str(item.fator_conversao_aplicado) if item.fator_conversao_aplicado else '1',
                            'nota_fiscal_numero': item.nota_fiscal.numero_nf if item.nota_fiscal else 'N/A',
                            'data_importacao': item.data_importacao_estoque.strftime('%d/%m/%Y') if item.data_importacao_estoque else 'N/A'
                        })
        
        return jsonify({
            'success': True,
            'materiais': materiais_encontrados
        })
    
    except Exception as e:
        logger.error(f'Erro ao buscar materiais de outras notas: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Erro ao buscar materiais: {str(e)}'
        }), 500

@nota_fiscal_bp.route('/api/vincular-material-outras-notas', methods=['POST'])
@login_required
def api_vincular_material_outras_notas():
    """
    API para vincular material a um item e a todos os outros itens similares (mesmo código ou descrição) na mesma nota fiscal
    """
    try:
        data = request.get_json()
        nf_id = data.get('nf_id')
        item_id = data.get('item_id')
        material_id = data.get('material_id')
        fator_conversao = data.get('fator_conversao')
        codigo = data.get('codigo', '').strip()
        descricao = data.get('descricao', '').strip()
        
        if not nf_id or not item_id or not material_id:
            return jsonify({
                'success': False,
                'message': 'Parâmetros obrigatórios não fornecidos'
            }), 400
        
        # Buscar a nota fiscal
        nota_fiscal = NotaFiscal.query.get_or_404(nf_id)
        
        # Verificar se o material existe
        material = Material.query.get(material_id)
        if not material:
            return jsonify({
                'success': False,
                'message': f'Material com ID {material_id} não encontrado'
            }), 404
        
        # Buscar o item original
        item_original = NotaFiscalItem.query.get_or_404(item_id)
        
        # Buscar todos os itens similares na mesma nota (mesmo código ou descrição)
        itens_similares = []
        
        # Buscar por código se fornecido
        if codigo:
            itens_por_codigo = NotaFiscalItem.query.filter(
                NotaFiscalItem.nf_id == nf_id,
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.material_id.is_(None)  # Apenas itens sem material vinculado
            ).all()
            itens_similares.extend(itens_por_codigo)
        
        # Buscar por descrição se fornecido
        if descricao:
            itens_por_descricao = NotaFiscalItem.query.filter(
                NotaFiscalItem.nf_id == nf_id,
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.material_id.is_(None)  # Apenas itens sem material vinculado
            ).all()
            # Adicionar apenas se não estiver na lista (evitar duplicatas)
            for item in itens_por_descricao:
                if item not in itens_similares:
                    itens_similares.append(item)
        
        # Se não encontrou itens similares, vincular apenas ao item original
        if not itens_similares:
            itens_similares = [item_original]
        elif item_original not in itens_similares:
            # Garantir que o item original está na lista
            itens_similares.append(item_original)
        
        # Vincular material a todos os itens similares
        itens_vinculados = 0
        for item in itens_similares:
            # Aplicar fator de conversão
            if fator_conversao:
                try:
                    item.fator_conversao_aplicado = float(fator_conversao)
                except (ValueError, TypeError):
                    # Se não conseguir converter, verificar se as unidades são iguais
                    if comparar_unidades(item.unidade, material.unidade_obj.nome):
                        item.fator_conversao_aplicado = 1
                    else:
                        item.fator_conversao_aplicado = None
            elif comparar_unidades(item.unidade, material.unidade_obj.nome):
                item.fator_conversao_aplicado = 1
            else:
                item.fator_conversao_aplicado = None
            
            # Vincular o material

            item.material_id = material_id
            item.save()
            itens_vinculados += 1
        
        # Atualizar NCM do material se necessário
        if item_original.ncm and not material.ncm:
            material.ncm = item_original.ncm
            material.save()
        
        mensagem = f'Material "{material.nome}" vinculado com sucesso a {itens_vinculados} item(ns)!'
        
        return jsonify({
            'success': True,
            'message': mensagem,
            'itens_vinculados': itens_vinculados
        })
    
    except Exception as e:
        logger.error(f'Erro ao vincular material a itens similares: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Erro ao vincular material: {str(e)}'
        }), 500

@nota_fiscal_bp.route('/api/vincular-itens-similares-todas-notas', methods=['POST'])
@login_required
def api_vincular_itens_similares_todas_notas():
    """
    API para vincular material a todos os itens similares (mesmo código e descrição) em TODAS as notas fiscais
    """
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        material_id = data.get('material_id')
        fator_conversao = data.get('fator_conversao')
        codigo = data.get('codigo', '').strip()
        descricao = data.get('descricao', '').strip()
        
        if not item_id or not material_id:
            return jsonify({
                'success': False,
                'message': 'Parâmetros obrigatórios não fornecidos'
            }), 400
        
        # Buscar o item original
        item_original = NotaFiscalItem.query.get_or_404(item_id)
        
        # Verificar se o material existe
        material = Material.query.get(material_id)
        if not material:
            return jsonify({
                'success': False,
                'message': f'Material com ID {material_id} não encontrado'
            }), 404
        
        # Buscar TODOS os itens similares em TODAS as notas fiscais (incluindo os que já têm material)
        # Critério: mesmo código E mesma descrição
        itens_similares_todos = []
        itens_ja_vinculados = []
        itens_sem_material = []
        
        # Buscar por código E descrição (ambos devem corresponder)
        if codigo and descricao:
            itens_encontrados = NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.id != item_id  # Excluir o item original
            ).all()
            itens_similares_todos.extend(itens_encontrados)
        elif codigo:
            # Se só tem código, buscar por código
            itens_encontrados = NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.id != item_id
            ).all()
            itens_similares_todos.extend(itens_encontrados)
        elif descricao:
            # Se só tem descrição, buscar por descrição
            itens_encontrados = NotaFiscalItem.query.filter(
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.id != item_id
            ).all()
            itens_similares_todos.extend(itens_encontrados)
        
        # Separar itens já vinculados dos que não têm material
        for item in itens_similares_todos:
            if item.material_id:
                itens_ja_vinculados.append(item)
            else:
                itens_sem_material.append(item)
        
        # Vincular material apenas aos itens que não têm material vinculado
        itens_vinculados = 0
        for item in itens_sem_material:
            # Aplicar fator de conversão
            if fator_conversao:
                try:
                    item.fator_conversao_aplicado = float(fator_conversao)
                except (ValueError, TypeError):
                    # Se não conseguir converter, verificar se as unidades são iguais
                    if comparar_unidades(item.unidade, material.unidade_obj.nome):
                        item.fator_conversao_aplicado = 1
                    else:
                        item.fator_conversao_aplicado = None
            elif comparar_unidades(item.unidade, material.unidade_obj.nome):
                item.fator_conversao_aplicado = 1
            else:
                item.fator_conversao_aplicado = None
            
            # Vincular o material
            item.material_id = material_id
            item.save()
            itens_vinculados += 1
        
        # Montar mensagem com estatísticas
        mensagem = f'Material "{material.nome}" vinculado com sucesso!\n\n'
        mensagem += f'• Itens já vinculados: {len(itens_ja_vinculados)}\n'
        mensagem += f'• Itens vinculados agora: {itens_vinculados}'
        
        if not itens_similares_todos and not itens_vinculados:
            mensagem = 'Nenhum item similar encontrado em outras notas fiscais para vincular.'
        
        return jsonify({
            'success': True,
            'message': mensagem,
            'itens_vinculados': itens_vinculados,
            'itens_ja_vinculados': len(itens_ja_vinculados),
            'total_itens_similares': len(itens_similares_todos)
        })
    
    except Exception as e:
        logger.error(f'Erro ao vincular itens similares em todas as notas: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Erro ao vincular itens similares: {str(e)}'
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
                'ncm': item.ncm,
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
        
        # Verificar se o material está vinculado
        if not item.material_id:
            return jsonify({
                'success': False,
                'message': 'Este item não está vinculado a um material do sistema'
            }), 400
        
        # Verificar se o item já foi importado (não retornar erro, apenas marcar)
        item_ja_importado = item.importado_estoque
        
        # Obter parâmetros adicionais
        centro_custo_id = request.form.get('centro_custo_id')
        observacao = request.form.get('observacao')
        importacao_automatica = request.form.get('importacao_automatica', 'false') == 'true'
        
        # Se for importação automática, ajusta a observação
        if importacao_automatica and not observacao:
            observacao = f"Importação automática da NF {item.nota_fiscal.numero_nf} de {item.nota_fiscal.nome_emitente}"
        
        # Buscar outros itens similares (mesmo código e descrição) que já estão vinculados mas não foram importados
        itens_similares_para_importar = []
        codigo = item.codigo
        descricao = item.descricao
        
        # Buscar por código E descrição (ambos devem corresponder)
        if codigo and descricao:
            itens_encontrados = NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.material_id.isnot(None),  # Já tem material vinculado
                NotaFiscalItem.importado_estoque == False,  # Ainda não foi importado
                NotaFiscalItem.id != item_id  # Excluir o item original
            ).all()
            itens_similares_para_importar.extend(itens_encontrados)
        elif codigo:
            # Se só tem código, buscar por código
            itens_encontrados = NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.material_id.isnot(None),
                NotaFiscalItem.importado_estoque == False,
                NotaFiscalItem.id != item_id
            ).all()
            itens_similares_para_importar.extend(itens_encontrados)
        elif descricao:
            # Se só tem descrição, buscar por descrição
            itens_encontrados = NotaFiscalItem.query.filter(
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.material_id.isnot(None),
                NotaFiscalItem.importado_estoque == False,
                NotaFiscalItem.id != item_id
            ).all()
            itens_similares_para_importar.extend(itens_encontrados)
        
        # Contar itens já importados (que já estavam importados antes)
        itens_ja_importados = 0
        if codigo and descricao:
            itens_ja_importados = NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.material_id.isnot(None),
                NotaFiscalItem.importado_estoque == True
            ).count()
        elif codigo:
            itens_ja_importados = NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.material_id.isnot(None),
                NotaFiscalItem.importado_estoque == True
            ).count()
        elif descricao:
            itens_ja_importados = NotaFiscalItem.query.filter(
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.material_id.isnot(None),
                NotaFiscalItem.importado_estoque == True
            ).count()
        
        # Verificar estado atual do estoque antes da importação
        from models.estoque import Estoque
        estoque_atual = Estoque.query.filter_by(material_id=item.material_id, tipo_item='material').first()
        qtd_atual = float(estoque_atual.quantidade) if estoque_atual else 0
        
        logger.info(f"API: Estoque atual para material {item.material_id}: {qtd_atual}")
        logger.info(f"API: Encontrados {len(itens_similares_para_importar)} itens similares para importar")
        
        # Importar o item original (apenas se ainda não foi importado)
        itens_importados = 0
        itens_com_erro = []
        
        if not item_ja_importado:
            sucesso, mensagem = item.importar_para_estoque(
                usuario_id=current_user.id,
                centro_custo_id=centro_custo_id if centro_custo_id else None,
                observacao=observacao
            )
            
            if sucesso:
                itens_importados += 1
            else:
                itens_com_erro.append({
                    'item_id': item.id,
                    'descricao': item.descricao,
                    'erro': mensagem
                })
        else:
            # Item já estava importado, incrementar contador de já importados
            itens_ja_importados += 1
        
        # Importar itens similares encontrados
        for item_similar in itens_similares_para_importar:
            try:
                sucesso_similar, mensagem_similar = item_similar.importar_para_estoque(
                    usuario_id=current_user.id,
                    centro_custo_id=centro_custo_id if centro_custo_id else None,
                    observacao=observacao or f"Importação automática da NF {item_similar.nota_fiscal.numero_nf if item_similar.nota_fiscal else 'N/A'}"
                )
                if sucesso_similar:
                    itens_importados += 1
                else:
                    itens_com_erro.append({
                        'item_id': item_similar.id,
                        'descricao': item_similar.descricao,
                        'erro': mensagem_similar
                    })
            except Exception as e:
                logger.error(f'Erro ao importar item similar {item_similar.id}: {str(e)}')
                itens_com_erro.append({
                    'item_id': item_similar.id,
                    'descricao': item_similar.descricao,
                    'erro': str(e)
                })
        
        # Verificar estado do estoque depois da importação
        db.session.refresh(estoque_atual) if estoque_atual else None
        estoque_depois = Estoque.query.filter_by(material_id=item.material_id, tipo_item='material').first()
        qtd_depois = float(estoque_depois.quantidade) if estoque_depois else 0
        
        logger.info(f"API: Estoque após importação para material {item.material_id}: {qtd_depois}")
        
        # Atualizar quantidade depois se houve importação
        if itens_importados > 0:
            db.session.refresh(estoque_depois) if estoque_depois else None
            estoque_depois = Estoque.query.filter_by(material_id=item.material_id, tipo_item='material').first()
            qtd_depois = float(estoque_depois.quantidade) if estoque_depois else 0
        
        # Registrar se foi importação automática (apenas se importou algo)
        if itens_importados > 0 and importacao_automatica:
            item.dados_adicionais = json.dumps({
                "importacao_automatica": True,
                "data_importacao_automatica": datetime.now().isoformat()
            })
            item.save()
        
        # Sempre retornar estatísticas, mesmo se o item já estava importado
        if item_ja_importado:
            mensagem_final = 'Este item já estava importado para o estoque.'
            if len(itens_similares_para_importar) > 0:
                mensagem_final += f' {len(itens_similares_para_importar)} item(ns) similar(es) foram encontrado(s) e importado(s).'
            elif itens_importados > 0:
                mensagem_final += f' {itens_importados} item(ns) similar(es) foram importado(s).'
        elif itens_importados > 0:
            mensagem_final = f'Item importado com sucesso!'
            if len(itens_similares_para_importar) > 0:
                mensagem_final += f' {len(itens_similares_para_importar)} item(ns) similar(es) também foram importado(s).'
        else:
            mensagem_final = 'Nenhum item foi importado.'
            if itens_com_erro:
                mensagem_final += f' {len(itens_com_erro)} item(ns) com erro.'
        
        # Retornar sempre com sucesso e estatísticas
        return jsonify({
            'success': True,
            'message': mensagem_final,
            'quantidade_anterior': qtd_atual,
            'quantidade_atual': qtd_depois,
            'importacao_automatica': importacao_automatica,
            'itens_importados': itens_importados,
            'itens_ja_importados': itens_ja_importados,
            'itens_com_erro': len(itens_com_erro),
            'itens_similares_encontrados': len(itens_similares_para_importar),
            'item_ja_estava_importado': item_ja_importado
        })
        
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

def buscar_transferencias_com_saldos_cnpj(filtros):
    """
    Função auxiliar reutilizável para buscar transferências e calcular saldos por CNPJ.
    
    Args:
        filtros (dict): Dicionário com os filtros:
            - data_inicio: str (formato 'YYYY-MM-DD')
            - data_fim: str (formato 'YYYY-MM-DD')
            - codigo_item: str
            - nome_item: str
            - cnpjs_emitente: list
            - cnpjs_destinatario: list
            - materiais_ids: list
    
    Returns:
        dict: Dicionário com:
            - transferencias: lista de objetos de transferência
            - cnpjs_unicos: lista ordenada de CNPJs únicos
            - saldos_por_cnpj: lista ordenada com saldos calculados por CNPJ
            - somatorias_por_cnpj: dicionário com somatórias por CNPJ (para colunas)
            - totais_gerais: dict com total_quantidade e total_valor
    """
    from models.nota_fiscal import NotaFiscal, NotaFiscalItem
    
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
    query = query.filter(NotaFiscal.status_processamento != 'cancelada')
    
    # Aplicar filtros
    if filtros.get('data_inicio'):
        try:
            data_inicio = datetime.strptime(filtros['data_inicio'], '%Y-%m-%d')
            query = query.filter(NotaFiscal.data_emissao >= data_inicio)
        except Exception:
            pass
    
    if filtros.get('data_fim'):
        try:
            data_fim = datetime.strptime(filtros['data_fim'], '%Y-%m-%d')
            query = query.filter(NotaFiscal.data_emissao <= data_fim)
        except Exception:
            pass
    
    if filtros.get('codigo_item'):
        query = query.filter(NotaFiscalItem.codigo.ilike(f'%{filtros["codigo_item"]}%'))
    
    if filtros.get('nome_item'):
        query = query.filter(NotaFiscalItem.descricao.ilike(f'%{filtros["nome_item"]}%'))
    
    if filtros.get('cnpjs_emitente'):
        query = query.filter(NotaFiscal.cnpj_emitente.in_(filtros['cnpjs_emitente']))
    
    if filtros.get('cnpjs_destinatario'):
        query = query.filter(NotaFiscal.cnpj_destinatario.in_(filtros['cnpjs_destinatario']))
    
    if filtros.get('materiais_ids'):
        try:
            materiais_ids_int = [int(mid) for mid in filtros['materiais_ids'] if mid]
            if materiais_ids_int:
                query = query.filter(NotaFiscalItem.material_id.in_(materiais_ids_int))
        except (ValueError, TypeError):
            pass
    
    query = query.order_by(NotaFiscal.data_emissao.desc())
    transferencias = query.all()
    
    # Calcular totais gerais
    total_quantidade = sum(t.quantidade for t in transferencias if t.quantidade)
    total_valor = sum(float(t.valor) for t in transferencias if t.valor)
    
    # Coletar todos os CNPJs únicos
    cnpjs_unicos = set()
    for t in transferencias:
        if t.cnpj_emitente:
            cnpjs_unicos.add(t.cnpj_emitente)
        if t.cnpj_destinatario:
            cnpjs_unicos.add(t.cnpj_destinatario)
    cnpjs_unicos = sorted(list(cnpjs_unicos))
    
    # Calcular saldos unificados por CNPJ
    # Considera o CNPJ tanto como emitente quanto como destinatário
    # Lógica: tipo_nota == 0 (Entrada) = adiciona, tipo_nota == 1 (Saída) = subtrai
    saldos_por_cnpj_dict = {}
    
    for t in transferencias:
        quantidade = t.quantidade if t.quantidade else 0
        valor = float(t.valor) if t.valor else 0
        
        # Processar CNPJ Emitente
        cnpj_emit = t.cnpj_emitente or 'Sem CNPJ'
        nome_emit = t.nome_emitente or 'Sem nome'
        if cnpj_emit not in saldos_por_cnpj_dict:
            saldos_por_cnpj_dict[cnpj_emit] = {
                'cnpj': cnpj_emit,
                'nome': nome_emit,
                'quantidade': 0,
                'valor': 0,
                'registros': 0
            }
        
        # Se for Entrada (tipo_nota == 0), adiciona ao saldo do emitente
        # Se for Saída (tipo_nota == 1), subtrai do saldo do emitente
        if t.tipo_nota == 0:  # Entrada
            saldos_por_cnpj_dict[cnpj_emit]['quantidade'] += quantidade
            saldos_por_cnpj_dict[cnpj_emit]['valor'] += valor
        elif t.tipo_nota == 1:  # Saída
            saldos_por_cnpj_dict[cnpj_emit]['quantidade'] -= quantidade
            saldos_por_cnpj_dict[cnpj_emit]['valor'] -= valor
        
        saldos_por_cnpj_dict[cnpj_emit]['registros'] += 1
        
        # Processar CNPJ Destinatário (somando ao mesmo CNPJ se for o mesmo)
        cnpj_dest = t.cnpj_destinatario or 'Sem CNPJ'
        nome_dest = t.nome_destinatario or 'Sem nome'
        if cnpj_dest not in saldos_por_cnpj_dict:
            saldos_por_cnpj_dict[cnpj_dest] = {
                'cnpj': cnpj_dest,
                'nome': nome_dest,
                'quantidade': 0,
                'valor': 0,
                'registros': 0
            }
        
        # Se for Entrada (tipo_nota == 0), adiciona ao saldo do destinatário
        # Se for Saída (tipo_nota == 1), subtrai do saldo do destinatário
        if t.tipo_nota == 0:  # Entrada
            saldos_por_cnpj_dict[cnpj_dest]['quantidade'] += quantidade
            saldos_por_cnpj_dict[cnpj_dest]['valor'] += valor
        elif t.tipo_nota == 1:  # Saída
            saldos_por_cnpj_dict[cnpj_dest]['quantidade'] -= quantidade
            saldos_por_cnpj_dict[cnpj_dest]['valor'] -= valor
        
        saldos_por_cnpj_dict[cnpj_dest]['registros'] += 1
    
    # Converter para lista ordenada por CNPJ
    saldos_por_cnpj = sorted(saldos_por_cnpj_dict.values(), key=lambda x: x['cnpj'])
    
    # Calcular somatórias por CNPJ para uso nas colunas (mesma fórmula do Excel)
    somatorias_por_cnpj = {}
    for cnpj in cnpjs_unicos:
        somatorias_por_cnpj[cnpj] = 0.0
    
    for t in transferencias:
        quantidade = float(t.quantidade) if t.quantidade else 0.0
        cnpj_emit = t.cnpj_emitente or ''
        cnpj_dest = t.cnpj_destinatario or ''
        is_saida = (t.tipo_nota == 1)
        
        for cnpj in cnpjs_unicos:
            valor = 0.0
            
            # Parte 1: Se CNPJ Emitente = CNPJ da coluna
            if cnpj_emit == cnpj:
                if is_saida:
                    valor -= quantidade
                else:
                    valor += quantidade
            
            # Parte 2: Se CNPJ Destinatário = CNPJ da coluna
            if cnpj_dest == cnpj:
                if is_saida:
                    valor += quantidade
                else:
                    valor -= quantidade
            
            # Parte 3: Se CNPJ Emitente = CNPJ Destinatário E CNPJ Destinatário = CNPJ da coluna
            if cnpj_emit == cnpj_dest == cnpj:
                if is_saida:
                    valor -= quantidade
                else:
                    valor += quantidade
            
            somatorias_por_cnpj[cnpj] += valor
    
    return {
        'transferencias': transferencias,
        'cnpjs_unicos': cnpjs_unicos,
        'saldos_por_cnpj': saldos_por_cnpj,
        'somatorias_por_cnpj': somatorias_por_cnpj,
        'totais_gerais': {
            'quantidade': total_quantidade,
            'valor': total_valor
        }
    }

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
    materiais_ids = request.args.getlist('material_id')

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
    if materiais_ids:
        try:
            materiais_ids_int = [int(mid) for mid in materiais_ids if mid]
            if materiais_ids_int:
                query = query.filter(NotaFiscalItem.material_id.in_(materiais_ids_int))
        except (ValueError, TypeError):
            pass

    query = query.order_by(NotaFiscal.data_emissao.desc())
    paginacao = query.paginate(page=page, per_page=per_page, error_out=False)
    transferencias = paginacao.items

    # Buscar CNPJs distintos para os dropdowns
    cnpjs_emitentes_lista = db.session.query(NotaFiscal.cnpj_emitente).distinct().order_by(NotaFiscal.cnpj_emitente).all()
    cnpjs_destinatarios_lista = db.session.query(NotaFiscal.cnpj_destinatario).distinct().order_by(NotaFiscal.cnpj_destinatario).all()
    cnpjs_emitentes = [c[0] for c in cnpjs_emitentes_lista if c[0]]
    cnpjs_destinatarios = [c[0] for c in cnpjs_destinatarios_lista if c[0]]

    # Buscar materiais que têm itens de nota fiscal vinculados
    materiais_vinculados = db.session.query(Material).join(
        NotaFiscalItem, Material.id == NotaFiscalItem.material_id
    ).filter(
        NotaFiscalItem.material_id.isnot(None)
    ).distinct().order_by(Material.nome).all()

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
        filtro_material_id=materiais_ids,
        cnpjs_emitentes=cnpjs_emitentes,
        cnpjs_destinatarios=cnpjs_destinatarios,
        materiais=materiais_vinculados
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
    materiais_ids = request.args.getlist('material_id')

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
    if materiais_ids:
        try:
            materiais_ids_int = [int(mid) for mid in materiais_ids if mid]
            if materiais_ids_int:
                query = query.filter(NotaFiscalItem.material_id.in_(materiais_ids_int))
        except (ValueError, TypeError):
            pass

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

@nota_fiscal_bp.route('/analise-transferencias/exportar-pdf', methods=['GET'])
@login_required
def analise_transferencias_exportar_pdf():
    """
    Exporta a análise de transferências para PDF considerando os filtros aplicados.
    """
    if not WEASYPRINT_AVAILABLE:
        flash('Funcionalidade de PDF indisponível. WeasyPrint não instalado.', 'danger')
        return redirect(url_for('nota_fiscal.analise_transferencias'))
    
    import os
    
    # Obter filtros da query string
    filtros = {
        'data_inicio': request.args.get('data_inicio', '').strip() or '',
        'data_fim': request.args.get('data_fim', '').strip() or '',
        'codigo_item': request.args.get('codigo_item', ''),
        'nome_item': request.args.get('nome_item', ''),
        'cnpjs_emitente': request.args.getlist('cnpj_emitente'),
        'cnpjs_destinatario': request.args.getlist('cnpj_destinatario'),
        'materiais_ids': request.args.getlist('material_id')
    }
    
    # Buscar dados usando função auxiliar
    resultado = buscar_transferencias_com_saldos_cnpj(filtros)
    
    # Preparar informações de filtros para exibir no PDF
    filtros_aplicados = {}
    if filtros['data_inicio']:
        try:
            data_inicio_dt = datetime.strptime(filtros['data_inicio'], '%Y-%m-%d')
            filtros_aplicados['data_inicio'] = data_inicio_dt.strftime('%d/%m/%Y')
        except:
            pass
    if filtros['data_fim']:
        try:
            data_fim_dt = datetime.strptime(filtros['data_fim'], '%Y-%m-%d')
            filtros_aplicados['data_fim'] = data_fim_dt.strftime('%d/%m/%Y')
        except:
            pass
    if filtros['codigo_item']:
        filtros_aplicados['codigo_item'] = filtros['codigo_item']
    if filtros['nome_item']:
        filtros_aplicados['nome_item'] = filtros['nome_item']
    if filtros['cnpjs_emitente']:
        filtros_aplicados['cnpj_emitente'] = filtros['cnpjs_emitente']
    if filtros['cnpjs_destinatario']:
        filtros_aplicados['cnpj_destinatario'] = filtros['cnpjs_destinatario']
    
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = None
    try:
        logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
        if os.path.exists(logo_path):
            logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
        else:
            logo_path_uri = None
    except:
        logo_path_uri = None
    
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = None
    try:
        logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
        if os.path.exists(logo_path):
            logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
        else:
            logo_path_uri = None
    except:
        logo_path_uri = None
    
    # Renderizar template HTML
    html = render_template(
        'notas_fiscais/analise_transferencias_pdf.html',
        transferencias=resultado['transferencias'],
        total_quantidade=resultado['totais_gerais']['quantidade'],
        total_valor=resultado['totais_gerais']['valor'],
        saldos_por_cnpj=resultado['saldos_por_cnpj'],
        filtros_aplicados=filtros_aplicados if filtros_aplicados else None,
        now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        logo_path=logo_path_uri
    )
    
    # Gerar PDF
    pdf_bytes = HTML(string=html).write_pdf(
        stylesheets=[CSS(string='body { font-family: Arial, sans-serif; }')]
    )
    
    # Preparar resposta
    pdf_io = io.BytesIO(pdf_bytes)
    pdf_io.seek(0)
    
    # Nome do arquivo com timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'analise_transferencias_{timestamp}.pdf'
    
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

def buscar_transferencias_com_saldos_cnpj(filtros):
    """
    Função auxiliar reutilizável para buscar transferências e calcular saldos por CNPJ.
    
    Args:
        filtros (dict): Dicionário com os filtros:
            - data_inicio: str (formato 'YYYY-MM-DD')
            - data_fim: str (formato 'YYYY-MM-DD')
            - codigo_item: str
            - nome_item: str
            - cnpjs_emitente: list
            - cnpjs_destinatario: list
            - materiais_ids: list
    
    Returns:
        dict: Dicionário com:
            - transferencias: lista de objetos de transferência
            - cnpjs_unicos: lista ordenada de CNPJs únicos
            - saldos_por_cnpj: dicionário com saldos calculados por CNPJ
            - totais_gerais: dict com total_quantidade e total_valor
    """
    from models.nota_fiscal import NotaFiscal, NotaFiscalItem
    
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
    query = query.filter(NotaFiscal.status_processamento != 'cancelada')
    
    # Aplicar filtros
    if filtros.get('data_inicio'):
        try:
            data_inicio = datetime.strptime(filtros['data_inicio'], '%Y-%m-%d')
            query = query.filter(NotaFiscal.data_emissao >= data_inicio)
        except Exception:
            pass
    
    if filtros.get('data_fim'):
        try:
            data_fim = datetime.strptime(filtros['data_fim'], '%Y-%m-%d')
            query = query.filter(NotaFiscal.data_emissao <= data_fim)
        except Exception:
            pass
    
    if filtros.get('codigo_item'):
        query = query.filter(NotaFiscalItem.codigo.ilike(f'%{filtros["codigo_item"]}%'))
    
    if filtros.get('nome_item'):
        query = query.filter(NotaFiscalItem.descricao.ilike(f'%{filtros["nome_item"]}%'))
    
    if filtros.get('cnpjs_emitente'):
        query = query.filter(NotaFiscal.cnpj_emitente.in_(filtros['cnpjs_emitente']))
    
    if filtros.get('cnpjs_destinatario'):
        query = query.filter(NotaFiscal.cnpj_destinatario.in_(filtros['cnpjs_destinatario']))
    
    if filtros.get('materiais_ids'):
        try:
            materiais_ids_int = [int(mid) for mid in filtros['materiais_ids'] if mid]
            if materiais_ids_int:
                query = query.filter(NotaFiscalItem.material_id.in_(materiais_ids_int))
        except (ValueError, TypeError):
            pass
    
    query = query.order_by(NotaFiscal.data_emissao.desc())
    transferencias = query.all()
    
    # Calcular totais gerais
    total_quantidade = sum(t.quantidade for t in transferencias if t.quantidade)
    total_valor = sum(float(t.valor) for t in transferencias if t.valor)
    
    # Coletar todos os CNPJs únicos
    cnpjs_unicos = set()
    for t in transferencias:
        if t.cnpj_emitente:
            cnpjs_unicos.add(t.cnpj_emitente)
        if t.cnpj_destinatario:
            cnpjs_unicos.add(t.cnpj_destinatario)
    cnpjs_unicos = sorted(list(cnpjs_unicos))
    
    # Calcular saldos unificados por CNPJ
    # Considera o CNPJ tanto como emitente quanto como destinatário
    # Lógica: tipo_nota == 0 (Entrada) = adiciona, tipo_nota == 1 (Saída) = subtrai
    saldos_por_cnpj_dict = {}
    
    for t in transferencias:
        quantidade = t.quantidade if t.quantidade else 0
        valor = float(t.valor) if t.valor else 0
        
        # Processar CNPJ Emitente
        cnpj_emit = t.cnpj_emitente or 'Sem CNPJ'
        nome_emit = t.nome_emitente or 'Sem nome'
        if cnpj_emit not in saldos_por_cnpj_dict:
            saldos_por_cnpj_dict[cnpj_emit] = {
                'cnpj': cnpj_emit,
                'nome': nome_emit,
                'quantidade': 0,
                'valor': 0,
                'registros': 0
            }
        
        # Se for Entrada (tipo_nota == 0), adiciona ao saldo do emitente
        # Se for Saída (tipo_nota == 1), subtrai do saldo do emitente
        if t.tipo_nota == 0:  # Entrada
            saldos_por_cnpj_dict[cnpj_emit]['quantidade'] += quantidade
            saldos_por_cnpj_dict[cnpj_emit]['valor'] += valor
        elif t.tipo_nota == 1:  # Saída
            saldos_por_cnpj_dict[cnpj_emit]['quantidade'] -= quantidade
            saldos_por_cnpj_dict[cnpj_emit]['valor'] -= valor
        
        saldos_por_cnpj_dict[cnpj_emit]['registros'] += 1
        
        # Processar CNPJ Destinatário (somando ao mesmo CNPJ se for o mesmo)
        cnpj_dest = t.cnpj_destinatario or 'Sem CNPJ'
        nome_dest = t.nome_destinatario or 'Sem nome'
        if cnpj_dest not in saldos_por_cnpj_dict:
            saldos_por_cnpj_dict[cnpj_dest] = {
                'cnpj': cnpj_dest,
                'nome': nome_dest,
                'quantidade': 0,
                'valor': 0,
                'registros': 0
            }
        
        # Se for Entrada (tipo_nota == 0), adiciona ao saldo do destinatário
        # Se for Saída (tipo_nota == 1), subtrai do saldo do destinatário
        if t.tipo_nota == 0:  # Entrada
            saldos_por_cnpj_dict[cnpj_dest]['quantidade'] += quantidade
            saldos_por_cnpj_dict[cnpj_dest]['valor'] += valor
        elif t.tipo_nota == 1:  # Saída
            saldos_por_cnpj_dict[cnpj_dest]['quantidade'] -= quantidade
            saldos_por_cnpj_dict[cnpj_dest]['valor'] -= valor
        
        saldos_por_cnpj_dict[cnpj_dest]['registros'] += 1
    
    # Converter para lista ordenada por CNPJ
    saldos_por_cnpj = sorted(saldos_por_cnpj_dict.values(), key=lambda x: x['cnpj'])
    
    # Calcular somatórias por CNPJ para uso nas colunas (mesma fórmula do Excel)
    somatorias_por_cnpj = {}
    for cnpj in cnpjs_unicos:
        somatorias_por_cnpj[cnpj] = 0.0
    
    for t in transferencias:
        quantidade = float(t.quantidade) if t.quantidade else 0.0
        cnpj_emit = t.cnpj_emitente or ''
        cnpj_dest = t.cnpj_destinatario or ''
        is_saida = (t.tipo_nota == 1)
        
        for cnpj in cnpjs_unicos:
            valor = 0.0
            
            # Parte 1: Se CNPJ Emitente = CNPJ da coluna
            if cnpj_emit == cnpj:
                if is_saida:
                    valor -= quantidade
                else:
                    valor += quantidade
            
            # Parte 2: Se CNPJ Destinatário = CNPJ da coluna
            if cnpj_dest == cnpj:
                if is_saida:
                    valor += quantidade
                else:
                    valor -= quantidade
            
            # Parte 3: Se CNPJ Emitente = CNPJ Destinatário E CNPJ Destinatário = CNPJ da coluna
            if cnpj_emit == cnpj_dest == cnpj:
                if is_saida:
                    valor -= quantidade
                else:
                    valor += quantidade
            
            somatorias_por_cnpj[cnpj] += valor
    
    return {
        'transferencias': transferencias,
        'cnpjs_unicos': cnpjs_unicos,
        'saldos_por_cnpj': saldos_por_cnpj,
        'somatorias_por_cnpj': somatorias_por_cnpj,
        'totais_gerais': {
            'quantidade': total_quantidade,
            'valor': total_valor
        }
    }

@nota_fiscal_bp.route('/analise-transferencias/modal-cnpj', methods=['GET'])
@login_required
def analise_transferencias_modal_cnpj():
    """
    Retorna dados formatados para o modal de análise por CNPJ.
    """
    # Obter filtros da query string
    filtros = {
        'data_inicio': request.args.get('data_inicio', '').strip() or '',
        'data_fim': request.args.get('data_fim', '').strip() or '',
        'codigo_item': request.args.get('codigo_item', ''),
        'nome_item': request.args.get('nome_item', ''),
        'cnpjs_emitente': request.args.getlist('cnpj_emitente'),
        'cnpjs_destinatario': request.args.getlist('cnpj_destinatario'),
        'materiais_ids': request.args.getlist('material_id')
    }
    
    # Buscar dados usando função auxiliar
    resultado = buscar_transferencias_com_saldos_cnpj(filtros)
    
    # Preparar dados de transferências para JSON
    dados_transferencias = []
    for t in resultado['transferencias']:
        tipo_nota_str = 'Entrada' if t.tipo_nota == 0 else ('Saída' if t.tipo_nota == 1 else str(t.tipo_nota))
        dados_transferencias.append({
            'data': t.data.isoformat() if t.data else None,
            'nome_item': t.nome_item or '',
            'codigo_item': t.codigo_item or '',
            'numero_nf': t.numero_nf or '',
            'cnpj_emitente': t.cnpj_emitente or '',
            'cnpj_destinatario': t.cnpj_destinatario or '',
            'tipo_nota': tipo_nota_str,
            'quantidade': float(t.quantidade) if t.quantidade else 0.0,
        })
    
    return jsonify({
        'success': True,
        'transferencias': dados_transferencias,
        'cnpjs': resultado['cnpjs_unicos'],
        'somatorias': resultado['somatorias_por_cnpj']
    })

@nota_fiscal_bp.route('/analise-transferencias/exportar-excel', methods=['GET'])
@login_required
def analise_transferencias_exportar_excel():
    """
    Exporta a análise de transferências para Excel considerando os filtros aplicados.
    """
    # Obter filtros da query string
    filtros = {
        'data_inicio': request.args.get('data_inicio', '').strip() or '',
        'data_fim': request.args.get('data_fim', '').strip() or '',
        'codigo_item': request.args.get('codigo_item', ''),
        'nome_item': request.args.get('nome_item', ''),
        'cnpjs_emitente': request.args.getlist('cnpj_emitente'),
        'cnpjs_destinatario': request.args.getlist('cnpj_destinatario'),
        'materiais_ids': request.args.getlist('material_id')
    }
    
    # Buscar dados usando função auxiliar
    resultado = buscar_transferencias_com_saldos_cnpj(filtros)
    transferencias = resultado['transferencias']
    cnpjs_unicos = resultado['cnpjs_unicos']
    
    # Preparar dados para o DataFrame
    dados = []
    for t in transferencias:
        tipo_nota_str = 'Entrada' if t.tipo_nota == 0 else ('Saída' if t.tipo_nota == 1 else str(t.tipo_nota))
        quantidade = float(t.quantidade) if t.quantidade else 0.0
        cnpj_emit = t.cnpj_emitente or ''
        cnpj_dest = t.cnpj_destinatario or ''
        is_saida = (t.tipo_nota == 1)
        
        linha = {
            'Data': t.data if t.data else None,
            'Nome do Item': t.nome_item or '',
            'Código do Item': t.codigo_item or '',
            'Número NF': t.numero_nf or '',
            'CNPJ Emitente': cnpj_emit,
            'CNPJ Destinatário': cnpj_dest,
            'Tipo da Nota': tipo_nota_str,
            'Quantidade': quantidade,
        }
        
        # Calcular valor para cada CNPJ conforme a fórmula
        # Fórmula Excel: SE($E2=J$1;SE($G2="Saída";-$H2;$H2);0)+SE($F2=J$1;SE($G2="Saída";$H2;-$H2);0)+SE(E($E2=$F2;$F2=J$1);SE($G2="Saída";-H2;H2);0)
        for cnpj in cnpjs_unicos:
            valor_cnpj = 0.0
            
            # Parte 1: Se CNPJ Emitente = CNPJ da coluna
            if cnpj_emit == cnpj:
                if is_saida:
                    valor_cnpj -= quantidade  # Saída: subtrai do emitente
                else:
                    valor_cnpj += quantidade  # Entrada: adiciona ao emitente
            
            # Parte 2: Se CNPJ Destinatário = CNPJ da coluna
            if cnpj_dest == cnpj:
                if is_saida:
                    valor_cnpj += quantidade  # Saída: adiciona ao destinatário
                else:
                    valor_cnpj -= quantidade  # Entrada: subtrai do destinatário
            
            # Parte 3: Se CNPJ Emitente = CNPJ Destinatário E CNPJ Destinatário = CNPJ da coluna
            # (Esta parte só se aplica quando emitente e destinatário são o mesmo)
            if cnpj_emit == cnpj_dest and cnpj_dest == cnpj:
                if is_saida:
                    valor_cnpj -= quantidade  # Saída: subtrai
                else:
                    valor_cnpj += quantidade  # Entrada: adiciona
            
            linha[cnpj] = valor_cnpj
        
        dados.append(linha)
    
    # Criar DataFrame
    df = pd.DataFrame(dados)
    
    # Converter coluna Data para datetime se necessário
    if 'Data' in df.columns:
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
    
    # Preparar dados de saldos para o DataFrame (usando resultado da função auxiliar)
    dados_saldos = []
    for dados in resultado['saldos_por_cnpj']:
        dados_saldos.append({
            'CNPJ': dados['cnpj'],
            'Nome': dados['nome'],
            'Registros': dados['registros'],
            'Saldo Quantidade': dados['quantidade'],
            'Saldo Valor': dados['valor']
        })
    
    df_saldos = pd.DataFrame(dados_saldos)
    
    # Criar arquivo Excel com múltiplas abas
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Aba 1: Transferências
        df.to_excel(writer, index=False, sheet_name='Transferências')
        
        # Aba 2: Saldos por CNPJ
        if not df_saldos.empty:
            df_saldos.to_excel(writer, index=False, sheet_name='Saldos por CNPJ')
        
        # Formatação
        workbook = writer.book
        worksheet = writer.sheets['Transferências']
        
        # Formatar cabeçalhos
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#3498db',
            'font_color': 'white',
            'border': 1
        })
        
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Formatar coluna de data
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        # Encontrar o índice da coluna 'Data'
        if 'Data' in df.columns:
            data_col_idx = list(df.columns).index('Data')
            worksheet.set_column(data_col_idx, data_col_idx, None, date_format)
        
        # Formatar valores monetários
        money_format = workbook.add_format({'num_format': 'R$ #,##0.00'})
        if 'Valor' in df.columns:
            valor_col_idx = list(df.columns).index('Valor')
            worksheet.set_column(valor_col_idx, valor_col_idx, None, money_format)
        
        # Formatar quantidade
        number_format = workbook.add_format({'num_format': '#,##0.00'})
        if 'Quantidade' in df.columns:
            quantidade_col_idx = list(df.columns).index('Quantidade')
            worksheet.set_column(quantidade_col_idx, quantidade_col_idx, None, number_format)
        
        # Formatar colunas de CNPJ (valores numéricos)
        for cnpj in cnpjs_unicos:
            if cnpj in df.columns:
                cnpj_col_idx = list(df.columns).index(cnpj)
                worksheet.set_column(cnpj_col_idx, cnpj_col_idx, None, number_format)
        
        # Ajustar largura das colunas
        for i, col in enumerate(df.columns):
            if col not in ['Data', 'Valor', 'Quantidade'] and col not in cnpjs_unicos:  # Já formatadas acima
                column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, min(column_len, 50))
            elif col in cnpjs_unicos:
                # Colunas de CNPJ: largura baseada no CNPJ (14 caracteres) + margem
                worksheet.set_column(i, i, 18)
        
        # Formatar a aba de saldos se existir
        if not df_saldos.empty:
            worksheet_saldos = writer.sheets['Saldos por CNPJ']
            for col_num, value in enumerate(df_saldos.columns.values):
                worksheet_saldos.write(0, col_num, value, header_format)
            
            for i, col in enumerate(df_saldos.columns):
                column_len = max(df_saldos[col].astype(str).map(len).max(), len(col)) + 2
                worksheet_saldos.set_column(i, i, min(column_len, 50))
            
            # Formatar valores monetários e numéricos
            money_format = workbook.add_format({'num_format': 'R$ #,##0.00'})
            number_format = workbook.add_format({'num_format': '#,##0.00'})
            
            worksheet_saldos.set_column('D:D', None, number_format)  # Saldo Quantidade
            worksheet_saldos.set_column('E:E', None, money_format)  # Saldo Valor
    
    output.seek(0)
    
    # Nome do arquivo com timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'analise_transferencias_{timestamp}.xlsx'
    
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
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

@nota_fiscal_bp.route('/total-valor-notas', methods=['GET'])
@login_required
def total_valor_notas():
    """Retorna o valor total das notas fiscais com os filtros aplicados"""
    try:
        # Obter query com filtros aplicados
        query = api_get_dados_notas_fiscais(request)
        
        # Obter apenas os IDs únicos das notas filtradas (evita duplicatas dos joins)
        nota_ids = [row[0] for row in query.with_entities(distinct(NotaFiscal.id)).all()]
        
        if not nota_ids:
            return jsonify({'valor_total': 0.0})
        
        # Calcular soma dos valores totais usando apenas os IDs únicos
        # Isso garante que cada nota seja contada apenas uma vez
        resultado = db.session.query(
            func.sum(NotaFiscal.valor_total)
        ).filter(
            NotaFiscal.id.in_(nota_ids)
        ).scalar()
        
        valor_total = float(resultado) if resultado is not None else 0.0
        
        return jsonify({
            'valor_total': valor_total
        })
    except Exception as e:
        logger.error(f'Erro ao obter valor total de notas: {str(e)}')
        return jsonify({'error': 'Erro ao obter valor total de notas', 'valor_total': 0.0}), 500

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
    print("request.args:", request.args)
    pagamento = request.args.get('status_pagamento',None)
    query = api_get_dados_notas_fiscais(request)
    print(f'query {time.time() - inicio}')
    #print(f'query: {query}')
    inicio = time.time()
    # Calcular valor total das notas filtradas
    valor_total_raw = db.session.query(
        func.coalesce(func.sum(NotaFiscal.valor_total), 0)
    ).select_from(NotaFiscal).filter(
        *query._where_criteria
    ).scalar()
    
    # Formatar valor total para exibição (formato dinheiro brasileiro: R$ 1.234,56)
    valor_total = float(valor_total_raw) if valor_total_raw else 0.0
    # Formatar com separador de milhares (.) e decimal (,)
    valor_total_formatado = f'R$ {valor_total:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    # Obter TODAS as notas primeiro (sem paginação)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    print(f'pagination {time.time() - inicio}')
    inicio = time.time()
    notas_fiscais_pagina = pagination.items
    notas_fiscais_pagina_upload = []
    print(f'notas_fiscais_pagina len:{len(notas_fiscais_pagina)} {time.time() - inicio}')
    for nota in notas_fiscais_pagina:
        # Extrair vencimento da coluna (pode ser string 'YYYY-MM-DD' ou None)
        vencimento_str = getattr(nota.NotaFiscal, 'vencimento', None) if hasattr(nota.NotaFiscal, 'vencimento') else None
        
        # Formatar vencimento para exibição
        vencimento_formatado = '-'
        if vencimento_str:
            try:
                # Se for string no formato 'YYYY-MM-DD', converter para datetime e formatar
                if isinstance(vencimento_str, str) and len(vencimento_str) == 10 and '-' in vencimento_str:
                    vencimento_date = datetime.strptime(vencimento_str, '%Y-%m-%d').date()
                    vencimento_formatado = vencimento_date.strftime('%d/%m/%Y')
                else:
                    vencimento_formatado = str(vencimento_str)
            except (ValueError, AttributeError):
                vencimento_formatado = str(vencimento_str) if vencimento_str else '-'
        
        # Criar um objeto simples para passar ao template
        # Row do SQLAlchemy é imutável, então criamos um dict ou objeto simples
        nota_dict = {
            'NotaFiscal': nota.NotaFiscal,
            'pagamento': getattr(nota, 'pagamento', 0),
            'upload': getattr(nota, 'upload', 0),
            'upload_protocolo': getattr(nota, 'upload_protocolo', 0),
            'upload_reembolso': getattr(nota, 'upload_reembolso', 0),
            'upload_arquivei': getattr(nota, 'upload_arquivei', 0),
            'vencimento': vencimento_str,
            'vencimento_formatado': vencimento_formatado,
            'id': nota.NotaFiscal.id,
            'numero_nf': nota.NotaFiscal.numero_nf
        }
        
        # Adicionar emitente e destinatário ao dicionário (não ao objeto NotaFiscal)
        # O objeto NotaFiscal pode ser imutável, então armazenamos no dicionário
        nota_dict['emitente'] = ('Matriz' if nota.NotaFiscal.cnpj_emitente in CNPJS_MATRIZ else 'Filiais' if nota.NotaFiscal.cnpj_emitente in CNPJS_FILIAIS else 'Terceiros')
        nota_dict['destinatario'] = ('Matriz' if nota.NotaFiscal.cnpj_destinatario in CNPJS_MATRIZ else 'Filiais' if nota.NotaFiscal.cnpj_destinatario in CNPJS_FILIAIS else 'Terceiros')
        
        # Tentar adicionar ao objeto NotaFiscal também (pode funcionar se for um objeto ORM normal)
        try:
            nota_dict['NotaFiscal'].emitente = nota_dict['emitente']
            nota_dict['NotaFiscal'].destinatario = nota_dict['destinatario']
        except (AttributeError, TypeError):
            # Se não conseguir, os valores já estão no dicionário
            pass

        
        notas_fiscais_pagina_upload.append(nota_dict)
    print(f'notas_fiscais_pagina_upload {time.time() - inicio}')
    
    print(f'tabela notas fiscais - página {page} de {pagination.pages}, total filtrado: {pagination.total} {time.time() - inicio}')
    # Passar todos os parâmetros de filtro para o template, para preservar nos links de paginação
    filtros_params = dict(request.args)
    # Remover 'page' dos parâmetros, pois será adicionado dinamicamente nos links
    if 'page' in filtros_params:
        del filtros_params['page']
    return render_template('notas_fiscais/notas_tabela.html', 
                         pagination=pagination, 
                         notas_fiscais=notas_fiscais_pagina_upload, 
                         total_resultados=pagination.total, 
                         valor_total=valor_total_formatado,
                         filtros_params=filtros_params)