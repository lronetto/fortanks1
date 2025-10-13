from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models.database import db
from models.permissoes import Modulo, Permissao
from models.usuario import Usuario
from models.departamento import Departamento
from models.colaborador import Colaborador
from forms.permissoes_forms import ModuloForm, PermissaoForm
import logging

logger = logging.getLogger(__name__)

permissoes_bp = Blueprint('permissoes', __name__)

@permissoes_bp.route('/')
@login_required
def index():
    """Lista todos os módulos do sistema"""
    try:
        modulos = Modulo.query.filter_by(status='Ativo').order_by(Modulo.ordem, Modulo.nome).all()
        return render_template('permissoes/index.html', modulos=modulos)
    except Exception as e:
        logger.error(f"Erro ao listar módulos: {str(e)}")
        flash('Erro ao carregar módulos', 'error')
        return redirect(url_for('dashboard.index'))

@permissoes_bp.route('/modulos')
@login_required
def listar_modulos():
    """Lista todos os módulos para administração"""
    try:
        modulos = Modulo.query.order_by(Modulo.ordem, Modulo.nome).all()
        return render_template('permissoes/modulos.html', modulos=modulos)
    except Exception as e:
        logger.error(f"Erro ao listar módulos: {str(e)}")
        flash('Erro ao carregar módulos', 'error')
        return redirect(url_for('dashboard.index'))

@permissoes_bp.route('/modulos/novo', methods=['GET', 'POST'])
@login_required
def novo_modulo():
    """Cria um novo módulo"""
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem criar módulos.', 'error')
        return redirect(url_for('permissoes.listar_modulos'))
    
    form = ModuloForm()
    
    if form.validate_on_submit():
        try:
            modulo = Modulo(
                nome=form.nome.data,
                descricao=form.descricao.data,
                icone=form.icone.data,
                url=form.url.data,
                ordem=form.ordem.data or 0
            )
            modulo.save()
            flash('Módulo criado com sucesso!', 'success')
            return redirect(url_for('permissoes.listar_modulos'))
        except Exception as e:
            logger.error(f"Erro ao criar módulo: {str(e)}")
            flash('Erro ao criar módulo', 'error')
    
    return render_template('permissoes/modulo_form.html', form=form, titulo='Novo Módulo')

@permissoes_bp.route('/modulos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_modulo(id):
    """Edita um módulo existente"""
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem editar módulos.', 'error')
        return redirect(url_for('permissoes.listar_modulos'))
    
    modulo = Modulo.query.get_or_404(id)
    form = ModuloForm(obj=modulo)
    
    if form.validate_on_submit():
        try:
            modulo.nome = form.nome.data
            modulo.descricao = form.descricao.data
            modulo.icone = form.icone.data
            modulo.url = form.url.data
            modulo.ordem = form.ordem.data or 0
            modulo.save()
            flash('Módulo atualizado com sucesso!', 'success')
            return redirect(url_for('permissoes.listar_modulos'))
        except Exception as e:
            logger.error(f"Erro ao atualizar módulo: {str(e)}")
            flash('Erro ao atualizar módulo', 'error')
    
    return render_template('permissoes/modulo_form.html', form=form, titulo='Editar Módulo', modulo=modulo)

@permissoes_bp.route('/modulos/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_modulo(id):
    """Exclui um módulo"""
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem excluir módulos.', 'error')
        return redirect(url_for('permissoes.listar_modulos'))
    
    try:
        modulo = Modulo.query.get_or_404(id)
        modulo.status = 'Inativo'
        modulo.save()
        flash('Módulo excluído com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao excluir módulo: {str(e)}")
        flash('Erro ao excluir módulo', 'error')
    
    return redirect(url_for('permissoes.listar_modulos'))

@permissoes_bp.route('/permissoes')
@login_required
def listar_permissoes():
    """Lista todas as permissões do sistema"""
    try:
        permissoes = db.session.query(Permissao).join(Modulo).order_by(
            Modulo.nome, Permissao.tipo_permissao
        ).all()
        return render_template('permissoes/permissoes.html', permissoes=permissoes)
    except Exception as e:
        logger.error(f"Erro ao listar permissões: {str(e)}")
        flash('Erro ao carregar permissões', 'error')
        return redirect(url_for('dashboard.index'))

@permissoes_bp.route('/permissoes/novo', methods=['GET', 'POST'])
@login_required
def nova_permissao():
    """Cria uma nova permissão"""
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem criar permissões.', 'error')
        return redirect(url_for('permissoes.listar_permissoes'))
    
    form = PermissaoForm()
    
    # Carregar opções para os campos de seleção
    form.modulo_id.choices = [(m.id, m.nome) for m in Modulo.query.filter_by(status='Ativo').order_by(Modulo.nome).all()]
    form.usuario_id.choices = [(u.id, u.nome) for u in Usuario.query.order_by(Usuario.nome).all()]
    form.departamento_id.choices = [(d.id, d.nome) for d in Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()]
    
    if form.validate_on_submit():
        try:
            permissao = Permissao(
                modulo_id=form.modulo_id.data,
                usuario_id=form.usuario_id.data if form.usuario_id.data else None,
                departamento_id=form.departamento_id.data if form.departamento_id.data else None,
                cargo=form.cargo.data if form.cargo.data else None,
                tipo_permissao=form.tipo_permissao.data,
                pode_visualizar=form.pode_visualizar.data,
                pode_criar=form.pode_criar.data,
                pode_editar=form.pode_editar.data,
                pode_excluir=form.pode_excluir.data,
                pode_exportar=form.pode_exportar.data
            )
            permissao.save()
            flash('Permissão criada com sucesso!', 'success')
            return redirect(url_for('permissoes.listar_permissoes'))
        except Exception as e:
            logger.error(f"Erro ao criar permissão: {str(e)}")
            flash('Erro ao criar permissão', 'error')
    
    return render_template('permissoes/permissao_form.html', form=form, titulo='Nova Permissão')

@permissoes_bp.route('/permissoes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_permissao(id):
    """Edita uma permissão existente"""
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem editar permissões.', 'error')
        return redirect(url_for('permissoes.listar_permissoes'))
    
    permissao = Permissao.query.get_or_404(id)
    form = PermissaoForm(obj=permissao)
    
    # Carregar opções para os campos de seleção
    form.modulo_id.choices = [(m.id, m.nome) for m in Modulo.query.filter_by(status='Ativo').order_by(Modulo.nome).all()]
    form.usuario_id.choices = [(u.id, u.nome) for u in Usuario.query.order_by(Usuario.nome).all()]
    form.departamento_id.choices = [(d.id, d.nome) for d in Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()]
    
    if form.validate_on_submit():
        try:
            permissao.modulo_id = form.modulo_id.data
            permissao.usuario_id = form.usuario_id.data if form.usuario_id.data else None
            permissao.departamento_id = form.departamento_id.data if form.departamento_id.data else None
            permissao.cargo = form.cargo.data if form.cargo.data else None
            permissao.tipo_permissao = form.tipo_permissao.data
            permissao.pode_visualizar = form.pode_visualizar.data
            permissao.pode_criar = form.pode_criar.data
            permissao.pode_editar = form.pode_editar.data
            permissao.pode_excluir = form.pode_excluir.data
            permissao.pode_exportar = form.pode_exportar.data
            permissao.save()
            flash('Permissão atualizada com sucesso!', 'success')
            return redirect(url_for('permissoes.listar_permissoes'))
        except Exception as e:
            logger.error(f"Erro ao atualizar permissão: {str(e)}")
            flash('Erro ao atualizar permissão', 'error')
    
    return render_template('permissoes/permissao_form.html', form=form, titulo='Editar Permissão', permissao=permissao)

@permissoes_bp.route('/permissoes/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_permissao(id):
    """Exclui uma permissão"""
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem excluir permissões.', 'error')
        return redirect(url_for('permissoes.listar_permissoes'))
    
    try:
        permissao = Permissao.query.get_or_404(id)
        permissao.status = 'Inativo'
        permissao.save()
        flash('Permissão excluída com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao excluir permissão: {str(e)}")
        flash('Erro ao excluir permissão', 'error')
    
    return redirect(url_for('permissoes.listar_permissoes'))

@permissoes_bp.route('/permissoes/usuario/<int:usuario_id>')
@login_required
def permissoes_usuario(usuario_id):
    """Lista permissões de um usuário específico"""
    try:
        usuario = Usuario.query.get_or_404(usuario_id)
        permissoes = Permissao.query.filter_by(usuario_id=usuario_id, status='Ativo').all()
        return render_template('permissoes/permissoes_usuario.html', usuario=usuario, permissoes=permissoes)
    except Exception as e:
        logger.error(f"Erro ao listar permissões do usuário: {str(e)}")
        flash('Erro ao carregar permissões do usuário', 'error')
        return redirect(url_for('permissoes.listar_permissoes'))

@permissoes_bp.route('/permissoes/departamento/<int:departamento_id>')
@login_required
def permissoes_departamento(departamento_id):
    """Lista permissões de um departamento específico"""
    try:
        departamento = Departamento.query.get_or_404(departamento_id)
        permissoes = Permissao.query.filter_by(departamento_id=departamento_id, status='Ativo').all()
        return render_template('permissoes/permissoes_departamento.html', departamento=departamento, permissoes=permissoes)
    except Exception as e:
        logger.error(f"Erro ao listar permissões do departamento: {str(e)}")
        flash('Erro ao carregar permissões do departamento', 'error')
        return redirect(url_for('permissoes.listar_permissoes'))

@permissoes_bp.route('/api/verificar-permissao')
@login_required
def api_verificar_permissao():
    """API para verificar permissão de um usuário em um módulo"""
    try:
        modulo_nome = request.args.get('modulo')
        acao = request.args.get('acao', 'visualizar')
        
        if not modulo_nome:
            return jsonify({'error': 'Módulo não especificado'}), 400
        
        tem_permissao = Permissao.verificar_permissao_completa(current_user, modulo_nome, acao)
        
        return jsonify({
            'tem_permissao': tem_permissao,
            'modulo': modulo_nome,
            'acao': acao
        })
    except Exception as e:
        logger.error(f"Erro ao verificar permissão: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@permissoes_bp.route('/api/modulos-usuario')
@login_required
def api_modulos_usuario():
    """API para retornar módulos que o usuário tem permissão de visualizar"""
    try:
        modulos_permitidos = []
        modulos = Modulo.query.filter_by(status='Ativo').order_by(Modulo.ordem, Modulo.nome).all()
        
        for modulo in modulos:
            if Permissao.verificar_permissao_completa(current_user, modulo.nome, 'visualizar'):
                modulos_permitidos.append(modulo.to_dict())
        
        return jsonify(modulos_permitidos)
    except Exception as e:
        logger.error(f"Erro ao buscar módulos do usuário: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

