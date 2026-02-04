from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, abort, make_response, Response
from markupsafe import Markup
from flask_login import login_required, current_user
from controllers.nota_fiscal_controller import api_get_dados_notas_fiscais
from models.nota_fiscal import CFOPS_COMPRA,CNPJS_MATRIZ_FILIAIS,CFOPS_TRANSFERENCIA
from models.dados_analiticos import DadoAnalitico
from models.reembolso import Reembolsos, ReembolsosDocumentos
from models.nota_fiscal import NotaFiscal,NotaFiscalItem
from models.centro_custo import CentroCusto
from models.usuario import Usuario
from models.database import db
from models.colaborador import Colaborador, DadosBancarios
from models.upload import Upload
from forms.reembolso_forms import ReembolsoForm, DocumentoAvulsoForm
from sqlalchemy import or_, and_, cast, Date, case, func
from sqlalchemy.orm import joinedload
from io import BytesIO
from datetime import datetime, date
from weasyprint import HTML
import json
import time
from models import PlanoConta
from models.dados_analiticos import PL_CUSTO,PL_0202,PL_0207,PL_0209
import requests
import base64
from PyPDF2 import PdfReader, PdfWriter
import tempfile
import os
import zipfile
import zipfile
reembolso_bp = Blueprint('reembolso', __name__, url_prefix='/reembolsos')
import dotenv
import os
dotenv.load_dotenv()
from utils.utils import formatarMoeda


def parse_data_documento(data_str):
    """
    Faz o parse de uma string de data, suportando múltiplos formatos.
    Tenta primeiro formato ISO datetime completo, depois formato de data simples.
    Se falhar, retorna a data atual.
    """
    if not data_str:
        return datetime.now()
    
    # Tentar formato ISO datetime completo (ex: '2024-01-01T00:00:00')
    formatos = [
        '%Y-%m-%dT%H:%M:%S',      # ISO datetime completo
        '%Y-%m-%dT%H:%M:%S.%f',   # ISO datetime com microsegundos
        '%Y-%m-%d %H:%M:%S',      # Datetime com espaço
        '%Y-%m-%d',               # Apenas data
    ]
    
    for formato in formatos:
        try:
            return datetime.strptime(data_str, formato)
        except ValueError:
            continue
    
    # Se nenhum formato funcionou, retornar data atual
    return datetime.now()

@reembolso_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Ou defina via config
    query = Reembolsos.query.filter_by(usuario_id=current_user.id).order_by(Reembolsos.data.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    reembolsos = pagination.items
    
    # Processar dados_adicionais para cada reembolso
    for reembolso in reembolsos:
        if reembolso.dados_adicionais:
            try:
                reembolso.dados_adicionais_parsed = json.loads(reembolso.dados_adicionais)
            except:
                reembolso.dados_adicionais_parsed = {}
        else:
            reembolso.dados_adicionais_parsed = {}
    
    form = ReembolsoForm()
    form.centro_custo_id.choices = [(c.id, f"{c.codigo} - {c.nome}") for c in CentroCusto.query.filter_by(ativo=True).all()]
    return render_template('reembolsos/index.html', reembolsos=reembolsos, form=form, pagination=pagination)

@reembolso_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo(): 
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            notas_selecionadas = json.loads(request.form.get('notas_selecionadas', '[]'))
            avulsos_data = json.loads(request.form.get('avulsos_data', '[]'))
            
            print("--------------------------------")
            print("request.form keys: ", list(request.form.keys()))
            print("request.files keys: ", list(request.files.keys()))
            print("request.files count: ", len(request.files))
            if request.files:
                print("request.files items:")
                for key, file in request.files.items():
                    if hasattr(file, 'filename') and file.filename:
                        print(f"  {key}: {file.filename} ({file.content_length if hasattr(file, 'content_length') else 'unknown'} bytes)")
                    else:
                        print(f"  {key}: {type(file)}")
            print("notas_selecionadas: ", notas_selecionadas)
            print("avulsos_data: ", avulsos_data)
            print("--------------------------------")
            # Validar centro de custo
            
            
            # Criar reembolso
            reembolso = Reembolsos(
                usuario_id=current_user.id,
                data=datetime.utcnow(),
                valor_total=0,  # Será atualizado após adicionar documentos
                numero_relatorio=f"RE{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            )
            db.session.add(reembolso)
            
            # Adicionar notas fiscais
            valor_total = 0
            for nota_data in notas_selecionadas:
                nota = NotaFiscal.query.get_or_404(nota_data['id'])
                doc = ReembolsosDocumentos(
                    reembolso=reembolso,
                    tipo='nota',
                    nota_fiscal_id=nota.id,
                    descricao=nota_data['descricao'],
                    valor=nota.valor_total,
                    fornecedor=nota.nome_emitente,
                    ndocumento=nota.numero_nf,
                    data_documento=nota.data_emissao,
                    centro_custo_id=nota_data.get('centro_custo_id')  # Adicionar centro de custo
                )
                db.session.add(doc)
                valor_total += float(nota.valor_total)
            
            # Adicionar documentos avulsos
            for idx, avulso_data in enumerate(avulsos_data):
                doc = ReembolsosDocumentos(
                    reembolso=reembolso,
                    tipo='avulso',
                    descricao=avulso_data['descricao'],
                    valor=avulso_data['valor'],
                    fornecedor=avulso_data.get('fornecedor', ''),
                    ndocumento=avulso_data.get('ndocumento', ''),
                    data_documento=parse_data_documento(avulso_data.get('data_documento')),
                    centro_custo_id=avulso_data.get('centro_custo_id')
                )
                db.session.add(doc)
                db.session.flush()  # Flush para obter o ID do documento antes de criar anexos
                valor_total += float(avulso_data['valor'])
                
                # Processar anexos do avulso usando modelo Upload
                # Buscar todos os arquivos que começam com o padrão do avulso
                anexos_processados = 0
                for file_key in request.files.keys():
                    if file_key.startswith(f'avulso_{idx}_anexo_'):
                        file = request.files[file_key]
                        if file and file.filename:
                            print(f'Processando anexo: {file_key}, filename: {file.filename}, doc.id: {doc.id}')
                            # Ler arquivo
                            file_content = file.read()
                            # Criar Upload manualmente (sem usar __init__ que faz commit)
                            upload = Upload()
                            upload.pai = 'ReembolsoDocumento'
                            upload.pai_id = doc.id
                            upload.tipo = 4
                            upload.filename = file.filename
                            upload.mimetype = file.content_type or 'application/octet-stream'
                            upload.uploaded_at = datetime.utcnow()  # Definir data explicitamente
                            # Converter para base64
                            if isinstance(file_content, bytes):
                                upload.blob = base64.b64encode(file_content).decode('utf-8')
                            else:
                                upload.blob = file_content
                            db.session.add(upload)
                            anexos_processados += 1
                            print(f'Upload criado: id={upload.id if hasattr(upload, "id") else "pendente"}, filename={upload.filename}, tamanho blob: {len(upload.blob) if upload.blob else 0}')
                print(f'Total de anexos processados para avulso {idx}: {anexos_processados}')
            
            # Atualizar valor total do reembolso
            reembolso.valor_total = valor_total
            
            # Salvar tudo em transação
            db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': 'Reembolso criado com sucesso!'})
            else:
                flash('Reembolso criado com sucesso!', 'success')
                return redirect(url_for('reembolso.index'))
                
        except Exception as e:
            db.session.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': str(e)})
            else:
                flash(f'Erro ao criar reembolso: {str(e)}', 'danger')
                return redirect(url_for('reembolso.index'))
    
    # GET: Exibir formulário
    centros_custo_objs = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.codigo.desc()).all()
    centros_custo = [{'id': c.id, 'codigo': c.codigo, 'nome': c.nome} for c in centros_custo_objs]
    #form = ReembolsoForm()
    #form.centro_custo_id.choices = [(c['id'], f"{c['codigo']} - {c['nome']}") for c in centros_custo]
    return render_template(
        'reembolsos/editar.html',
        modo='novo',
        centros_custo=centros_custo
    )

@reembolso_bp.route('/buscar_notas', methods=['GET','POST'])
@login_required
def nota_fiscal_busca_reembolso():
    print('buscar_notas')
    tinicial = time.time()
    if request.method == 'POST':
        try:
            print(f'request: {request.get_json()}')
            json_request = request.get_json()
            reembolso_id = json_request.get('reembolso_id', '')
            # Obter parâmetros de paginação
            notas_selecionadas = json_request.get('notas_selecionadas', [])
            # Filtro de pagamento
            print(f'request.form: {request.form.to_dict()}')
            page = json_request.get('page', 1)
            per_page = json_request.get('per_page', 25)
            pagamento = json_request.get('pagamento', '')
            json_filtros = {
                'page': page,
                'per_page': per_page,
                'notas_selecionadas': notas_selecionadas,
                'busca': json_request.get('numero', ''),
                'fornecedor': json_request.get('fornecedor', ''),
                'data_inicial': request.form.get('data_ini', ''),
                'data_final': json_request.get('data_fim', ''),
                'valor_minimo': json_request.get('valor_minimo', ''),
                'valor_maximo': json_request.get('valor_maximo', ''),
                'valor_exato': json_request.get('valor_exato', ''),
            }
            if pagamento:
                if pagamento == '0':
                    json_filtros['status_pagamento'] = 'nao_pago'
                elif pagamento == '1':
                    json_filtros['status_pagamento'] = 'pago'
                elif pagamento == '2':
                    json_filtros['status_pagamento'] = 'sem_envio'
                elif pagamento == '3':
                    json_filtros['status_pagamento'] = 'apenas_reembolso'
                elif pagamento == '4':
                    json_filtros['status_pagamento'] = 'selecionados'
                elif pagamento == '5':
                    json_filtros['status_pagamento'] = 'reembolso_e_nao_pago'
                elif pagamento == '6':
                    json_filtros['status_pagamento'] = 'reembolso_e_nao_pago_e_nao_selecionados'
            print(f'json_filtros: {json_filtros}')
            query = api_get_dados_notas_fiscais(json_filtros)
            pagination = query.paginate(page=page, per_page=per_page,error_out=False)
            notas = pagination.items
            # Processar notas para o JSON de resposta
            notas_filtradas = []
            for n in notas:
                try:
                    nota_fiscal_obj = n.NotaFiscal
                    selecionada = nota_fiscal_obj.id in [item.get('id') for item in notas_selecionadas if item.get('id')]
                    reembolso_documento = ReembolsosDocumentos.query.filter_by(nota_fiscal_id=n.NotaFiscal.id,reembolso_id=reembolso_id).first()
                    # Encontrar o item selecionado correspondente
                    item_selecionado = next((item for item in notas_selecionadas if item.get('id') == nota_fiscal_obj.id), None)
                    # Construir o doc baseado na seleção
                    doc_info = ''
                    if selecionada and item_selecionado:
                        doc_info = {
                            'cc': item_selecionado.get('centro_custo_id') or '',
                            'descricao': item_selecionado.get('descricao') or ''
                        }
                    notas_filtradas.append({
                        'doc': doc_info,
                        'id': nota_fiscal_obj.id,
                        'selecionada': selecionada,
                        'numero_nf': nota_fiscal_obj.numero_nf,
                        'nome_emitente': nota_fiscal_obj.nome_emitente,
                        'data_emissao': nota_fiscal_obj.data_emissao.isoformat() if nota_fiscal_obj.data_emissao else '',
                        'valor_total': float(nota_fiscal_obj.valor_total) if nota_fiscal_obj.valor_total else 0.0,
                        'pagamento': n.pagamento if hasattr(n, 'pagamento') else 0,
                        'upload': n.upload if hasattr(n, 'upload') else 0,
                        'upload_envio': n.upload_protocolo if hasattr(n, 'upload_protocolo') else 0,
                        'upload_reembolso': n.upload_reembolso if hasattr(n, 'upload_reembolso') else 0,
                        'upload_arquivei': n.upload_arquivei if hasattr(n, 'upload_arquivei') else 0,
                        'chave_acesso': nota_fiscal_obj.chave_acesso or '',
                    })
                except Exception as e:
                    print(f'Erro ao processar nota: {str(e)}')
                    continue
            
            print('tempo de execução3: ',time.time()-tinicial)
            print(f'notas_filtradas: {len(notas_filtradas)}')
            print(f'pagination: {pagination.page} {pagination.pages} {pagination.total} {pagination.per_page}')

            return jsonify({
                'notas': notas_filtradas,
                'page': pagination.page,
                'pages': pagination.pages,
                'total': pagination.total,
                'has_next': len(notas_filtradas) == pagination.per_page,
                'has_prev': pagination.page > 1
            })

        except Exception as e:
            print(f'Erro ao buscar notas: {str(e)}')
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500


@reembolso_bp.route('/datatables/notas', methods=['POST'])
@login_required
def datatables_notas():
    """Endpoint DataTables para notas fiscais"""
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        # Parâmetros do DataTables
        draw = int(data.get('draw', 1))
        start = int(data.get('start', 0))
        length = int(data.get('length', 25))
        page = (start // length) + 1
        per_page = length
        
        # Parâmetros de ordenação
        order_by = 'data_emissao'
        order_dir = 'desc'
        order_column_index = None
        if 'order' in data and len(data['order']) > 0:
            order_column_index = int(data['order'][0].get('column', 1))
            order_dir = data['order'][0].get('dir', 'desc')
            
            # Mapeamento de índices de colunas para campos de ordenação
            # 0: data_emissao_sort (oculta), 1: selecao (checkbox), 2: data_emissao (visível), 3: nome_emitente, 4: numero_nf, 5: valor_total, 6: pagamento, 7: descricao, 8: centro_custo
            column_mapping = {
                0: 'data_emissao',  # Coluna oculta de data
                2: 'data_emissao',  # Coluna visível de data
                3: 'nome_emitente',
                4: 'numero_nf'
            }
            order_by = column_mapping.get(order_column_index, 'data_emissao')
        
        #print(f'[datatables_notas] Ordenação: coluna {order_column_index}, campo: {order_by}, direção: {order_dir}')
    
        # Filtros
        notas_selecionadas = data.get('notas_selecionadas', [])
        if isinstance(notas_selecionadas, str):
            try:
                notas_selecionadas = json.loads(notas_selecionadas)
            except:
                notas_selecionadas = []
        
        # Criar dicionário de notas selecionadas para busca rápida
        notas_selecionadas_dict = {}
        if notas_selecionadas:
            for nota_sel in notas_selecionadas:
                nota_id = int(nota_sel.get('id', 0)) if isinstance(nota_sel, dict) else int(nota_sel) if isinstance(nota_sel, (int, str)) else 0
                if nota_id:
                    notas_selecionadas_dict[nota_id] = nota_sel if isinstance(nota_sel, dict) else {}
        
        json_filtros = {
            'page': page,
            'per_page': per_page,
            'busca': data.get('busca', ''),
            'data_inicial': data.get('data_inicial', ''),
            'data_final': data.get('data_final', ''),
            'valor_minimo': data.get('valor_minimo', ''),
            'valor_maximo': data.get('valor_maximo', ''),
            'valor_exato': data.get('valor_exato', ''),
            'reembolso_id': data.get('reembolso_id', ''),
            'order_by': order_by,
            'order_dir': order_dir,
            'emitente': 'Terceiros' 
        }
        
        
        pagamento = data.get('pagamento', '')
        if pagamento:
            if pagamento == '0':
                json_filtros['status_pagamento'] = 'nao_pago'
            elif pagamento == '1':
                json_filtros['status_pagamento'] = 'pago'
            elif pagamento == '2':
                json_filtros['status_pagamento'] = 'sem_envio'
            elif pagamento == '3':
                json_filtros['status_pagamento'] = 'apenas_reembolso'
            elif pagamento == '4':
                json_filtros['status_pagamento'] = 'selecionados'
            elif pagamento == '5':
                json_filtros['status_pagamento'] = 'reembolso_e_nao_pago'
            elif pagamento == '6':
                json_filtros['status_pagamento'] = 'reembolso_e_nao_pago_e_nao_selecionados'
            elif pagamento == '7':
                json_filtros['status_upload'] = '3nao'
                json_filtros['status_pagamento'] = 'selecionados'
        

        print(json.dumps(json_filtros, indent=4))
        #print(f'Filtro pagamento: {pagamento}, status_pagamento: {json_filtros.get("status_pagamento")}')
        #print(f'Notas selecionadas: {notas_selecionadas}')
        
        reembolso_id = data.get('reembolso_id', '')
        
        # Buscar notas
        query = api_get_dados_notas_fiscais(json_filtros)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        notas = pagination.items
        print(f'Notas: {len(notas)}')
        # Processar notas para DataTables - retornar apenas dados brutos
        notas_data = []
        for n in notas:
            try:
                nota_fiscal_obj = n.NotaFiscal
                nota_id = nota_fiscal_obj.id
                
                # Verificar se a nota está no reembolso usando a coluna reembolso do banco
                esta_no_reembolso_db = bool(n.reembolso if hasattr(n, 'reembolso') else 0)
                
                # Verificar se a nota está na lista de selecionadas do frontend
                esta_na_lista_selecionadas = nota_id in notas_selecionadas_dict
                
                # A nota está selecionada se estiver no banco OU na lista do frontend
                esta_no_reembolso = esta_no_reembolso_db or esta_na_lista_selecionadas
                
                # Buscar dados do documento do reembolso se houver (prioridade: lista frontend > banco)
                item_selecionado = None
                
                # Primeiro, verificar se está na lista do frontend (tem prioridade)
                if esta_na_lista_selecionadas:
                    nota_sel = notas_selecionadas_dict[nota_id]
                    if isinstance(nota_sel, dict):
                        item_selecionado = {
                            'centro_custo_id': nota_sel.get('centro_custo_id') or None,
                            'descricao': nota_sel.get('descricao') or ''
                        }
                
                # Se não encontrou na lista do frontend, buscar no banco
                if not item_selecionado and esta_no_reembolso_db and reembolso_id:
                    try:
                        reembolso_doc = ReembolsosDocumentos.query.filter_by(
                            nota_fiscal_id=nota_id,
                            reembolso_id=reembolso_id
                        ).first()
                        if reembolso_doc:
                            item_selecionado = {
                                'centro_custo_id': reembolso_doc.centro_custo_id,
                                'descricao': reembolso_doc.descricao or ''
                            }
                    except Exception as e:
                        print(f'Erro ao buscar documento do reembolso: {str(e)}')
                
                # Formatar data para ordenação (ISO)
                data_emissao_sort = ''
                if nota_fiscal_obj.data_emissao:
                    data_emissao_sort = nota_fiscal_obj.data_emissao.strftime('%Y-%m-%d')
                
                notas_data.append({
                    'DT_RowId': f'nota_{nota_id}',
                    'id': nota_id,
                    'data_emissao': nota_fiscal_obj.data_emissao.isoformat() if nota_fiscal_obj.data_emissao else None,
                    'data_emissao_sort': data_emissao_sort,
                    'nome_emitente': nota_fiscal_obj.nome_emitente or '',
                    'numero_nf': nota_fiscal_obj.numero_nf or '',
                    'valor_total': float(nota_fiscal_obj.valor_total) if nota_fiscal_obj.valor_total else 0.0,
                    'pagamento': n.pagamento if hasattr(n, 'pagamento') else 0,
                    'upload': n.upload if hasattr(n, 'upload') else 0,
                    'upload_reembolso': n.upload_reembolso if hasattr(n, 'upload_reembolso') else 0,
                    'upload_protocolo': n.upload_protocolo if hasattr(n, 'upload_protocolo') else 0,
                    'selecionada': esta_no_reembolso,
                    'reembolso': esta_no_reembolso,
                    'centro_custo_id': item_selecionado.get('centro_custo_id') if item_selecionado else None,
                    'descricao': item_selecionado.get('descricao') if item_selecionado else ''
                })
            except Exception as e:
                print(f'Erro ao processar nota: {str(e)}')
                import traceback
                traceback.print_exc()
                continue
        
        response_data = {
            'draw': draw,
            'recordsTotal': pagination.total,
            'recordsFiltered': pagination.total,
            'data': notas_data
        }
        #print(f'Retornando {len(notas_data)} notas de {pagination.total} total')
        #print(f'Response data keys: {response_data.keys()}')
        return jsonify(response_data)
    except Exception as e:
        print(f'Erro ao buscar notas DataTables: {str(e)}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'draw': 1, 'recordsTotal': 0, 'recordsFiltered': 0, 'data': []}), 500

@reembolso_bp.route('/<int:reembolso_id>/avulso/<int:avulso_id>', methods=['PUT', 'POST'])
@login_required
def salvar_avulso_individual(reembolso_id, avulso_id):
    """Endpoint para salvar/atualizar um documento avulso individual"""
    try:
        reembolso = Reembolsos.query.get_or_404(reembolso_id)
        
        # Verificar permissão
        if reembolso.usuario_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Acesso negado'}), 403
        
        # Buscar documento existente ou criar novo
        if avulso_id > 0:
            doc = ReembolsosDocumentos.query.filter_by(
                id=avulso_id,
                reembolso_id=reembolso_id,
                tipo='avulso'
            ).first()
            print(f'doc: {doc}')
            if not doc:
                return jsonify({'error': 'Documento não encontrado'}), 404
        else:
            # Criar novo documento
            doc = ReembolsosDocumentos(
                reembolso=reembolso,
                tipo='avulso'
            )
            db.session.add(doc)
            db.session.flush()
        
        # Atualizar campos do documento
        data = request.form
        doc.descricao = data.get('descricao', '')
        doc.valor = float(data.get('valor', 0))
        doc.fornecedor = data.get('fornecedor', '')
        doc.ndocumento = data.get('ndocumento', '')
        doc.data_documento = parse_data_documento(data.get('data_documento'))
        doc.centro_custo_id = data.get('centro_custo_id') or None
        
        # Processar anexos removidos
        print(f'data: {data}')
        anexos_removidos = json.loads(data.get('anexos_removidos', '[]'))
        if anexos_removidos:
            uploads = Upload.query.filter_by(
                pai='ReembolsosDocumentos',
                pai_id=doc.id,
                tipo=4
            ).all()
            for upload in uploads:
                if upload.id in anexos_removidos:
                    db.session.delete(upload)
        
        # Processar novos anexos
        anexos_processados = 0
        print(f'request.files: {request.files}')
        print(f'reembolso: {reembolso_id}')
        print(f'avulso: {avulso_id}')
        print(f'Processando novos anexos: {request.files}')
        for file_key in request.files.keys():
            if file_key.startswith('anexo_'):
                file = request.files[file_key]
                if file and hasattr(file, 'filename') and file.filename:
                    file_content = file.read()
                    try:
                        # Verificar se o upload já existe antes de criar
                        upload_existente = Upload.query.filter_by(
                            pai='ReembolsosDocumentos',
                            pai_id=doc.id,
                            tipo=4,
                            filename=file.filename
                        ).first()
                        
                        if upload_existente:
                           pass
                        else:
                           Upload(pai='ReembolsosDocumentos', pai_id=doc.id, tipo=4, filename=file.filename, mimetype=file.content_type, blob=file_content)
                    except Exception as e:
                        print(f'Erro ao criar/atualizar upload: {str(e)}')
                        import traceback
                        traceback.print_exc()
                        db.session.rollback()
        
        # Atualizar valor total do reembolso
        valor_total = 0
        for doc in reembolso.documentos:
            if doc.tipo == 'avulso':
                valor_total += float(doc.valor) if doc.valor else 0.0
            elif doc.tipo == 'nota':
                valor_total += float(doc.valor) if doc.valor else 0.0
        reembolso.valor_total = valor_total
        
        db.session.commit()
        
        # Buscar anexos atualizados
        anexos_upload = Upload.query.filter_by(
            pai_id=doc.id,
            pai='ReembolsosDocumentos',
            tipo=4
        ).all()
        anexos_list = [
            {'id': upload.id, 'filename': upload.filename}
            for upload in anexos_upload
        ]
        
        return jsonify({
            'success': True,
            'avulso': {
                'id': doc.id,
                'fornecedor': doc.fornecedor or '',
                'ndocumento': doc.ndocumento or '',
                'data_documento': doc.data_documento.strftime('%Y-%m-%d') if doc.data_documento else None,
                'descricao': doc.descricao or '',
                'valor': float(doc.valor) if doc.valor else 0.0,
                'centro_custo_id': doc.centro_custo_id,
                'anexos_count': len(anexos_list),
                'anexos': anexos_list
            }
        })
    except Exception as e:
        db.session.rollback()
        print(f'Erro ao salvar avulso individual: {str(e)}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@reembolso_bp.route('/datatables/avulsos', methods=['POST'])
@login_required
def datatables_avulsos():
    """Endpoint DataTables para documentos avulsos"""
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        # Parâmetros do DataTables
        draw = int(data.get('draw', 1))
        start = int(data.get('start', 0))
        length = int(data.get('length', 25))
        reembolso_id = data.get('reembolso_id', '')
        
        # Parâmetros de ordenação
        order_column_index = 0
        order_dir = 'desc'
        if 'order' in data and len(data['order']) > 0:
            order_column_index = int(data['order'][0].get('column', 0))
            order_dir = data['order'][0].get('dir', 'desc')
        
        print(f'[datatables_avulsos] Recebido reembolso_id: {reembolso_id}, tipo: {type(reembolso_id)}')
        print(f'[datatables_avulsos] Ordenação: coluna {order_column_index}, direção {order_dir}')
        print(f'[datatables_avulsos] Paginação: start={start}, length={length}')
        
        # Buscar avulsos do banco de dados
        avulsos_list = []
        if reembolso_id and str(reembolso_id).strip() and str(reembolso_id) != '0':
            try:
                reembolso_id_int = int(reembolso_id)
                print(f'[datatables_avulsos] Buscando reembolso com ID: {reembolso_id_int}')
                reembolso = Reembolsos.query.get(reembolso_id_int)
                if reembolso:
                    # Verificar permissão
                    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
                        print(f'[datatables_avulsos] Acesso negado para reembolso {reembolso_id_int}')
                        return jsonify({'error': 'Acesso negado', 'draw': draw, 'recordsTotal': 0, 'recordsFiltered': 0, 'data': []}), 403
                    
                    print(f'[datatables_avulsos] Reembolso encontrado, total de documentos: {len(reembolso.documentos)}')
                    # Buscar documentos avulsos
                    for doc in reembolso.documentos:
                        if doc.tipo == 'avulso':
                            # Formatar data
                            data_documento = None
                            if doc.data_documento:
                                data_documento = doc.data_documento.strftime('%Y-%m-%d')
                            
                            # Buscar anexos
                            anexos_upload = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsosDocumentos', tipo=4).all()
                            anexos_list = [
                                {'id': upload.id, 'filename': upload.filename}
                                for upload in anexos_upload
                            ]
                            
                            avulsos_list.append({
                                'id': doc.id,
                                'fornecedor': doc.fornecedor or '',
                                'ndocumento': doc.ndocumento or '',
                                'data_documento': data_documento,
                                'descricao': doc.descricao or '',
                                'valor': float(doc.valor) if doc.valor else 0.0,
                                'centro_custo_id': doc.centro_custo_id,
                                'anexos_count': len(anexos_list),
                                'anexos': anexos_list
                            })
                    print(f'[datatables_avulsos] Total de avulsos encontrados: {len(avulsos_list)}')
                else:
                    print(f'[datatables_avulsos] Reembolso não encontrado com ID: {reembolso_id_int}')
            except (ValueError, TypeError) as e:
                print(f'[datatables_avulsos] Erro ao processar reembolso_id: {reembolso_id}, erro: {str(e)}')
        else:
            print(f'[datatables_avulsos] reembolso_id vazio ou zero, retornando lista vazia')
        
        # Processar avulsos para DataTables - retornar apenas dados brutos
        avulsos_data = []
        for idx, avulso in enumerate(avulsos_list):
            try:
                # Formatar data para exibição e ordenação
                data_doc = ''
                data_doc_sort = ''
                if avulso.get('data_documento'):
                    try:
                        if isinstance(avulso.get('data_documento'), str):
                            data_obj = datetime.strptime(avulso.get('data_documento').split('T')[0], '%Y-%m-%d')
                        else:
                            data_obj = avulso.get('data_documento')
                        if hasattr(data_obj, 'strftime'):
                            data_doc = data_obj.strftime('%d/%m/%Y')
                            data_doc_sort = data_obj.strftime('%Y-%m-%d')  # Formato ISO para ordenação
                        else:
                            data_doc = str(avulso.get('data_documento', ''))
                            data_doc_sort = ''
                    except:
                        data_doc = str(avulso.get('data_documento', ''))
                        data_doc_sort = ''
                
                # Buscar nome do centro de custo
                centroCustoNome = ''
                if avulso.get('centro_custo_id'):
                    centro = CentroCusto.query.get(avulso.get('centro_custo_id'))
                    if centro:
                        centroCustoNome = f'{centro.codigo} - {centro.nome}'
                
                anexosCount = avulso.get('anexos_count', 0) or (len(avulso.get('anexos', [])) if avulso.get('anexos') else 0)
                
                avulsos_data.append({
                    'DT_RowId': f'avulso_{avulso.get("id", idx)}',
                    'id': avulso.get('id', idx),
                    'data_documento': data_doc,
                    'data_documento_sort': data_doc_sort,  # Campo oculto para ordenação
                    'fornecedor': avulso.get('fornecedor', ''),
                    'numero': avulso.get('ndocumento', ''),
                    'valor': float(avulso.get('valor', 0)),
                    'anexos_count': anexosCount,
                    'descricao': avulso.get('descricao', ''),
                    'centro_custo_id': avulso.get('centro_custo_id'),
                    'centro_custo': centroCustoNome,
                    '_raw_data': {
                        'index': idx,
                        'avulso': avulso
                    }
                })
            except Exception as e:
                print(f'Erro ao processar avulso: {str(e)}')
                import traceback
                traceback.print_exc()
                continue
        
        # Aplicar ordenação
        # Mapeamento de índices de colunas para campos de ordenação
        # Estrutura das colunas no DataTables:
        # 0: data_documento_sort (oculta), 1: data_documento (visível, mas ordena pela 0), 2: fornecedor, 3: numero, 4: valor, 5: anexos_count, 6: descricao, 7: centro_custo, 8: acoes
        column_mapping = {
            0: 'data_documento_sort',  # Coluna oculta
            1: 'data_documento_sort',  # Coluna visível de data ordena pela oculta
            2: 'fornecedor',
            3: 'numero',
            4: 'valor',
            5: 'anexos_count',
            6: 'descricao',
            7: 'centro_custo'
        }
        
        # Mapeamento direto: agora a coluna 1 (visível) também usa data_documento_sort diretamente
        # porque mudei a coluna para usar data_documento_sort como data source
        sort_key = column_mapping.get(order_column_index, 'data_documento_sort')
        reverse = (order_dir == 'desc')
        
        print(f'[datatables_avulsos] Índice da coluna clicada: {order_column_index}')
        print(f'[datatables_avulsos] Ordenando por: {sort_key}, direção: {order_dir}')
        print(f'[datatables_avulsos] Total de registros antes da ordenação: {len(avulsos_data)}')
        
        try:
            # Ordenar os dados
            if sort_key == 'data_documento_sort':
                # Ordenar por data (usar o campo de ordenação ISO)
                # Tratar strings vazias como menor valor
                avulsos_data.sort(key=lambda x: x.get('data_documento_sort', '') or '0000-00-00', reverse=reverse)
            elif sort_key == 'valor':
                # Ordenar por valor numérico
                avulsos_data.sort(key=lambda x: float(x.get('valor', 0) or 0), reverse=reverse)
            elif sort_key == 'anexos_count':
                # Ordenar por contagem de anexos
                avulsos_data.sort(key=lambda x: int(x.get('anexos_count', 0) or 0), reverse=reverse)
            else:
                # Ordenar por string (fornecedor, numero, descricao, centro_custo)
                avulsos_data.sort(key=lambda x: str(x.get(sort_key, '') or '').lower(), reverse=reverse)
            print(f'[datatables_avulsos] Ordenação aplicada com sucesso')
        except Exception as e:
            print(f'[datatables_avulsos] Erro ao ordenar: {str(e)}')
            import traceback
            traceback.print_exc()
            # Em caso de erro, manter ordem original
        
        # Aplicar paginação
        total_records = len(avulsos_data)
        paginated_data = avulsos_data[start:start + length]
        
        print(f'[datatables_avulsos] Total: {total_records}, Retornando: {len(paginated_data)} (start={start}, length={length})')
        
        response_data = {
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': total_records,
            'data': paginated_data
        }
        print(f'[datatables_avulsos] Retornando {len(paginated_data)} avulsos de {total_records} total')
        return jsonify(response_data)
    except Exception as e:
        print(f'Erro ao buscar avulsos DataTables: {str(e)}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'draw': 1, 'recordsTotal': 0, 'recordsFiltered': 0, 'data': []}), 500

@reembolso_bp.route('/<int:reembolso_id>/pdf_template')
@login_required
def pdf_template(reembolso_id):
    reembolso = Reembolsos.query.options(
        joinedload(Reembolsos.usuario).joinedload(Usuario.colaborador).joinedload(Colaborador.dados_bancarios)
    ).get_or_404(reembolso_id)
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    # Carregar uploads das notas fiscais
    for doc in reembolso.documentos:
        if doc.tipo == 'nota' and doc.nota_fiscal:
            print(f'Carregando uploads para nota fiscal {doc.nota_fiscal.id}')
            uploads = Upload.query.filter(
                Upload.pai_id == doc.nota_fiscal.id,
                Upload.pai == 'NotaFiscal',
                Upload.tipo == 3
            ).all()
            print(f'Uploads encontrados: {len(uploads)}')
            doc.nota_fiscal.uploads = uploads
    
    print(f'Total de documentos: {len(reembolso.documentos)}')
    for doc in reembolso.documentos:
        print(f'Documento: {doc.tipo} - {doc.ndocumento}')
        if doc.tipo == 'nota' and doc.nota_fiscal:
            print(f'Uploads da nota: {len(doc.nota_fiscal.uploads)}')
        elif doc.tipo == 'avulso':
            anexos_count = len(Upload.query.filter_by(pai_id=doc.id, pai='ReembolsoDocumento', tipo=4).all())
            print(f'Anexos do documento avulso: {anexos_count}')
    
    html = render_template('reembolsos/pdf_template.html', reembolso=reembolso)
    return reembolso,html

def dias_desde_1900(data):
    """Calcula o número de dias desde 01/01/1900 até a data informada"""
    data_inicial = date(1900, 1, 1)
    return (data - data_inicial).days

@reembolso_bp.route('/exportar_pdf/<int:id>')
@login_required
def exportar_pdf(id):
    reembolso = Reembolsos.query.options(
        joinedload(Reembolsos.usuario).joinedload(Usuario.colaborador).joinedload(Colaborador.dados_bancarios)
    ).filter(Reembolsos.id==id).first()
    if not reembolso:
        abort(404)
    
    # Verificar permissão
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    # Buscar todos os centros de custo e anos do reembolso com seus dados
    # Agrupar por centro de custo e ano da data do documento
    CCsAnos = db.session.query(
        CentroCusto, 
        ReembolsosDocumentos.centro_custo_id,
        func.extract('year', ReembolsosDocumentos.data_documento).label('ano')
    ).\
        join(ReembolsosDocumentos, CentroCusto.id == ReembolsosDocumentos.centro_custo_id).\
        filter(ReembolsosDocumentos.reembolso_id == id,
               ReembolsosDocumentos.data_documento.isnot(None)).\
        group_by(
            ReembolsosDocumentos.centro_custo_id, 
            CentroCusto.id, 
            CentroCusto.codigo, 
            CentroCusto.nome,
            func.extract('year', ReembolsosDocumentos.data_documento)
        ).\
        order_by(CentroCusto.nome, func.extract('year', ReembolsosDocumentos.data_documento).desc()).all()
    
    # Criar ZIP em memória
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Para cada combinação de centro de custo e ano, criar um PDF separado
        for centro_custo, centro_custo_id, ano in CCsAnos:
            # Criar um PdfWriter para este centro de custo e ano
            pdf_writer = PdfWriter()
            
            # Buscar documentos deste centro de custo e ano
            docs = ReembolsosDocumentos.query.\
                filter(ReembolsosDocumentos.reembolso_id == id, 
                       ReembolsosDocumentos.centro_custo_id == centro_custo_id,
                       func.extract('year', ReembolsosDocumentos.data_documento) == ano).\
                order_by(ReembolsosDocumentos.data_documento.desc()).all()
            
            if not docs:
                continue
            
            valor_total = sum(doc.valor for doc in docs)
            # Calcula o número de dias desde 1900
            dias = dias_desde_1900(reembolso.data.date())
            nrel = valor_total + dias
            html = render_template('reembolsos/pdf_template.html', docs=docs, reembolso=reembolso, nrel=nrel, valor_total=valor_total)
            pdf_bytes = HTML(string=html, base_url=request.base_url).write_pdf()
            pdf_writer.append_pages_from_reader(PdfReader(BytesIO(pdf_bytes)))

            for doc in docs:
                if doc.tipo == 'nota' and doc.nota_fiscal:
                    doc.nota_fiscal.uploads = Upload.query.filter_by(pai_id=doc.nota_fiscal.id, pai='NotaFiscal', tipo=3).all()
                
                if doc.tipo == 'nota' and doc.nota_fiscal and doc.nota_fiscal.uploads:
                    for upload in doc.nota_fiscal.uploads:
                        if upload.mimetype == 'application/pdf':
                            try:
                                # Converte o blob base64 para bytes
                                pdf_bytes = base64.b64decode(upload.blob)
                                # Adiciona o PDF ao final
                                pdf_writer.append_pages_from_reader(PdfReader(BytesIO(pdf_bytes)))
                            except Exception as e:
                                print(f"Erro ao processar PDF da nota fiscal {doc.ndocumento}: {str(e)}")
                elif doc.tipo == 'avulso':
                    # Buscar anexos usando modelo Upload
                    anexos = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsosDocumentos', tipo=4).all()
                    for anexo in anexos:
                        if anexo.mimetype == 'application/pdf':
                            try:
                                # Converte o blob base64 para bytes
                                # Tenta decodificar base64, se falhar assume que já está em bytes
                                try:
                                    pdf_bytes = base64.b64decode(anexo.blob)
                                except:
                                    # Se não for base64, assume que já está em bytes (compatibilidade com dados antigos)
                                    if isinstance(anexo.blob, str):
                                        pdf_bytes = anexo.blob.encode('latin-1')
                                    else:
                                        pdf_bytes = anexo.blob
                                # Adiciona o PDF ao final
                                pdf_writer.append_pages_from_reader(PdfReader(BytesIO(pdf_bytes)))
                            except Exception as e:
                                print(f"Erro ao processar PDF do documento avulso {doc.ndocumento}: {str(e)}")
            
            # Salvar PDF deste centro de custo e ano em BytesIO
            pdf_output = BytesIO()
            pdf_writer.write(pdf_output)
            pdf_output.seek(0)
            
            # Criar nome do arquivo baseado no centro de custo e ano
            # Limpar caracteres inválidos do nome do arquivo
            nome_arquivo = f"{centro_custo.codigo} - {centro_custo.nome} - {int(ano)}".replace('/', '_').replace('\\', '_').replace(':', '_')
            nome_arquivo = f"{nome_arquivo}.pdf"
            
            # Adicionar PDF ao ZIP
            zip_file.writestr(nome_arquivo, pdf_output.getvalue())
            
            # Fechar recursos
            pdf_output.close()
            pdf_writer.close()
    
    # Preparar resposta ZIP
    zip_buffer.seek(0)
    response = make_response(zip_buffer.getvalue())
    zip_buffer.close()
    
    response.headers['Content-Type'] = 'application/zip'
    response.headers['Content-Disposition'] = f'attachment; filename=reembolso_{reembolso.numero_relatorio}_por_centro_custo_ano.zip'
    return response

@reembolso_bp.route('/anexo/<int:anexo_id>/download')
@login_required
def download_anexo(anexo_id):
    # Buscar upload usando modelo Upload
    upload = Upload.query.get_or_404(anexo_id)
    
    # Verificar se é um anexo de reembolso (tipo=4)
    if upload.tipo != 4 or upload.pai != 'ReembolsoDocumento':
        abort(404)
    
    # Buscar documento e reembolso
    doc = ReembolsosDocumentos.query.get_or_404(upload.pai_id)
    reembolso = doc.reembolso
    
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    # Obter conteúdo do arquivo (Upload já decodifica base64)
    file_content = upload.get_blob()
    if not file_content:
        abort(404)
    
    return send_file(BytesIO(file_content), download_name=upload.filename, mimetype=upload.mimetype, as_attachment=True)

@reembolso_bp.route('/<int:reembolso_id>/editar', methods=['GET', 'POST'])
@login_required
def editar(reembolso_id):
    print(f'reembolso_id: {reembolso_id}')
    reembolso = Reembolsos.query.get_or_404(reembolso_id)
   
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    # Verificar se o reembolso foi enviado
    dados = {}
    if reembolso.dados_adicionais:
        try:
            dados = json.loads(reembolso.dados_adicionais)
        except:
            dados = {}
    
    if dados.get('enviado', False):
        flash('Este reembolso foi enviado e não pode ser editado.', 'warning')
        return redirect(url_for('reembolso.index'))

    if request.method == 'POST':
        print(f'salvar editar reembolso')
        print(f'request.form: {request.form}')
        
        # Log detalhado dos arquivos recebidos
        print("=" * 50)
        print("ARQUIVOS RECEBIDOS NO BACKEND (EDICÃO):")
        print(f"Total de arquivos: {len(request.files)}")
        print("Chaves dos arquivos:", list(request.files.keys()))
        for key, file in request.files.items():
            if hasattr(file, 'filename') and file.filename:
                print(f"  {key}: {file.filename} (tipo: {file.content_type})")
            else:
                print(f"  {key}: {type(file)} (sem filename)")
        print("=" * 50)
        
        try:
            # Atualizar campos principais
            reembolso.numero_relatorio = request.form.get('numero_relatorio')
            notas_selecionadas = json.loads(request.form.get('notas_selecionadas', '[]'))
            avulsos_data = json.loads(request.form.get('avulsos_data', '[]'))
            print(f'notas_selecionadas: {notas_selecionadas}')
            print(f'avulsos_data: {avulsos_data}')
            
            # Coletar IDs de notas fiscais que devem ser mantidas
            notas_ids_manter = []
            for nota_data in notas_selecionadas:
                nota_id = nota_data.get('id')
                if nota_id:
                    notas_ids_manter.append(int(nota_id))
            print(f'Notas que devem ser mantidas: {notas_ids_manter}')
            
            # Coletar IDs de documentos avulsos que serão mantidos (editados)
            avulsos_ids_manter = []
            for avulso_data in avulsos_data:
                avulso_id = avulso_data.get('id')
                # Se tem ID e não é timestamp (IDs de timestamp são muito grandes)
                if avulso_id and isinstance(avulso_id, int) and avulso_id < 1000000000000:
                    avulsos_ids_manter.append(avulso_id)
            
            # Limpar apenas docs que não estão sendo mantidos
            for doc in list(reembolso.documentos):
                # Se for avulso e não está na lista de manter, deletar
                if doc.tipo == 'avulso' and doc.id not in avulsos_ids_manter:
                    # Remove anexos se for avulso (usando modelo Upload)
                    uploads = Upload.query.filter_by(
                        pai_id=doc.id,
                        pai='ReembolsosDocumentos',
                        tipo=4
                    ).all()
                    for upload in uploads:
                        db.session.delete(upload)
                    db.session.delete(doc)
                    print(f'Documento avulso {doc.id} deletado')
                # Se for nota e não está na lista de manter, deletar
                elif doc.tipo == 'nota':
                    if doc.nota_fiscal_id not in notas_ids_manter:
                        print(f'Documento nota {doc.id} (nota_fiscal_id={doc.nota_fiscal_id}) deletado - não está na lista de manter')
                        db.session.delete(doc)
                    else:
                        print(f'Documento nota {doc.id} (nota_fiscal_id={doc.nota_fiscal_id}) mantido - está na lista')
            db.session.flush()

            valor_total = 0
            # Processar notas fiscais - atualizar existentes ou criar novas
            for nota_data in notas_selecionadas:
                nota_id = nota_data.get('id')
                if not nota_id:
                    print(f'Aviso: Nota fiscal sem ID, pulando...')
                    continue
                    
                nota = NotaFiscal.query.get(nota_id)
                if not nota:
                    print(f'Erro: Nota fiscal {nota_id} não encontrada, pulando...')
                    continue
                
                # Verificar se já existe documento para esta nota
                doc_existente = ReembolsosDocumentos.query.filter_by(
                    reembolso_id=reembolso_id,
                    tipo='nota',
                    nota_fiscal_id=nota_id
                ).first()
                
                if doc_existente:
                    # Atualizar documento existente
                    print(f'Atualizando documento existente para nota {nota_id}')
                    doc_existente.descricao = nota_data.get('descricao', '')
                    doc_existente.valor = nota.valor_total
                    doc_existente.fornecedor = nota.nome_emitente
                    doc_existente.ndocumento = nota.numero_nf
                    doc_existente.data_documento = nota.data_emissao
                    doc_existente.centro_custo_id = nota_data.get('centro_custo_id')
                    doc = doc_existente
                else:
                    # Criar novo documento
                    print(f'Criando novo documento para nota {nota_id}')
                    doc = ReembolsosDocumentos(
                        reembolso=reembolso,
                        tipo='nota',
                        nota_fiscal_id=nota.id,
                        descricao=nota_data.get('descricao', ''),
                        valor=nota.valor_total,
                        fornecedor=nota.nome_emitente,
                        ndocumento=nota.numero_nf,
                        data_documento=nota.data_emissao,
                        centro_custo_id=nota_data.get('centro_custo_id')
                    )
                    db.session.add(doc)
                
                valor_total += float(nota.valor_total)
            # Adicionar documentos avulsos
            for idx, avulso_data in enumerate(avulsos_data):
                print(f'Processando avulso {idx}: id={avulso_data.get("id")}, descricao={avulso_data.get("descricao")}')
                # Verificar se é um documento existente (tem ID numérico, não timestamp)
                avulso_id = avulso_data.get('id')
                doc_existente = None
                anexos_existentes_ids = []
                
                # Se tem ID e não é um timestamp (IDs de timestamp são muito grandes)
                if avulso_id and isinstance(avulso_id, int) and avulso_id < 1000000000000:
                    # Buscar documento existente
                    doc_existente = ReembolsosDocumentos.query.filter_by(
                        id=avulso_id,
                        reembolso_id=reembolso_id,
                        tipo='avulso'
                    ).first()
                    print(f'Documento existente encontrado: {doc_existente.id if doc_existente else "não encontrado"}')
                    
                    if doc_existente:
                        # Coletar IDs dos anexos que devem ser preservados (usando modelo Upload)
                        anexos_removidos = avulso_data.get('anexos_removidos', [])
                        uploads_existentes = Upload.query.filter_by(
                            pai_id=doc_existente.id,
                            pai='ReembolsosDocumentos',
                            tipo=4
                        ).all()
                        anexos_existentes = [u for u in uploads_existentes if u.id not in anexos_removidos]
                        anexos_existentes_ids = [u.id for u in anexos_existentes]
                        print(f'Anexos existentes: {len(uploads_existentes)}, removidos: {len(anexos_removidos)}, preservados: {len(anexos_existentes)}')
                
                # Criar ou atualizar documento
                if doc_existente:
                    # Atualizar documento existente
                    doc = doc_existente
                    doc.descricao = avulso_data['descricao']
                    doc.valor = avulso_data['valor']
                    doc.fornecedor = avulso_data.get('fornecedor', '')
                    doc.ndocumento = avulso_data.get('ndocumento', '')
                    doc.data_documento = parse_data_documento(avulso_data.get('data_documento'))
                    doc.centro_custo_id = avulso_data.get('centro_custo_id')
                    
                    # Remover anexos marcados para remoção (usando modelo Upload)
                    anexos_removidos = avulso_data.get('anexos_removidos', [])
                    if anexos_removidos:
                        # Buscar uploads do documento
                        uploads = Upload.query.filter_by(
                            pai='ReembolsosDocumentos',
                            pai_id=doc.id,
                            tipo=4
                        ).all()
                        for upload in uploads:
                            if upload.id in anexos_removidos:
                                print(f'Removendo anexo: {upload.id} - {upload.filename}')
                                db.session.delete(upload)
                else:
                    # Criar novo documento
                    doc = ReembolsosDocumentos(
                        reembolso=reembolso,
                        tipo='avulso',
                        descricao=avulso_data['descricao'],
                        valor=avulso_data['valor'],
                        fornecedor=avulso_data.get('fornecedor', ''),
                        ndocumento=avulso_data.get('ndocumento', ''),
                        data_documento=parse_data_documento(avulso_data.get('data_documento')),
                        centro_custo_id=avulso_data.get('centro_custo_id')
                    )
                    db.session.add(doc)
                    db.session.flush()  # Flush para obter o ID do documento antes de criar anexos
                    print(f'Novo documento criado: id={doc.id}')
                
                valor_total += float(avulso_data['valor'])
                
                # Processar novos anexos do avulso usando modelo Upload
                # Buscar todos os arquivos que começam com o padrão do avulso
                print(f'Buscando arquivos para avulso {idx} (padrão: avulso_{idx}_anexo_)')
                print(f'Total de arquivos em request.files: {len(request.files)}')
                print(f'Arquivos disponíveis: {list(request.files.keys())}')
                anexos_processados = 0
                arquivos_encontrados = []
                for file_key in request.files.keys():
                    print(f'Verificando arquivo: {file_key}, começa com avulso_{idx}_anexo_? {file_key.startswith(f"avulso_{idx}_anexo_")}')
                    if file_key.startswith(f'avulso_{idx}_anexo_'):
                        arquivos_encontrados.append(file_key)
                        file = request.files[file_key]
                        print(f'Arquivo encontrado: {file_key}, filename: {file.filename if hasattr(file, "filename") else "N/A"}, type: {type(file)}')
                        if file and hasattr(file, 'filename') and file.filename:
                            print(f'Processando anexo (editar): {file_key}, filename: {file.filename}, doc.id: {doc.id}')
                            # Ler arquivo
                            file_content = file.read()
                            # Criar Upload usando o __init__ que faz save automático
                            # O __init__ retorna True se criou ou False se já existe
                            try:
                                upload_instance = Upload(
                                    pai='ReembolsosDocumentos',
                                    pai_id=doc.id,
                                    tipo=4,
                                    filename=file.filename,
                                    mimetype=file.content_type or 'application/octet-stream',
                                    blob=file_content  # Passar bytes, o __init__ converte para base64
                                )
                                
                                # O __init__ retorna True/False, mas o objeto self foi modificado
                                # Buscar o upload criado ou existente
                                upload = Upload.query.filter_by(
                                    pai='ReembolsosDocumentos',
                                    pai_id=doc.id,
                                    tipo=4,
                                    filename=file.filename,
                                    mimetype=file.content_type or 'application/octet-stream'
                                ).first()
                                
                                if upload:
                                    anexos_processados += 1
                                    print(f'✓ Upload criado/encontrado (editar): id={upload.id}, filename={upload.filename}, tamanho blob: {len(upload.blob) if upload.blob else 0}')
                                else:
                                    print(f'✗ ERRO: Upload não foi encontrado após criação')
                                    raise Exception('Upload não foi encontrado após criação')
                            except Exception as e:
                                print(f'✗ ERRO ao criar upload: {str(e)}')
                                import traceback
                                traceback.print_exc()
                                # Não fazer rollback aqui, deixar o rollback geral tratar
                                raise
                print(f'Arquivos encontrados para avulso {idx}: {arquivos_encontrados}')
                print(f'Total de anexos processados para avulso {idx} (editar): {anexos_processados}')
            reembolso.valor_total = valor_total
            
            # Verificar se há uploads pendentes antes do commit
            uploads_pendentes = [obj for obj in db.session.new if isinstance(obj, Upload)]
            print(f'Uploads pendentes antes do commit: {len(uploads_pendentes)}')
            for up in uploads_pendentes:
                print(f'  - Upload pendente: id={up.id if hasattr(up, "id") else "None"}, filename={up.filename}, pai_id={up.pai_id}')
            
            db.session.commit()
            print('✓ Commit realizado com sucesso!')
            flash('Reembolso atualizado com sucesso!', 'success')
            return redirect(url_for('reembolso.index'))
        except Exception as e:
            print(f'✗ ERRO ao salvar reembolso: {str(e)}')
            import traceback
            traceback.print_exc()
            db.session.rollback()
            flash(f'Erro ao atualizar reembolso: {str(e)}', 'danger')
            return redirect(url_for('reembolso.editar', reembolso_id=reembolso_id))
    # GET: Preencher formulário
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    centros_custo = [{'id': c.id, 'codigo': c.codigo, 'nome': c.nome} for c in centros_custo]
    
    # Carregar documentos avulsos do reembolso
    avulsos = []
    notas = []
    for doc in reembolso.documentos:
        if doc.tipo == 'avulso':
            # Formatar data para YYYY-MM-DD (formato necessário para input type="date")
            data_documento = None
            if doc.data_documento:
                data_documento = doc.data_documento.strftime('%Y-%m-%d')
            
            # Buscar anexos
            anexos_upload = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsosDocumentos', tipo=4).all()
            anexos_list = [
                {'id': upload.id, 'filename': upload.filename}
                for upload in anexos_upload
            ]
            
            avulsos.append({
                'id': doc.id,
                'fornecedor': doc.fornecedor or '',
                'ndocumento': doc.ndocumento or '',
                'data_documento': data_documento,
                'descricao': doc.descricao,
                'valor': float(doc.valor),
                'centro_custo_id': doc.centro_custo_id,
                'anexos_count': len(anexos_list),
                'anexos': anexos_list
            })
        if doc.tipo == 'nota':
            notas.append({
                'id': doc.nota_fiscal_id,
                'descricao': doc.descricao,
                'valor': doc.valor,
                'centro_custo_id': doc.centro_custo_id
            })
    
    return render_template('reembolsos/editar.html', 
                         modo='editar',
                         reembolso_id=reembolso_id,
                         reembolso=reembolso,
                         notas=notas,
                         centros_custo=centros_custo,
                         avulsos=avulsos)

def notas_json(reembolso):
    notas = []
    for doc in reembolso.documentos:
        if doc.tipo == 'nota' and doc.nota_fiscal:
            notas.append({
                'id': doc.nota_fiscal.id,
                'descricao': doc.descricao,
                'valor': Decimal(doc.valor),
                'centro_custo_id': doc.centro_custo_id
            })
    return Markup(json.dumps(notas))

def avulsos_json(reembolso):
    avulsos = []
    for doc in reembolso.documentos:
        if doc.tipo == 'avulso':
            # Buscar anexos usando modelo Upload
            uploads = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsosDocumentos', tipo=4).all()
            avulsos.append({
                'id': doc.id,
                'descricao': doc.descricao,
                'valor': float(doc.valor),
                'centro_custo_id': doc.centro_custo_id,
                'anexos': [
                    {'id': upload.id, 'filename': upload.filename}
                    for upload in uploads
                ]
            })
    return Markup(json.dumps(avulsos))

# Modificar endpoint para fornecedores de documentos avulsos e emitentes de notas fiscais
@reembolso_bp.route('/fornecedores_avulsos')
@login_required
def fornecedores_avulsos():
    # Buscar documentos avulsos e extrair os nomes dos fornecedores
    docs = ReembolsosDocumentos.query.filter_by(tipo='avulso').group_by(ReembolsosDocumentos.fornecedor).all()
    fornecedores = set()
    for doc in docs:
        if doc.fornecedor:
            fornecedores.add(doc.fornecedor)
    # Buscar emitentes de notas fiscais
    notas = NotaFiscal.query.group_by(NotaFiscal.nome_emitente).all()
    for nota in notas:
        if nota.nome_emitente:
            fornecedores.add(nota.nome_emitente)
    return jsonify(list(fornecedores))

# Rotas para upload/download de anexos e exportação PDF serão implementadas na próxima etapa.

@reembolso_bp.route('/<int:reembolso_id>/alternar_enviado', methods=['POST'])
@login_required
def alternar_enviado(reembolso_id):
    """Alterna o estado de enviado do reembolso"""
    reembolso = Reembolsos.query.get_or_404(reembolso_id)
    
    # Verificar permissão
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403
    
    try:
        # Carregar dados_adicionais existentes ou criar novo
        dados = {}
        if reembolso.dados_adicionais:
            try:
                dados = json.loads(reembolso.dados_adicionais)
            except:
                dados = {}
        
        # Alternar estado de enviado
        dados['enviado'] = not dados.get('enviado', False)
        if dados.get('enviado'):
            dados['data_envio'] = datetime.utcnow().isoformat()
        else:
            dados.pop('data_envio', None)
        
        # Salvar em dados_adicionais
        reembolso.dados_adicionais = json.dumps(dados)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'enviado': dados['enviado'],
            'data_envio': dados.get('data_envio')
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@reembolso_bp.route('/<int:reembolso_id>/apagar', methods=['POST'])
@login_required
def apagar(reembolso_id):
    reembolso = Reembolsos.query.get_or_404(reembolso_id)
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        flash('Você não tem permissão para apagar este reembolso.', 'danger')
        return redirect(url_for('reembolso.index'))
    try:
        # Remover anexos dos documentos avulsos (usando modelo Upload)
        for doc in list(reembolso.documentos):
            if doc.tipo == 'avulso':
                uploads = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsosDocumentos', tipo=4).all()
                for upload in uploads:
                    db.session.delete(upload)
            db.session.delete(doc)
        db.session.delete(reembolso)
        db.session.commit()
        flash('Reembolso apagado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao apagar reembolso: {str(e)}', 'danger')
    return redirect(url_for('reembolso.index'))

@reembolso_bp.route('/nota/<int:nota_id>/documentos', methods=['GET'])
@login_required
def listar_documentos_nota(nota_id):
    print(f'listar_documentos_nota: {nota_id}');
    try:
        documentos = Upload.query.filter(Upload.pai_id==nota_id, Upload.pai=='NotaFiscal').all()
        print(f'documentos: {documentos}')
        return jsonify([{
            'id': doc.id,
            'tipo': doc.tipo,
            'filename': doc.filename,
            'mimetype': doc.mimetype,
            'uploaded_at': doc.uploaded_at.isoformat()
        } for doc in documentos])
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@reembolso_bp.route('/nota/documentos', methods=['POST'])
@login_required
def adicionar_documentos_nota():
    try:
        nota_id = request.form.get('nota_id')
        if not nota_id:
            return jsonify({'error': 'ID da nota não fornecido'}), 400

        # Verificar se a nota existe
        nota = NotaFiscal.query.get_or_404(nota_id)

        # Processar cada arquivo
        for file in request.files.getlist('anexos'):
            if file and file.filename:
                # Ler o arquivo e converter para base64
                file_content = file.read()
                file_base64 = base64.b64encode(file_content).decode('utf-8')

                # Criar upload
                upload = Upload(
                    pai='NotasFiscais',
                    pai_id=nota_id,
                    tipo=2,
                    filename=file.filename,
                    mimetype=file.content_type,
                    blob=file_base64
                )
                upload.save()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@reembolso_bp.route('/documento/<int:documento_id>', methods=['DELETE'])
@login_required
def excluir_documento(documento_id):
    try:
        upload = Upload.query.get_or_404(documento_id)
        upload.delete()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@reembolso_bp.route('/documento/<int:documento_id>/download')
@login_required
def download_documento(documento_id):
    try:
        upload = Upload.query.get_or_404(documento_id)
        file_content = base64.b64decode(upload.blob)
        return send_file(
            BytesIO(file_content),
            download_name=upload.filename,
            mimetype=upload.mimetype,
            as_attachment=True
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400 