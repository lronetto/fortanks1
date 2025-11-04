from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, abort, make_response, Response
from markupsafe import Markup
from flask_login import login_required, current_user
from controllers.nota_fiscal_controller import api_get_dados_notas_fiscais
from models.nota_fiscal import CFOPS_COMPRA,CNPJS_MATRIZ_FILIAIS,CFOPS_TRANSFERENCIA
from models.dados_analiticos import DadoAnalitico
from models import db, Reembolso, ReembolsoDocumento, ReembolsoAnexo, NotaFiscal,NotaFiscalItem ,CentroCusto
from models.upload import Upload
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
            
            print(notas_selecionadas)
            print(avulsos_data)
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
                    data_documento=datetime.strptime(avulso_data.get('data_documento', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d'),
                    centro_custo_id=avulso_data.get('centro_custo_id')
                )
                db.session.add(doc)
                valor_total += float(avulso_data['valor'])
                
                # Processar anexos do avulso
                for file_idx in range(100):  # Limite arbitrário de 100 anexos por avulso
                    file_key = f'avulso_{idx}_anexo_{file_idx}'
                    if file_key not in request.files:
                        break
                    file = request.files[file_key]
                    if file and file.filename:
                        anexo = ReembolsoAnexo(
                            documento=doc,
                            filename=file.filename,
                            mimetype=file.content_type,
                            blob=file.read()
                        )
                        db.session.add(anexo)
            
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
    form = ReembolsoForm()
    form.centro_custo_id.choices = [(c['id'], f"{c['codigo']} - {c['nome']}") for c in centros_custo]
    return render_template(
        'reembolsos/form.html',
        form=form,
        modo='novo',
        notas_json='[]',
        avulsos_json='[]',
        centros_custo=centros_custo
    )

@reembolso_bp.route('/buscar_notas', methods=['GET','POST'])
@login_required
def nota_fiscal_busca_reembolso():
    print('buscar_notas')
    tinicial = time.time()
    if request.method == 'POST':
        try:
            filtros = request.get_json()
            filtros['cnpj_emitente'] = CNPJS_MATRIZ_FILIAIS
            filtros['cfop'] = CFOPS_TRANSFERENCIA

            notas_filtradas,pagination = nota_fiscal_busca(filtros)
            print('tempo de execução3: ',time.time()-tinicial)
           
            #pagination = notas_filtradas.paginate(page=page, per_page=per_page, error_out=False)
            #notas_filtradas = pagination.items
            print(f'Total de notas encontradas: {pagination.total}')
            print(f'Total de páginas: {pagination.pages}')
            # Se após filtrar por pagamento ficar com menos itens que a página atual,
            # precisamos buscar mais itens para preencher a página
           

            print(f'Total de notas encontradas: {pagination.total}')
            print(f'Total de páginas: {pagination.pages}')

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
        else:
            print(f'Anexos do documento: {len(doc.anexos)}')
    
    html = render_template('reembolsos/pdf_template.html', reembolso=reembolso)
    return reembolso,html

def dias_desde_1900(data):
    """Calcula o número de dias desde 01/01/1900 até a data informada"""
    data_inicial = date(1900, 1, 1)
    return (data - data_inicial).days

@reembolso_bp.route('/exportar_pdf/<int:id>')
def exportar_pdf(id):
    reembolso = Reembolso.query.join(Usuario, Reembolso.usuario_id==Usuario.id).get_or_404(id)
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
            elif doc.tipo == 'avulso':
                doc.anexos = Upload.query.filter_by(pai_id=doc.id, pai='ReembolsoDocumento', tipo=3).all()
        
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
            elif doc.tipo == 'avulso' and doc.anexos:
                for anexo in doc.anexos:
                    if anexo.mimetype == 'application/pdf':
                        try:
                            # Converte o blob base64 para bytes
                            pdf_bytes = base64.b64decode(anexo.blob)
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
    anexo = ReembolsoAnexo.query.get_or_404(anexo_id)
    reembolso = anexo.documento.reembolso
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)
    return send_file(BytesIO(anexo.blob), download_name=anexo.filename, mimetype=anexo.mimetype, as_attachment=True)

@reembolso_bp.route('/<int:reembolso_id>/editar', methods=['GET', 'POST'])
@login_required
def editar(reembolso_id):
    print(f'reembolso_id: {reembolso_id}')
    reembolso = Reembolso.query.get_or_404(reembolso_id)
    re = ReembolsoDocumento.query.filter_by(reembolso_id=reembolso_id).all()
    notas = []
    for r in re:
        if r.tipo == 'nota':
            notas.append({
                'id': r.nota_fiscal_id,
                'descricao': r.descricao,
                'valor': r.valor,
                'centro_custo_id': r.centro_custo_id
            })
        else:
            notas.append({
                'id': r.id,
            })

    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)

    if request.method == 'POST':
        print(f'salvar editar reembolso')
        try:
            # Atualizar campos principais
            reembolso.numero_relatorio = request.form.get('numero_relatorio')
            notas_selecionadas = json.loads(request.form.get('notas_selecionadas', '[]'))
            avulsos_data = json.loads(request.form.get('avulsos_data', '[]'))

            # Limpar docs antigos
            for doc in list(reembolso.documentos):
                # Remove anexos se for avulso
                if doc.tipo == 'avulso':
                    for anexo in list(doc.anexos):
                        db.session.delete(anexo)
                db.session.delete(doc)
            db.session.flush()

            valor_total = 0
            # Adicionar notas fiscais
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
                    centro_custo_id=nota_data['centro_custo_id']
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
                    data_documento=datetime.strptime(avulso_data.get('data_documento', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d'),
                    centro_custo_id=avulso_data.get('centro_custo_id')
                )
                db.session.add(doc)
                valor_total += float(avulso_data['valor'])
                # Processar anexos do avulso
                for file_idx in range(100):
                    file_key = f'avulso_{idx}_anexo_{file_idx}'
                    if file_key not in request.files:
                        break
                    file = request.files[file_key]
                    if file and file.filename:
                        anexo = ReembolsoAnexo(
                            documento=doc,
                            filename=file.filename,
                            mimetype=file.content_type,
                            blob=file.read()
                        )
                        db.session.add(anexo)
            reembolso.valor_total = valor_total
            db.session.commit()
            flash('Reembolso atualizado com sucesso!', 'success')
            return redirect(url_for('reembolso.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar reembolso: {str(e)}', 'danger')
            return redirect(url_for('reembolso.editar', reembolso_id=reembolso_id))
    # GET: Preencher formulário
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    centros_custo = [{'id': c.id, 'codigo': c.codigo, 'nome': c.nome} for c in centros_custo]
    return render_template('reembolsos/editar.html', modo='editar',reembolso_id=reembolso_id,notas=notas,centros_custo=centros_custo)

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
            avulsos.append({
                'id': doc.id,
                'descricao': doc.descricao,
                'valor': float(doc.valor),
                'centro_custo_id': doc.centro_custo_id,
                'anexos': [
                    {'id': anexo.id, 'filename': anexo.filename}
                    for anexo in doc.anexos
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
        # Remover anexos dos documentos avulsos
        for doc in list(reembolso.documentos):
            if doc.tipo == 'avulso':
                for anexo in list(doc.anexos):
                    db.session.delete(anexo)
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