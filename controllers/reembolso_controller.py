from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, abort, make_response, Response
from markupsafe import Markup
from flask_login import login_required, current_user
from controllers.nota_fiscal_controller import api_get_dados_notas_fiscais
from models.nota_fiscal import CFOPS_COMPRA,CNPJS_MATRIZ_FILIAIS,CFOPS_TRANSFERENCIA
from models.dados_analiticos import DadoAnalitico
from models import db, Reembolso, ReembolsoDocumento, ReembolsoAnexo, NotaFiscal,NotaFiscalItem ,CentroCusto,Usuario
from models.upload import Upload
from models.reembolso import ReembolsoAnexo
from forms.reembolso_forms import ReembolsoForm, DocumentoAvulsoForm
from sqlalchemy import or_, and_, cast, Date, case, func
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
reembolso_bp = Blueprint('reembolso', __name__, url_prefix='/reembolsos')
import dotenv
import os
dotenv.load_dotenv()

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
    query = Reembolso.query.filter_by(usuario_id=current_user.id).order_by(Reembolso.data.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    reembolsos = pagination.items
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
            reembolso = Reembolso(
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
                doc = ReembolsoDocumento(
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
                doc = ReembolsoDocumento(
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
            # Obter filtros do JSON do body
            filtros = request.get_json() if request.is_json else {}
            
            # Obter parâmetros de paginação
            page = filtros.get('page', request.args.get('page', 1, type=int))
            per_page = filtros.get('per_page', request.args.get('per_page', 25, type=int))
            
            # Filtro de pagamento
            pagamento_filtro = filtros.get('pagamento', '')
            notas_selecionadas = filtros.get('notas_selecionadas', [])
            ids = filtros.get('ids', [])
            
            # Adicionar joins para informações de pagamento e reembolso
            tem_pagamento_column = func.max(case((DadoAnalitico.id != None, 1), else_=0)).label('tem_pagamento')
            upload_column = func.max(case((Upload.id != None, 1), else_=0)).label('upload')
            upload_envio_column = func.max(case((Upload.tipo == 2, 1), else_=0)).label('upload_envio')
            upload_reembolso_column = func.max(case((Upload.tipo == 3, 1), else_=0)).label('upload_reembolso')
            
            # Criar query com joins (similar ao que api_get_dados_notas_fiscais faz, mas com joins necessários)
            join_conditions_pagamento = and_(
                NotaFiscal.valor_total == DadoAnalitico.valor,
                DadoAnalitico.documento.like('%' + NotaFiscal.numero_nf + '%')
            )
            join_conditions_upload = and_(
                Upload.pai_id == NotaFiscal.id,
                Upload.pai == 'NotaFiscal'
            )
            
            query = db.session.query(
                NotaFiscal,
                tem_pagamento_column,
                upload_column,
                upload_envio_column,
                upload_reembolso_column,
                ReembolsoDocumento
            ).select_from(NotaFiscal).filter(NotaFiscal.status_processamento != 'cancelada')
            
            # Aplicar filtros (usando a mesma lógica de api_get_dados_notas_fiscais)
            if filtros.get('numero'):
                busca_like = f"%{filtros.get('numero')}%"
                query = query.filter(
                    or_(
                        NotaFiscal.numero_nf.ilike(busca_like),
                        NotaFiscal.nome_emitente.ilike(busca_like),
                        NotaFiscal.chave_acesso.ilike(busca_like)
                    )
                )
            if filtros.get('fornecedor'):
                query = query.filter(NotaFiscal.nome_emitente.ilike(f"%{filtros.get('fornecedor')}%"))
            if filtros.get('data_inicial') or filtros.get('data_ini'):
                data_ini = filtros.get('data_inicial') or filtros.get('data_ini')
                try:
                    data_inicio = datetime.strptime(data_ini, '%Y-%m-%d')
                    query = query.filter(NotaFiscal.data_emissao >= data_inicio)
                except:
                    pass
            if filtros.get('data_final') or filtros.get('data_fim'):
                data_fim = filtros.get('data_final') or filtros.get('data_fim')
                try:
                    data_final = datetime.strptime(data_fim, '%Y-%m-%d')
                    query = query.filter(NotaFiscal.data_emissao <= data_final)
                except:
                    pass
            if filtros.get('valor_minimo'):
                query = query.filter(NotaFiscal.valor_total >= float(filtros.get('valor_minimo')))
            if filtros.get('valor_maximo'):
                query = query.filter(NotaFiscal.valor_total <= float(filtros.get('valor_maximo')))
            if filtros.get('valor_exato'):
                query = query.filter(NotaFiscal.valor_total == float(filtros.get('valor_exato')))
            
            # Filtros de CNPJ e CFOP
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ_FILIAIS))
            query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(CFOPS_TRANSFERENCIA)))
            
            # Joins
            query = query.outerjoin(DadoAnalitico, join_conditions_pagamento)
            query = query.outerjoin(ReembolsoDocumento, ReembolsoDocumento.nota_fiscal_id == NotaFiscal.id)
            query = query.outerjoin(Upload, join_conditions_upload)
            
            # Filtros de pagamento
            if pagamento_filtro == '0':  # Não Pago
                query = query.having(tem_pagamento_column == 0)
            elif pagamento_filtro == '1':  # Pago
                query = query.having(tem_pagamento_column == 1)
            elif pagamento_filtro == '2':  # Sem upload de envio
                query = query.having(upload_envio_column == 0)
            elif pagamento_filtro == '3':  # Com upload de reembolso
                query = query.having(upload_reembolso_column == 1)
            elif pagamento_filtro == '4':  # Selecionados
                query = query.filter(NotaFiscal.id.in_(ids))
            
            # Agrupar e ordenar
            query = query.group_by(NotaFiscal.id)
            query = query.order_by(NotaFiscal.data_emissao.desc())
            
            # Aplicar paginação
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            notas = pagination.items
            
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
                        'data_emissao': nota_fiscal_obj.data_emissao.isoformat() if nota_fiscal_obj.data_emissao else '',
                        'valor_total': float(nota_fiscal_obj.valor_total) if nota_fiscal_obj.valor_total else 0.0,
                        'pagamento': n.tem_pagamento if hasattr(n, 'tem_pagamento') else 0,
                        'upload': n.upload if hasattr(n, 'upload') else 0,
                        'upload_envio': n.upload_envio if hasattr(n, 'upload_envio') else 0,
                        'upload_reembolso': n.upload_reembolso if hasattr(n, 'upload_reembolso') else 0,
                        'chave_acesso': nota_fiscal_obj.chave_acesso or '',
                    })
                except Exception as e:
                    print(f'Erro ao processar nota: {str(e)}')
                    continue
            
            print('tempo de execução3: ',time.time()-tinicial)

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
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Método não permitido'}), 405

@reembolso_bp.route('/<int:reembolso_id>/pdf_template')
@login_required
def pdf_template(reembolso_id):
    reembolso = Reembolso.query.get_or_404(reembolso_id)
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
def exportar_pdf(id):
    reembolso = Reembolso.query.join(Usuario, Reembolso.usuario_id==Usuario.id).filter(Reembolso.id==id).first()
    if not reembolso:
        abort(404)
    pdf_writer = PdfWriter()
    CCs = ReembolsoDocumento.query.\
    filter(ReembolsoDocumento.reembolso_id==id)\
    .join(CentroCusto, ReembolsoDocumento.centro_custo_id==CentroCusto.id)\
    .group_by(ReembolsoDocumento.centro_custo_id)\
            .order_by(CentroCusto.nome).\
            filter(CentroCusto.codigo.like('0014-00')).all()
            
    
    for cc in CCs:
        docs = ReembolsoDocumento.query.\
            filter(ReembolsoDocumento.reembolso_id==id, 
                   ReembolsoDocumento.centro_custo_id==cc.centro_custo_id).\
                    order_by(ReembolsoDocumento.data_documento.desc()).all()
        valor_total = sum(doc.valor for doc in docs)
        # Calcula o número de dias desde 1900
        dias = dias_desde_1900(reembolso.data.date())
        nrel = valor_total+dias
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
                anexos = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsoDocumento', tipo=4).all()
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
    
    # Salva o PDF final em um BytesIO
    output = BytesIO()
    pdf_writer.write(output)
    output.seek(0)
    
    response = make_response(output.getvalue())
    output.close()
    pdf_writer.close()
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=reembolso_{reembolso.numero_relatorio}.pdf'
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
    doc = ReembolsoDocumento.query.get_or_404(upload.pai_id)
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
    reembolso = Reembolso.query.get_or_404(reembolso_id)
   
    

    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)

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
            # Coletar IDs de documentos avulsos que serão mantidos (editados)
            avulsos_ids_manter = []
            for avulso_data in avulsos_data:
                avulso_id = avulso_data.get('id')
                # Se tem ID e não é timestamp (IDs de timestamp são muito grandes)
                if avulso_id and isinstance(avulso_id, int) and avulso_id < 1000000000000:
                    avulsos_ids_manter.append(avulso_id)
            
            # Limpar apenas docs que não estão sendo editados
            for doc in list(reembolso.documentos):
                # Se for avulso e não está na lista de manter, deletar
                if doc.tipo == 'avulso' and doc.id not in avulsos_ids_manter:
                    # Remove anexos se for avulso
                    for anexo in list(doc.anexos):
                        db.session.delete(anexo)
                    db.session.delete(doc)
                # Se for nota, deletar (será recriado)
                elif doc.tipo == 'nota':
                    db.session.delete(doc)
            db.session.flush()

            valor_total = 0
            # Adicionar notas fiscais
            for nota_data in notas_selecionadas:
                nota_id = nota_data.get('id')
                if not nota_id:
                    print(f'Aviso: Nota fiscal sem ID, pulando...')
                    continue
                    
                nota = NotaFiscal.query.get(nota_id)
                if not nota:
                    print(f'Erro: Nota fiscal {nota_id} não encontrada, pulando...')
                    continue
                    
                doc = ReembolsoDocumento(
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
                    doc_existente = ReembolsoDocumento.query.filter_by(
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
                            pai='ReembolsoDocumento',
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
                            pai='ReembolsoDocumento',
                            pai_id=doc.id,
                            tipo=4
                        ).all()
                        for upload in uploads:
                            if upload.id in anexos_removidos:
                                print(f'Removendo anexo: {upload.id} - {upload.filename}')
                                db.session.delete(upload)
                else:
                    # Criar novo documento
                    doc = ReembolsoDocumento(
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
                                    pai='ReembolsoDocumento',
                                    pai_id=doc.id,
                                    tipo=4,
                                    filename=file.filename,
                                    mimetype=file.content_type or 'application/octet-stream',
                                    blob=file_content  # Passar bytes, o __init__ converte para base64
                                )
                                
                                # O __init__ retorna True/False, mas o objeto self foi modificado
                                # Buscar o upload criado ou existente
                                upload = Upload.query.filter_by(
                                    pai='ReembolsoDocumento',
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
            avulsos.append({
                'id': doc.id,
                'fornecedor': doc.fornecedor or '',
                'ndocumento': doc.ndocumento or '',
                'data_documento': doc.data_documento.isoformat() if doc.data_documento else None,
                'descricao': doc.descricao,
                'valor': float(doc.valor),
                'centro_custo_id': doc.centro_custo_id,
                'anexos_count': len(Upload.query.filter_by(pai_id=doc.id, pai='ReembolsoDocumento', tipo=4).all()),
                'anexos': [
                    {'id': upload.id, 'filename': upload.filename}
                    for upload in Upload.query.filter_by(pai_id=doc.id, pai='ReembolsoDocumento', tipo=4).all()
                ]
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
            uploads = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsoDocumento', tipo=4).all()
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
    docs = ReembolsoDocumento.query.filter_by(tipo='avulso').group_by(ReembolsoDocumento.fornecedor).all()
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

@reembolso_bp.route('/<int:reembolso_id>/apagar', methods=['POST'])
@login_required
def apagar(reembolso_id):
    reembolso = Reembolso.query.get_or_404(reembolso_id)
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        flash('Você não tem permissão para apagar este reembolso.', 'danger')
        return redirect(url_for('reembolso.index'))
    try:
        # Remover anexos dos documentos avulsos (usando modelo Upload)
        for doc in list(reembolso.documentos):
            if doc.tipo == 'avulso':
                uploads = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsoDocumento', tipo=4).all()
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
    try:
        documentos = Upload.query.filter(Upload.pai_id==nota_id, Upload.pai=='NotaFiscal').all()
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
                    pai='nota_fiscal',
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