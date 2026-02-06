from flask import render_template, redirect, url_for, flash, request, jsonify
import logging

from controllers.admin import admin_bp, PERMISSOES_DISPONIVEL
from models.database import db
from models.usuario import Usuario
from models.departamento import Departamento
from models.cargo import Cargo

logger = logging.getLogger(__name__)

# Importar modelos de permissões
try:
    from models.permissoes import Modulo, Permissao
except ImportError:
    Modulo = None
    Permissao = None

@admin_bp.route('/permissoes')
def permissoes_index():
    """
    Página principal de gerenciamento de permissões
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível. Execute o script SQL primeiro.', 'warning')
        return redirect(url_for('admin.index'))
    
    try:
        # Estatísticas
        total_modulos = Modulo.query.count()
        modulos_ativos = Modulo.query.filter_by(status='Ativo').count()
        total_permissoes = Permissao.query.count()
        permissoes_ativas = Permissao.query.filter_by(status='Ativo').count()
        
        # Módulos recentes
        modulos_recentes = Modulo.query.order_by(Modulo.criado_em.desc()).limit(5).all()
        
        # Permissões recentes
        permissoes_recentes = db.session.query(Permissao).join(Modulo).order_by(
            Permissao.criado_em.desc()
        ).limit(5).all()
        
        # Dados para os modais
        modulos = Modulo.query.filter_by(status='Ativo').order_by(Modulo.nome).all()
        usuarios = Usuario.query.order_by(Usuario.nome).all()
        departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
        cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
        
        return render_template('admin/permissoes/index.html',
                            total_modulos=total_modulos,
                            modulos_ativos=modulos_ativos,
                            total_permissoes=total_permissoes,
                            permissoes_ativas=permissoes_ativas,
                            modulos_recentes=modulos_recentes,
                            permissoes_recentes=permissoes_recentes,
                            modulos=modulos,
                            usuarios=usuarios,
                            departamentos=departamentos,
                            cargos=cargos)
    except Exception as e:
        logger.error(f"Erro ao carregar página de permissões: {str(e)}")
        flash('Erro ao carregar página de permissões', 'error')
        return redirect(url_for('admin.index'))

@admin_bp.route('/permissoes/modulos')
def permissoes_modulos():
    """
    Lista todos os módulos do sistema
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível.', 'warning')
        return redirect(url_for('admin.index'))
    
    try:
        modulos = Modulo.query.order_by(Modulo.ordem, Modulo.nome).all()
        return render_template('admin/permissoes/modulos.html', 
                             modulos=modulos)
    except Exception as e:
        logger.error(f"Erro ao listar módulos: {str(e)}")
        flash('Erro ao carregar módulos', 'error')
        return redirect(url_for('admin.permissoes_index'))

@admin_bp.route('/permissoes/modulos/novo', methods=['GET', 'POST'])
def permissoes_modulo_novo():
    """
    Cria um novo módulo
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível.', 'warning')
        return redirect(url_for('admin.permissoes_modulos'))
    
    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').strip()
            if not nome:
                flash('Nome do módulo é obrigatório', 'error')
                return render_template('admin/permissoes/modulo_form.html', titulo='Novo Módulo')
            
            # Verificar se já existe módulo com esse nome
            if Modulo.query.filter_by(nome=nome).first():
                flash('Já existe um módulo com esse nome', 'error')
                return render_template('admin/permissoes/modulo_form.html', titulo='Novo Módulo')
            
            modulo = Modulo(
                nome=nome,
                descricao=request.form.get('descricao', '').strip() or None,
                icone=request.form.get('icone', '').strip() or None,
                url=request.form.get('url', '').strip() or None,
                ordem=int(request.form.get('ordem', 0) or 0)
            )
            modulo.save()
            flash('Módulo criado com sucesso!', 'success')
            
            # Se for requisição AJAX, retornar JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': 'Módulo criado com sucesso!'})
            
            return redirect(url_for('admin.permissoes_modulos'))
        except ValueError as e:
            logger.error(f"Erro de validação ao criar módulo: {str(e)}")
            flash('Erro de validação: ordem deve ser um número', 'error')
        except Exception as e:
            logger.error(f"Erro ao criar módulo: {str(e)}")
            flash(f'Erro ao criar módulo: {str(e)}', 'error')
    
    return render_template('admin/permissoes/modulo_form.html', titulo='Novo Módulo')

@admin_bp.route('/permissoes/modulos/<int:id>/editar', methods=['GET', 'POST'])
def permissoes_modulo_editar(id):
    """
    Edita um módulo existente
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível.', 'warning')
        return redirect(url_for('admin.permissoes_modulos'))
    
    try:
        modulo = Modulo.query.get_or_404(id)
        
        if request.method == 'POST':
            try:
                nome = request.form.get('nome', '').strip()
                if not nome:
                    flash('Nome do módulo é obrigatório', 'error')
                    return render_template('admin/permissoes/modulo_form.html', titulo='Editar Módulo', modulo=modulo)
                
                # Verificar se já existe outro módulo com esse nome
                outro_modulo = Modulo.query.filter_by(nome=nome).first()
                if outro_modulo and outro_modulo.id != modulo.id:
                    flash('Já existe um módulo com esse nome', 'error')
                    return render_template('admin/permissoes/modulo_form.html', titulo='Editar Módulo', modulo=modulo)
                
                modulo.nome = nome
                modulo.descricao = request.form.get('descricao', '').strip() or None
                modulo.icone = request.form.get('icone', '').strip() or None
                modulo.url = request.form.get('url', '').strip() or None
                modulo.ordem = int(request.form.get('ordem', 0) or 0)
                modulo.save()
                flash('Módulo atualizado com sucesso!', 'success')
                
                # Se for requisição AJAX, retornar JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': True, 'message': 'Módulo atualizado com sucesso!'})
                
                return redirect(url_for('admin.permissoes_modulos'))
            except ValueError as e:
                logger.error(f"Erro de validação ao atualizar módulo: {str(e)}")
                flash('Erro de validação: ordem deve ser um número', 'error')
            except Exception as e:
                logger.error(f"Erro ao atualizar módulo: {str(e)}")
                flash(f'Erro ao atualizar módulo: {str(e)}', 'error')
        
        return render_template('admin/permissoes/modulo_form.html', titulo='Editar Módulo', modulo=modulo)
    except Exception as e:
        logger.error(f"Erro ao editar módulo: {str(e)}")
        flash('Módulo não encontrado', 'error')
        return redirect(url_for('admin.permissoes_modulos'))

@admin_bp.route('/permissoes/modulos/<int:id>/excluir', methods=['POST'])
def permissoes_modulo_excluir(id):
    """
    Exclui (desativa) um módulo
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível.', 'warning')
        return redirect(url_for('admin.permissoes_modulos'))
    
    try:
        modulo = Modulo.query.get_or_404(id)
        modulo.status = 'Inativo'
        modulo.save()
        flash('Módulo excluído com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao excluir módulo: {str(e)}")
        flash('Erro ao excluir módulo', 'error')
    
    return redirect(url_for('admin.permissoes_modulos'))

@admin_bp.route('/permissoes/permissoes')
def permissoes_listar():
    """
    Lista todas as permissões do sistema
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível.', 'warning')
        return redirect(url_for('admin.index'))
    
    try:
        # Filtros
        tipo_filtro = request.args.get('tipo', '')
        modulo_filtro = request.args.get('modulo', '', type=int)
        
        query = db.session.query(Permissao).join(Modulo)
        
        if tipo_filtro:
            query = query.filter(Permissao.tipo_permissao == tipo_filtro)
        
        if modulo_filtro:
            query = query.filter(Permissao.modulo_id == modulo_filtro)
        
        permissoes = query.order_by(Modulo.nome, Permissao.tipo_permissao).all()
        modulos = Modulo.query.filter_by(status='Ativo').order_by(Modulo.nome).all()
        usuarios = Usuario.query.order_by(Usuario.nome).all()
        departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
        cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
        
        return render_template('admin/permissoes/permissoes.html', 
                             permissoes=permissoes, 
                             modulos=modulos,
                             usuarios=usuarios,
                             departamentos=departamentos,
                             cargos=cargos,
                             tipo_filtro=tipo_filtro,
                             modulo_filtro=modulo_filtro)
    except Exception as e:
        logger.error(f"Erro ao listar permissões: {str(e)}")
        flash('Erro ao carregar permissões', 'error')
        return redirect(url_for('admin.permissoes_index'))

@admin_bp.route('/permissoes/permissoes/novo', methods=['GET', 'POST'])
def permissoes_nova():
    """
    Cria uma nova permissão
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível.', 'warning')
        return redirect(url_for('admin.permissoes_listar'))
    
    # Carregar dados para os selects
    modulos = Modulo.query.filter_by(status='Ativo').order_by(Modulo.nome).all()
    usuarios = Usuario.query.order_by(Usuario.nome).all()
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
    
    if request.method == 'POST':
        try:
            modulo_id = request.form.get('modulo_id', type=int)
            tipo_permissao = request.form.get('tipo_permissao', '').strip()
            
            if not modulo_id:
                flash('Módulo é obrigatório', 'error')
                return render_template('admin/permissoes/permissao_form.html', 
                                     titulo='Nova Permissão',
                                     modulos=modulos,
                                     usuarios=usuarios,
                                     departamentos=departamentos,
                                     cargos=cargos)
            
            if not tipo_permissao:
                flash('Tipo de permissão é obrigatório', 'error')
                return render_template('admin/permissoes/permissao_form.html', 
                                     titulo='Nova Permissão',
                                     modulos=modulos,
                                     usuarios=usuarios,
                                     departamentos=departamentos,
                                     cargos=cargos)
            
            # Obter permissões específicas
            pode_visualizar = bool(request.form.get('pode_visualizar'))
            pode_criar = bool(request.form.get('pode_criar'))
            pode_editar = bool(request.form.get('pode_editar'))
            pode_excluir = bool(request.form.get('pode_excluir'))
            pode_exportar = bool(request.form.get('pode_exportar'))
            
            # Processar múltiplas seleções e criar permissões
            permissoes_criadas = 0
            
            if tipo_permissao == 'usuario':
                usuario_ids = request.form.getlist('usuario_id')
                usuario_ids = [int(id) for id in usuario_ids if id]
                if not usuario_ids:
                    flash('Selecione pelo menos um usuário', 'error')
                    return render_template('admin/permissoes/permissao_form.html', 
                                         titulo='Nova Permissão',
                                         modulos=modulos,
                                         usuarios=usuarios,
                                         departamentos=departamentos,
                                         cargos=cargos)
                
                # Criar uma permissão para cada usuário selecionado
                for usuario_id in usuario_ids:
                    # Verificar se já existe permissão para evitar duplicatas
                    existe = Permissao.query.filter_by(
                        modulo_id=modulo_id,
                        usuario_id=usuario_id,
                        tipo_permissao='usuario',
                        status='Ativo'
                    ).first()
                    
                    if not existe:
                        permissao = Permissao(
                            modulo_id=modulo_id,
                            usuario_id=usuario_id,
                            departamento_id=None,
                            cargo_id=None,
                            tipo_permissao=tipo_permissao,
                            pode_visualizar=pode_visualizar,
                            pode_criar=pode_criar,
                            pode_editar=pode_editar,
                            pode_excluir=pode_excluir,
                            pode_exportar=pode_exportar
                        )
                        permissao.save()
                        permissoes_criadas += 1
                
            elif tipo_permissao == 'departamento':
                departamento_ids = request.form.getlist('departamento_id')
                departamento_ids = [int(id) for id in departamento_ids if id]
                if not departamento_ids:
                    flash('Selecione pelo menos um departamento', 'error')
                    return render_template('admin/permissoes/permissao_form.html', 
                                         titulo='Nova Permissão',
                                         modulos=modulos,
                                         usuarios=usuarios,
                                         departamentos=departamentos,
                                         cargos=cargos)
                
                # Criar uma permissão para cada departamento selecionado
                for departamento_id in departamento_ids:
                    # Verificar se já existe permissão para evitar duplicatas
                    existe = Permissao.query.filter_by(
                        modulo_id=modulo_id,
                        departamento_id=departamento_id,
                        tipo_permissao='departamento',
                        status='Ativo'
                    ).first()
                    
                    if not existe:
                        permissao = Permissao(
                            modulo_id=modulo_id,
                            usuario_id=None,
                            departamento_id=departamento_id,
                            cargo_id=None,
                            tipo_permissao=tipo_permissao,
                            pode_visualizar=pode_visualizar,
                            pode_criar=pode_criar,
                            pode_editar=pode_editar,
                            pode_excluir=pode_excluir,
                            pode_exportar=pode_exportar
                        )
                        permissao.save()
                        permissoes_criadas += 1
                
            elif tipo_permissao == 'cargo':
                cargo_ids = request.form.getlist('cargo_id')
                cargo_ids = [int(id) for id in cargo_ids if id]
                if not cargo_ids:
                    flash('Selecione pelo menos um cargo', 'error')
                    return render_template('admin/permissoes/permissao_form.html', 
                                         titulo='Nova Permissão',
                                         modulos=modulos,
                                         usuarios=usuarios,
                                         departamentos=departamentos,
                                         cargos=cargos)
                
                # Criar uma permissão para cada cargo selecionado
                for cargo_id in cargo_ids:
                    # Verificar se já existe permissão para evitar duplicatas
                    existe = Permissao.query.filter_by(
                        modulo_id=modulo_id,
                        cargo_id=cargo_id,
                        tipo_permissao='cargo',
                        status='Ativo'
                    ).first()
                    
                    if not existe:
                        permissao = Permissao(
                            modulo_id=modulo_id,
                            usuario_id=None,
                            departamento_id=None,
                            cargo_id=cargo_id,
                            tipo_permissao=tipo_permissao,
                            pode_visualizar=pode_visualizar,
                            pode_criar=pode_criar,
                            pode_editar=pode_editar,
                            pode_excluir=pode_excluir,
                            pode_exportar=pode_exportar
                        )
                        permissao.save()
                        permissoes_criadas += 1
            
            if permissoes_criadas > 0:
                flash(f'{permissoes_criadas} permissão(ões) criada(s) com sucesso!', 'success')
            else:
                flash('Nenhuma permissão foi criada. As permissões selecionadas já existem.', 'warning')
            
            # Se for requisição AJAX, retornar JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True, 
                    'message': f'{permissoes_criadas} permissão(ões) criada(s) com sucesso!' if permissoes_criadas > 0 else 'Nenhuma permissão foi criada. As permissões selecionadas já existem.',
                    'permissoes_criadas': permissoes_criadas
                })
            
            return redirect(url_for('admin.permissoes_listar'))
        except Exception as e:
            logger.error(f"Erro ao criar permissão: {str(e)}")
            flash(f'Erro ao criar permissão: {str(e)}', 'error')
    
    return render_template('admin/permissoes/permissao_form.html', 
                         titulo='Nova Permissão',
                         modulos=modulos,
                         usuarios=usuarios,
                         departamentos=departamentos,
                         cargos=cargos)

@admin_bp.route('/permissoes/permissoes/<int:id>/editar', methods=['GET', 'POST'])
def permissoes_editar(id):
    """
    Edita uma permissão existente
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível.', 'warning')
        return redirect(url_for('admin.permissoes_listar'))
    
    try:
        permissao = Permissao.query.get_or_404(id)
        
        # Carregar dados para os selects
        modulos = Modulo.query.filter_by(status='Ativo').order_by(Modulo.nome).all()
        usuarios = Usuario.query.order_by(Usuario.nome).all()
        departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
        cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
        
        if request.method == 'POST':
            try:
                modulo_id = request.form.get('modulo_id', type=int)
                tipo_permissao = request.form.get('tipo_permissao', '').strip()
                
                if not modulo_id:
                    flash('Módulo é obrigatório', 'error')
                    return render_template('admin/permissoes/permissao_form.html', 
                                         titulo='Editar Permissão',
                                         permissao=permissao,
                                         modulos=modulos,
                                         usuarios=usuarios,
                                         departamentos=departamentos,
                                         cargos=cargos)
                
                if not tipo_permissao:
                    flash('Tipo de permissão é obrigatório', 'error')
                    return render_template('admin/permissoes/permissao_form.html', 
                                         titulo='Editar Permissão',
                                         permissao=permissao,
                                         modulos=modulos,
                                         usuarios=usuarios,
                                         departamentos=departamentos,
                                         cargos=cargos)
                
                # Obter permissões específicas
                pode_visualizar = bool(request.form.get('pode_visualizar'))
                pode_criar = bool(request.form.get('pode_criar'))
                pode_editar = bool(request.form.get('pode_editar'))
                pode_excluir = bool(request.form.get('pode_excluir'))
                pode_exportar = bool(request.form.get('pode_exportar'))
                
                # Processar múltiplas seleções
                permissoes_atualizadas = 0
                permissoes_criadas = 0
                
                if tipo_permissao == 'usuario':
                    usuario_ids = request.form.getlist('usuario_id')
                    usuario_ids = [int(id) for id in usuario_ids if id]
                    if not usuario_ids:
                        flash('Selecione pelo menos um usuário', 'error')
                        return render_template('admin/permissoes/permissao_form.html', 
                                             titulo='Editar Permissão',
                                             permissao=permissao,
                                             modulos=modulos,
                                             usuarios=usuarios,
                                             departamentos=departamentos,
                                             cargos=cargos)
                    
                    # Se apenas um usuário selecionado, atualizar a permissão existente
                    if len(usuario_ids) == 1 and usuario_ids[0] == permissao.usuario_id:
                        permissao.modulo_id = modulo_id
                        permissao.pode_visualizar = pode_visualizar
                        permissao.pode_criar = pode_criar
                        permissao.pode_editar = pode_editar
                        permissao.pode_excluir = pode_excluir
                        permissao.pode_exportar = pode_exportar
                        permissao.save()
                        permissoes_atualizadas = 1
                    else:
                        # Se múltiplos ou diferente, criar novas permissões
                        for usuario_id in usuario_ids:
                            # Verificar se já existe
                            existe = Permissao.query.filter_by(
                                modulo_id=modulo_id,
                                usuario_id=usuario_id,
                                tipo_permissao='usuario',
                                status='Ativo'
                            ).first()
                            
                            if not existe:
                                nova_permissao = Permissao(
                                    modulo_id=modulo_id,
                                    usuario_id=usuario_id,
                                    departamento_id=None,
                                    cargo_id=None,
                                    tipo_permissao=tipo_permissao,
                                    pode_visualizar=pode_visualizar,
                                    pode_criar=pode_criar,
                                    pode_editar=pode_editar,
                                    pode_excluir=pode_excluir,
                                    pode_exportar=pode_exportar
                                )
                                nova_permissao.save()
                                permissoes_criadas += 1
                        
                        # Desativar permissão original se não estiver na lista
                        if permissao.usuario_id not in usuario_ids:
                            permissao.status = 'Inativo'
                            permissao.save()
                            permissoes_atualizadas = 1
                
                elif tipo_permissao == 'departamento':
                    departamento_ids = request.form.getlist('departamento_id')
                    departamento_ids = [int(id) for id in departamento_ids if id]
                    if not departamento_ids:
                        flash('Selecione pelo menos um departamento', 'error')
                        return render_template('admin/permissoes/permissao_form.html', 
                                             titulo='Editar Permissão',
                                             permissao=permissao,
                                             modulos=modulos,
                                             usuarios=usuarios,
                                             departamentos=departamentos,
                                             cargos=cargos)
                    
                    # Se apenas um departamento selecionado, atualizar a permissão existente
                    if len(departamento_ids) == 1 and departamento_ids[0] == permissao.departamento_id:
                        permissao.modulo_id = modulo_id
                        permissao.pode_visualizar = pode_visualizar
                        permissao.pode_criar = pode_criar
                        permissao.pode_editar = pode_editar
                        permissao.pode_excluir = pode_excluir
                        permissao.pode_exportar = pode_exportar
                        permissao.save()
                        permissoes_atualizadas = 1
                    else:
                        # Se múltiplos ou diferente, criar novas permissões
                        for departamento_id in departamento_ids:
                            # Verificar se já existe
                            existe = Permissao.query.filter_by(
                                modulo_id=modulo_id,
                                departamento_id=departamento_id,
                                tipo_permissao='departamento',
                                status='Ativo'
                            ).first()
                            
                            if not existe:
                                nova_permissao = Permissao(
                                    modulo_id=modulo_id,
                                    usuario_id=None,
                                    departamento_id=departamento_id,
                                    cargo_id=None,
                                    tipo_permissao=tipo_permissao,
                                    pode_visualizar=pode_visualizar,
                                    pode_criar=pode_criar,
                                    pode_editar=pode_editar,
                                    pode_excluir=pode_excluir,
                                    pode_exportar=pode_exportar
                                )
                                nova_permissao.save()
                                permissoes_criadas += 1
                        
                        # Desativar permissão original se não estiver na lista
                        if permissao.departamento_id not in departamento_ids:
                            permissao.status = 'Inativo'
                            permissao.save()
                            permissoes_atualizadas = 1
                
                elif tipo_permissao == 'cargo':
                    cargo_ids = request.form.getlist('cargo_id')
                    cargo_ids = [int(id) for id in cargo_ids if id]
                    if not cargo_ids:
                        flash('Selecione pelo menos um cargo', 'error')
                        return render_template('admin/permissoes/permissao_form.html', 
                                             titulo='Editar Permissão',
                                             permissao=permissao,
                                             modulos=modulos,
                                             usuarios=usuarios,
                                             departamentos=departamentos,
                                             cargos=cargos)
                    
                    # Se apenas um cargo selecionado, atualizar a permissão existente
                    if len(cargo_ids) == 1 and cargo_ids[0] == permissao.cargo_id:
                        permissao.modulo_id = modulo_id
                        permissao.pode_visualizar = pode_visualizar
                        permissao.pode_criar = pode_criar
                        permissao.pode_editar = pode_editar
                        permissao.pode_excluir = pode_excluir
                        permissao.pode_exportar = pode_exportar
                        permissao.save()
                        permissoes_atualizadas = 1
                    else:
                        # Se múltiplos ou diferente, criar novas permissões
                        for cargo_id in cargo_ids:
                            # Verificar se já existe
                            existe = Permissao.query.filter_by(
                                modulo_id=modulo_id,
                                cargo_id=cargo_id,
                                tipo_permissao='cargo',
                                status='Ativo'
                            ).first()
                            
                            if not existe:
                                nova_permissao = Permissao(
                                    modulo_id=modulo_id,
                                    usuario_id=None,
                                    departamento_id=None,
                                    cargo_id=cargo_id,
                                    tipo_permissao=tipo_permissao,
                                    pode_visualizar=pode_visualizar,
                                    pode_criar=pode_criar,
                                    pode_editar=pode_editar,
                                    pode_excluir=pode_excluir,
                                    pode_exportar=pode_exportar
                                )
                                nova_permissao.save()
                                permissoes_criadas += 1
                        
                        # Desativar permissão original se não estiver na lista
                        if permissao.cargo_id not in cargo_ids:
                            permissao.status = 'Inativo'
                            permissao.save()
                            permissoes_atualizadas = 1
                
                # Mensagem de sucesso
                mensagem = []
                if permissoes_atualizadas > 0:
                    mensagem.append(f'{permissoes_atualizadas} permissão(ões) atualizada(s)')
                if permissoes_criadas > 0:
                    mensagem.append(f'{permissoes_criadas} permissão(ões) criada(s)')
                
                if mensagem:
                    flash(' e '.join(mensagem) + ' com sucesso!', 'success')
                else:
                    flash('Nenhuma alteração foi realizada.', 'warning')
                
                # Se for requisição AJAX, retornar JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True, 
                        'message': ' e '.join(mensagem) + ' com sucesso!' if mensagem else 'Nenhuma alteração foi realizada.',
                        'permissoes_atualizadas': permissoes_atualizadas,
                        'permissoes_criadas': permissoes_criadas
                    })
                
                return redirect(url_for('admin.permissoes_listar'))
            except Exception as e:
                logger.error(f"Erro ao atualizar permissão: {str(e)}")
                flash(f'Erro ao atualizar permissão: {str(e)}', 'error')
        
        return render_template('admin/permissoes/permissao_form.html', 
                             titulo='Editar Permissão',
                             permissao=permissao,
                             modulos=modulos,
                             usuarios=usuarios,
                             departamentos=departamentos,
                             cargos=cargos)
    except Exception as e:
        logger.error(f"Erro ao editar permissão: {str(e)}")
        flash('Permissão não encontrada', 'error')
        return redirect(url_for('admin.permissoes_listar'))

@admin_bp.route('/permissoes/permissoes/<int:id>/excluir', methods=['POST'])
def permissoes_excluir(id):
    """
    Exclui (desativa) uma permissão
    """
    if not PERMISSOES_DISPONIVEL:
        flash('Sistema de permissões não está disponível.', 'warning')
        return redirect(url_for('admin.permissoes_listar'))
    
    try:
        permissao = Permissao.query.get_or_404(id)
        permissao.status = 'Inativo'
        permissao.save()
        flash('Permissão excluída com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao excluir permissão: {str(e)}")
        flash('Erro ao excluir permissão', 'error')
    
    return redirect(url_for('admin.permissoes_listar'))
