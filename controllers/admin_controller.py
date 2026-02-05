from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime
import logging
from sqlalchemy import text, inspect

from models.database import db
from models.usuario import Usuario
from models.centro_custo import CentroCusto
from models.contrato import Contrato
from models.material import Materiais
from models.plano_conta import PlanoConta
from models.cliente import Cliente
from models.endereco import Endereco
from models.logs import Logs
from models.departamento import Departamento
from models.cargo import Cargo
from models.upload import Upload

logger = logging.getLogger(__name__)

# Importar modelos de permissões
try:
    from models.permissoes import Modulo, Permissao
    PERMISSOES_DISPONIVEL = True
except ImportError:
    PERMISSOES_DISPONIVEL = False
    logger.warning("Modelos de permissões não encontrados. Interface de permissões não estará disponível.")

admin_bp = Blueprint('admin', __name__)

# Middleware para verificar se o usuário é administrador
@admin_bp.before_request
@login_required
def verificar_admin():
    if not current_user.is_permissao('admin'):
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))
 
@admin_bp.route('/')
def index():
    """
    Página inicial da área administrativa com resumo das tabelas do banco de dados
    """
    try:
        # Obter todas as tabelas do banco de dados
        inspector = inspect(db.engine)
        tabelas = inspector.get_table_names()
        
        tabelas_info = []
        uploads_por_tipo = {}
        
        # Mapeamento de tipos de upload
        tipos_upload = {
            0: 'Não definido',
            1: 'Arquivei',
            2: 'Protocolo',
            3: 'Reembolso',
            4: 'Avulso',
            5: 'Certificado'
        }
        
        # Para cada tabela, obter informações
        for tabela in sorted(tabelas):
            try:
                # Contar registros
                count_query = text(f"SELECT COUNT(*) as total FROM `{tabela}`")
                result = db.session.execute(count_query)
                total_registros = result.scalar() or 0
                
                # Obter tamanho da tabela (MySQL)
                size_query = text("""
                    SELECT 
                        ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
                    FROM information_schema.TABLES 
                    WHERE table_schema = DATABASE()
                    AND table_name = :table_name
                """)
                size_result = db.session.execute(size_query, {'table_name': tabela})
                size_row = size_result.fetchone()
                tamanho_mb = float(size_row[0]) if size_row and size_row[0] else 0.0
                
                tabelas_info.append({
                    'nome': tabela,
                    'total_registros': total_registros,
                    'tamanho_mb': tamanho_mb
                })
                
                # Se for a tabela Uploads, obter informações por tipo
                if tabela == 'Uploads':
                    tipo_query = text("""
                        SELECT 
                            tipo,
                            COUNT(*) as total,
                            ROUND(SUM(LENGTH(`blob`)) / 1024 / 1024, 2) as tamanho_mb
                        FROM Uploads
                        GROUP BY tipo
                        ORDER BY tipo
                    """)
                    tipo_result = db.session.execute(tipo_query)
                    for row in tipo_result:
                        tipo = row[0] if row[0] is not None else 0
                        total = row[1]
                        tamanho = float(row[2]) if row[2] else 0.0
                        tipo_nome = tipos_upload.get(tipo, f'Tipo {tipo}')
                        uploads_por_tipo[tipo_nome] = {
                            'total': total,
                            'tamanho_mb': tamanho
                        }
                    
                    # Adicionar total de registros sem tipo
                    sem_tipo_query = text("""
                        SELECT 
                            COUNT(*) as total,
                            ROUND(SUM(LENGTH(`blob`)) / 1024 / 1024, 2) as tamanho_mb
                        FROM Uploads 
                        WHERE tipo IS NULL
                    """)
                    sem_tipo_result = db.session.execute(sem_tipo_query)
                    sem_tipo_row = sem_tipo_result.fetchone()
                    if sem_tipo_row and sem_tipo_row[0] and sem_tipo_row[0] > 0:
                        uploads_por_tipo['Sem tipo'] = {
                            'total': sem_tipo_row[0],
                            'tamanho_mb': float(sem_tipo_row[1]) if sem_tipo_row[1] else 0.0
                        }
                
            except Exception as e:
                logger.warning(f"Erro ao obter informações da tabela {tabela}: {str(e)}")
                tabelas_info.append({
                    'nome': tabela,
                    'total_registros': 0,
                    'tamanho_mb': 0.0,
                    'erro': str(e)
                })
        
        # Calcular totais gerais
        total_registros_geral = sum(t['total_registros'] for t in tabelas_info)
        total_tamanho_geral = sum(t['tamanho_mb'] for t in tabelas_info)
        
        # Ordenar tabelas por tamanho (maior primeiro)
        tabelas_info.sort(key=lambda x: x['tamanho_mb'], reverse=True)
        
        return render_template('admin/index.html',
                            tabelas_info=tabelas_info,
                            uploads_por_tipo=uploads_por_tipo,
                            total_registros_geral=total_registros_geral,
                            total_tamanho_geral=total_tamanho_geral,
                            total_tabelas=len(tabelas_info))
    
    except Exception as e:
        logger.error(f"Erro ao carregar página de admin: {str(e)}")
        flash(f'Erro ao carregar informações do banco de dados: {str(e)}', 'error')
        return render_template('admin/index.html',
                            tabelas_info=[],
                            uploads_por_tipo={},
                            total_registros_geral=0,
                            total_tamanho_geral=0.0,
                            total_tabelas=0)

@admin_bp.route('/configuracoes')
def configuracoes():
    """
    Página de configurações do sistema
    """
    return render_template('admin/configuracoes.html')

@admin_bp.route('/logs')
def logs():
    """
    Página de logs do sistema
    """
    # Parâmetros de paginação
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Parâmetros de filtro
    local_filtro = request.args.get('local', '').strip()
    data_inicial = request.args.get('data_inicial', '')
    data_final = request.args.get('data_final', '')
    
    # Construir query base
    query = Logs.query
    
    # Aplicar filtros
    if local_filtro:
        query = query.filter(Logs.local.ilike(f'%{local_filtro}%'))
    
    if data_inicial:
        try:
            data_inicial_obj = datetime.strptime(data_inicial, '%Y-%m-%d')
            query = query.filter(Logs.data >= data_inicial_obj)
        except ValueError:
            pass
    
    if data_final:
        try:
            data_final_obj = datetime.strptime(data_final, '%Y-%m-%d')
            # Adicionar 23:59:59 para incluir o dia inteiro
            data_final_obj = data_final_obj.replace(hour=23, minute=59, second=59)
            query = query.filter(Logs.data <= data_final_obj)
        except ValueError:
            pass
    
    # Ordenar por data (mais recente primeiro)
    query = query.order_by(Logs.data.desc())
    
    # Aplicar paginação
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    logs = pagination.items
    
    return render_template('admin/logs.html', 
                         logs=logs, 
                         pagination=pagination)

@admin_bp.route('/backup')
def backup():
    """
    Página de backup do sistema
    """
    # Aqui você pode implementar a lógica para realizar backups do banco de dados
    return render_template('admin/backup.html')

# =====================================================
# Rotas de Gerenciamento de Permissões
# =====================================================

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