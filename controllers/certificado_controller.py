from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime
import json
import base64
from io import BytesIO

from models.database import db
from models.certificado import Certificado
from models.upload import Upload

certificado_bp = Blueprint('certificado', __name__)

@certificado_bp.route('/')
@login_required
def index():
    """
    Lista todos os certificados
    """
    from datetime import date
    certificados = Certificado.query.filter_by(ativo=True).order_by(Certificado.data_vencimento.desc()).all()
    hoje = date.today()
    return render_template('certificados/index.html', certificados=certificados, hoje=hoje)

@certificado_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cria um novo certificado
    """
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            tipo = request.form.get('tipo')
            data_str = request.form.get('data')
            data_vencimento_str = request.form.get('data_vencimento')
            dados_adicionais_json = request.form.get('dados_adicionais')
            
            # Validação básica
            if not nome:
                flash('Por favor, informe o nome do certificado.', 'danger')
                return redirect(url_for('certificado.index'))
            
            # Converter datas
            data = None
            if data_str:
                try:
                    data = datetime.strptime(data_str, '%Y-%m-%d').date()
                except:
                    pass
            
            data_vencimento = None
            if data_vencimento_str:
                try:
                    data_vencimento = datetime.strptime(data_vencimento_str, '%Y-%m-%d').date()
                except:
                    pass
            
            # Processar dados adicionais
            dados_adicionais = None
            if dados_adicionais_json:
                try:
                    # Validar JSON
                    json.loads(dados_adicionais_json)
                    dados_adicionais = dados_adicionais_json
                except:
                    # Se não for JSON válido, criar um objeto JSON simples
                    dados_adicionais = json.dumps({}, ensure_ascii=False)
            
            # Criar o novo certificado
            novo_certificado = Certificado(
                nome=nome,
                tipo=tipo,
                data=data,
                data_vencimento=data_vencimento,
                dados_adicionais=dados_adicionais
            )
            
            novo_certificado.save()
            
            # Processar uploads de documentos
            certificado_id = novo_certificado.id
            uploads_processados = 0
            
            for file_key in request.files.keys():
                if file_key.startswith('documento_'):
                    file = request.files[file_key]
                    if file and file.filename:
                        file_content = file.read()
                        upload = Upload()
                        upload.pai = 'Certificado'
                        upload.pai_id = certificado_id
                        upload.tipo = 5  # Tipo 5 para certificados
                        upload.filename = file.filename
                        upload.mimetype = file.content_type or 'application/octet-stream'
                        upload.uploaded_at = datetime.utcnow()
                        
                        if isinstance(file_content, bytes):
                            upload.blob = base64.b64encode(file_content).decode('utf-8')
                        else:
                            upload.blob = file_content
                        
                        db.session.add(upload)
                        uploads_processados += 1
            
            if uploads_processados > 0:
                db.session.commit()
            
            flash('Certificado criado com sucesso.', 'success')
            return redirect(url_for('certificado.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar certificado: {str(e)}', 'danger')
            return redirect(url_for('certificado.index'))
    
    return redirect(url_for('certificado.index'))

@certificado_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um certificado existente
    """
    certificado = Certificado.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            tipo = request.form.get('tipo')
            data_str = request.form.get('data')
            data_vencimento_str = request.form.get('data_vencimento')
            dados_adicionais_json = request.form.get('dados_adicionais')
            
            # Validação básica
            if not nome:
                flash('Por favor, informe o nome do certificado.', 'danger')
                return redirect(url_for('certificado.index'))
            
            # Converter datas
            data = None
            if data_str:
                try:
                    data = datetime.strptime(data_str, '%Y-%m-%d').date()
                except:
                    pass
            
            data_vencimento = None
            if data_vencimento_str:
                try:
                    data_vencimento = datetime.strptime(data_vencimento_str, '%Y-%m-%d').date()
                except:
                    pass
            
            # Processar dados adicionais
            if dados_adicionais_json:
                try:
                    # Validar JSON
                    json.loads(dados_adicionais_json)
                    certificado.dados_adicionais = dados_adicionais_json
                except:
                    pass
            
            # Atualizar o certificado
            certificado.nome = nome
            certificado.tipo = tipo
            certificado.data = data
            certificado.data_vencimento = data_vencimento
            certificado.atualizado_em = datetime.now()
            
            certificado.save()
            
            # Processar novos uploads de documentos
            uploads_processados = 0
            
            for file_key in request.files.keys():
                if file_key.startswith('documento_'):
                    file = request.files[file_key]
                    if file and file.filename:
                        file_content = file.read()
                        upload = Upload()
                        upload.pai = 'Certificado'
                        upload.pai_id = certificado.id
                        upload.tipo = 5  # Tipo 5 para certificados
                        upload.filename = file.filename
                        upload.mimetype = file.content_type or 'application/octet-stream'
                        upload.uploaded_at = datetime.utcnow()
                        
                        if isinstance(file_content, bytes):
                            upload.blob = base64.b64encode(file_content).decode('utf-8')
                        else:
                            upload.blob = file_content
                        
                        db.session.add(upload)
                        uploads_processados += 1
            
            if uploads_processados > 0:
                db.session.commit()
            
            flash('Certificado atualizado com sucesso.', 'success')
            return redirect(url_for('certificado.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar certificado: {str(e)}', 'danger')
            return redirect(url_for('certificado.index'))
    
    # Buscar documentos anexos
    documentos = Upload.query.filter_by(pai='Certificado', pai_id=id, tipo=5).all()
    
    return jsonify({
        'certificado': certificado.to_dict(),
        'documentos': [doc.to_dict() for doc in documentos] if documentos else []
    })

@certificado_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um certificado (soft delete)
    """
    certificado = Certificado.query.get_or_404(id)
    
    try:
        certificado.ativo = False
        certificado.save()
        flash('Certificado excluído com sucesso.', 'success')
    except Exception as e:
        flash(f'Erro ao excluir certificado: {str(e)}', 'danger')
    
    return redirect(url_for('certificado.index'))

@certificado_bp.route('/visualizar/<int:id>')
@login_required
def visualizar(id):
    """
    Visualiza os detalhes de um certificado
    """
    certificado = Certificado.query.get_or_404(id)
    documentos = Upload.query.filter_by(pai='Certificado', pai_id=id, tipo=5).all()
    
    return jsonify({
        'certificado': certificado.to_dict(),
        'documentos': [doc.to_dict() for doc in documentos] if documentos else []
    })

@certificado_bp.route('/documento/<int:doc_id>/download')
@login_required
def download_documento(doc_id):
    """
    Faz download de um documento anexo
    """
    upload = Upload.query.get_or_404(doc_id)
    
    if upload.pai != 'Certificado' or upload.tipo != 5:
        flash('Documento não encontrado.', 'danger')
        return redirect(url_for('certificado.index'))
    
    try:
        blob_data = upload.get_blob()
        if blob_data:
            return send_file(
                BytesIO(blob_data),
                mimetype=upload.mimetype,
                as_attachment=True,
                download_name=upload.filename
            )
        else:
            flash('Erro ao recuperar arquivo.', 'danger')
            return redirect(url_for('certificado.index'))
    except Exception as e:
        flash(f'Erro ao fazer download: {str(e)}', 'danger')
        return redirect(url_for('certificado.index'))

@certificado_bp.route('/documento/<int:doc_id>/excluir', methods=['POST'])
@login_required
def excluir_documento(doc_id):
    """
    Exclui um documento anexo
    """
    upload = Upload.query.get_or_404(doc_id)
    
    if upload.pai != 'Certificado' or upload.tipo != 5:
        return jsonify({'success': False, 'message': 'Documento não encontrado.'}), 404
    
    try:
        certificado_id = upload.pai_id
        upload.delete()
        flash('Documento excluído com sucesso.', 'success')
        return jsonify({'success': True, 'message': 'Documento excluído com sucesso.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao excluir documento: {str(e)}'}), 500
