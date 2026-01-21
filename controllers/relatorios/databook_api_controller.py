from flask import Blueprint, request, jsonify
from flask_login import login_required
from models.tanque import Tanques, TanquesGrupos

# Blueprint para APIs compartilhadas do DataBook
databook_api_bp = Blueprint('databook_api', __name__, url_prefix='/relatorios/databook/api')

@databook_api_bp.route('/tanques')
@login_required
def api_tanques():
    """
    API para retornar tanques filtrados por projeto e grupo
    Endpoint compartilhado para todos os relatórios do DataBook
    """
    contrato_id = request.args.get('contrato_id', type=int)
    grupo_id = request.args.get('grupo_id', type=int)
    
    query = Tanques.query
    
    if contrato_id:
        query = query.filter_by(contrato_id=contrato_id)
    
    if grupo_id:
        # Filtrar por grupo de tanques
        grupo = TanquesGrupos.query.get(grupo_id)
        if grupo and grupo.tanques:
            tanque_ids_grupo = [tanque.id for tanque in grupo.tanques]
            query = query.filter(Tanques.id.in_(tanque_ids_grupo))
    
    tanques = query.order_by(Tanques.nome).all()
    
    tanques_json = [{
        'id': tanque.id,
        'nome': tanque.nome
    } for tanque in tanques]
    
    return jsonify({'tanques': tanques_json})

@databook_api_bp.route('/grupos')
@login_required
def api_grupos():
    """
    API para retornar grupos de tanques filtrados por projeto
    Endpoint compartilhado para todos os relatórios do DataBook
    """
    contrato_id = request.args.get('contrato_id', type=int)
    
    # Buscar todos os grupos
    grupos = TanquesGrupos.query.order_by(TanquesGrupos.nome).all()
    
    grupos_filtrados = []
    for grupo in grupos:
        # Se há filtro de projeto, verificar se o grupo tem tanques desse projeto
        if contrato_id:
            tanques_do_projeto = [t for t in grupo.tanques if t.contrato_id == contrato_id]
            if tanques_do_projeto:
                grupos_filtrados.append({
                    'id': grupo.id,
                    'nome': grupo.nome
                })
        else:
            # Sem filtro, retornar todos os grupos
            grupos_filtrados.append({
                'id': grupo.id,
                'nome': grupo.nome
            })
    
    return jsonify({'grupos': grupos_filtrados})
