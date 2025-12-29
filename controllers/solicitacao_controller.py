from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime
from models.database import db
from models.solicitacao import Solicitacoes, SolicitacoesItens
from models.material import Materiais
from models.centro_custo import CentroCusto
from models.usuario import Usuario
from models.colaborador import Colaborador
from utils.email_utils import enviar_email

# Importar WeasyPrint (requer instalação: pip install WeasyPrint)
# e instalação de dependências de sistema (Pango, Cairo, etc.)
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    # Logar um aviso se WeasyPrint não estiver disponível
    # import logging
    # logging.warning("WeasyPrint não encontrado. A funcionalidade de enviar PDF por e-mail estará desabilitada.")

solicitacao_bp = Blueprint('solicitacao', __name__, url_prefix='/solicitacoes')

@solicitacao_bp.route('/')
@login_required
def index():
    """Lista todas as solicitações"""
    # Se for gerente ou superior, mostra todas as solicitações
    if current_user.is_gerente_ou_superior:
        solicitacoes = Solicitacoes.query.order_by(Solicitacoes.data_solicitacao.desc()).all()
    else:
        # Se não, mostra apenas as próprias solicitações
        solicitacoes = Solicitacoes.query.filter_by(solicitante_id=current_user.id).order_by(Solicitacoes.data_solicitacao.desc()).all()
    
    # Buscar dados para o formulário no modal
    materiais = Materiais.query.order_by(Materiais.nome).all()
    centros_custo = CentroCusto.query.order_by(CentroCusto.nome).all()
    
    return render_template('solicitacoes/index.html', 
                          solicitacoes=solicitacoes,
                          materiais=materiais,
                          centros_custo=centros_custo)

@solicitacao_bp.route('/novo', methods=['POST'])
@login_required
def novo():
    """Cria uma nova solicitação"""
    try:
        # Criar nova solicitação sem número (será definido após obter o ID)
        solicitacao = Solicitacoes(
            data_necessidade=datetime.strptime(request.form.get('nova_data_necessidade'), '%Y-%m-%d').date(),
            centro_custo_id=request.form.get('nova_centro_custo_id'),
            solicitante_id=current_user.id,
            observacoes=request.form.get('nova_observacoes')
        )
        
        # Adicionar itens
        materiais = request.form.getlist('nova_material_id[]')
        quantidades = request.form.getlist('nova_quantidade[]')
        unidades = request.form.getlist('nova_unidade[]')
        observacoes = request.form.getlist('nova_observacoes_item[]')
        
        for i in range(len(materiais)):
            if materiais[i] and quantidades[i]:
                item = SolicitacoesItens(
                    material_id=materiais[i],
                    quantidade=quantidades[i],
                    unidade=unidades[i],
                    observacoes=observacoes[i]
                )
                solicitacao.itens.append(item)
        
        # Salvar para obter o ID
        db.session.add(solicitacao)
        db.session.flush()
        
        # Definir o número da solicitação igual ao ID
        solicitacao.numero = str(solicitacao.id)
        
        # Concluir a transação
        db.session.commit()
        
        flash('Solicitação criada com sucesso!', 'success')
        return redirect(url_for('solicitacao.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao criar solicitação: {str(e)}', 'danger')
        return redirect(url_for('solicitacao.index'))

@solicitacao_bp.route('/<int:id>/aprovar', methods=['POST'])
@login_required

def aprovar(id):
    """Aprova uma solicitação"""
    if not current_user.is_gerente_ou_superior:
        flash('Você não tem permissão para aprovar solicitações.', 'danger')
        return redirect(url_for('solicitacao.index'))
    
    solicitacao = Solicitacoes.query.get_or_404(id)
    solicitacao.aprovar(current_user.id)
    flash('Solicitação aprovada com sucesso!', 'success')
    return redirect(url_for('solicitacao.index'))

@solicitacao_bp.route('/<int:id>/rejeitar', methods=['POST'])
@login_required

def rejeitar(id):
    """Rejeita uma solicitação"""
    if not current_user.is_gerente_ou_superior:
        flash('Você não tem permissão para rejeitar solicitações.', 'danger')
        return redirect(url_for('solicitacao.index'))
    
    solicitacao = Solicitacoes.query.get_or_404(id)
    solicitacao.rejeitar(current_user.id)
    flash('Solicitação rejeitada com sucesso!', 'success')
    return redirect(url_for('solicitacao.index'))

@solicitacao_bp.route('/<int:id>/cancelar', methods=['POST'])
@login_required

def cancelar(id):
    """Cancela uma solicitação"""
    solicitacao = Solicitacoes.query.get_or_404(id)
    
    # Verificar permissão
    if not current_user.is_gerente_ou_superior and solicitacao.solicitante_id != current_user.id:
        flash('Você não tem permissão para cancelar esta solicitação.', 'danger')
        return redirect(url_for('solicitacao.index'))
    
    solicitacao.cancelar()
    flash('Solicitação cancelada com sucesso!', 'success')
    return redirect(url_for('solicitacao.index'))

@solicitacao_bp.route('/<int:id>/editar', methods=['POST'])
@login_required
def editar(id):
    """Edita uma solicitação pendente"""
    solicitacao = Solicitacoes.query.get_or_404(id)
    
    # Verificar permissão e status
    if not current_user.is_gerente_ou_superior and solicitacao.solicitante_id != current_user.id:
        flash('Você não tem permissão para editar esta solicitação.', 'danger')
        return redirect(url_for('solicitacao.index'))
    
    if solicitacao.status != 'Pendente':
        flash('Apenas solicitações pendentes podem ser editadas.', 'warning')
        return redirect(url_for('solicitacao.index'))
    
    try:
        print(request.form)
        # Atualizar dados da solicitação
        solicitacao.data_necessidade = datetime.strptime(request.form.get('editar_data_necessidade'), '%Y-%m-%d').date()
        solicitacao.centro_custo_id = request.form.get('editar_centro_custo_id')
        solicitacao.observacoes = request.form.get('editar_observacoes')
        
        # Remover todos os itens atuais
        for item in solicitacao.itens:
            db.session.delete(item)
        
        # Adicionar novos itens
        materiais = request.form.getlist('editar_material_id[]')
        quantidades = request.form.getlist('editar_quantidade[]')
        unidades = request.form.getlist('editar_unidade[]')
        observacoes = request.form.getlist('editar_observacoes_item[]')
        
        for i in range(len(materiais)):
            if materiais[i] and quantidades[i]:
                item = SolicitacoesItens(
                    solicitacao_id=solicitacao.id,
                    material_id=materiais[i],
                    quantidade=quantidades[i],
                    unidade=unidades[i],
                    observacoes=observacoes[i]
                )
                db.session.add(item)
        
        db.session.commit()
        flash('Solicitação atualizada com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar solicitação: {str(e)}', 'danger')
    
    return redirect(url_for('solicitacao.index'))

# API endpoints
@solicitacao_bp.route('/api/materiais')
@login_required
def api_materiais():
    """API para retornar materiais em formato JSON"""
    query = Materiais.query
    
    # Filtro por código ou nome
    search = request.args.get('q')
    if search:
        query = query.filter(
            db.or_(
                Materiais.codigo.like(f'%{search}%'),
                Materiais.nome.like(f'%{search}%')
            )
        )
    
    materiais = query.order_by(Materiais.nome).limit(100).all()
    
    result = []
    for m in materiais:
        result.append({
            'id': m.id,
            'codigo': m.codigo,
            'nome': m.nome,
            'unidade': m.unidade
        })
    
    return jsonify(result)

@solicitacao_bp.route('/<int:id>/enviar_email_aprovacao', methods=['POST'])
@login_required
def enviar_email_aprovacao(id):
    """Envia um e-mail de notificação de aprovação para o solicitante."""
    # Verificar permissão
    if not current_user.is_gerente_ou_superior:
        flash('Você não tem permissão para executar esta ação.', 'danger')
        return redirect(url_for('solicitacao.index'))

    solicitacao = Solicitacoes.query.get_or_404(id)

    # Verificar se a solicitação está aprovada
    if solicitacao.status != 'Aprovada':
        flash('Esta solicitação não está aprovada.', 'warning')
        return redirect(url_for('solicitacao.index'))

    # Verificar se o solicitante tem e-mail cadastrado
    if not solicitacao.solicitante or not solicitacao.solicitante.email:
        flash(f'O solicitante {solicitacao.solicitante.nome} não possui um e-mail cadastrado.', 'warning')
        return redirect(url_for('solicitacao.index'))

    try:
        assunto = f"Solicitação #{solicitacao.id} Aprovada"
        destinatario = solicitacao.solicitante.email
        
        # Renderizar um template de email ou criar o corpo do email aqui
        # Idealmente, usar render_template para um HTML de email
        corpo_email = f"""
        Olá {solicitacao.solicitante.nome},

        Sua solicitação de material #{solicitacao.id} foi aprovada.

        Data da Solicitação: {solicitacao.data_solicitacao.strftime('%d/%m/%Y')}
        Data da Necessidade: {solicitacao.data_necessidade.strftime('%d/%m/%Y')}
        Centro de Custo: {solicitacao.centro_custo.nome}

        Atenciosamente,
        Equipe Fortanks
        """
        
        # Chamar a função de envio de email real
        sucesso_envio = enviar_email(
            destinatario=destinatario, 
            assunto=assunto, 
            corpo_html=corpo_email # Passar como HTML, a função cuidará do texto puro
        )

        if sucesso_envio:
            flash('E-mail de aprovação enviado com sucesso!', 'success')
        else:
            flash('Erro ao enviar e-mail de aprovação. Verifique os logs.', 'danger')

    except Exception as e:
        # Logar o erro também seria bom aqui
        current_app.logger.error(f'Erro inesperado na rota enviar_email_aprovacao: {e}')
        flash(f'Erro ao tentar enviar e-mail: {str(e)}', 'danger')

    return redirect(url_for('solicitacao.index')) 

@solicitacao_bp.route('/<int:id>/pdf', methods=['GET'])
@login_required
def pdf(id):
    """Visualiza uma solicitação"""
    solicitacao = Solicitacoes.query.options(db.joinedload(Solicitacoes.solicitante), 
                                            db.joinedload(Solicitacoes.centro_custo),
                                            db.joinedload(Solicitacoes.aprovador),
                                            db.joinedload(Solicitacoes.itens).joinedload(SolicitacoesItens.material)
                                            ).get_or_404(id)
    try:
        # Renderizar o template HTML para o PDF
        html_string = render_template('solicitacoes/pdf_template.html', solicitacao=solicitacao)
        
        # Gerar PDF usando WeasyPrint
        pdf_bytes = HTML(string=html_string).write_pdf()
        nome_arquivo_pdf = f'solicitacao_{solicitacao.id}.pdf'
        
    except Exception as e:
        current_app.logger.error(f"Erro ao gerar PDF para solicitação {id}: {e}")
        flash('Erro interno ao gerar o PDF da solicitação.', 'danger')
    return render_template('solicitacoes/pdf_template.html', solicitacao=solicitacao)

@solicitacao_bp.route('/<int:id>/enviar_pdf_email', methods=['POST', 'GET'])
@login_required
def enviar_pdf_email(id):
    """Gera um PDF da solicitação e envia por e-mail para destinatários pré-definidos e o solicitante."""
    if not WEASYPRINT_AVAILABLE:
        flash('A funcionalidade de envio de PDF por e-mail está temporariamente indisponível (dependência ausente). ', 'warning')
        return redirect(url_for('solicitacao.index'))

    # Verificar permissão (ajuste conforme necessário)
    if not current_user.is_gerente_ou_superior:
        flash('Você não tem permissão para executar esta ação.', 'danger')
        return redirect(url_for('solicitacao.index'))

    solicitacao = Solicitacoes.query.options(db.joinedload(Solicitacoes.solicitante), 
                                            db.joinedload(Solicitacoes.centro_custo),
                                            db.joinedload(Solicitacoes.aprovador),
                                            db.joinedload(Solicitacoes.itens).joinedload(SolicitacoesItens.material)
                                            ).get_or_404(id)

    # --- Obter Destinatários ---
    destinatarios = set() # Usar set para evitar duplicatas
    
    # Adicionar solicitante (se tiver email)
    if solicitacao.solicitante and solicitacao.solicitante.email:
        destinatarios.add(solicitacao.solicitante.email)
    else:
        flash(f'Aviso: O solicitante {solicitacao.solicitante.nome} não possui e-mail cadastrado e não receberá a cópia.', 'info')
    lista = request.form.get('lista_destinatarios', current_app.config.get('EMAILS_PDF_SOLICITACAO', ''))
    if lista:
        lista_destinatarios = [email.strip() for email in lista.split(',') if email.strip()]
        destinatarios.update(lista_destinatarios)
    else:
        flash('Nenhum destinatário válido encontrado para enviar o e-mail.', 'danger')
        return redirect(url_for('solicitacao.index'))
    
        # Decida se quer impedir o envio ou apenas avisar
        # flash('Nenhum e-mail pré-definido configurado para envio.', 'warning') 
        
    if not destinatarios:
         flash('Nenhum destinatário válido encontrado para enviar o e-mail.', 'danger')
         return redirect(url_for('solicitacao.index'))
         
    # Converter para lista para a função de email
    lista_destinatarios = list(destinatarios)
    
    # --- Gerar PDF --- 
    try:
        # Renderizar o template HTML para o PDF
        html_string = render_template('solicitacoes/pdf_template.html', solicitacao=solicitacao)
        
        # Gerar PDF usando WeasyPrint
        pdf_bytes = HTML(string=html_string).write_pdf()
        nome_arquivo_pdf = f'solicitacao_{solicitacao.id}.pdf'
        
    except Exception as e:
        current_app.logger.error(f"Erro ao gerar PDF para solicitação {id}: {e}")
        flash('Erro interno ao gerar o PDF da solicitação.', 'danger')
        return redirect(url_for('solicitacao.index'))
        
    # --- Preparar e Enviar Email ---    
    try:
        assunto = f"Solicitação de Material #{solicitacao.id} - PDF Anexo"
        mensagem_adicional = request.form.get('mensagem_adicional', '')
        
        # Corpo do e-mail (pode ser simples ou usar outro template)
        corpo_html = f"""
        <p>Prezados,</p>
        <p>Segue em anexo o PDF da solicitação de material #{solicitacao.id}.</p>
        """
        if mensagem_adicional:
            corpo_html += f"<p><strong>Mensagem adicional:</strong><br>{mensagem_adicional}</p>"
        corpo_html += "<p>Atenciosamente,<br>Sistema Fortanks</p>"
        
        # Definir o anexo
        anexos = [(nome_arquivo_pdf, 'application/pdf', pdf_bytes)]
        
        # Chamar a função de envio
        sucesso_envio = enviar_email(
            destinatario=lista_destinatarios,
            assunto=assunto,
            corpo_html=corpo_html,
            anexos=anexos
        )
        
        if sucesso_envio:
            flash(f'PDF da solicitação #{id} enviado por e-mail para: {", ".join(lista_destinatarios)}', 'success')
        else:
            flash('Erro ao enviar o e-mail com o PDF. Verifique os logs.', 'danger')
            
    except Exception as e:
        current_app.logger.error(f'Erro inesperado ao enviar PDF por e-mail para solicitação {id}: {e}')
        flash(f'Erro interno ao tentar enviar o e-mail: {str(e)}', 'danger')

    return redirect(url_for('solicitacao.index')) 

@solicitacao_bp.route('/<int:id>/dados', methods=['GET'])
@login_required
def get_dados_solicitacao(id):
    """Retorna os dados de uma solicitação em formato JSON"""
    solicitacao = Solicitacoes.query.options(
        db.joinedload(Solicitacoes.centro_custo),
        db.joinedload(Solicitacoes.aprovador).joinedload(Usuario.colaborador),
        db.joinedload(Solicitacoes.solicitante).joinedload(Usuario.colaborador),
        db.joinedload(Solicitacoes.itens).joinedload(SolicitacoesItens.material).joinedload(Materiais.unidade_obj)
    ).get_or_404(id)

    # Verificar permissão
    if not current_user.is_gerente_ou_superior and solicitacao.solicitante_id != current_user.id:
        return jsonify({'error': 'Sem permissão'}), 403

    # Preparar dados da solicitação
    dados = {
        'id': solicitacao.id,
        'data_necessidade': solicitacao.data_necessidade.strftime('%Y-%m-%d'),
        'centro_custo_id': solicitacao.centro_custo_id,
        'centro_custo_nome': solicitacao.centro_custo.nome,
        'centro_custo_codigo': solicitacao.centro_custo.codigo,
        'aprovador_id': solicitacao.aprovador_id,
        'aprovador_nome': solicitacao.aprovador.colaborador.nome if solicitacao.aprovador and solicitacao.aprovador.colaborador else '',
        'solicitante_id': solicitacao.solicitante_id,
        'solicitante_nome': solicitacao.solicitante.colaborador.nome if solicitacao.solicitante and solicitacao.solicitante.colaborador else '',
        'status': solicitacao.status,
        'observacoes': solicitacao.observacoes,
        'itens': []
    }

    # Adicionar itens
    for item in solicitacao.itens:
        dados['itens'].append({
            'id': item.id,
            'material_id': item.material_id,
            'material': {
                'nome': item.material.nome,
                'codigo': item.material.codigo if item.material.codigo else '',
                'unidade_obj': {
                    'nome': item.material.unidade_obj.nome if item.material.unidade_obj else ''
                }
            } if item.material else {},
            'quantidade': item.quantidade,
            'unidade_id': item.material.unidade_id if item.material else None,
            'observacoes': item.observacoes
        })

    return jsonify(dados) 

@solicitacao_bp.route('/<int:id>/emails_predefinidos', methods=['GET'])
@login_required
def get_emails_predefinidos(id):
    """Retorna os e-mails pré-definidos para uma solicitação"""
    solicitacao = Solicitacoes.query.get_or_404(id)
    emails_predefinidos = current_app.config.get('EMAILS_PDF_SOLICITACAO', '')
    return jsonify({'email_solicitante': solicitacao.solicitante.email if solicitacao.solicitante else '', 'emails_predefinidos': emails_predefinidos})