from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models.database import db
from models.grupo_material import GrupoMaterial
from models.material import Material
from models.estoque import Estoque
from forms.forms import FormGrupoMaterial
from sqlalchemy import or_, and_
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Criar blueprint
grupo_material_bp = Blueprint('grupo_material', __name__, url_prefix='/grupos-materiais')

@grupo_material_bp.route('/')
@login_required
def index():
    """
    Lista todos os grupos de materiais
    """
    try:
        # Parâmetros de busca e filtro
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '')
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Query base
        query = GrupoMaterial.query
        
        # Aplicar filtros
        if search:
            query = query.filter(
                or_(
                    GrupoMaterial.nome.ilike(f'%{search}%'),
                    GrupoMaterial.descricao.ilike(f'%{search}%'),
                    GrupoMaterial.codigo.ilike(f'%{search}%')
                )
            )
        
        if status == 'ativo':
            query = query.filter_by(ativo=True)
        elif status == 'inativo':
            query = query.filter_by(ativo=False)
        
        # Ordenar e paginar
        grupos = query.order_by(GrupoMaterial.nome).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return render_template('grupos_materiais/index.html', 
                             grupos=grupos, 
                             search=search, 
                             status=status)
    
    except Exception as e:
        logger.error(f"Erro ao listar grupos de materiais: {str(e)}")
        flash('Erro ao carregar grupos de materiais.', 'error')
        return render_template('grupos_materiais/index.html', grupos=None)

@grupo_material_bp.route('/novo', methods=['POST'])
@login_required
def novo():
    """
    Cria um novo grupo de materiais via API
    """
    try:
        data = request.get_json()
        
        # Validar dados obrigatórios
        if not data.get('nome'):
            return jsonify({
                'success': False,
                'message': 'Nome do grupo é obrigatório'
            }), 400
        
        # Verificar se já existe um grupo com o mesmo nome ou código
        grupo_existente = GrupoMaterial.query.filter(
            or_(
                GrupoMaterial.nome == data.get('nome'),
                GrupoMaterial.codigo == data.get('codigo')
            )
        ).first()
        
        if grupo_existente:
            if grupo_existente.nome == data.get('nome'):
                return jsonify({
                    'success': False,
                    'message': 'Já existe um grupo com este nome'
                }), 400
            else:
                return jsonify({
                    'success': False,
                    'message': 'Já existe um grupo com este código'
                }), 400
        
        # Criar novo grupo
        grupo = GrupoMaterial(
            nome=data.get('nome'),
            descricao=data.get('descricao', ''),
            codigo=data.get('codigo', ''),
            cor=data.get('cor', ''),
            icone=data.get('icone', ''),
            ativo=data.get('ativo', True),
            criado_por_id=current_user.id
        )
        
        grupo.save()
        
        return jsonify({
            'success': True,
            'message': 'Grupo de materiais criado com sucesso!',
            'grupo': grupo.to_dict()
        })
    
    except Exception as e:
        logger.error(f"Erro ao criar grupo de materiais: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao criar grupo de materiais: {str(e)}'
        }), 500

@grupo_material_bp.route('/<int:id>')
@login_required
def detalhes(id):
    """
    Exibe detalhes de um grupo de materiais
    """
    try:
        grupo = GrupoMaterial.query.get_or_404(id)
        return render_template('grupos_materiais/detalhes.html', grupo=grupo)
    
    except Exception as e:
        logger.error(f"Erro ao exibir detalhes do grupo {id}: {str(e)}")
        flash('Erro ao carregar detalhes do grupo.', 'error')
        return redirect(url_for('grupo_material.index'))

@grupo_material_bp.route('/<int:id>/editar', methods=['POST'])
@login_required
def editar(id):
    """
    Edita um grupo de materiais via API
    """
    try:
        grupo = GrupoMaterial.query.get_or_404(id)
        data = request.get_json()
        
        # Validar dados obrigatórios
        if not data.get('nome'):
            return jsonify({
                'success': False,
                'message': 'Nome do grupo é obrigatório'
            }), 400
        
        # Verificar se já existe outro grupo com o mesmo nome ou código
        grupo_existente = GrupoMaterial.query.filter(
            or_(
                GrupoMaterial.nome == data.get('nome'),
                GrupoMaterial.codigo == data.get('codigo')
            )
        ).filter(GrupoMaterial.id != id).first()
        
        if grupo_existente:
            if grupo_existente.nome == data.get('nome'):
                return jsonify({
                    'success': False,
                    'message': 'Já existe outro grupo com este nome'
                }), 400
            else:
                return jsonify({
                    'success': False,
                    'message': 'Já existe outro grupo com este código'
                }), 400
        
        # Atualizar grupo
        grupo.nome = data.get('nome')
        grupo.descricao = data.get('descricao', '')
        grupo.codigo = data.get('codigo', '')
        grupo.cor = data.get('cor', '')
        grupo.icone = data.get('icone', '')
        grupo.ativo = data.get('ativo', True)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Grupo de materiais atualizado com sucesso!',
            'grupo': grupo.to_dict()
        })
    
    except Exception as e:
        logger.error(f"Erro ao editar grupo {id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao editar grupo de materiais: {str(e)}'
        }), 500

@grupo_material_bp.route('/<int:id>/excluir', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um grupo de materiais via API
    """
    try:
        grupo = GrupoMaterial.query.get_or_404(id)
        
        # Contar materiais antes de excluir para mensagem informativa
        try:
            # Usar SQL direto para contar materiais sem carregar o relacionamento
            sql_count = "SELECT COUNT(*) FROM materiais_grupos WHERE grupo_id = :grupo_id"
            result = db.session.execute(db.text(sql_count), {'grupo_id': id}).fetchone()
            total_materiais = result[0] if result else 0
        except Exception as e:
            logger.warning(f"Erro ao contar materiais do grupo {id}: {str(e)}")
            total_materiais = 0
        
        # Remover associações com materiais primeiro
        try:
            sql_delete = "DELETE FROM materiais_grupos WHERE grupo_id = :grupo_id"
            db.session.execute(db.text(sql_delete), {'grupo_id': id})
            db.session.flush()
        except Exception as e:
            logger.warning(f"Erro ao remover associações do grupo {id}: {str(e)}")
            # Continuar mesmo se houver erro (pode não ter associações)
        
        # Excluir o grupo
        db.session.delete(grupo)
        db.session.commit()
        
        mensagem = 'Grupo de materiais excluído com sucesso!'
        if total_materiais > 0:
            mensagem += f' {total_materiais} material(is) foram desassociado(s) do grupo.'
        
        return jsonify({
            'success': True,
            'message': mensagem
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir grupo {id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Erro ao excluir grupo de materiais: {str(e)}'
        }), 500

@grupo_material_bp.route('/<int:id>/materiais')
@login_required
def materiais(id):
    """
    Lista os materiais de um grupo
    """
    try:
        grupo = GrupoMaterial.query.get_or_404(id)
        search = request.args.get('search', '').strip()
        
        # Query para materiais do grupo usando SQL direto
        if search:
            sql = """
                SELECT m.id FROM materiais m 
                INNER JOIN materiais_grupos mg ON m.id = mg.material_id 
                WHERE mg.grupo_id = :grupo_id 
                AND (m.nome LIKE :search OR m.codigo LIKE :search OR m.descricao LIKE :search)
                ORDER BY m.nome
            """
            material_ids = db.session.execute(
                db.text(sql), 
                {'grupo_id': grupo.id, 'search': f'%{search}%'}
            ).fetchall()
        else:
            sql = """
                SELECT m.id FROM materiais m 
                INNER JOIN materiais_grupos mg ON m.id = mg.material_id 
                WHERE mg.grupo_id = :grupo_id 
                ORDER BY m.nome
            """
            material_ids = db.session.execute(
                db.text(sql), 
                {'grupo_id': grupo.id}
            ).fetchall()
        
        # Buscar os materiais pelos IDs
        if material_ids:
            ids = [row[0] for row in material_ids]
            materiais = Material.query.filter(Material.id.in_(ids)).order_by(Material.nome).all()
        else:
            materiais = []
        
        return render_template('grupos_materiais/materiais.html', 
                             grupo=grupo, 
                             materiais=materiais, 
                             search=search)
    
    except Exception as e:
        logger.error(f"Erro ao listar materiais do grupo {id}: {str(e)}")
        flash('Erro ao carregar materiais do grupo.', 'error')
        return redirect(url_for('grupo_material.index'))

@grupo_material_bp.route('/<int:id>/adicionar-material', methods=['POST'])
@login_required
def adicionar_material(id):
    """
    Adiciona um material ao grupo
    """
    try:
        logger.info(f"Tentando adicionar material ao grupo {id}")
        grupo = GrupoMaterial.query.get_or_404(id)
        material_id_raw = request.json.get('material_id')
        
        logger.info(f"Material ID recebido: {material_id_raw}, tipo: {type(material_id_raw)}")
        
        if material_id_raw is None:
            return jsonify({'success': False, 'message': 'ID do material não fornecido'})
        
        # Garantir que material_id seja um inteiro
        try:
            material_id = int(material_id_raw)
        except (ValueError, TypeError) as e:
            logger.error(f"Erro ao converter material_id: {e}, valor recebido: {material_id_raw}")
            return jsonify({'success': False, 'message': f'ID do material inválido: {material_id_raw}'})
        
        logger.info(f"Material ID convertido: {material_id}")
        
        # Buscar o material usando get com o ID inteiro
        material = Material.query.get(material_id)
        if not material:
            logger.warning(f"Material com ID {material_id} não encontrado")
            return jsonify({'success': False, 'message': f'Material com ID {material_id} não encontrado'})
        
        logger.info(f"Material encontrado: {material.nome}")
        
        # Adicionar o material (o método já verifica duplicatas)
        material_adicionado = grupo.adicionar_material(material)
        
        if not material_adicionado:
            logger.warning(f"Material {material_id} já está no grupo {id}")
            return jsonify({'success': False, 'message': 'Material já está neste grupo'})
        
        logger.info(f"Material {material.nome} adicionado ao grupo {grupo.nome}")
        
        return jsonify({
            'success': True, 
            'message': f'Material "{material.nome}" adicionado ao grupo com sucesso!'
        })
    
    except Exception as e:
        db.session.rollback()
        error_msg = str(e)
        logger.error(f"Erro ao adicionar material ao grupo {id}: {error_msg}")
        
        # Verificar se é erro de duplicata (pode ocorrer em race conditions)
        if 'Duplicate entry' in error_msg or '1062' in error_msg:
            return jsonify({
                'success': False, 
                'message': 'Material já está neste grupo'
            })
        
        return jsonify({
            'success': False, 
            'message': f'Erro ao adicionar material ao grupo: {error_msg}'
        }), 500

@grupo_material_bp.route('/<int:id>/remover-material', methods=['POST'])
@login_required
def remover_material(id):
    """
    Remove um material do grupo
    """
    try:
        grupo = GrupoMaterial.query.get_or_404(id)
        material_id = request.json.get('material_id')
        
        if not material_id:
            return jsonify({'success': False, 'message': 'ID do material não fornecido'})
        
        material = Material.query.get(material_id)
        if not material:
            return jsonify({'success': False, 'message': 'Material não encontrado'})
        
        if material not in grupo.materiais:
            return jsonify({'success': False, 'message': 'Material não está neste grupo'})
        
        grupo.remover_material(material)
        
        return jsonify({
            'success': True, 
            'message': f'Material "{material.nome}" removido do grupo com sucesso!'
        })
    
    except Exception as e:
        logger.error(f"Erro ao remover material do grupo {id}: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro ao remover material do grupo'})

@grupo_material_bp.route('/api/buscar-materiais')
@login_required
def api_buscar_materiais():
    """
    API para buscar materiais para adicionar ao grupo
    """
    try:
        grupo_id = request.args.get('grupo_id')
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '').strip()
        categoria = request.args.get('categoria', '').strip()
        
        # Query base para materiais que estão em estoque
        # Filtrar apenas materiais que têm registro em estoque com tipo_item = 'material'
        query = Material.query.join(Estoque, and_(
            Estoque.material_id == Material.id,
            Estoque.tipo_item == 'material'
        )).distinct()
        
        
        
        # Filtrar por categoria
        if categoria:
            query = query.filter(Material.categoria.ilike(f'%{categoria}%'))
        
        # Se foi fornecido um grupo_id, excluir materiais já no grupo
        if grupo_id:
            try:
                grupo_id_int = int(grupo_id)
                grupo = GrupoMaterial.query.get(grupo_id_int)
                if grupo:
                    # Usar SQL direto para excluir materiais já no grupo
                    sql = "SELECT material_id FROM materiais_grupos WHERE grupo_id = :grupo_id"
                    materiais_no_grupo = db.session.execute(
                        db.text(sql), {'grupo_id': grupo_id_int}
                    ).fetchall()
                    if materiais_no_grupo:
                        ids_excluir = [row[0] for row in materiais_no_grupo]
                        query = query.filter(~Material.id.in_(ids_excluir))
            except (ValueError, TypeError):
                # Se grupo_id não for um número válido, ignorar
                pass
        
        # Aplicar busca
        if search:
            query = query.filter(
                or_(
                    Material.nome.ilike(f'%{search}%'),
                    Material.codigo.ilike(f'%{search}%'),
                    Material.descricao.ilike(f'%{search}%')
                )
            )
        
        # Ordenar por nome
        query = query.order_by(Material.nome)
        
        materiais = query.limit(100).all()
        
        logger.info(f"API buscar-materiais: encontrados {len(materiais)} materiais (search: '{search}', grupo_id: {grupo_id}, status: {status})")
        
        return jsonify({
            'success': True,
            'materiais': [{
                'id': m.id,
                'nome': m.nome,
                'codigo': m.codigo or '',
                'categoria': m.categoria or '',
                'unidade': m.get_unidade_nome() or '',
                'ativo': m.ativo
            } for m in materiais]
        })
    
    except Exception as e:
        logger.error(f"Erro na API de busca de materiais: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro ao buscar materiais'})

@grupo_material_bp.route('/api/listar-json')
@login_required
def api_listar_json():
    """
    API para listar grupos em formato JSON
    """
    try:
        # Parâmetros de filtro
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '')
        
        # Query base
        query = GrupoMaterial.query
        
        # Aplicar filtros
        if search:
            query = query.filter(
                or_(
                    GrupoMaterial.nome.ilike(f'%{search}%'),
                    GrupoMaterial.descricao.ilike(f'%{search}%'),
                    GrupoMaterial.codigo.ilike(f'%{search}%')
                )
            )
        
        if status == 'ativo':
            query = query.filter_by(ativo=True)
        elif status == 'inativo':
            query = query.filter_by(ativo=False)
        
        # Obter todos os grupos (não apenas ativos)
        grupos = query.order_by(GrupoMaterial.nome).all()
        
        return jsonify({
            'success': True,
            'grupos': [grupo.to_dict() for grupo in grupos]
        })
    
    except Exception as e:
        logger.error(f"Erro na API de listagem de grupos: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro ao listar grupos'})

@grupo_material_bp.route('/api/<int:id>/materiais')
@login_required
def api_materiais(id):
    """
    API para listar materiais de um grupo em formato JSON
    """
    try:
        grupo = GrupoMaterial.query.get_or_404(id)
        search = request.args.get('search', '').strip()
        
        # Query para materiais do grupo usando SQL direto
        if search:
            sql = """
                SELECT m.id FROM materiais m 
                INNER JOIN materiais_grupos mg ON m.id = mg.material_id 
                WHERE mg.grupo_id = :grupo_id 
                AND (m.nome LIKE :search OR m.codigo LIKE :search OR m.descricao LIKE :search)
                ORDER BY m.nome
            """
            material_ids = db.session.execute(
                db.text(sql), 
                {'grupo_id': grupo.id, 'search': f'%{search}%'}
            ).fetchall()
        else:
            sql = """
                SELECT m.id FROM materiais m 
                INNER JOIN materiais_grupos mg ON m.id = mg.material_id 
                WHERE mg.grupo_id = :grupo_id 
                ORDER BY m.nome
            """
            material_ids = db.session.execute(
                db.text(sql), 
                {'grupo_id': grupo.id}
            ).fetchall()
        
        # Buscar os materiais pelos IDs
        if material_ids:
            ids = [row[0] for row in material_ids]
            materiais = Material.query.filter(Material.id.in_(ids)).order_by(Material.nome).all()
        else:
            materiais = []
        
        materiais_data = []
        for material in materiais:
            materiais_data.append({
                'id': material.id,
                'codigo': material.codigo or '',
                'nome': material.nome,
                'categoria': material.categoria or '',
                'unidade': material.unidade_obj.nome if material.unidade_obj else '',
                'ativo': material.ativo
            })
        
        return jsonify({
            'success': True,
            'grupo': {
                'id': grupo.id,
                'nome': grupo.nome,
                'codigo': grupo.codigo or '',
                'descricao': grupo.descricao or '',
                'cor': grupo.cor or '',
                'icone': grupo.icone or ''
            },
            'materiais': materiais_data,
            'total': len(materiais_data)
        })
    
    except Exception as e:
        logger.error(f"Erro na API de materiais do grupo {id}: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro ao listar materiais do grupo'})
