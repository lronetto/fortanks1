from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime
import json
import base64
from io import BytesIO

from models.database import db
from models.certificado import Certificados, CertificadosTipos
from models.upload import Upload

certificado_bp = Blueprint('certificado', __name__)

@certificado_bp.route('/')
@login_required
def index():
    """
    Lista todos os certificados
    """
    from datetime import date
    certificados = Certificados.query.filter_by(ativo=True).order_by(Certificados.data_vencimento.desc()).all()
    hoje = date.today()
    tipos = CertificadosTipos.query.filter_by(ativo=True).order_by(CertificadosTipos.nome).all()
    return render_template('cadastro_operacional/certificados/index.html', certificados=certificados, hoje=hoje, tipos=tipos)

@certificado_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cria um novo certificado
    """
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            tipo_id_str = request.form.get('tipo_id')
            tipo_id = None
            tipo_nome = None
            
            # Processar tipo_id
            if tipo_id_str:
                try:
                    tipo_id = int(tipo_id_str)
                    tipo_certificado = CertificadosTipos.query.get(tipo_id)
                    if tipo_certificado:
                        tipo_nome = tipo_certificado.nome
                except:
                    pass
            
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
            
            # Processar dados adicionais dos campos dinâmicos
            dados_adicionais = {}
            if tipo_certificado:
                campos_config = tipo_certificado.get_dados_adicionais()
                if campos_config and 'campos' in campos_config:
                    for campo in campos_config['campos']:
                        campo_nome = campo.get('nome')
                        if campo_nome:
                            valor = request.form.get(f'campo_{campo_nome}')
                            if valor:
                                dados_adicionais[campo_nome] = valor
            
            # Se houver dados_adicionais_json (para compatibilidade), mesclar
            if dados_adicionais_json:
                try:
                    dados_json = json.loads(dados_adicionais_json)
                    dados_adicionais.update(dados_json)
                except:
                    pass
            
            # Criar o novo certificado
            novo_certificado = Certificados(
                nome=nome,
                tipo=tipo_nome,  # Mantido para compatibilidade
                tipo_id=tipo_id,
                data=data,
                data_vencimento=data_vencimento,
                dados_adicionais=json.dumps(dados_adicionais, ensure_ascii=False) if dados_adicionais else None
            )
            
            novo_certificado.save()
            
            # Processar uploads de documentos
            certificado_id = novo_certificado.id
            uploads_processados = 0
            
            # Processar todos os arquivos com nome documento_*
            for file_key in request.files.keys():
                if file_key.startswith('documento_'):
                    # Usar getlist para pegar todos os arquivos com o mesmo nome (quando multiple é usado)
                    files = request.files.getlist(file_key)
                    for file in files:
                        if file and file.filename:
                            try:
                                Upload(pai='Certificado', pai_id=certificado_id, tipo=5, filename=file.filename, mimetype=file.content_type or 'application/octet-stream', blob=file.read())
                            except Exception as e:
                                import traceback
                                traceback.print_exc()
                                print(f'Erro ao processar upload: {str(e)}')
                                db.session.rollback()
                                flash(f'Erro ao processar upload: {str(e)}', 'danger')
                                return redirect(url_for('certificado.index'))
            
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
    certificado = Certificados.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            tipo_id_str = request.form.get('tipo_id')
            tipo_id = None
            tipo_nome = None
            
            # Processar tipo_id
            if tipo_id_str:
                try:
                    tipo_id = int(tipo_id_str)
                    tipo_certificado = CertificadosTipos.query.get(tipo_id)
                    if tipo_certificado:
                        tipo_nome = tipo_certificado.nome
                except:
                    pass
            
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
            
            # Processar dados adicionais dos campos dinâmicos
            dados_adicionais = certificado.get_dados_adicionais() if certificado.dados_adicionais else {}
            tipo_certificado = None
            if tipo_id_str:
                try:
                    tipo_id = int(tipo_id_str)
                    tipo_certificado = CertificadosTipos.query.get(tipo_id)
                except:
                    pass
            
            if tipo_certificado:
                campos_config = tipo_certificado.get_dados_adicionais()
                if campos_config and 'campos' in campos_config:
                    for campo in campos_config['campos']:
                        campo_nome = campo.get('nome')
                        if campo_nome:
                            valor = request.form.get(f'campo_{campo_nome}')
                            if valor:
                                dados_adicionais[campo_nome] = valor
            
            # Se houver dados_adicionais_json (para compatibilidade), mesclar
            if dados_adicionais_json:
                try:
                    dados_json = json.loads(dados_adicionais_json)
                    dados_adicionais.update(dados_json)
                except:
                    pass
            
            # Atualizar o certificado
            certificado.nome = nome
            certificado.tipo = tipo_nome  # Mantido para compatibilidade
            certificado.tipo_id = tipo_id
            certificado.data = data
            certificado.data_vencimento = data_vencimento
            certificado.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False) if dados_adicionais else None
            certificado.atualizado_em = datetime.now()
            
            certificado.save()
            
            # Processar novos uploads de documentos
            uploads_processados = 0
            
            # Processar todos os arquivos com nome documento_*
            for file_key in request.files.keys():
                if file_key.startswith('documento_'):
                    # Usar getlist para pegar todos os arquivos com o mesmo nome (quando multiple é usado)
                    files = request.files.getlist(file_key)
                    for file in files:
                        if file and file.filename:
                            try:
                                Upload(pai='Certificado', pai_id=certificado.id, tipo=5, filename=file.filename, mimetype=file.content_type or 'application/octet-stream', blob=file.read())
                            except Exception as e:
                                import traceback
                                traceback.print_exc()
                                print(f'Erro ao processar upload: {str(e)}')
                                db.session.rollback()
                                flash(f'Erro ao processar upload: {str(e)}', 'danger')
                                return redirect(url_for('certificado.index'))
            
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
    tipos = CertificadosTipos.query.filter_by(ativo=True).order_by(CertificadosTipos.nome).all()
    
    return jsonify({
        'certificado': certificado.to_dict(),
        'documentos': [doc.to_dict() for doc in documentos] if documentos else [],
        'tipos': [tipo.to_dict() for tipo in tipos]
    })

@certificado_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um certificado (soft delete)
    """
    certificado = Certificados.query.get_or_404(id)
    
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
    certificado = Certificados.query.get_or_404(id)
    documentos = Upload.query.filter_by(pai='Certificado', pai_id=id, tipo=5).all()
    
    return jsonify({
        'certificado': certificado.to_dict(),
        'documentos': [doc.to_dict() for doc in documentos] if documentos else []
    })

@certificado_bp.route('/api/tipo/<int:tipo_id>/campos')
@login_required
def get_campos_tipo(tipo_id):
    """
    Retorna os campos configurados para um tipo de certificado
    """
    tipo = CertificadosTipos.query.get_or_404(tipo_id)
    return jsonify({
        'tipo': tipo.to_dict(),
        'campos': tipo.get_dados_adicionais().get('campos', []) if tipo.get_dados_adicionais() else []
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

# Rotas para Tipos de Certificados
@certificado_bp.route('/tipos')
@login_required
def tipos_index():
    """
    Lista todos os tipos de certificados
    """
    tipos = CertificadosTipos.query.filter_by(ativo=True).order_by(CertificadosTipos.nome).all()
    return render_template('cadastro_operacional/certificados/tipos_index.html', tipos=tipos)

@certificado_bp.route('/tipos/novo', methods=['GET', 'POST'])
@login_required
def tipos_novo():
    """
    Cria um novo tipo de certificado
    """
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            dados_adicionais_json = request.form.get('dados_adicionais')
            
            # Validação básica
            if not nome:
                flash('Por favor, informe o nome do tipo de certificado.', 'danger')
                return redirect(url_for('certificado.tipos_index'))
            
            # Verificar se já existe um tipo com o mesmo nome
            tipo_existente = CertificadosTipos.query.filter_by(nome=nome, ativo=True).first()
            if tipo_existente:
                flash('Já existe um tipo de certificado com este nome.', 'danger')
                return redirect(url_for('certificado.tipos_index'))
            
            # Processar dados adicionais
            dados_adicionais = None
            if dados_adicionais_json:
                try:
                    # Validar JSON
                    json.loads(dados_adicionais_json)
                    dados_adicionais = dados_adicionais_json
                except json.JSONDecodeError:
                    flash('Os dados adicionais devem estar em formato JSON válido.', 'danger')
                    return redirect(url_for('certificado.tipos_index'))
            
            # Criar o novo tipo de certificado
            novo_tipo = CertificadosTipos(
                nome=nome,
                dados_adicionais=dados_adicionais
            )
            
            novo_tipo.save()
            
            flash('Tipo de certificado criado com sucesso.', 'success')
            return redirect(url_for('certificado.tipos_index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar tipo de certificado: {str(e)}', 'danger')
            return redirect(url_for('certificado.tipos_index'))
    
    return redirect(url_for('certificado.tipos_index'))

@certificado_bp.route('/tipos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def tipos_editar(id):
    """
    Edita um tipo de certificado existente
    """
    tipo = CertificadosTipos.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            dados_adicionais_json = request.form.get('dados_adicionais')
            
            # Validação básica
            if not nome:
                flash('Por favor, informe o nome do tipo de certificado.', 'danger')
                return redirect(url_for('certificado.tipos_index'))
            
            # Verificar se já existe outro tipo com o mesmo nome
            tipo_existente = CertificadosTipos.query.filter(
                CertificadosTipos.nome == nome,
                CertificadosTipos.id != id,
                CertificadosTipos.ativo == True
            ).first()
            if tipo_existente:
                flash('Já existe um tipo de certificado com este nome.', 'danger')
                return redirect(url_for('certificado.tipos_index'))
            
            # Processar dados adicionais
            if dados_adicionais_json and dados_adicionais_json.strip():
                try:
                    # Validar JSON
                    json.loads(dados_adicionais_json)
                    tipo.dados_adicionais = dados_adicionais_json
                except json.JSONDecodeError:
                    flash('Os dados adicionais devem estar em formato JSON válido.', 'danger')
                    return redirect(url_for('certificado.tipos_index'))
            else:
                tipo.dados_adicionais = None
            
            # Atualizar o tipo de certificado
            tipo.nome = nome
            tipo.atualizado_em = datetime.now()
            
            tipo.save()
            
            flash('Tipo de certificado atualizado com sucesso.', 'success')
            return redirect(url_for('certificado.tipos_index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar tipo de certificado: {str(e)}', 'danger')
            return redirect(url_for('certificado.tipos_index'))
    
    return jsonify({
        'tipo': tipo.to_dict()
    })

@certificado_bp.route('/tipos/excluir/<int:id>', methods=['POST'])
@login_required
def tipos_excluir(id):
    """
    Exclui um tipo de certificado (soft delete)
    """
    tipo = CertificadosTipos.query.get_or_404(id)
    
    try:
        tipo.ativo = False
        tipo.save()
        flash('Tipo de certificado excluído com sucesso.', 'success')
    except Exception as e:
        flash(f'Erro ao excluir tipo de certificado: {str(e)}', 'danger')
    
    return redirect(url_for('certificado.tipos_index'))

@certificado_bp.route('/tipos/visualizar/<int:id>')
@login_required
def tipos_visualizar(id):
    """
    Visualiza os detalhes de um tipo de certificado
    """
    tipo = CertificadosTipos.query.get_or_404(id)
    
    return jsonify({
        'tipo': tipo.to_dict()
    })

@certificado_bp.route('/api/bobinas', methods=['GET'])
@login_required
def api_buscar_bobinas():
    """
    Busca números de bobina de certificados com tipo_id=1
    Os números estão em dados_adicionais no campo 'nbobina' separados por ';'
    Retorna também a data de fabricação (data do certificado) e o ID do certificado
    """
    try:
        termo = request.args.get('term', '').strip()
        
        # Buscar certificados com tipo_id=1 e ativo
        certificados = Certificados.query.filter_by(
            tipo_id=1,
            ativo=True
        ).all()
        
        # Dicionário para armazenar bobinas com seus dados
        # Chave: número da bobina, Valor: {certificado_id, data_fabricacao}
        bobinas_dict = {}
        
        for certificado in certificados:
            dados_adicionais = certificado.get_dados_adicionais()
            if dados_adicionais and 'nbobina' in dados_adicionais:
                nbobina_str = dados_adicionais.get('nbobina', '')
                if nbobina_str:
                    # Separar por ';' e limpar espaços
                    bobinas = [b.strip() for b in nbobina_str.split(';') if b.strip()]
                    # Data do certificado será usada como data de fabricação
                    data_fabricacao = dados_adicionais.get('dataFabricao', '')
                    ncertificado = dados_adicionais.get('ncertificado', '')
                    
                    for bobina_num in bobinas:
                        # Se a bobina já existe, manter a primeira ocorrência (ou pode escolher outra lógica)
                        if bobina_num not in bobinas_dict:
                            bobinas_dict[bobina_num] = {
                                'certificado_id': certificado.id,
                                'data_fabricacao': data_fabricacao,
                                'ncertificado': ncertificado
                            }
        
        # Converter para lista e ordenar
        bobinas_list = sorted(bobinas_dict.items(), key=lambda x: (len(x[0]), x[0]))
        
        # Filtrar por termo se fornecido
        if termo:
            bobinas_list = [(num, dados) for num, dados in bobinas_list if termo.lower() in num.lower()]
        
        # Formatar para Select2 com dados adicionais
        results = []
        for bobina_num, dados in bobinas_list:
            results.append({
                'id': bobina_num,
                'text': bobina_num,
                'certificado_id': dados['certificado_id'],
                'data_fabricacao': dados['data_fabricacao'],
                'ncertificado': dados['ncertificado']
            })
        
        return jsonify({
            'results': results
        })
    except Exception as e:
        return jsonify({
            'results': [],
            'error': str(e)
        }), 500