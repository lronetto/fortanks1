"""
Controller para manipulação de dados analíticos financeiros.
Permite visualização, filtragem e análise dos dados importados.
"""
import os
import io
import json
import csv
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from calendar import monthrange
import pandas as pd # Adicionar import
from typing import Optional, List, Dict, Any
import pprint # Ensure pprint is imported

from flask import Blueprint, render_template, redirect, url_for, request, jsonify, current_app, send_file # Add jsonify
from flask_login import login_required, current_user
from sqlalchemy import extract, func, desc, asc, and_, or_, case
from werkzeug.utils import secure_filename
from openpyxl.utils import get_column_letter # Importar utilitário

from models import DadoAnalitico, CentroCusto, PlanoConta, Usuario
from models.database import db
from utils.decorators import role_required
from scripts.importador_dados_analiticos import importar_arquivo_local, executar_importacao_async
from config.config import Config
import tempfile
import threading
import asyncio
import traceback
from flask import flash
from models.dados_analiticos import PL_RECOP, PL_0201, PL_0202, PL_0203, PL_0204, PL_0205, PL_0206, PL_0207, PL_0208, PL_0209, PL_0210, PL_0211, PL_0212, PL_0213, PL_CUSTO, PL_00
# Configurar logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # Definir nível para DEBUG para capturar mais logs
# Adicionar um handler se não houver um configurado (ex: para console)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Criar o blueprint
dados_analiticos_bp = Blueprint('dados_analiticos', __name__)

@dados_analiticos_bp.before_request
def verificar_permissao():
    if not current_user.is_permissao('dados_analiticos'):
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('dashboard.index'))

def aplicar_ordenacao(query, sort_by, sort_dir):
    """
    Função auxiliar para aplicar ordenação nas consultas.
    
    Args:
        query: Consulta SQLAlchemy
        sort_by: Campo para ordenar
        sort_dir: Direção da ordenação ('asc' ou 'desc')
        
    Returns:
        Consulta com ordenação aplicada
    """
    if sort_by == 'data_pagamento':
        if sort_dir == 'asc':
            query = query.order_by(DadoAnalitico.data_pagamento.asc())
        else:
            query = query.order_by(DadoAnalitico.data_pagamento.desc())
    elif sort_by == 'documento':
        if sort_dir == 'asc':
            query = query.order_by(DadoAnalitico.documento.asc())
        else:
            query = query.order_by(DadoAnalitico.documento.desc())
    elif sort_by == 'emitente':
        if sort_dir == 'asc':
            query = query.order_by(DadoAnalitico.emitente.asc())
        else:
            query = query.order_by(DadoAnalitico.emitente.desc())
    elif sort_by == 'debito_credito':
        if sort_dir == 'asc':
            query = query.order_by(DadoAnalitico.debito_credito.asc())
        else:
            query = query.order_by(DadoAnalitico.debito_credito.desc())
    elif sort_by == 'historico':
        if sort_dir == 'asc':
            query = query.order_by(DadoAnalitico.historico.asc())
        else:
            query = query.order_by(DadoAnalitico.historico.desc())
    elif sort_by == 'valor':
        if sort_dir == 'asc':
            query = query.order_by(DadoAnalitico.valor.asc())
        else:
            query = query.order_by(DadoAnalitico.valor.desc())
    elif sort_by == 'centro_custo':
        # Verificar se já está joinado para evitar duplicação
        if 'centro_custo' not in str(query):
            query = query.join(CentroCusto, DadoAnalitico.centro_custo_id == CentroCusto.id)
        
        if sort_dir == 'asc':
            query = query.order_by(CentroCusto.nome.asc())
        else:
            query = query.order_by(CentroCusto.nome.desc())
    elif sort_by == 'plano_conta':
        # Verificar se já está joinado para evitar duplicação
        if 'plano_conta' not in str(query):
            query = query.join(PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id)
        
        if sort_dir == 'asc':
            query = query.order_by(PlanoConta.descricao.asc())
        else:
            query = query.order_by(PlanoConta.descricao.desc())
    else:
        # Ordenação padrão por data
        query = query.order_by(DadoAnalitico.data_pagamento.desc())
    
    return query


@dados_analiticos_bp.route('/')
@login_required
#@role_required('visualizar_dados_analiticos')
def index():
    """
    Exibe a lista de dados analíticos com opções de filtro.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Verificar se temos dados na tabela
    total_global = DadoAnalitico.query.count()
    logger.info(f"Total de registros na tabela DadosAnaliticos: {total_global}")
    
    # Obter parâmetros de filtro
    filtros = {
        'ano': request.args.get('ano', type=int),
        'mes': request.args.get('mes', type=int),
        'centro_custo_id': request.args.get('centro_custo_id', type=int),
        'plano_conta_id': request.args.get('plano_conta_id', type=int),
        'sort_by': request.args.get('sort_by', 'data_pagamento'),
        'sort_dir': request.args.get('sort_dir', 'desc'),
        'emitente_filtro': request.args.get('emitente_filtro', type=str),
        'historico_filtro': request.args.get('historico_filtro', type=str),
        'documento': request.args.get('documento_filtro',type=str)
    }
    
    logger.info(f"Filtros aplicados: {filtros}")
    
    # Construir a query base
    query = DadoAnalitico.query
    
    # Aplicar filtros
    if filtros['ano']:
        query = query.filter(DadoAnalitico.ano == filtros['ano'])
    
    if filtros['mes']:
        query = query.filter(DadoAnalitico.mes == filtros['mes'])
    
    if filtros['centro_custo_id']:
        query = query.filter(DadoAnalitico.centro_custo_id == filtros['centro_custo_id'])
    
    if filtros['plano_conta_id']:
        query = query.filter(DadoAnalitico.plano_conta_id == filtros['plano_conta_id'])
    
    # NOVOS FILTROS DE TEXTO
    if filtros['emitente_filtro']:
        query = query.filter(DadoAnalitico.emitente.ilike(f"%{filtros['emitente_filtro']}%" ))
    if filtros['historico_filtro']:
        query = query.filter(DadoAnalitico.historico.ilike(f"%{filtros['historico_filtro']}%" ))
    
    if filtros['documento']:
        query = query.filter(DadoAnalitico.documento.ilike(f"%{filtros['documento']}%" ))
        
    # Ordenar por coluna selecionada
    query = aplicar_ordenacao(query, filtros['sort_by'], filtros['sort_dir'])
    
    # Contar registros após filtrar
    filtrados = query.count()
   # logger.info(f"Registros após aplicar filtros: {filtrados}")
    
    # Paginação
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    dados = pagination.items
    
    logger.info(f"Itens retornados após paginação: {len(dados)}")
    
    # Se não existirem dados, remover filtros de ano
    if filtrados == 0 and filtros['ano']:
        # Tentar buscar todos os anos
        anos_query = db.session.query(DadoAnalitico.ano).distinct().order_by(DadoAnalitico.ano.desc())
        anos_existentes = [a[0] for a in anos_query.all() if a[0] is not None]
        
        if anos_existentes:
            # Redirecionar para o ano mais recente
            flash(f"Não foram encontrados dados para o ano {filtros['ano']}. Mostrando dados do ano {anos_existentes[0]}.", 'info')
            return redirect(url_for('dados_analiticos.index', 
                                    ano=anos_existentes[0], 
                                    mes=filtros['mes'],
                                    centro_custo_id=filtros['centro_custo_id'],
                                    plano_conta_id=filtros['plano_conta_id']))
    
    # Obter anos disponíveis
    anos_disponiveis = db.session.query(DadoAnalitico.ano).distinct().order_by(DadoAnalitico.ano.desc()).all()
    anos_disponiveis = [ano[0] for ano in anos_disponiveis if ano[0] is not None]
    
    if not anos_disponiveis and filtros['ano']:
        anos_disponiveis = [filtros['ano']]
    anos_disponiveis.insert(0, '')
    
    # Obter centros de custo e planos de conta para filtros
    centros_custo = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.codigo).all()
    planos_conta = PlanoConta.query.filter_by(ativo=True).order_by(PlanoConta.descricao).all()
    
    # Calcular totais
    total_registros = pagination.total
    
    total_valor = db.session.query(func.sum(DadoAnalitico.valor)).filter(
        *(cond for cond in [
            DadoAnalitico.ano == filtros['ano'] if filtros['ano'] else True,
            DadoAnalitico.mes == filtros['mes'] if filtros['mes'] else True,
            DadoAnalitico.centro_custo_id == filtros['centro_custo_id'] if filtros['centro_custo_id'] else True,
            DadoAnalitico.plano_conta_id == filtros['plano_conta_id'] if filtros['plano_conta_id'] else True,
            DadoAnalitico.emitente.ilike(f"%{filtros['emitente_filtro']}%") if filtros['emitente_filtro'] else True,
            DadoAnalitico.historico.ilike(f"%{filtros['historico_filtro']}%") if filtros['historico_filtro'] else True
        ] if cond is not True)
    ).scalar() or 0
    
    # Se não existem dados, mostrar mensagem
    if total_global == 0:
        flash('Não existem dados analíticos no sistema. Por favor, importe dados através do botão "Importar Dados".', 'warning')
    elif filtrados == 0:
        flash('Não foram encontrados dados com os filtros selecionados. Tente alterar os filtros.', 'info')
    
    return render_template(
        'relatorios/dados_analiticos/index.html',
        dados=dados,
        pagination=pagination,
        filtros=filtros,
        anos_disponiveis=anos_disponiveis,
        centros_custo=centros_custo,
        planos_conta=planos_conta,
        total_registros=total_registros,
        total_valor=total_valor
    )

@dados_analiticos_bp.route('/importar', methods=['GET', 'POST'])
@login_required
#@verificar_permissao('importar_dados_analiticos')
def importar():
    """
    Importa dados de um arquivo ou redireciona para a página de importação.
    """
    if request.method == 'POST':
        # Verificar se há arquivos na requisição
        if 'arquivo' not in request.files:
            flash('Nenhum arquivo selecionado', 'danger')
            return redirect(request.url)
        
        arquivo = request.files['arquivo']
        
        # Verificar se o arquivo foi selecionado
        if arquivo.filename == '':
            flash('Nenhum arquivo selecionado', 'danger')
            return redirect(request.url)
        
        # Verificar extensão do arquivo
        extensao = arquivo.filename.rsplit('.', 1)[1].lower() if '.' in arquivo.filename else None
        extensoes_permitidas = {'csv', 'xls', 'xlsx', 'html'}
        
        if extensao not in extensoes_permitidas:
            flash(f'Formato de arquivo não suportado. Formatos permitidos: {", ".join(extensoes_permitidas)}', 'danger')
            return redirect(request.url)
        
        # Salvar arquivo temporariamente
        temp_dir = os.path.join(Config.UPLOAD_FOLDER, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        filename = secure_filename(arquivo.filename)
        temp_path = os.path.join(temp_dir, filename)
        arquivo.save(temp_path)
        
        try:
            # Importar arquivo usando a função adequada
            resultado = importar_arquivo_local(temp_path, current_user.id)
            
            if resultado['sucesso']:
                flash(f"Importação concluída com sucesso! {resultado['registros']} registros importados.", 'success')
            else:
                flash(f"Erro na importação: {resultado['mensagem']}", 'danger')
            
            # Remover arquivo temporário
            os.remove(temp_path)
            
        except Exception as e:
            logger.error(f"Erro ao importar arquivo: {str(e)}", exc_info=True)
            flash(f"Erro ao processar o arquivo: {str(e)}", 'danger')
            # Tentar remover arquivo temporário
            try:
                os.remove(temp_path)
            except:
                pass
        
        # Redirecionar para o dashboard para visualizar os dados importados
        if resultado['registros'] > 0:
            return redirect(url_for('dados_analiticos.dashboard'))
        else:
            return redirect(url_for('dados_analiticos.index'))
    
    # Método GET - redireciona para a página principal com o modal aberto
    return redirect(url_for('dados_analiticos.index'))

@dados_analiticos_bp.route('/importar-dados-csv')
@login_required
#@verificar_permissao('importar_dados_analiticos')
def importar_dados_csv():
    """
    Importa dados do arquivo CSV para o banco de dados.
    """
    # Caminho para o arquivo CSV (ajustar se necessário)
    arquivo_csv = os.path.join(current_app.config['ROOT_PATH'], '..', 'dados_extraidos.csv')
    
    if not os.path.exists(arquivo_csv):
        flash(f"Arquivo {arquivo_csv} não encontrado!", 'danger')
        return redirect(url_for('dados_analiticos.index'))
    
    # Inicializar contadores
    registros_processados = 0
    registros_inseridos = 0
    registros_ignorados = 0
    erros = []
    
    try:
        # Mapear centros de custo e planos de conta existentes
        centros_custo = {cc.nome.lower(): cc for cc in CentroCusto.query.all()}
        centros_custo_codigo = {cc.codigo.lower(): cc for cc in CentroCusto.query.all() if cc.codigo}
        
        planos_conta = {pc.descricao.lower(): pc for pc in PlanoConta.query.all()}
        planos_conta_codigo = {pc.codigo.lower(): pc for pc in PlanoConta.query.all() if pc.codigo}
        
        # Ler arquivo CSV
        with open(arquivo_csv, 'r', encoding='utf-8-sig') as file:
            csv_reader = csv.reader(file, delimiter=';')
            
            # Ler cabeçalho
            headers = next(csv_reader, None)
            if not headers:
                flash("Arquivo CSV vazio ou inválido", 'danger')
                return redirect(url_for('dados_analiticos.index'))
            
            logger.info(f"Cabeçalho do CSV: {headers}")
            
            # Mapear índices das colunas
            indices = {}
            for i, header in enumerate(headers):
                header_lower = header.lower().strip()
                if header_lower == 'centro de custo':
                    indices['centro_custo'] = i
                elif header_lower == 'centro de custo codigo':
                    indices['centro_custo_codigo'] = i
                elif header_lower == 'plano de conta':
                    indices['plano_conta'] = i
                elif header_lower == 'plano de conta codigo':
                    indices['plano_conta_codigo'] = i
                elif header_lower == 'data pgto':
                    indices['data_pagamento'] = i
                elif header_lower == 'documento':
                    indices['documento'] = i
                elif header_lower == 'emitente':
                    indices['emitente'] = i
                elif header_lower == 'd/b':
                    indices['debito_credito'] = i
                elif header_lower == 'histórico' or header_lower == 'historico':
                    indices['historico'] = i
                elif header_lower == 'liberado por':
                    indices['liberado_por'] = i
                elif 'banco' in header_lower:
                    indices['banco'] = i
                elif header_lower == 'cheque':
                    indices['cheque'] = i
                elif 'valor' in header_lower and 'r$' in header_lower:
                    indices['valor'] = i
                elif header_lower == 'pago':
                    indices['pago'] = i
            
            logger.info(f"Colunas mapeadas: {indices}")
            
            # Verificar se temos as colunas mínimas necessárias
            colunas_necessarias = ['centro_custo', 'plano_conta', 'data_pagamento', 'valor']
            for col in colunas_necessarias:
                if col not in indices:
                    flash(f"Coluna obrigatória '{col}' não encontrada no CSV", 'danger')
                    return redirect(url_for('dados_analiticos.index'))
            
            # Processar linhas
            for row_num, row in enumerate(csv_reader, start=2):  # start=2 pois 1 é o cabeçalho
                try:
                    registros_processados += 1
                    
                    # Extrair dados da linha
                    centro_custo_nome = row[indices['centro_custo']].strip() if 'centro_custo' in indices and indices['centro_custo'] < len(row) else None
                    centro_custo_codigo = row[indices['centro_custo_codigo']].strip() if 'centro_custo_codigo' in indices and indices['centro_custo_codigo'] < len(row) else None
                    
                    plano_conta_nome = row[indices['plano_conta']].strip() if 'plano_conta' in indices and indices['plano_conta'] < len(row) else None
                    plano_conta_codigo = row[indices['plano_conta_codigo']].strip() if 'plano_conta_codigo' in indices and indices['plano_conta_codigo'] < len(row) else None
                    
                    data_str = row[indices['data_pagamento']].strip() if 'data_pagamento' in indices and indices['data_pagamento'] < len(row) else None
                    documento = row[indices['documento']].strip() if 'documento' in indices and indices['documento'] < len(row) else None
                    emitente = row[indices['emitente']].strip() if 'emitente' in indices and indices['emitente'] < len(row) else None
                    debito_credito = row[indices['debito_credito']].strip() if 'debito_credito' in indices and indices['debito_credito'] < len(row) else None
                    historico = row[indices['historico']].strip() if 'historico' in indices and indices['historico'] < len(row) else None
                    liberado_por = row[indices['liberado_por']].strip() if 'liberado_por' in indices and indices['liberado_por'] < len(row) else None
                    banco = row[indices['banco']].strip() if 'banco' in indices and indices['banco'] < len(row) else None
                    cheque = row[indices['cheque']].strip() if 'cheque' in indices and indices['cheque'] < len(row) else None
                    
                    valor_str = row[indices['valor']].strip() if 'valor' in indices and indices['valor'] < len(row) else None
                    pago_str = row[indices['pago']].strip() if 'pago' in indices and indices['pago'] < len(row) else None
                    
                    # Pular linhas sem dados essenciais
                    if not centro_custo_nome and not centro_custo_codigo:
                        logger.debug(f"Linha {row_num}: Pulando - sem centro de custo")
                        registros_ignorados += 1
                        continue
                        
                    if not plano_conta_nome and not plano_conta_codigo:
                        logger.debug(f"Linha {row_num}: Pulando - sem plano de conta")
                        registros_ignorados += 1
                        continue
                        
                    if not data_str:
                        logger.debug(f"Linha {row_num}: Pulando - sem data de pagamento")
                        registros_ignorados += 1
                        continue
                        
                    if not valor_str:
                        logger.debug(f"Linha {row_num}: Pulando - sem valor")
                        registros_ignorados += 1
                        continue
                    
                    # Transformar os dados
                    # Converter data
                    data_pagamento = None
                    try:
                        if '/' in data_str:
                            dia, mes, ano = data_str.split('/')
                            data_pagamento = datetime(int(ano), int(mes), int(dia)).date()
                        elif '-' in data_str:
                            partes = data_str.split('-')
                            if len(partes[0]) == 4:  # formato YYYY-MM-DD
                                ano, mes, dia = partes
                            else:  # formato DD-MM-YYYY
                                dia, mes, ano = partes
                            data_pagamento = datetime(int(ano), int(mes), int(dia)).date()
                    except Exception as e:
                        logger.warning(f"Linha {row_num}: Erro ao converter data '{data_str}': {str(e)}")
                        data_pagamento = None
                    
                    if not data_pagamento:
                        logger.debug(f"Linha {row_num}: Pulando - data inválida: {data_str}")
                        registros_ignorados += 1
                        continue
                    
                    # Converter valor (tratar formatos R$ 1.234,56 ou 1234.56 ou 1234,56)
                    valor = 0
                    try:
                        # Remover símbolos de moeda e espaços
                        valor_limpo = valor_str.replace('R$', '').replace(' ', '')
                        
                        # Tratar separadores
                        if ',' in valor_limpo:
                            # Formato brasileiro (1.234,56)
                            valor_limpo = valor_limpo.replace('.', '')
                            valor_limpo = valor_limpo.replace(',', '.')
                        
                        valor = float(valor_limpo)
                    except Exception as e:
                        logger.warning(f"Linha {row_num}: Erro ao converter valor '{valor_str}': {str(e)}")
                        registros_ignorados += 1
                        continue
                    
                    # Converter pago (S/N, Sim/Não, True/False, etc)
                    pago = False
                    if pago_str:
                        pago_str = pago_str.lower()
                        pago = pago_str in ['s', 'sim', 'true', '1', 'y', 'yes']
                    
                    # Encontrar ou criar centro de custo
                    centro_custo_id = None
                    if centro_custo_nome:
                        # Procurar por nome
                        cc = centros_custo.get(centro_custo_nome.lower())
                        if cc:
                            centro_custo_id = cc.id
                        else:
                            # Criar novo centro de custo
                            novo_cc = CentroCusto(
                                nome=centro_custo_nome,
                                codigo=centro_custo_codigo,
                                ativo=True,
                                criado_em=datetime.now()
                            )
                            db.session.add(novo_cc)
                            db.session.flush()  # Obter ID sem commit
                            centro_custo_id = novo_cc.id
                            centros_custo[centro_custo_nome.lower()] = novo_cc
                            if centro_custo_codigo:
                                centros_custo_codigo[centro_custo_codigo.lower()] = novo_cc
                    elif centro_custo_codigo:
                        # Procurar por código
                        cc = centros_custo_codigo.get(centro_custo_codigo.lower())
                        if cc:
                            centro_custo_id = cc.id
                    
                    # Encontrar ou criar plano de conta
                    plano_conta_id = None
                    if plano_conta_nome:
                        # Procurar por nome
                        pc = planos_conta.get(plano_conta_nome.lower())
                        if pc:
                            plano_conta_id = pc.id
                        else:
                            # Criar novo plano de conta
                            novo_pc = PlanoConta(
                                descricao=plano_conta_nome,
                                codigo=plano_conta_codigo,
                                ativo=True,
                                criado_em=datetime.now()
                            )
                            db.session.add(novo_pc)
                            db.session.flush()  # Obter ID sem commit
                            plano_conta_id = novo_pc.id
                            planos_conta[plano_conta_nome.lower()] = novo_pc
                            if plano_conta_codigo:
                                planos_conta_codigo[plano_conta_codigo.lower()] = novo_pc
                    elif plano_conta_codigo:
                        # Procurar por código
                        pc = planos_conta_codigo.get(plano_conta_codigo.lower())
                        if pc:
                            plano_conta_id = pc.id
                    
                    # Verificar se já existe um registro idêntico
                    existe = DadoAnalitico.query.filter(
                        DadoAnalitico.data_pagamento == data_pagamento,
                        DadoAnalitico.documento == documento,
                        DadoAnalitico.emitente == emitente,
                        DadoAnalitico.valor == valor
                    ).first()
                    
                    if existe:
                        logger.debug(f"Linha {row_num}: Registro já existe (data={data_pagamento}, doc={documento}, valor={valor})")
                        registros_ignorados += 1
                        continue
                    
                    # Criar novo registro
                    novo_dado = DadoAnalitico(
                        centro_custo_id=centro_custo_id,
                        plano_conta_id=plano_conta_id,
                        data_pagamento=data_pagamento,
                        documento=documento,
                        emitente=emitente,
                        debito_credito=debito_credito,
                        historico=historico,
                        liberado_por=liberado_por,
                        banco=banco,
                        cheque=cheque,
                        valor=valor,
                        pago=pago,
                        importado_por=current_user.id,
                        importado_em=datetime.now()
                    )
                    
                    # Garantir que ano e mês são derivados da data
                    novo_dado.ano = data_pagamento.year
                    novo_dado.mes = data_pagamento.month
                    
                    db.session.add(novo_dado)
                    
                    # Commit a cada 1000 registros para não sobrecarregar a memória
                    if registros_inseridos % 1000 == 0 and registros_inseridos > 0:
                        db.session.commit()
                        logger.info(f"Progresso: {registros_inseridos} registros importados...")
                    
                    registros_inseridos += 1
                    
                    if registros_inseridos % 100 == 0:
                        logger.info(f"Processados {registros_inseridos} registros...")
                
                except Exception as e:
                    erro_msg = f"Linha {row_num}: Erro ao processar linha: {str(e)}"
                    logger.error(erro_msg)
                    erros.append(erro_msg)
                    registros_ignorados += 1
                    db.session.rollback()  # Reverter alterações da linha atual
            
            # Commit final
            try:
                db.session.commit()
                flash(f"Importação concluída: {registros_inseridos} registros inseridos, {registros_ignorados} ignorados.", 'success')
            except Exception as e:
                db.session.rollback()
                erro_msg = f"Erro ao finalizar importação: {str(e)}"
                logger.error(erro_msg)
                flash(erro_msg, 'danger')
                if erros:
                    for erro in erros[:5]:  # Mostrar apenas os 5 primeiros erros
                        flash(erro, 'danger')
                    if len(erros) > 5:
                        flash(f"... e mais {len(erros) - 5} erros.", 'danger')
    
    except Exception as e:
        erro_msg = f"Erro geral durante a importação: {str(e)}"
        logger.error(erro_msg, exc_info=True)
        flash(erro_msg, 'danger')
    
    # Redirecionar para o dashboard para visualizar os dados importados
    if registros_inseridos > 0:
        return redirect(url_for('dados_analiticos.dashboard'))
    else:
        return redirect(url_for('dados_analiticos.index'))

@dados_analiticos_bp.route('/api/iniciar-extracao', methods=['GET'])
@login_required
#@verificar_permissao('importar_dados_analiticos')
def api_iniciar_extracao():
    """
    Inicia a extração automática de dados usando Playwright
    """
    loop = asyncio.new_event_loop() 
    asyncio.set_event_loop(loop)
    logger.info("Iniciando extração de dados analíticos...")
    resultado = loop.run_until_complete(
            executar_importacao_async(current_user.id)
        )   
    #resultado = executar_importacao_async(current_user.id)
    return jsonify(resultado)

@dados_analiticos_bp.route('/dashboard')
@login_required
def dashboard():
    """Exibe o dashboard com os gráficos de análise financeira"""
    # Obter filtros
    ano = request.args.get('ano', '')  # Vazio como padrão para mostrar "Todos os Anos"
    mes = request.args.get('mes')
    cc_id = request.args.get('cc_id')
    
    # Definir filtros para passar para o template
    filtros = {
        'ano': ano,
        'mes': int(mes) if mes and mes.isdigit() else None,
        'cc_id': cc_id
    }
    
    # Obter lista de anos disponíveis usando SQLAlchemy
    anos_disponiveis = db.session.query(
        extract('year', DadoAnalitico.data_pagamento).distinct().label('ano')
    ).order_by('ano').all()
    
    anos = [int(ano.ano) for ano in anos_disponiveis if ano.ano is not None]
    
    # Obter centros de custo usando SQLAlchemy
    centros_custo = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.codigo).all()
    
    # Título do período para exibição
    periodo_texto = f"{ano}" if ano else "Todos os Anos"
    if mes and mes.isdigit():
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        periodo_texto += f" - {meses[int(mes)-1]}"
    
    return render_template('relatorios/dados_analiticos/dashboard.html',
                           anos=anos,
                           centros_custo=centros_custo,
                           filtros=filtros,
                           periodo_texto=periodo_texto)

@dados_analiticos_bp.route('/api/dashboard-data')
@login_required
def api_dashboard_data():
    """API para retornar dados do dashboard via AJAX"""
    try:
        from sqlalchemy import func, extract, case, Float
        
        # Obter filtros
        ano = request.args.get('ano')
        mes = request.args.get('mes')
        cc_id = request.args.get('cc_id')
        
        logger.info(f"API Dashboard - Filtros recebidos: ano={ano}, mes={mes}, cc_id={cc_id}")
        
        # Verificar quantidade total de registros na tabela
        total_registros = DadoAnalitico.query.count()
        logger.info(f"API Dashboard - Total de registros na tabela: {total_registros}")
        
        # Inicializar variáveis para evitar erros
        total_geral = 0
        total_receitas = 0
        total_despesas = 0
        labels_meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
        dados_meses = [0.0] * 12
        labels_cc = []
        valores_cc = []
        labels_pc = []
        valores_pc = []
        receitas_por_mes = [0.0] * 12
        despesas_por_mes = [0.0] * 12
        acumulado_por_mes = [0.0] * 12
        periodo_texto = "Todos os Anos"
        titulo_grafico = "Evolução Mensal"
        
        # Título do gráfico (inicializado aqui para evitar erros)
        if ano:
            periodo_texto = f"{ano}"
            titulo_grafico = f"Evolução Mensal - {periodo_texto}"
            if mes and mes.isdigit():
                meses_nomes_completos = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
                periodo_texto += f" - {meses_nomes_completos[int(mes)-1]}"
                titulo_grafico = f"Evolução Mensal - {periodo_texto}"

        if cc_id and cc_id.strip():
            try:
                centro_custo = CentroCusto.query.get(cc_id)
                if centro_custo:
                    titulo_grafico = f"Evolução Mensal - {centro_custo.nome} - {periodo_texto}"
            except Exception as e:
                logger.error(f"Erro ao obter centro de custo para título: {str(e)}")

        # Se não há dados, retornar estrutura vazia mas válida
        if total_registros == 0:
            logger.warning("API Dashboard - Nenhum registro encontrado na tabela de dados analíticos")
            return jsonify({
                'total_geral': 0.0,
                'total_receitas': 0.0,
                'total_despesas': 0.0,
                'periodo_texto': periodo_texto,
                'titulo_grafico': titulo_grafico,
                'valores_meses': [0.0] * 12,
                'labels_meses': labels_meses,
                'labels_cc': [],
                'valores_cc': [],
                'labels_pc': [],
                'valores_pc': [],
                'receitas_por_mes': [0.0] * 12,
                'despesas_por_mes': [0.0] * 12,
                'acumulado_por_mes': [0.0] * 12,
                'status': 'empty',
                'message': 'Nenhum dado encontrado'
            })

        # Calcular total geral
        try:
            logger.info("API Dashboard - Calculando total geral")
            query_total = db.session.query(func.sum(DadoAnalitico.valor))
            
            # Aplicar filtros
            if ano:
                query_total = query_total.filter(extract('year', DadoAnalitico.data_pagamento) == ano)
            
            if mes and mes.isdigit():
                query_total = query_total.filter(extract('month', DadoAnalitico.data_pagamento) == mes)
            
            if cc_id and cc_id.strip():
                query_total = query_total.filter(DadoAnalitico.centro_custo_id == cc_id)
            
            # Executar a query
            total_geral = query_total.scalar() or 0
            logger.info(f"API Dashboard - Total geral calculado: {total_geral}")
        except Exception as e:
            logger.error(f"Erro ao calcular total geral: {str(e)}", exc_info=True)
            total_geral = 0
        
        # Se existirem registros, calcular os dados para os gráficos
        if total_registros > 0:
            # Calcular valores por mês
            try:
                logger.info("API Dashboard - Calculando valores por mês")
                if ano:
                    valores_meses_query = db.session.query(
                        extract('month', DadoAnalitico.data_pagamento).label('mes'),
                        func.sum(DadoAnalitico.valor).label('total')
                    ).join(PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id).filter(extract('year', DadoAnalitico.data_pagamento) == ano, PlanoConta.codigo.in_(PL_RECOP))
                    
                    if cc_id and cc_id.strip():
                        valores_meses_query = valores_meses_query.filter(DadoAnalitico.centro_custo_id == cc_id)
                    
                    valores_meses_query = valores_meses_query.group_by('mes').order_by('mes').all()
                    logger.info(f"API Dashboard - Valores por mês encontrados: {len(valores_meses_query)}")
                    
                    for resultado in valores_meses_query:
                        if resultado.mes and 1 <= resultado.mes <= 12:
                            dados_meses[int(resultado.mes)-1] = float(resultado.total or 0)
                else:
                    # Para todos os anos, agrupar por mês
                    valores_meses_query = db.session.query(
                        extract('month', DadoAnalitico.data_pagamento).label('mes'),
                        func.sum(DadoAnalitico.valor).label('total')
                    )
                    
                    if cc_id and cc_id.strip():
                        valores_meses_query = valores_meses_query.filter(DadoAnalitico.centro_custo_id == cc_id)
                    
                    valores_meses_query = valores_meses_query.group_by('mes').order_by('mes').all()
                
                    # Para "Todos os anos", mostramos a soma de cada mês através dos anos
                    meses_somados = {}
                    for resultado in valores_meses_query:
                        if resultado.mes and 1 <= int(resultado.mes) <= 12:
                            mes_num = int(resultado.mes)
                            if mes_num not in meses_somados:
                                meses_somados[mes_num] = 0
                            meses_somados[mes_num] += float(resultado.total or 0)
                    
                    # Preencher o array de dados
                    for i in range(1, 13):
                        dados_meses[i-1] = meses_somados.get(i, 0)
            except Exception as e:
                logger.error(f"Erro ao calcular valores por mês: {str(e)}", exc_info=True)
                # Manter valores padrão inicializados
            
            # Top 10 Centros de Custo
            try:
                logger.info("API Dashboard - Calculando top 10 centros de custo")
                cc_query = db.session.query(
                    CentroCusto.nome,
                    func.sum(DadoAnalitico.valor).label('total')
                ).join(
                    DadoAnalitico, DadoAnalitico.centro_custo_id == CentroCusto.id,
                    PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id
                )
                
                if ano:
                    cc_query = cc_query.filter(extract('year', DadoAnalitico.data_pagamento) == ano)
                
                if mes and mes.isdigit():
                    cc_query = cc_query.filter(extract('month', DadoAnalitico.data_pagamento) == mes)
                
                if cc_id and cc_id.strip():
                    cc_query = cc_query.filter(DadoAnalitico.centro_custo_id == cc_id)
                
                cc_query = cc_query.filter(PlanoConta.codigo.in_(PL_RECOP))
                cc_resultados = cc_query.group_by(CentroCusto.id).order_by(func.sum(DadoAnalitico.valor).desc()).limit(10).all()
                logger.info(f"API Dashboard - Centros de custo encontrados: {len(cc_resultados)}")
                
                # Transformar em listas para o gráfico
                labels_cc = [cc.nome for cc in cc_resultados if cc.nome]
                valores_cc = [float(cc.total or 0) for cc in cc_resultados if cc.nome]
            except Exception as e:
                logger.error(f"Erro ao calcular top 10 centros de custo: {str(e)}", exc_info=True)
                # Manter valores padrão inicializados
            
            # Top 10 Planos de Conta
            try:
                logger.info("API Dashboard - Calculando top 10 planos de conta")
                pc_query = db.session.query(
                    PlanoConta.descricao,
                    func.sum(DadoAnalitico.valor).label('total')
                ).join(
                    DadoAnalitico, DadoAnalitico.plano_conta_id == PlanoConta.id,
                    PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id
                )
                
                if ano:
                    pc_query = pc_query.filter(extract('year', DadoAnalitico.data_pagamento) == ano)
                
                if mes and mes.isdigit():
                    pc_query = pc_query.filter(extract('month', DadoAnalitico.data_pagamento) == mes)
                
                if cc_id and cc_id.strip():
                    pc_query = pc_query.filter(DadoAnalitico.centro_custo_id == cc_id)
                pc_query = pc_query.filter(PlanoConta.codigo.in_(PL_RECOP))
                pc_resultados = pc_query.group_by(PlanoConta.codigo).order_by(func.sum(DadoAnalitico.valor).desc()).limit(10).all()
                logger.info(f"API Dashboard - Planos de conta encontrados: {len(pc_resultados)}")
                
                # Transformar em listas para o gráfico
                labels_pc = [pc.descricao for pc in pc_resultados if pc.descricao]
                valores_pc = [float(pc.total or 0) for pc in pc_resultados if pc.descricao and pc.plano_conta.codigo.in_(PL_CUSTO)]
            except Exception as e:
                logger.error(f"Erro ao calcular top 10 planos de conta: {str(e)}", exc_info=True)
                # Manter valores padrão inicializados
            
            # Receitas vs Despesas
            try:
                logger.info("API Dashboard - Calculando receitas vs despesas")
                # Usar abordagem alternativa: valores positivos como receitas e negativos como despesas
                valores_alternativos_query = db.session.query(
                    extract('month', DadoAnalitico.data_pagamento).label('mes'),
                    func.sum(case([(DadoAnalitico.valor > 0, DadoAnalitico.valor)], else_=0)).label('receita'),
                    func.sum(case([(DadoAnalitico.valor < 0, DadoAnalitico.valor)], else_=0)).label('despesa')
                )
                
                if ano:
                    valores_alternativos_query = valores_alternativos_query.filter(extract('year', DadoAnalitico.data_pagamento) == ano)
                
                if cc_id and cc_id.strip():
                    valores_alternativos_query = valores_alternativos_query.filter(DadoAnalitico.centro_custo_id == cc_id)
                
                resultados_alternativos = valores_alternativos_query.group_by('mes').all()
                logger.info(f"API Dashboard - Resultados alternativos encontrados: {len(resultados_alternativos)}")
                
                # Inicializar arrays
                receitas_por_mes = [0.0] * 12
                despesas_por_mes = [0.0] * 12
                acumulado_por_mes = [0.0] * 12
                
                # Preencher arrays
                for resultado in resultados_alternativos:
                    if resultado.mes and 1 <= int(resultado.mes) <= 12:
                        idx = int(resultado.mes) - 1
                        receitas_por_mes[idx] = float(resultado.receita or 0)
                        despesas_por_mes[idx] = float(resultado.despesa or 0)
                
                # Calcular acumulado
                acumulado = 0
                for i in range(12):
                    acumulado += receitas_por_mes[i] + despesas_por_mes[i]
                    acumulado_por_mes[i] = acumulado
                    
                # Calcular totais para cards
                total_receitas = sum(receitas_por_mes)
                total_despesas = sum(despesas_por_mes)
                logger.info(f"API Dashboard - Total receitas: {total_receitas}, Total despesas: {total_despesas}")
            except Exception as e:
                logger.error(f"Erro ao calcular receitas vs despesas: {str(e)}", exc_info=True)
                # Manter valores padrão inicializados
        
        logger.info("API Dashboard - Preparando resposta JSON")
        return jsonify({
            'total_geral': float(total_geral),
            'total_receitas': float(total_receitas),
            'total_despesas': float(total_despesas),
            'periodo_texto': periodo_texto,
            'titulo_grafico': titulo_grafico,
            'valores_meses': dados_meses,
            'labels_meses': labels_meses,
            'labels_cc': labels_cc,
            'valores_cc': valores_cc,
            'labels_pc': labels_pc,
            'valores_pc': valores_pc,
            'receitas_por_mes': receitas_por_mes,
            'despesas_por_mes': despesas_por_mes,
            'acumulado_por_mes': acumulado_por_mes,
            'status': 'success'
        })
    except Exception as e:
        logger.error(f"Erro geral na API de dashboard: {str(e)}", exc_info=True)
        # Tente fornecer uma mensagem de erro mais detalhada
        error_details = traceback.format_exc()
        logger.error(f"Detalhes do erro:\n{error_details}")
        
        return jsonify({
            'error': str(e),
            'status': 'error',
            'message': 'Ocorreu um erro ao processar os dados do dashboard: ' + str(e),
            'details': error_details[:200]  # Limitar os detalhes para não expor muito da estrutura
        }), 500, {'Content-Type': 'application/json; charset=utf-8'}

@dados_analiticos_bp.route('/exportar')
@login_required
#@verificar_permissao('visualizar_dados_analiticos')
def exportar():
    """
    Exporta os dados analíticos filtrados para um arquivo Excel.
    Reutiliza a lógica de filtro da visualização principal.
    """
    try:
        # Obter parâmetros de filtro (adaptado para múltiplos centros de custo)
        filtros = {
                'ano': request.args.get('ano', type=int),
            'mes': request.args.get('mes', type=int),
                'centro_custo_ids': request.args.getlist('centro_custo_id', type=int) # Recebe lista
                # 'plano_conta_id': request.args.get('plano_conta_id', type=int), # Removido - não usado no dashboard mensal
                # 'sort_by': request.args.get('sort_by', 'data_pagamento'), # Removido - ordena por data padrão
                # 'sort_dir': request.args.get('sort_dir', 'desc')
            }
        
        logger.info(f"Exportação - Filtros aplicados: {filtros}")
        
        # Construir a query base com joins necessários para nomes
        query = db.session.query(DadoAnalitico).options(
            db.joinedload(DadoAnalitico.centro_custo),
            db.joinedload(DadoAnalitico.plano_conta)
        )
    
    # Aplicar filtros
        if filtros['ano']:
            query = query.filter(DadoAnalitico.ano == filtros['ano'])
        
        if filtros['mes']:
            query = query.filter(DadoAnalitico.mes == filtros['mes'])
        
            # Aplicar filtro de múltiplos centros de custo
            if filtros['centro_custo_ids']:
                query = query.filter(DadoAnalitico.centro_custo_id.in_(filtros['centro_custo_ids']))
            
            # Ordenação padrão por data para exportação
            query = query.order_by(DadoAnalitico.data_pagamento.asc())
        
        # Executar a query
        dados = query.all()
        
        logger.info(f"Exportação - {len(dados)} registros encontrados.")
        
        if not dados:
            flash("Nenhum dado encontrado para os filtros selecionados.", "warning")
            # Redirecionar de volta ou mostrar mensagem
            # Idealmente, o botão de exportar deveria ser desabilitado se não houver dados,
            # mas por enquanto, redirecionamos para a página anterior.
            referer = request.headers.get("Referer")
            return redirect(referer or url_for('dados_analiticos.dashboard_mensal'))

        # Preparar dados para DataFrame
        dados_para_df = []
        for dado in dados:
                dados_para_df.append({
                    'Data Pagamento': dado.data_pagamento.strftime('%d/%m/%Y') if dado.data_pagamento else None,
                    'Ano': dado.ano,
                    'Mês': dado.mes,
                    'Centro Custo Código': dado.centro_custo.codigo if dado.centro_custo else None,
                    'Centro Custo Nome': dado.centro_custo.nome if dado.centro_custo else None,
                    'Plano Conta Código': dado.plano_conta.codigo if dado.plano_conta else None,
                    'Plano Conta Descrição': dado.plano_conta.descricao if dado.plano_conta else None,
                    'Documento': dado.documento,
                    'Emitente': dado.emitente,
                    'Débito/Crédito': dado.debito_credito,
                    'Histórico': dado.historico,
                    'Valor': float(dado.valor) if dado.valor is not None else 0.0
                })
            
        # Criar DataFrame
        df = pd.DataFrame(dados_para_df)
        
        # Criar Excel na memória
        output = io.BytesIO()
        # Alterar engine para openpyxl
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Adicionar encoding utf-8 explicitamente (geralmente redundante com openpyxl)
            # Remover argumento 'encoding', pois não é válido para to_excel com engine openpyxl
            df.to_excel(writer, index=False, sheet_name='Dados Analíticos') #, encoding='utf-8')
            # Auto-ajuste das colunas (opcional, requer openpyxl)
            # worksheet = writer.sheets['Dados Analíticos']
            # for column in worksheet.columns:
            #     max_length = 0
            #     column_letter = get_column_letter(column[0].column)
            #     for cell in column:
            #         try:
            #             if len(str(cell.value)) > max_length:
            #                 max_length = len(cell.value)
            #         except:
            #             pass
            #     adjusted_width = (max_length + 2)
            #     worksheet.column_dimensions[column_letter].width = adjusted_width
        output.seek(0)
        
        # Nome do arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"export_dados_analiticos_{timestamp}.xlsx"
    
        logger.info(f"Exportação - Enviando arquivo: {filename}")
        
            # Enviar arquivo Excel
        return send_file(
                output,
            as_attachment=True,
            download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

    except Exception as e:
        logger.error(f"Erro durante a exportação para Excel: {str(e)}", exc_info=True)
        flash(f"Ocorreu um erro ao gerar o arquivo Excel: {str(e)}", "danger")
        referer = request.headers.get("Referer")
        return redirect(referer or url_for('dados_analiticos.dashboard_mensal'))

@dados_analiticos_bp.route('/api/dados-por-mes')
@login_required
#@verificar_permissao('visualizar_dados_analiticos')
def api_dados_por_mes():
    """
    Retorna dados por mês para API.
    """
    # Obter parâmetros
    ano = request.args.get('ano', datetime.now().year, type=int)
    centro_custo_id = request.args.get('centro_custo_id', type=int)
    
    # Consulta para valores por mês
    valores_meses = db.session.query(
        DadoAnalitico.mes,
        func.sum(DadoAnalitico.valor).label('total')
    ).filter(
        DadoAnalitico.ano == ano,
        DadoAnalitico.centro_custo_id == centro_custo_id if centro_custo_id else True
    ).group_by(
        DadoAnalitico.mes
    ).order_by(
        DadoAnalitico.mes
    ).all()
    
    # Formatar para JSON
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    dados_meses = [0] * 12
    for mes, total in valores_meses:
        if mes and 1 <= mes <= 12:
            dados_meses[mes-1] = float(total)
    
    return jsonify({
        'labels': meses,
        'data': dados_meses
    })


@dados_analiticos_bp.route('/api/dados-por-plano-conta')
@login_required
#@verificar_permissao('visualizar_dados_analiticos')
def api_dados_por_plano_conta():
    """
    Retorna dados por plano de conta para API.
    """
    # Obter parâmetros
    ano = request.args.get('ano', datetime.now().year, type=int)
    centro_custo_id = request.args.get('centro_custo_id', type=int)
    limit = request.args.get('limit', 10, type=int)
    
    # Consulta para valores por plano de conta
    query = db.session.query(
        PlanoConta.descricao.label('nome'),
        func.sum(DadoAnalitico.valor).label('total')
    ).join(
        PlanoConta, PlanoConta.id == DadoAnalitico.plano_conta_id
    ).filter(
        DadoAnalitico.ano == ano,
        DadoAnalitico.centro_custo_id == centro_custo_id if centro_custo_id else True
    ).group_by(
        PlanoConta.descricao
    ).order_by(
        func.sum(DadoAnalitico.valor).desc()
    ).limit(limit)
    
    dados_pc = query.all()
    
    # Formatar para JSON
    labels = [item[0] for item in dados_pc]
    valores = [float(item[1]) for item in dados_pc]
    
    return jsonify({
        'labels': labels,
        'data': valores
    })

@dados_analiticos_bp.route('/api/totais')
@login_required
#@verificar_permissao('visualizar_dados_analiticos')
def api_totais():
    """
    Retorna totais para a API.
    """
    # Obter parâmetros
    ano = request.args.get('ano', datetime.now().year, type=int)
    centro_custo_id = request.args.get('centro_custo_id', type=int)
    
    # Calcular total geral
    total_geral = db.session.query(
        func.sum(DadoAnalitico.valor)
    ).filter(
        DadoAnalitico.ano == ano,
        DadoAnalitico.centro_custo_id == centro_custo_id if centro_custo_id else True
    ).scalar() or 0
    
    # Calcular média mensal
    valores_meses = db.session.query(
        DadoAnalitico.mes,
        func.sum(DadoAnalitico.valor).label('total')
    ).filter(
        DadoAnalitico.ano == ano,
        DadoAnalitico.centro_custo_id == centro_custo_id if centro_custo_id else True
    ).group_by(
        DadoAnalitico.mes
    ).all()
    
    if valores_meses:
        media_mensal = float(total_geral) / len(valores_meses)
    else:
        media_mensal = 0
    
    # Encontrar maior e menor mês
    maior_mes = None
    maior_valor = 0
    menor_mes = None
    menor_valor = float('inf')
    
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    for mes, valor in valores_meses:
        if mes and 1 <= mes <= 12:
            if float(valor) > maior_valor:
                maior_valor = float(valor)
                maior_mes = meses[mes-1]
            
            if float(valor) < menor_valor:
                menor_valor = float(valor)
                menor_mes = meses[mes-1]
    
    # Se não houver dados, definir valores padrão
    if menor_valor == float('inf'):
        menor_valor = 0
        menor_mes = "N/A"
    
    return jsonify({
        'total_geral': float(total_geral),
        'media_mensal': media_mensal,
        'maior_mes': maior_mes,
        'maior_valor': maior_valor,
        'menor_mes': menor_mes,
        'menor_valor': menor_valor
    })



@dados_analiticos_bp.route('/dashboard/mensal')
@login_required
def dashboard_mensal():
    """Exibe o dashboard mensal com os gráficos de análise financeira usando Plotly"""
    # Obter filtros
    ano = request.args.get('ano', '')  # Vazio como padrão para mostrar "Todos os Anos"
    mes = request.args.get('mes')
    # Alterado para obter lista de IDs de centro de custo
    cc_ids = request.args.getlist('cc_id') 
    
    # Definir filtros para passar para o template
    filtros = {
        'ano': ano,
        'mes': int(mes) if mes and mes.isdigit() else None,
        # Passar a lista de cc_ids
        'cc_id': cc_ids 
    }
    
    # Obter lista de anos disponíveis usando SQLAlchemy
    anos_disponiveis = db.session.query(
        extract('year', DadoAnalitico.data_pagamento).distinct().label('ano')
    ).order_by('ano').all()
    
    anos = [int(ano.ano) for ano in anos_disponiveis if ano.ano is not None]
    
    # Obter centros de custo usando SQLAlchemy
    centros_custo = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.codigo).all()
    
    # Título do período para exibição
    periodo_texto = f"{ano}" if ano else "Todos os Anos"
    if mes and mes.isdigit():
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        periodo_texto += f" - {meses[int(mes)-1]}"
    
    return render_template('relatorios/dados_analiticos/dashboard_mensal.html',
                          anos=anos,
                          centros_custo=centros_custo,
                          filtros=filtros,
                          periodo_texto=periodo_texto)

@dados_analiticos_bp.route('/api/dashboard-mensal')
@login_required
def api_dashboard_mensal():
    """API para retornar dados do dashboard mensal via AJAX"""
    try:
        # Obter filtros
        ano = request.args.get('ano')
        mes = request.args.get('mes')
        cc_ids = request.args.getlist('cc_id') 
        
        logger.info(f"API Dashboard Mensal - Filtros recebidos: ano={ano}, mes={mes}, cc_ids={cc_ids}")
        
        # Chamar função auxiliar para obter os dados
        dados_calculados = _calcular_dados_dashboard_mensal(ano, mes, cc_ids)
        return jsonify(dados_calculados)
        
    except Exception as e:
        logger.error(f"Erro na API de dashboard mensal: {str(e)}", exc_info=True)
        # Tenta capturar mais detalhes do erro se possível
        error_details = traceback.format_exc()
        return jsonify({
            'error': str(e),
            'message': 'Ocorreu um erro ao processar os dados do dashboard: ' + str(e),
            'details': error_details[:500] # Aumentar limite para detalhes
        }), 500, {'Content-Type': 'application/json; charset=utf-8'}

# --- Função Auxiliar para Cálculo dos Dados do Dashboard Mensal ---
def _calcular_dados_dashboard_mensal(ano: Optional[str], mes: Optional[str], cc_ids: List[int]):
    """
    Calcula os dados necessários para o dashboard mensal e a tabela de resumo.
    Reutilizada pela API e pela exportação da tabela.
    
    Args:
        ano: Ano selecionado (string ou None).
        mes: Mês selecionado (string ou None).
        cc_ids: Lista de IDs de centros de custo selecionados.
        
    Returns:
        Dicionário contendo os dados calculados.
    """
    logger.info(f"Calculando dados para Dashboard Mensal: ano={ano}, mes={mes}, cc_ids={cc_ids}")
        
    # Inicializar variáveis
    labels_meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    meses_completos = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    
    # Verificar se é visualização de todos os anos
    todos_anos = not (ano and ano.strip())
    ano_int = int(ano) if ano and ano.strip() else None
    mes_int = int(mes) if mes and mes.isdigit() else None

    # Estrutura de retorno
    dados_calculados = {
        'todos_anos': todos_anos,
        'ano_selecionado': ano_int,
        'mes_selecionado': mes_int,
        'labels_meses': labels_meses,
        'meses_completos': meses_completos,
        'receitas_por_mes': [0.0] * 12,
        'custos_por_mes': [0.0] * 12,
        'saldo_por_mes': [0.0] * 12,
        'receitas_acumuladas_por_mes': [0.0] * 12,
        'custos_acumulados_por_mes': [0.0] * 12,
        'saldo_acumulado_por_mes': [0.0] * 12,
        'anos_disponiveis': [],
        'receitas_por_ano_mes': {},
        'custos_por_ano_mes': {},
        'saldo_por_ano_mes': {},
        'labels_anos_meses': [],
        'valores_receitas_anos': [],
        'valores_custos_anos': [],
        'valores_saldo_anos': [],
        'valores_saldo_acumulado_anos': [],
        'labels_cc': [],
        'valores_cc': [],
        'total_receita': 0.0,
        'total_custo': 0.0,
        'ultima_atualizacao': '',
        'detalhes_por_plano': {},
        'detalhes_por_plano_hierarquico': {},
        'periodo_texto': ""
    }
        
        # Título do período para exibição
    periodo_texto = f"{ano_int}" if ano_int else "Todos os Anos"
    if mes_int:
        periodo_texto += f" - {meses_completos[mes_int-1]}"
    dados_calculados['periodo_texto'] = periodo_texto

    # --- Obter dados básicos (Receita e Custo Total) --- 
    try:
        # Obter a data mais recente de importação
        ultima_importacao = db.session.query(func.max(DadoAnalitico.importado_em)).scalar()
        dados_calculados['ultima_atualizacao'] = ultima_importacao.strftime('%d/%m/%Y %H:%M:%S') if ultima_importacao else ''

        query_base = db.session.query(DadoAnalitico).join(
                PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id
        )
        
        # Aplicar filtros de data e CC
        if ano_int:
            query_base = query_base.filter(extract('year', DadoAnalitico.data_pagamento) == ano_int)
        if mes_int:
            query_base = query_base.filter(extract('month', DadoAnalitico.data_pagamento) == mes_int)
        if cc_ids:
            query_base = query_base.filter(DadoAnalitico.centro_custo_id.in_(cc_ids))

        # Calcular totais
        total_receita_query = query_base.filter(PlanoConta.codigo.in_(PL_RECOP)).with_entities(func.sum(DadoAnalitico.valor))
        total_custo_query = query_base.filter(PlanoConta.codigo.in_(PL_CUSTO)).with_entities(func.sum(DadoAnalitico.valor))
        
        dados_calculados['total_receita'] = float(total_receita_query.scalar() or 0)
        dados_calculados['total_custo'] = float(total_custo_query.scalar() or 0)
        logger.info(f"Totais calculados: Receita={dados_calculados['total_receita']}, Custo={dados_calculados['total_custo']}")

    except Exception as e:
        logger.error(f"Erro ao calcular totais de receita e custo: {str(e)}", exc_info=True)
        # Retorna dados zerados se falhar
        return dados_calculados 
        
    # --- Cálculos específicos por tipo de visualização (Todos Anos vs Ano Único) --- 
    if todos_anos:
        # Cálculo para todos os anos (agrupado por ano/mês)
        try:
            anos_query = db.session.query(
                extract('year', DadoAnalitico.data_pagamento).label('ano')
            ).distinct().order_by('ano').all()
            dados_calculados['anos_disponiveis'] = [int(a.ano) for a in anos_query if a.ano is not None]
            logger.info(f"Anos disponíveis: {dados_calculados['anos_disponiveis']}")

            query_dados_anos = db.session.query(
                    extract('year', DadoAnalitico.data_pagamento).label('ano'),
                    extract('month', DadoAnalitico.data_pagamento).label('mes'),
                    PlanoConta.codigo.label('plano_codigo'),
                    func.sum(DadoAnalitico.valor).label('total')
                ).join(
                    PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id
                ).filter(
                    DadoAnalitico.data_pagamento != None
                )
            # Aplicar filtros de mês e CC se existirem
            if mes_int:
                query_dados_anos = query_dados_anos.filter(extract('month', DadoAnalitico.data_pagamento) == mes_int)
            if cc_ids:
                query_dados_anos = query_dados_anos.filter(DadoAnalitico.centro_custo_id.in_(cc_ids))
            
            query_dados_anos = query_dados_anos.group_by('ano', 'mes', 'plano_codigo').order_by('ano', 'mes')
            resultados_anos = query_dados_anos.all()
            
            # Processar resultados para preencher dicionários
            for r in resultados_anos:
                if r.ano is None or r.mes is None: continue
                key = f"{int(r.ano)}-{int(r.mes)}"
                if key not in dados_calculados['receitas_por_ano_mes']:
                    dados_calculados['receitas_por_ano_mes'][key] = 0.0
                    dados_calculados['custos_por_ano_mes'][key] = 0.0
                valor = float(r.total or 0)
                if r.plano_codigo in PL_RECOP: dados_calculados['receitas_por_ano_mes'][key] += valor
                elif r.plano_codigo in PL_CUSTO: dados_calculados['custos_por_ano_mes'][key] += valor

            # Calcular saldo e criar listas ordenadas para gráficos
            # Ordenar as chaves cronologicamente (Ano, Mês)
            def sort_key_func(key):
                ano, mes = map(int, key.split('-'))
                return ano, mes
            keys_ordenadas = sorted(dados_calculados['receitas_por_ano_mes'].keys(), key=sort_key_func)

            saldo_acumulado = 0
            for key in keys_ordenadas:
                ano_mes_split = key.split('-')
                label_ano_mes = f"{labels_meses[int(ano_mes_split[1])-1]}/{ano_mes_split[0][-2:]}" # Formato Ex: Jan/23
                receita = dados_calculados['receitas_por_ano_mes'][key]
                custo = dados_calculados['custos_por_ano_mes'][key]
                saldo = receita - custo
                saldo_acumulado += saldo
                dados_calculados['saldo_por_ano_mes'][key] = saldo
                dados_calculados['labels_anos_meses'].append(label_ano_mes)
                dados_calculados['valores_receitas_anos'].append(receita)
                dados_calculados['valores_custos_anos'].append(custo)
                dados_calculados['valores_saldo_anos'].append(saldo)
                dados_calculados['valores_saldo_acumulado_anos'].append(saldo_acumulado)
                
            # Popular listas mensais com dados do último ano disponível (se aplicável e se não houver filtro de mês)
            if not mes_int and dados_calculados['anos_disponiveis']:
                    ultimo_ano = dados_calculados['anos_disponiveis'][-1]
                    for mes_idx in range(12):
                        key_ultimo_ano = f"{ultimo_ano}-{mes_idx+1}"
                        if key_ultimo_ano in dados_calculados['receitas_por_ano_mes']:
                            dados_calculados['receitas_por_mes'][mes_idx] = dados_calculados['receitas_por_ano_mes'][key_ultimo_ano]
                            dados_calculados['custos_por_mes'][mes_idx] = dados_calculados['custos_por_ano_mes'][key_ultimo_ano]
                            dados_calculados['saldo_por_mes'][mes_idx] = dados_calculados['saldo_por_ano_mes'][key_ultimo_ano]
                    # Calcular acumulados para o último ano
                    acum_r, acum_c, acum_s = 0.0, 0.0, 0.0
                    for mes_idx in range(12):
                        acum_r += dados_calculados['receitas_por_mes'][mes_idx]
                        acum_c += dados_calculados['custos_por_mes'][mes_idx]
                        acum_s += dados_calculados['saldo_por_mes'][mes_idx]
                        dados_calculados['receitas_acumuladas_por_mes'][mes_idx] = acum_r
                        dados_calculados['custos_acumulados_por_mes'][mes_idx] = acum_c
                        dados_calculados['saldo_acumulado_por_mes'][mes_idx] = acum_s
                
        except Exception as e: 
            logger.error(f"Erro ao calcular dados para todos os anos: {str(e)}", exc_info=True)

    elif ano_int:
        # Cálculo para um único ano (agrupado por mês)
        try:
            query_dados_mes = db.session.query(
                    extract('month', DadoAnalitico.data_pagamento).label('mes'),
                PlanoConta.codigo.label('plano_codigo'),
                    func.sum(DadoAnalitico.valor).label('total')
                ).join(
                    PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id
                ).filter(
                extract('year', DadoAnalitico.data_pagamento) == ano_int
            )
            # Aplicar filtros de mês e CC se existirem
            if mes_int:
                query_dados_mes = query_dados_mes.filter(extract('month', DadoAnalitico.data_pagamento) == mes_int)
            if cc_ids:
                query_dados_mes = query_dados_mes.filter(DadoAnalitico.centro_custo_id.in_(cc_ids))
            
            query_dados_mes = query_dados_mes.group_by('mes', 'plano_codigo').order_by('mes')
            resultados_mes = query_dados_mes.all()
            
            # Processar resultados para preencher listas mensais
            for r in resultados_mes:
                if r.mes is None: continue
                mes_idx = int(r.mes) - 1
                if 0 <= mes_idx < 12:
                    valor = float(r.total or 0)
                    if r.plano_codigo in PL_RECOP: dados_calculados['receitas_por_mes'][mes_idx] += valor
                    elif r.plano_codigo in PL_CUSTO: dados_calculados['custos_por_mes'][mes_idx] += valor
            
            # Calcular saldo e acumulados mensais
            acum_r, acum_c, acum_s = 0.0, 0.0, 0.0
            for mes_idx in range(12):
                receita_mes = dados_calculados['receitas_por_mes'][mes_idx]
                custo_mes = dados_calculados['custos_por_mes'][mes_idx]
                saldo_mes = receita_mes - custo_mes
                dados_calculados['saldo_por_mes'][mes_idx] = saldo_mes
                
                acum_r += receita_mes
                acum_c += custo_mes
                acum_s += saldo_mes
                dados_calculados['receitas_acumuladas_por_mes'][mes_idx] = acum_r
                dados_calculados['custos_acumulados_por_mes'][mes_idx] = acum_c
                dados_calculados['saldo_acumulado_por_mes'][mes_idx] = acum_s
                        
        except Exception as e:
            logger.error(f"Erro ao calcular dados para o ano {ano_int}: {str(e)}", exc_info=True)
            
    # --- Cálculo do Top Centros de Custo (independente de ser ano único ou todos) ---
    try:
        query_cc = db.session.query(
            CentroCusto.nome,
                    func.sum(DadoAnalitico.valor).label('total')
                ).join(
           
            DadoAnalitico, DadoAnalitico.centro_custo_id == CentroCusto.id
        ).join(
            PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id
        ).filter(PlanoConta.codigo.in_(PL_RECOP)) # Apenas custos para top CC
        
        # Aplicar filtros de data (CC não é filtrado aqui, pois queremos o top geral ou do período)
        if ano_int:
            query_cc = query_cc.filter(extract('year', DadoAnalitico.data_pagamento) == ano_int)
        if mes_int:
            query_cc = query_cc.filter(extract('month', DadoAnalitico.data_pagamento) == mes_int)
        # Se cc_ids foi fornecido, filtra por eles em vez de calcular o top
        if cc_ids:
            query_cc = query_cc.filter(DadoAnalitico.centro_custo_id.in_(cc_ids))
            
        query_cc = query_cc.group_by(DadoAnalitico.centro_custo_id).order_by(func.sum(DadoAnalitico.valor).asc())
        # Limita o top N apenas se não houver filtro de CC específico
        if not cc_ids: 
             query_cc = query_cc.limit(10) 
             
        cc_resultados = query_cc.all()
        dados_calculados['labels_cc'] = [r.nome for r in cc_resultados]
        dados_calculados['valores_cc'] = [float(r.total or 0) for r in cc_resultados]

    except Exception as e:
        logger.error(f"Erro ao calcular top centros de custo: {str(e)}", exc_info=True)

    # --- Cálculo Detalhes por Plano de Conta (Refatorado para Agrupar Primeiro) --- 
    try:
        # Query base continua a mesma
        query_base_detalhe = db.session.query(
            PlanoConta.codigo.label('plano_codigo'),
            PlanoConta.descricao.label('plano_descricao'),
            PlanoConta.indice.label('plano_indice'), 
            func.sum(DadoAnalitico.valor).label('total')
        ).join(PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id)
        
        # Aplicar filtros de data e CC
        if ano_int: query_base_detalhe = query_base_detalhe.filter(extract('year', DadoAnalitico.data_pagamento) == ano_int)
        if mes_int: query_base_detalhe = query_base_detalhe.filter(extract('month', DadoAnalitico.data_pagamento) == mes_int)
        if cc_ids: query_base_detalhe = query_base_detalhe.filter(DadoAnalitico.centro_custo_id.in_(cc_ids))
            
        # Agrupar pelos campos relevantes (sem ordenar por índice ainda)
        detalhes_plano_resultados = query_base_detalhe.group_by(
            PlanoConta.codigo, PlanoConta.descricao, PlanoConta.indice 
        ).all() # Obter todos os resultados individuais
        
        logger.info(f"Detalhes plano query results count: {len(detalhes_plano_resultados)}")

        # *** NOVA LÓGICA: Construir árvores separadas por grupo ***
        arvore_receitas = {}
        arvore_custos = {}
        arvore_outros = {}
        planos_processados_count = 0

        for resultado in detalhes_plano_resultados:
             # Validar se o índice existe e não está vazio
            if resultado.plano_indice and resultado.plano_indice.strip(): 
                codigo_plano = resultado.plano_codigo
                indice_plano = resultado.plano_indice.strip()
                nome_plano = resultado.plano_descricao
                valor_plano = float(resultado.total or 0)
                
                # Determinar o grupo e a árvore de destino
                grupo_chave = 'OUTROS'
                arvore_destino = arvore_outros
                if codigo_plano in PL_RECOP:
                    grupo_chave = 'RECEITAS'
                    arvore_destino = arvore_receitas
                elif codigo_plano in PL_CUSTO:
                    grupo_chave = 'CUSTOS'
                    arvore_destino = arvore_custos
                    
                #logger.debug(f"Processing: Idx={indice_plano}, Cod={codigo_plano}, Grupo={grupo_chave}, Valor={valor_plano}")
                
                # Inserir na árvore correta
                try:
                    inserir_na_arvore(
                        arvore_destino, 
                        indice_plano,
                        nome_plano, 
                        valor_plano,
                        codigo_plano 
                    )
                    planos_processados_count += 1
                except Exception as insert_err:
                    logger.warning(f"Erro ao inserir nó {indice_plano} na árvore {grupo_chave}: {insert_err}", exc_info=True)
            else:
                logger.warning(f"Skipping result due to empty or null indice: Plano Cod={resultado.plano_codigo}, Desc={resultado.plano_descricao}")
        
       # logger.info(f"Total planos processados e inseridos nas árvores: {planos_processados_count}")

        # *** Calcular totais e ordenar para CADA árvore ***
        resultado_final_agrupado = {}
        grupo_map = {
            'RECEITAS': {'nome': 'RECEITAS', 'arvore': arvore_receitas},
            'CUSTOS': {'nome': 'CUSTOS', 'arvore': arvore_custos},
            'OUTROS': {'nome': 'OUTROS', 'arvore': arvore_outros}
        }

        for grupo_chave, grupo_info in grupo_map.items():
            arvore_atual = grupo_info['arvore']
            if not arvore_atual: # Pular se a árvore estiver vazia
                #logger.info(f"Grupo {grupo_chave} está vazio, pulando cálculo de totais e ordenação.")
                continue 
            
            #logger.info(f"Calculando totais e ordenando para grupo: {grupo_chave}")
            valor_total_grupo = 0.0
            # Calcular totais recursivamente
            for raiz_key in list(arvore_atual.keys()): 
                try:
                    valor_total_grupo += calcular_totais_arvore(arvore_atual[raiz_key], raiz_key)
                except Exception as calc_err:
                    logger.warning(f"Erro ao calcular totais para raiz {raiz_key} no grupo {grupo_chave}: {calc_err}", exc_info=True) 
            
            # Ordenar as chaves raiz da árvore do grupo
            try:
                chaves_raiz_ordenadas = sorted(arvore_atual.keys(), key=lambda k: tuple(map(int, k.split('.'))))
            except ValueError:
                logger.warning(f"Não foi possível ordenar numericamente as chaves raiz do grupo {grupo_chave}, usando ordenação alfabética.")
                chaves_raiz_ordenadas = sorted(arvore_atual.keys())
            arvore_ordenada_grupo = {k: arvore_atual[k] for k in chaves_raiz_ordenadas}
            
            # Adicionar ao resultado final
            resultado_final_agrupado[grupo_chave] = {
                'nome': grupo_info['nome'],
                'valor_total': valor_total_grupo,
                'arvore_indices': arvore_ordenada_grupo # Mudar chave para corresponder ao frontend
            }
            #logger.debug(f"Grupo {grupo_chave} finalizado. Total: {valor_total_grupo}. Árvore:{pprint.pformat(arvore_ordenada_grupo)}")

        # --- DEBUGGING LOG FINAL ---
        #logger.info(f"Final GROUPED hierarchical data being returned (Top level keys): {list(resultado_final_agrupado.keys())}") 
        # logger.debug(f"Estrutura Final Agrupada e Ordenada:\n{pprint.pformat(resultado_final_agrupado)}\n")
        # --- END DEBUGGING LOG ---
        
        # *** ATRIBUIÇÃO FINAL AO RESULTADO ***
        dados_calculados['detalhes_por_plano_hierarquico'] = resultado_final_agrupado
        #logger.info(f"Detalhes por plano hierárquico (agrupados por tipo) calculados com sucesso.") 

    except Exception as e:
        logger.error(f"Erro GERAL ao calcular detalhes por plano de conta hierárquico: {str(e)}", exc_info=True) 
        dados_calculados['detalhes_por_plano_hierarquico'] = {} 
    
        # ... (Restante da função _calcular_dados_dashboard_mensal, certificando-se de que não há código antigo de agrupamento/árvore única remanescente) ...
    #print(f"Dados calculados: {dados_calculados}")
    return dados_calculados

@dados_analiticos_bp.route('/api/dados-por-centro-custo')
@login_required
#@verificar_permissao('visualizar_dados_analiticos')
def api_dados_por_centro_custo():
    """
    Retorna dados por centro de custo para API.
    """
    # Obter parâmetros
    ano = request.args.get('ano', datetime.now().year, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    # Consulta para valores por centro de custo
    dados_cc = db.session.query(
        CentroCusto.nome,
                func.sum(DadoAnalitico.valor).label('total')
            ).join(
        CentroCusto, CentroCusto.id == DadoAnalitico.centro_custo_id
            ).filter(
        DadoAnalitico.ano == ano
    ).group_by(
        CentroCusto.nome
    ).order_by(
        func.sum(DadoAnalitico.valor).desc()
    ).limit(limit).all()
    
    # Formatar para JSON
    labels = [item[0] for item in dados_cc]
    valores = [float(item[1]) for item in dados_cc]
    
    return jsonify({
        'labels': labels,
        'data': valores
    })




@dados_analiticos_bp.route('/dashboard/status')
@login_required
def dashboard_status():
    """
    Rota para verificar o status dos dados no dashboard
    """
    # Verificar quantidade total de registros na tabela
    total_registros = DadoAnalitico.query.count()
    
    # Verificar categorias de planos de conta
    planos_receita = db.session.query(PlanoConta).filter(PlanoConta.codigo.in_(PL_RECOP)).all()
    planos_custo = db.session.query(PlanoConta).filter(PlanoConta.codigo.in_(PL_CUSTO)).all()
    
    # Verificar dados por categoria
    receitas = db.session.query(func.sum(DadoAnalitico.valor)).join(
        PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id
    ).filter(
        PlanoConta.codigo.in_(PL_RECOP)
    ).scalar() or 0
    
    custos = db.session.query(func.sum(DadoAnalitico.valor)).join(
        PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id
    ).filter(
        PlanoConta.codigo.in_(PL_CUSTO)
    ).scalar() or 0
    
    # Verificar dados gerais
    dados_por_mes = db.session.query(
        extract('month', DadoAnalitico.data_pagamento).label('mes'),
        func.sum(DadoAnalitico.valor).label('total')
    ).group_by('mes').order_by('mes').all()
    
    return jsonify({
        'total_registros': total_registros,
        'total_planos_receita': len(planos_receita),
        'total_planos_custo': len(planos_custo),
        'valor_receitas': float(receitas),
        'valor_custos': float(custos),
        'planos_receita': [{'codigo': p.codigo, 'descricao': p.descricao} for p in planos_receita],
        'planos_custo': [{'codigo': p.codigo, 'descricao': p.descricao} for p in planos_custo[:10]],
        'dados_por_mes': [{'mes': r.mes, 'total': float(r.total)} for r in dados_por_mes]
    })





@dados_analiticos_bp.route('/api/exportar-dashboard-mensal-tabela')
@login_required
def exportar_dashboard_mensal_tabela():
    """Exporta a tabela de resumo mensal (Receita/Custo/Saldo - Mensal/Acumulado) para Excel."""
    try:
        # Obter filtros da requisição
        ano = request.args.get('ano')
        mes = request.args.get('mes')
        cc_ids = request.args.getlist('cc_id', type=int) # Usar cc_id como no frontend
        
        logger.info(f"Exportação Tabela Mensal - Filtros: ano={ano}, mes={mes}, cc_ids={cc_ids}")

        # Chamar a função auxiliar para obter os dados calculados
        dados = _calcular_dados_dashboard_mensal(ano, mes, cc_ids)
        
        # Verificar se há dados para exportar (focado nos dados mensais)
        # Uma simples verificação se o cálculo foi bem sucedido (pode ser mais específica)
        if dados is None or (not dados['total_receita'] and not dados['total_custo']):
             flash("Nenhum dado de resumo mensal encontrado para os filtros selecionados.", "warning")
             referer = request.headers.get("Referer")
             return redirect(referer or url_for('dados_analiticos.dashboard_mensal'))

        # Preparar dados para o DataFrame (Períodos nas colunas)
        is_todos_anos = dados['todos_anos']
        metricas_nomes = [
            'Receita', 'Receita Acumulada', 'Custo', 
            'Custo Acumulado', 'Saldo', 'Saldo Acumulado'
        ]
        
        # Selecionar labels e dados corretos baseados no filtro de ano
        if is_todos_anos:
            labels_periodo = dados.get('labels_anos_meses', [])
            # Calcular acumulados que a API não retorna diretamente para "todos anos"
            receitas_acum_anos = pd.Series(dados.get('valores_receitas_anos', [])).cumsum().tolist()
            custos_acum_anos = pd.Series(dados.get('valores_custos_anos', [])).cumsum().tolist()
            dados_para_exportar = [
                dados.get('valores_receitas_anos', []),
                receitas_acum_anos,
                dados.get('valores_custos_anos', []),
                custos_acum_anos,
                dados.get('valores_saldo_anos', []),
                dados.get('valores_saldo_acumulado_anos', [])
            ]
        else:
            labels_periodo = dados.get('labels_meses', []) # Jan, Fev, ...
            chaves_dados = [ # Usar chaves mensais
                'receitas_por_mes', 'receitas_acumuladas_por_mes', 'custos_por_mes',
                'custos_acumulados_por_mes', 'saldo_por_mes', 'saldo_acumulado_por_mes'
            ]
            dados_para_exportar = [dados.get(chave, [0.0]*12) for chave in chaves_dados]
         
        # Criar dicionário para o DataFrame { Coluna: [Valores] }
        df_data = {'Métrica': metricas_nomes}
        num_periodos = len(labels_periodo)

        for i, periodo_label in enumerate(labels_periodo):
            coluna_periodo = []
            for j in range(len(metricas_nomes)): # Iterar sobre métricas
                 # Acessar a lista correta de dados e pegar o valor do período i
                valor = dados_para_exportar[j][i] if i < len(dados_para_exportar[j]) else 0.0
                coluna_periodo.append(valor)
            df_data[periodo_label] = coluna_periodo
             
        df = pd.DataFrame(df_data)

        # Criar Excel na memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Resumo Mensal')
            # Formatação (Opcional, mas recomendada para moeda)
            # workbook = writer.book # Não precisamos mais disso para add_format
            worksheet = writer.sheets['Resumo Mensal']
            currency_format_string = 'R$ #,##0.00' # Definir formato como string
            # Aplicar formato às colunas de valor (B até a última coluna de período)
            if num_periodos > 0:
                # last_col_letter = pd.io.excel._xlsxwriter.utility.xl_col_to_name(num_periodos) # B=1, C=2... num_periodos=0 -> erro? 
                # Melhor usar openpyxl.utils
                for col_idx in range(2, num_periodos + 2): # Colunas B (2) até a última (num_periodos + 1)
                    col_letter = get_column_letter(col_idx)
                    worksheet.column_dimensions[col_letter].number_format = currency_format_string
                    worksheet.column_dimensions[col_letter].width = 18 # Ajustar largura
                else: # Caso não haja períodos
                    pass # Não formata colunas de dados
                #worksheet.set_column('A:A', 25) # Ajustar largura coluna Métrica
                worksheet.column_dimensions['A'].width = 25 # Definir largura da coluna A usando column_dimensions
        output.seek(0)
 
         # Nome do arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ano_str = ano if ano and ano.strip() else "TodosAnos"
        filename = f"resumo_mensal_{ano_str}_{timestamp}.xlsx"
        
        logger.info(f"Exportação Tabela Mensal - Enviando arquivo: {filename}")

        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        logger.error(f"Erro durante a exportação da tabela mensal para Excel: {str(e)}", exc_info=True)
        flash(f"Ocorreu um erro ao gerar o arquivo Excel da tabela: {str(e)}", "danger")
        referer = request.headers.get("Referer")
        return redirect(referer or url_for('dados_analiticos.dashboard_mensal'))

@dados_analiticos_bp.route('/api/detalhes-movimentacao-plano-conta')
@login_required
def api_detalhes_movimentacao_plano_conta():
    """Busca as movimentações individuais para um plano de conta específico, dados os filtros."""
    try:
        # Obter filtros da requisição
        ano = request.args.get('ano')
        mes = request.args.get('mes')
        cc_ids_str = request.args.getlist('cc_id') # Vem como lista de strings
        plano_conta_codigo = request.args.get('plano_conta_codigo')

        # Validar plano_conta_codigo
        if not plano_conta_codigo:
            return jsonify({'error': 'Código do Plano de Conta não fornecido.', 'movimentacoes': []}), 400

        logger.info(f"API Detalhes Movimentação - Filtros: ano={ano}, mes={mes}, cc_ids={cc_ids_str}, plano_conta_codigo={plano_conta_codigo}")

        # Converter filtros
        ano_int = int(ano) if ano and ano.strip() else None
        mes_int = int(mes) if mes and mes.isdigit() else None
        cc_ids = [int(id_str) for id_str in cc_ids_str if id_str.isdigit()]

        # Buscar Plano de Conta pelo código para obter o ID
        plano_conta = PlanoConta.query.filter_by(codigo=plano_conta_codigo).first()
        if not plano_conta:
             return jsonify({'error': f'Plano de Conta com código {plano_conta_codigo} não encontrado.', 'movimentacoes': []}), 404
        plano_conta_id = plano_conta.id

        # Construir query base
        query = db.session.query(DadoAnalitico).join(CentroCusto).filter(DadoAnalitico.plano_conta_id == plano_conta_id)

        # Aplicar filtros de data e CC
        if ano_int:
            query = query.filter(extract('year', DadoAnalitico.data_pagamento) == ano_int)
        if mes_int:
            query = query.filter(extract('month', DadoAnalitico.data_pagamento) == mes_int)
        if cc_ids:
            query = query.filter(DadoAnalitico.centro_custo_id.in_(cc_ids))

        # Ordenar (opcional, por data por exemplo)
        query = query.order_by(CentroCusto.codigo, CentroCusto.nome, DadoAnalitico.data_pagamento)

        movimentacoes = query.all()

        # Agrupar por Centro de Custo no Python
        resultado_agrupado = {}
        for mov in movimentacoes:
            if mov.centro_custo:
                # Usar "código - nome" como chave do grupo
                cc_chave = f"{mov.centro_custo.codigo} - {mov.centro_custo.nome}"
            else:
                cc_chave = "000 - Sem Centro de Custo" # Usar um código padrão para ordenação

            if cc_chave not in resultado_agrupado:
                resultado_agrupado[cc_chave] = {'movimentacoes': [], 'subtotal': 0}

            # Formatar data_pagamento se existir
            data_pagamento_fmt = mov.data_pagamento.strftime('%d/%m/%Y') if mov.data_pagamento else '-'

            # Adicionar detalhes da movimentação
            resultado_agrupado[cc_chave]['movimentacoes'].append({
                'data_pagamento': data_pagamento_fmt,
                'documento': mov.documento,
                'emitente': mov.emitente,
                'historico': mov.historico,
                'valor': mov.valor
            })
            # Acumular subtotal
            resultado_agrupado[cc_chave]['subtotal'] += mov.valor

        if not movimentacoes:
            return jsonify({'agrupado_por_cc': {}, 'message': 'Nenhuma movimentação encontrada para esta conta e filtros.'})

        return jsonify({'agrupado_por_cc': resultado_agrupado})

    except ValueError as ve:
         logger.error(f"Erro de valor nos filtros da API de detalhes de movimentação: {str(ve)}", exc_info=True)
         return jsonify({'error': f'Erro nos parâmetros: {str(ve)}', 'movimentacoes': []}), 400
    except Exception as e:
        logger.error(f"Erro na API de detalhes de movimentação: {str(e)}", exc_info=True)
        return jsonify({'error': f'Erro interno do servidor: {str(e)}', 'movimentacoes': []}), 500

# Configurar jsonify para não escapar caracteres unicode

# --- Funções Auxiliares para Hierarquia ---

# Função auxiliar para inserir/atualizar nó na árvore hierárquica
def inserir_na_arvore(raiz: Dict[str, Any], indice: str, nome: str, valor: float, codigo: str): # Adicionado parametro codigo
   # logger.debug(f"--> Inserir_na_arvore called: indice='{indice}', nome='{nome}', valor={valor}, codigo='{codigo}'")
    partes = indice.split('.')
    no_atual = raiz
    indice_acumulado = ""

    for i, parte in enumerate(partes):
    #    logger.debug(f"  Processing parte='{parte}', nivel={i}") # DEBUG LOG
        # Construir o índice completo do nó atual
        if indice_acumulado:
            indice_acumulado_parte = indice_acumulado + "." + parte
        else:
            indice_acumulado_parte = parte
            
        if parte not in no_atual:
            # logger.debug(f"    Parte '{parte}' NOT in current node. Creating...") # DEBUG LOG
             nome_no = ""
             if i < len(partes) - 1:
             #    logger.debug(f"    This is not the last part, attempting to find parent name for index '{indice_acumulado_parte}'") # DEBUG LOG
                 plano_pai = PlanoConta.query.filter_by(indice=indice_acumulado_parte).first()
                 if plano_pai:
                      nome_no = plano_pai.descricao 
              #        logger.debug(f"      Parent found: '{nome_no}'") # DEBUG LOG
                 else:
                      nome_no = f"Grupo {indice_acumulado_parte}" # Placeholder
                      #logger.debug(f"      Parent not found, using placeholder: '{nome_no}'") # DEBUG LOG
             else:
                 #logger.debug(f"    This IS the last part, name will be set later.") # DEBUG LOG
                 pass

             no_atual[parte] = {'nome': nome_no, 'valor': 0.0, 'filhos': {}, 'indice_completo': indice_acumulado_parte}
             
        if i == len(partes) - 1:
             #logger.debug(f"    Last part. Updating node '{parte}': nome='{nome}', valor={valor}, codigo='{codigo}'") # Log atualizado
             no_atual[parte]['nome'] = nome # Nome real da conta
             no_atual[parte]['valor'] = valor # Valor específico desta conta
             no_atual[parte]['codigo'] = codigo # <<< ARMAZENAR O CÓDIGO AQUI
             
        indice_acumulado = indice_acumulado_parte
        #logger.debug(f"    Navigating into filhos of '{parte}'") # DEBUG LOG
        no_atual = no_atual[parte]['filhos']
    #logger.debug(f"<-- Inserir_na_arvore finished for indice='{indice}'") # DEBUG LOG


# Função auxiliar para calcular totais recursivamente (após construir a árvore)
def calcular_totais_arvore(no: Dict[str, Any], indice_pai: str = "Raiz") -> float: # Adicionado indice_pai para log
    # Obter valor próprio do nó (existente apenas em folhas vindas da query)
    valor_proprio = no.get('valor', 0.0) 
    #logger.debug(f"  [CalcTotais] Nó: {no.get('indice_completo', indice_pai)}, Valor Próprio: {valor_proprio}")
    
    total_filhos = 0.0
    if 'filhos' in no and no['filhos']:
        #logger.debug(f"    [CalcTotais] Calculando filhos de {no.get('indice_completo', indice_pai)}...")
        for filho_key, filho_no in no['filhos'].items():
            total_filho_calculado = calcular_totais_arvore(filho_no, no.get('indice_completo', indice_pai) + '.' + filho_key)
            #logger.debug(f"      [CalcTotais] Filho {filho_no.get('indice_completo', filho_key)} retornou total: {total_filho_calculado}")
            total_filhos += total_filho_calculado
        #logger.debug(f"    [CalcTotais] Total SOMADO dos filhos de {no.get('indice_completo', indice_pai)}: {total_filhos}")
    else:
        pass
        #logger.debug(f"    [CalcTotais] Nó {no.get('indice_completo', indice_pai)} não tem filhos.")
            
    # O valor total do nó é seu valor próprio mais a soma dos totais dos filhos
    valor_total_calculado = valor_proprio + total_filhos 
    no['valor_total'] = valor_total_calculado 
    #logger.debug(f"  [CalcTotais] Nó: {no.get('indice_completo', indice_pai)}, Valor Total FINAL: {valor_total_calculado} (Proprio: {valor_proprio} + Filhos: {total_filhos})")
    return no['valor_total']

# --- Fim Funções Auxiliares ---

# --- Rota API para Detalhes Hierárquicos de um Período/Métrica Específico ---
@dados_analiticos_bp.route('/api/detalhes-hierarquicos-periodo')
@login_required
def api_detalhes_hierarquicos_periodo():
    """Retorna a árvore hierárquica de contas para um período e métrica específicos."""
    try:
        # Obter parâmetros
        ano_str = request.args.get('ano')
        mes_str = request.args.get('mes')
        cc_ids = request.args.getlist('cc_id')
        metric_type = request.args.get('metric_type') # 'RECEITAS' ou 'CUSTOS'

        #logger.info(f"API Detalhes Hierárquicos Período: Ano={ano_str}, Mes={mes_str}, CCs={cc_ids}, Métrica={metric_type}")

        # Validar e converter parâmetros
        ano_int = int(ano_str) if ano_str and ano_str.isdigit() else None
        mes_int = int(mes_str) if mes_str and mes_str.isdigit() else None
        
        if not ano_int or not mes_int or not metric_type or metric_type not in ['RECEITAS', 'CUSTOS']:
            logger.warning("Parâmetros inválidos recebidos.")
            return jsonify({'error': 'Parâmetros inválidos (ano, mês e metric_type [RECEITAS/CUSTOS] são obrigatórios).'}), 400
            
        # Determinar a lista de códigos de plano de conta a filtrar
        codigos_filtro = []
        if metric_type == 'RECEITAS':
            codigos_filtro = PL_RECOP
        elif metric_type == 'CUSTOS':
            codigos_filtro = PL_CUSTO
        
        if not codigos_filtro:
             logger.error(f"Não foi possível determinar códigos de filtro para metric_type={metric_type}")
             return jsonify({'error': 'Tipo de métrica inválido.'}), 400

        # --- Query e Construção da Árvore Específica ---
        query_detalhe_periodo = db.session.query(
            PlanoConta.codigo.label('plano_codigo'),
            PlanoConta.descricao.label('plano_descricao'),
            PlanoConta.indice.label('plano_indice'), 
            func.sum(DadoAnalitico.valor).label('total')
        ).join(PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id)
        
        # Aplicar filtros OBRIGATÓRIOS de período
        query_detalhe_periodo = query_detalhe_periodo.filter(
            extract('year', DadoAnalitico.data_pagamento) == ano_int,
            extract('month', DadoAnalitico.data_pagamento) == mes_int
        )
        # Aplicar filtro de CCs se fornecido
        if cc_ids:
            query_detalhe_periodo = query_detalhe_periodo.filter(DadoAnalitico.centro_custo_id.in_(cc_ids))
            
        # Aplicar filtro por códigos da métrica
        query_detalhe_periodo = query_detalhe_periodo.filter(PlanoConta.codigo.in_(codigos_filtro))
            
        # Agrupar e obter resultados
        resultados_periodo = query_detalhe_periodo.group_by(
            PlanoConta.codigo, PlanoConta.descricao, PlanoConta.indice 
        ).all()
        
        #logger.info(f"Query detalhe período encontrou {len(resultados_periodo)} resultados.")

        # Construir a árvore hierárquica para estes resultados
        arvore_especifica = {}
        for r in resultados_periodo:
            if r.plano_indice and r.plano_indice.strip():
                try:
                    inserir_na_arvore(
                        arvore_especifica, 
                        r.plano_indice.strip(), 
                        r.plano_descricao, 
                        float(r.total or 0),
                        r.plano_codigo
                    )
                except Exception as insert_err:
                     logger.warning(f"Erro ao inserir nó {r.plano_indice} na árvore específica: {insert_err}", exc_info=True)
            else:
                logger.warning(f"Skipping result (índice vazio): Cod={r.plano_codigo}")

        # Calcular totais para a árvore
        valor_total_arvore = 0.0
        for raiz_key in list(arvore_especifica.keys()): 
            try:
                valor_total_arvore += calcular_totais_arvore(arvore_especifica[raiz_key], raiz_key)
            except Exception as calc_err:
                 logger.warning(f"Erro ao calcular totais para raiz {raiz_key} na árvore específica: {calc_err}", exc_info=True)
                 
        # Ordenar a árvore
        try:
            chaves_raiz_ordenadas = sorted(arvore_especifica.keys(), key=lambda k: tuple(map(int, k.split('.'))))
        except ValueError:
            chaves_raiz_ordenadas = sorted(arvore_especifica.keys())
        arvore_especifica_ordenada = {k: arvore_especifica[k] for k in chaves_raiz_ordenadas}
        
        #logger.info(f"Árvore específica construída e calculada. Total: {valor_total_arvore}")
        #logger.debug(f"Estrutura Árvore Específica:\n{pprint.pformat(arvore_especifica_ordenada)}")
        
        # Retornar a árvore diretamente (o frontend espera a árvore dentro de um grupo, mas podemos adaptar)
        # Para manter consistência com o que o JS espera AGORA ao clicar na tabela, 
        # vamos retornar um objeto similar, mas contendo apenas esta árvore.
        return jsonify({
            'nome': metric_type, # Nome do grupo principal
            'valor_total': valor_total_arvore,
            'arvore_indices': arvore_especifica_ordenada # A árvore calculada
        })

    except Exception as e:
        logger.error(f"Erro na API api_detalhes_hierarquicos_periodo: {str(e)}", exc_info=True)
        return jsonify({'error': 'Erro interno ao processar a solicitação.'}), 500
# --- Fim Rota API Detalhes Hierárquicos Período ---
