from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from utils.password import hash_password
from datetime import datetime

from models.database import db
from models.usuario import Usuario
from models.cargo import Cargo
from models.departamento import Departamento

usuario_bp = Blueprint('usuario', __name__)

# Middleware para verificar se o usuário tem permissão
@usuario_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_admin:
        # Se for requisição AJAX, retornar JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/usuarios/api/'):
            return jsonify({'error': 'Acesso restrito. Você não tem permissão para acessar esta área.'}), 403
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@usuario_bp.route('/')
@login_required
def index():
    """
    Lista todos os usuários
    """
    cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    return render_template('usuarios/index.html', cargos=cargos, departamentos=departamentos)

@usuario_bp.route('/api/dados')
@login_required
def api_dados():
    """
    API para retornar dados dos usuários em JSON (para DataTable)
    """
    usuarios = Usuario.query.order_by(Usuario.id.desc()).all()
    print(f"Total de usuários encontrados: {len(usuarios)}")
    dados = []
    for usuario in usuarios:
        # Formatar cargo
        cargo_badge = ''
        cargo_nome = usuario.cargo_rel.nome if usuario.cargo_rel else ''
        if cargo_nome.lower() == 'admin':
            cargo_badge = '<span class="badge bg-danger">Administrador</span>'
        elif cargo_nome.lower() == 'diretor':
            cargo_badge = '<span class="badge bg-primary">Diretor</span>'
        elif cargo_nome.lower() == 'gerente':
            cargo_badge = '<span class="badge bg-success">Gerente</span>'
        else:
            cargo_badge = f'<span class="badge bg-secondary">{cargo_nome}</span>'
        
        # Formatar último login
        ultimo_login_str = 'Nunca'
        if usuario.ultimo_login:
            ultimo_login_str = usuario.ultimo_login.strftime('%d/%m/%Y %H:%M')
        
        # Botões de ação
        botoes_acao = f'''
            <div class="btn-group" role="group">
                <button type="button" class="btn btn-sm btn-primary btn-editar-usuario" 
                    data-bs-toggle="tooltip" title="Editar"
                    data-id="{usuario.id}"
                    data-nome="{usuario.nome}"
                    data-email="{usuario.email}"
                    data-departamento-id="{usuario.departamento_id}"
                    data-cargo-id="{usuario.cargo_id}">
                    <i class="fas fa-edit"></i>
                </button>
                <button type="button" class="btn btn-sm btn-warning btn-resetar-senha" 
                    data-bs-toggle="tooltip" title="Resetar Senha"
                    data-id="{usuario.id}"
                    data-nome="{usuario.nome}">
                    <i class="fas fa-key"></i>
                </button>
        '''
        
        # Adicionar botão de excluir apenas se não for o usuário atual
        if usuario.id != current_user.id:
            # O CSRF token será adicionado via JavaScript no frontend
            botoes_acao += f'''
                <form id="form-excluir-{usuario.id}"
                    action="{url_for('usuario.excluir', id=usuario.id)}" method="POST"
                    class="d-inline form-excluir">
                    <button type="submit" class="btn btn-sm btn-danger" data-bs-toggle="tooltip"
                        title="Excluir">
                        <i class="fas fa-trash"></i>
                    </button>
                </form>
            '''
        
        botoes_acao += '</div>'
        
        dados.append({
            'id': usuario.id,
            'nome': usuario.nome or '',
            'email': usuario.email or '',
            'departamento': usuario.departamento or '',
            'cargo': cargo_badge,
            'cargo_raw': cargo_nome,
            'ultimo_login': ultimo_login_str,
            'ultimo_login_raw': usuario.ultimo_login.isoformat() if usuario.ultimo_login else '',
            'acoes': botoes_acao
        })
    
    print(f"Total de dados preparados: {len(dados)}")
    response = jsonify({'data': dados})
    print(f"Response status: {response.status_code}")
    return response

@usuario_bp.route('/api/cargos')
@login_required
def api_cargos():
    """
    API para retornar lista de cargos ativos em JSON
    """
    cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
    dados = [{'id': cargo.id, 'nome': cargo.nome} for cargo in cargos]
    return jsonify({'cargos': dados})

@usuario_bp.route('/api/departamentos')
@login_required
def api_departamentos():
    """
    API para retornar lista de departamentos ativos em JSON
    """
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    dados = [{'id': dept.id, 'nome': dept.nome} for dept in departamentos]
    return jsonify({'departamentos': dados})

@usuario_bp.route('/api/colaboradores')
@login_required
def api_colaboradores():
    """
    API para retornar lista de colaboradores sem usuário em JSON
    """
    from models.colaborador import Colaborador
    from sqlalchemy import and_
    
    # Buscar IDs de colaboradores que já têm usuário
    colaboradores_com_usuario_ids = db.session.query(Usuario.colaborador_id).filter(
        Usuario.colaborador_id.isnot(None)
    ).distinct().all()
    
    ids_com_usuario = [row[0] for row in colaboradores_com_usuario_ids]
    
    # Buscar colaboradores ativos que ainda não têm usuário
    query = Colaborador.query.filter(Colaborador.status == 'Ativo')
    
    if ids_com_usuario:
        query = query.filter(~Colaborador.id.in_(ids_com_usuario))
    
    # Busca por termo se fornecido
    termo = request.args.get('termo', '').strip()
    if termo:
        query = query.filter(Colaborador.nome.ilike(f'%{termo}%'))
    
    colaboradores = query.order_by(Colaborador.nome).limit(50).all()
    
    dados = [{
        'id': col.id, 
        'nome': col.nome,
        'email': col.email or '',
        'cargo': col.cargo.nome if col.cargo else '',
        'cargo_id': col.cargo_id if col.cargo else None,
        'departamento': col.departamento.nome if col.departamento else '',
        'departamento_id': col.departamento_id if col.departamento else None
    } for col in colaboradores]
    
    print(f"Total de colaboradores encontrados: {len(dados)}")
    return jsonify({'colaboradores': dados})

@usuario_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cria um novo usuário
    """
    if request.method == 'POST':
        # Verificar se é requisição AJAX
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        colaborador_id = request.form.get('colaborador_id')
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        departamento_id = request.form.get('departamento_id')
        cargo_id = request.form.get('cargo_id')
        
        # Validação básica
        if not nome or not email or not senha or not departamento_id or not cargo_id:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Por favor, preencha todos os campos.'}), 400
            flash('Por favor, preencha todos os campos.', 'danger')
            cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
            departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
            return render_template('usuarios/novo.html', cargos=cargos, departamentos=departamentos)
        
        # Verifica se o email já está em uso
        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Este email já está em uso.'}), 400
            flash('Este email já está em uso.', 'danger')
            cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
            departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
            return render_template('usuarios/novo.html', cargos=cargos, departamentos=departamentos)
        
        # Se foi selecionado um colaborador, verificar se já tem usuário
        if colaborador_id:
            from models.colaborador import Colaborador
            colaborador = Colaborador.query.get(colaborador_id)
            if colaborador and colaborador.usuario:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Este colaborador já possui um usuário.'}), 400
                flash('Este colaborador já possui um usuário.', 'danger')
                cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
                departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
                return render_template('usuarios/novo.html', cargos=cargos, departamentos=departamentos)
        
        # Cria o novo usuário
        novo_usuario = Usuario(
            nome=nome,
            email=email,
            senha=hash_password(senha),
            departamento_id=int(departamento_id),
            cargo_id=int(cargo_id),
            colaborador_id=int(colaborador_id) if colaborador_id else None
        )
        
        db.session.add(novo_usuario)
        db.session.commit()
        
        if is_ajax:
            return jsonify({'success': True, 'message': 'Usuário criado com sucesso.'})
        
        flash('Usuário criado com sucesso.', 'success')
        return redirect(url_for('usuario.index'))
    
    return render_template('usuarios/novo.html')

@usuario_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um usuário existente
    """
    usuario = Usuario.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        departamento_id = request.form.get('departamento_id')
        cargo_id = request.form.get('cargo_id')
        
        # Validação básica
        if not nome or not email or not departamento_id or not cargo_id:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Por favor, preencha todos os campos.'}), 400
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('usuarios/editar.html', usuario=usuario)
        
        # Verifica se o email já está em uso por outro usuário
        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente and usuario_existente.id != id:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Este email já está em uso.'}), 400
            flash('Este email já está em uso.', 'danger')
            return render_template('usuarios/editar.html', usuario=usuario)
        
        # Atualiza o usuário
        usuario.nome = nome
        usuario.email = email
        usuario.departamento_id = int(departamento_id)
        usuario.cargo_id = int(cargo_id)
        
        db.session.commit()
        
        if is_ajax:
            return jsonify({'success': True, 'message': 'Usuário atualizado com sucesso.'})
        
        flash('Usuário atualizado com sucesso.', 'success')
        return redirect(url_for('usuario.index'))
    
    if is_ajax:
        return jsonify({
            'success': True,
            'usuario': {
                'id': usuario.id,
                'nome': usuario.nome,
                'email': usuario.email,
                'departamento': usuario.departamento,
                'cargo_id': usuario.cargo_id,
                'departamento_id': usuario.departamento_id
            }
        })
    
    return render_template('usuarios/editar.html', usuario=usuario)

@usuario_bp.route('/resetar-senha/<int:id>', methods=['GET', 'POST'])
def resetar_senha(id):
    """
    Reseta a senha de um usuário
    """
    usuario = Usuario.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')
        
        # Validação básica
        if not nova_senha or not confirmar_senha:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Por favor, preencha todos os campos.'}), 400
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('usuarios/resetar_senha.html', usuario=usuario)
        
        # Validação de tamanho mínimo da senha
        if len(nova_senha) < 6:
            if is_ajax:
                return jsonify({'success': False, 'message': 'A senha deve ter no mínimo 6 caracteres.'}), 400
            flash('A senha deve ter no mínimo 6 caracteres.', 'danger')
            return render_template('usuarios/resetar_senha.html', usuario=usuario)
        
        # Verifica se as senhas coincidem
        if nova_senha != confirmar_senha:
            if is_ajax:
                return jsonify({'success': False, 'message': 'As senhas não coincidem.'}), 400
            flash('As senhas não coincidem.', 'danger')
            return render_template('usuarios/resetar_senha.html', usuario=usuario)
        
        # Atualiza a senha
        usuario.senha = hash_password(nova_senha)
        db.session.commit()
        
        if is_ajax:
            return jsonify({'success': True, 'message': 'Senha resetada com sucesso.'})
        
        flash('Senha resetada com sucesso.', 'success')
        return redirect(url_for('usuario.index'))
    
    if is_ajax:
        return jsonify({
            'success': True,
            'usuario': {
                'id': usuario.id,
                'nome': usuario.nome
            }
        })
    
    return render_template('usuarios/resetar_senha.html', usuario=usuario)

@usuario_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um usuário
    """
    usuario = Usuario.query.get_or_404(id)
    
    # Não permite excluir o próprio usuário
    if usuario.id == current_user.id:
        flash('Você não pode excluir seu próprio usuário.', 'danger')
        return redirect(url_for('usuario.index'))
    
    db.session.delete(usuario)
    db.session.commit()
    
    flash('Usuário excluído com sucesso.', 'success')
    return redirect(url_for('usuario.index')) 