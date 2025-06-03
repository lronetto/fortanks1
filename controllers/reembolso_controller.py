from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, abort, make_response, Response
from markupsafe import Markup
from flask_login import login_required, current_user
from models.nota_fiscal import CFOPS_COMPRA
from models.dados_analiticos import DadoAnalitico
from models import db, Reembolso, ReembolsoDocumento, ReembolsoAnexo, NotaFiscal,NotaFiscalItem ,CentroCusto
from forms.reembolso_forms import ReembolsoForm, DocumentoAvulsoForm
from sqlalchemy import or_, and_
from io import BytesIO
from datetime import datetime
from weasyprint import HTML
import json
import time
from models import PlanoConta
from models.dados_analiticos import PL_CUSTO,PL_0202,PL_0207,PL_0209
import requests
import base64
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
            centro_custo_id = request.form.get('centro_custo_id')
            notas_selecionadas = json.loads(request.form.get('notas_selecionadas', '[]'))
            avulsos_data = json.loads(request.form.get('avulsos_data', '[]'))
            print(f'request.form: {request.form}')
            # Validar centro de custo
            centro_custo = CentroCusto.query.get_or_404(centro_custo_id)
            
            # Criar reembolso
            reembolso = Reembolso(
                usuario_id=current_user.id,
                centro_custo_id=centro_custo_id,
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
                    data_documento=nota.data_emissao
                )
                db.session.add(doc)
                valor_total += float(nota.valor_total)
            
            # Adicionar documentos avulsos
            for idx, avulso_data in enumerate(avulsos_data):
                doc = ReembolsoDocumento(
                    reembolso=reembolso,
                    fornecedor=avulso_data['fornecedor'],
                    ndocumento=avulso_data['ndocumento'],
                    data_documento=avulso_data['data_documento'],
                    tipo='avulso',
                    descricao=avulso_data['descricao'],
                    valor=avulso_data['valor']
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
    form = ReembolsoForm()
    form.centro_custo_id.choices = [(c.id, f"{c.codigo} - {c.nome}") for c in CentroCusto.query.filter_by(ativo=True).all()]
    return render_template('reembolsos/novo.html', form=form)

@reembolso_bp.route('/buscar_notas', methods=['GET','POST'])
@login_required
def buscar_notas():
    if request.method == 'POST':
        try:
            print(f'request.get_json(): {request.get_json()}')
            filtros = request.get_json()
            page = int(filtros.get('page', 1))
            per_page = int(filtros.get('per_page', 10))
            ids = filtros.get('ids', [])
            pagamento_filtro = filtros.get('pagamento', '')
            valor_minimo = filtros.get('valor_minimo')
            valor_maximo = filtros.get('valor_maximo')
            tinicial = time.time()
            query = NotaFiscal.query.filter(NotaFiscal.status_processamento!='cancelada')
            #query = query.filter(NotaFiscal.cnpj_emitente.notlike('%27126997000187%'))
            #query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.notlike('%5949%')))
            if filtros.get('numero'):
                print(f'filtros["numero"]: {filtros["numero"]}')
                query = query.filter(NotaFiscal.numero_nf.ilike(f'%{filtros["numero"]}%'))
            if filtros.get('fornecedor'):
                print(f'filtros["fornecedor"]: {filtros["fornecedor"]}')
                query = query.filter(NotaFiscal.nome_emitente.ilike(f'%{filtros["fornecedor"]}%'))
            if filtros.get('data_inicial'):
                print(f'filtros["data_inicial"]: {filtros["data_inicial"]}')
                query = query.filter(NotaFiscal.data_emissao >= filtros['data_inicial'])
            if filtros.get('data_final'):
                print(f'filtros["data_final"]: {filtros["data_final"]}')
                query = query.filter(NotaFiscal.data_emissao <= filtros['data_final'])
            if valor_minimo:
                print(f'valor_minimo: {valor_minimo}')
                query = query.filter(NotaFiscal.valor_total >= float(valor_minimo))
            if valor_maximo:
                print(f'valor_maximo: {valor_maximo}')
                query = query.filter(NotaFiscal.valor_total <= float(valor_maximo))
            if ids:
                print(f'ids: {ids}')
                query = query.filter(or_(NotaFiscal.id.in_(ids)))
            # Filtrar por pagamento
            notas = query.order_by(NotaFiscal.data_emissao.desc()).all()
            notas_filtradas = []
            tfinal = time.time()
            print(f'Tempo de execução1: {tfinal - tinicial} segundos')
            tinicial = time.time()
            
            for n in notas:
                pag = DadoAnalitico.query.\
                    join(PlanoConta,DadoAnalitico.plano_conta_id==PlanoConta.id).\
                    filter(PlanoConta.codigo.notin_(PL_0202+PL_0207+PL_0209)).\
                    filter(DadoAnalitico.documento==n.numero_nf.lstrip('0')).\
                    filter(DadoAnalitico.valor==n.valor_total).first()
                valor_pagamento = pag.valor if pag else 0
                if pagamento_filtro == '0' and valor_pagamento != 0:
                    continue  # Só não pagos
                if pagamento_filtro == '1' and valor_pagamento == 0:
                    continue  # Só pagos
                notas_filtradas.append({
                    'id': n.id,
                    'numero_nf': n.numero_nf,
                    'nome_emitente': n.nome_emitente,
                    'data_emissao': n.data_emissao.isoformat(),
                    'valor_total': float(n.valor_total),
                    'pagamento': valor_pagamento,
                    'chave_acesso': getattr(n, 'chave_acesso', '')
                })
            tfinal = time.time()
            print(f'Tempo de execução2: {tfinal - tinicial} segundos')
            # Paginação manual após filtro
            total = len(notas_filtradas)
            start = (page-1)*per_page
            end = start+per_page
            notas_pagina = notas_filtradas[start:end]
            return jsonify({
                'notas': notas_pagina,
                'page': page,
                'pages': (total + per_page - 1) // per_page,
                'total': total,
                'has_next': end < total,
                'has_prev': start > 0
            })
        except Exception as e:
            print(f'request.get_json(): {str(e)}')
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Método não permitido'}), 405

@reembolso_bp.route('/<int:reembolso_id>/pdf')
@login_required
def exportar_pdf(reembolso_id):
    reembolso = Reembolso.query.get_or_404(reembolso_id)
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)
    html = render_template('reembolsos/pdf_template.html', reembolso=reembolso)
    pdf = HTML(string=html, base_url=request.base_url).write_pdf()
    response = make_response(pdf)
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
    reembolso = Reembolso.query.get_or_404(reembolso_id)
    if reembolso.usuario_id != current_user.id and not current_user.is_admin:
        abort(403)
    if request.method == 'POST':
        try:
            # Atualizar campos principais
            reembolso.centro_custo_id = request.form.get('centro_custo_id')
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
                    valor=nota.valor_total
                )
                db.session.add(doc)
                valor_total += float(nota.valor_total)
            # Adicionar documentos avulsos
            for idx, avulso_data in enumerate(avulsos_data):
                doc = ReembolsoDocumento(
                    reembolso=reembolso,
                    tipo='avulso',
                    descricao=avulso_data['descricao'],
                    valor=avulso_data['valor']
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
    form = ReembolsoForm(obj=reembolso)
    form.centro_custo_id.choices = [(c.id, f"{c.codigo} - {c.nome}") for c in CentroCusto.query.filter_by(ativo=True).all()]
    return render_template('reembolsos/editar.html', form=form, reembolso=reembolso)

def notas_json(reembolso):
    notas = []
    for doc in reembolso.documentos:
        if doc.tipo == 'nota' and doc.nota_fiscal:
            notas.append({
                'id': doc.nota_fiscal.id,
                'descricao': doc.descricao,
                'valor': float(doc.valor)
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