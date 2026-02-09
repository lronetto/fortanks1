from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import or_
import json

from models.database import db
from models.contrato import Contrato
from models.centro_custo import CentroCusto
from models.cliente import Cliente

contrato_bp = Blueprint('contrato', __name__)

# Middleware para verificar se o usuário tem permissão
@contrato_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_gerente_ou_superior:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@contrato_bp.route('/')
def index():
    """
    Lista todos os contratos
    """
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    clientes = Cliente.query.filter_by(ativo=True).all()
    return render_template('contratos/index.html', centros_custo=centros_custo, clientes=clientes)

@contrato_bp.route('/api/datatables', methods=['GET'])
def api_datatables():
    """
    Endpoint AJAX para DataTables - retorna dados de contratos em formato JSON
    """
    try:
        # Parâmetros do DataTables
        draw = request.args.get('draw', 1, type=int)
        start = request.args.get('start', 0, type=int)
        length = request.args.get('length', 25, type=int)
        search_value = request.args.get('search[value]', '', type=str).strip()
        
        # Parâmetros de ordenação
        order_column_index = int(request.args.get('order[0][column]', 0))
        order_dir = request.args.get('order[0][dir]', 'desc')
        
        # Mapear índice da coluna para campo de ordenação
        column_mapping = {
            0: Contrato.id,
            1: Contrato.nome,
            2: CentroCusto.codigo,
            3: Contrato.cliente_direto_id,
            4: Contrato.cidade,
            5: Contrato.valor_total,
            6: Contrato.data_base
        }
        
        # Query base com joins necessários
        query = Contrato.query.join(CentroCusto, Contrato.centro_custo_id == CentroCusto.id)\
            .options(db.joinedload(Contrato.centro_custo), 
                    db.joinedload(Contrato.cliente_direto),
                    db.joinedload(Contrato.cliente_final))
        
        # Aplicar busca
        if search_value:
            query = query.filter(
                or_(
                    Contrato.nome.ilike(f'%{search_value}%'),
                    Contrato.cidade.ilike(f'%{search_value}%'),
                    Contrato.estado.ilike(f'%{search_value}%'),
                    CentroCusto.codigo.ilike(f'%{search_value}%'),
                    CentroCusto.nome.ilike(f'%{search_value}%')
                )
            )
        
        # Contar total de registros (antes da paginação)
        total_records = Contrato.query.count()
        records_filtered = query.count()
        
        # Aplicar ordenação
        order_column = column_mapping.get(order_column_index, Contrato.id)
        if order_dir == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
        
        # Aplicar paginação
        contratos = query.offset(start).limit(length).all()
        
        # Formatar dados para o DataTables
        data = []
        for contrato in contratos:
            # Formatar valor total
            valor_total_formatado = f"R$ {float(contrato.valor_total):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            
            # Formatar data base
            data_base_formatada = ''
            if contrato.data_base:
                data_base_formatada = contrato.data_base.strftime('%d/%m/%Y')
            
            # Cliente direto
            cliente_direto_nome = contrato.cliente_direto.nome if contrato.cliente_direto else '-'
            
            # Centro de custo
            centro_custo_texto = f"{contrato.centro_custo.codigo} - {contrato.centro_custo.nome}" if contrato.centro_custo else '-'
            
            # Local
            local_texto = f"{contrato.cidade}/{contrato.estado}" if contrato.cidade and contrato.estado else '-'
            
            # HTML das ações
            acoes_html = f'''
                <div class="btn-group" role="group">
                    <a href="{url_for('contrato.visualizar', id=contrato.id)}" 
                       class="btn btn-sm btn-info" data-bs-toggle="tooltip" title="Visualizar">
                        <i class="fas fa-eye"></i>
                    </a>
                    <button type="button" class="btn btn-sm btn-primary btn-editar-contrato" 
                            data-id="{contrato.id}" data-bs-toggle="tooltip" title="Editar">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-danger btn-excluir-contrato" 
                            data-id="{contrato.id}" data-nome="{contrato.nome}" data-bs-toggle="tooltip" title="Excluir">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            '''
            
            data.append({
                'id': contrato.id,
                'nome': contrato.nome,
                'centro_custo': centro_custo_texto,
                'cliente': cliente_direto_nome,
                'local': local_texto,
                'valor_total': valor_total_formatado,
                'data_base': data_base_formatada,
                'acoes': acoes_html,
                # Dados para edição
                'descricao': contrato.descricao or '',
                'centro_custo_id': contrato.centro_custo_id,
                'cliente_direto_id': contrato.cliente_direto_id or '',
                'cliente_final_id': contrato.cliente_final_id or '',
                'estado': contrato.estado or '',
                'cidade': contrato.cidade or '',
                'data_base_value': contrato.data_base.strftime('%Y-%m-%d') if contrato.data_base else '',
                'valor_mat': float(contrato.valor_mat) if contrato.valor_mat else 0,
                'valor_ser': float(contrato.valor_ser) if contrato.valor_ser else 0
            })
        
        return jsonify({
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': records_filtered,
            'data': data
        })
        
    except Exception as e:
        return jsonify({
            'draw': request.args.get('draw', 1, type=int),
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e)
        }), 500

@contrato_bp.route('/novo', methods=['GET', 'POST'])
def novo():
    """
    Cria um novo contrato
    """
    # Busca todos os centros de custo ativos para o formulário
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    
    # Busca todos os clientes ativos para o formulário
    clientes = Cliente.query.filter_by(ativo=True).all()
    
    if request.method == 'POST':
        centro_custo_id = request.form.get('centro_custo_id')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        estado = request.form.get('estado')
        cidade = request.form.get('cidade')
        cliente_direto_id = request.form.get('cliente_direto_id')
        cliente_final_id = request.form.get('cliente_final_id')
        valor_material = request.form.get('venda_material', '0')
        valor_servico = request.form.get('venda_servico', '0')
        data_base = request.form.get('data_base', '0')
        cnpjs_associados = request.form.get('cnpjs_associados', '[]')
        
        # Validação básica
        if not centro_custo_id or not nome:
            flash('Por favor, preencha todos os campos obrigatórios.', 'danger')
            return render_template('contratos/novo.html', centros_custo=centros_custo, clientes=clientes)
        
        # Criar o novo contrato
        try:
            contrato = Contrato()
            contrato.centro_custo_id = centro_custo_id
            contrato.nome = nome
            contrato.descricao = descricao
            contrato.estado = estado
            contrato.cidade = cidade
            contrato.cliente_direto_id = cliente_direto_id if cliente_direto_id else None
            contrato.cliente_final_id = cliente_final_id if cliente_final_id else None
            # Processar data_base
            if data_base and data_base != '0':
                try:
                    contrato.data_base = datetime.strptime(data_base, '%Y-%m-%d')
                except:
                    contrato.data_base = None
            else:
                contrato.data_base = None
            
            # Converter valores de string para números
            valor_material = valor_material.replace('R$', '').replace('.', '').replace(',', '.').strip() if valor_material else '0'
            valor_servico = valor_servico.replace('R$', '').replace('.', '').replace(',', '.').strip() if valor_servico else '0'
            
            valor_material_float = float(valor_material)
            valor_servico_float = float(valor_servico)
            
            contrato.valor_mat = valor_material_float
            contrato.valor_ser = valor_servico_float
            # Calcular o valor total somando os valores de material e serviço
            contrato.valor_total = valor_material_float + valor_servico_float
            
            # Processar CNPJs associados (armazenar como JSON na coluna conf)
            try:
                cnpjs_list = json.loads(cnpjs_associados) if cnpjs_associados else []
                if isinstance(cnpjs_list, list) and len(cnpjs_list) > 0:
                    contrato.conf = json.dumps({'cnpjs_associados': cnpjs_list})
                else:
                    contrato.conf = None
            except:
                contrato.conf = None
            
            # Outros campos aqui...
            
            db.session.add(contrato)
            db.session.commit()
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': 'Contrato criado com sucesso!',
                    'contrato_id': contrato.id
                })
            
            flash('Contrato criado com sucesso!', 'success')
            return redirect(url_for('contrato.index'))
        except Exception as e:
            db.session.rollback()
            error_msg = f'Erro ao criar contrato: {str(e)}'
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
            
            flash(error_msg, 'danger')
    
    # Verificar se é requisição AJAX (GET)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'centros_custo': [{'id': cc.id, 'codigo': cc.codigo, 'nome': cc.nome} for cc in centros_custo],
            'clientes': [{'id': c.id, 'nome': c.nome, 'cnpj': c.cnpj} for c in clientes]
        })
    
    return render_template('contratos/novo.html', centros_custo=centros_custo, clientes=clientes)

@contrato_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """
    Edita um contrato existente
    """
    contrato = Contrato.query.get_or_404(id)
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    clientes = Cliente.query.filter_by(ativo=True).all()
    if request.method == 'POST':
        print(f'request.form: {request.form}');
        centro_custo_id = request.form.get('centro_custo_id')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        estado = request.form.get('estado')
        cidade = request.form.get('cidade')
        cliente_direto_id = request.form.get('cliente_direto_id')
        cliente_final_id = request.form.get('cliente_final_id')
        data_base = request.form.get('data_base', '0')
        cnpjs_associados = request.form.get('cnpjs_associados', '[]')
        # Validação básica
        if not centro_custo_id or not nome:
            flash('Por favor, preencha todos os campos obrigatórios.', 'danger')
            return render_template('contratos/editar.html', contrato=contrato, centros_custo=centros_custo, clientes=clientes)
        
        try:
            contrato.centro_custo_id = centro_custo_id
            contrato.nome = nome
            contrato.descricao = descricao
            contrato.estado = estado
            contrato.cidade = cidade
            contrato.cliente_direto_id = cliente_direto_id if cliente_direto_id else None
            contrato.cliente_final_id = cliente_final_id if cliente_final_id else None
            # Processar data_base
            if data_base and data_base != '0':
                try:
                    contrato.data_base = datetime.strptime(data_base, '%Y-%m-%d')
                except:
                    contrato.data_base = None
            else:
                contrato.data_base = None
            
            # Obter e processar os valores monetários
            valor_material = request.form.get('venda_material', '0')
            valor_servico = request.form.get('venda_servico', '0')
            
            # Converter valores de string para números
            valor_material = valor_material.replace('R$', '').replace('.', '').replace(',', '.').strip() if valor_material else '0'
            valor_servico = valor_servico.replace('R$', '').replace('.', '').replace(',', '.').strip() if valor_servico else '0'
            
            valor_material_float = float(valor_material)
            valor_servico_float = float(valor_servico)
            
            contrato.valor_mat = valor_material_float
            contrato.valor_ser = valor_servico_float
            # Calcular o valor total somando os valores de material e serviço
            contrato.valor_total = valor_material_float + valor_servico_float

            # Outros campos aqui...
            contrato.conf = json.dumps({'cnpjs_associados': cnpjs_associados})
            db.session.commit()
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': 'Contrato atualizado com sucesso!',
                    'contrato_id': contrato.id
                })
            
            flash('Contrato atualizado com sucesso!', 'success')
            return redirect(url_for('contrato.index'))
        except Exception as e:
            db.session.rollback()
            error_msg = f'Erro ao atualizar contrato: {str(e)}'
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
            
            flash(error_msg, 'danger')
    
    # Verificar se é requisição AJAX (GET)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Processar CNPJs associados da coluna conf
        cnpjs_associados = []
        if contrato.conf:
            try:
                conf_data = json.loads(contrato.conf)
                if isinstance(conf_data, dict) and 'cnpjs_associados' in conf_data:
                    cnpjs_associados = conf_data['cnpjs_associados']
            except:
                pass
        
        return jsonify({
            'contrato': {
                'id': contrato.id,
                'nome': contrato.nome,
                'descricao': contrato.descricao or '',
                'centro_custo_id': contrato.centro_custo_id,
                'cliente_direto_id': contrato.cliente_direto_id or '',
                'cliente_final_id': contrato.cliente_final_id or '',
                'estado': contrato.estado or '',
                'cidade': contrato.cidade or '',
                'data_base': contrato.data_base.strftime('%Y-%m-%d') if contrato.data_base else '',
                'valor_mat': float(contrato.valor_mat) if contrato.valor_mat else 0,
                'valor_ser': float(contrato.valor_ser) if contrato.valor_ser else 0,
                'cnpjs_associados': json.dumps(cnpjs_associados) if cnpjs_associados else ''
            },
            'centros_custo': [{'id': cc.id, 'codigo': cc.codigo, 'nome': cc.nome} for cc in centros_custo],
            'clientes': [{'id': c.id, 'nome': c.nome, 'cnpj': c.cnpj} for c in clientes]
        })
    
    return render_template('contratos/editar.html', contrato=contrato, centros_custo=centros_custo, clientes=clientes)

@contrato_bp.route('/visualizar/<int:id>')
def visualizar(id):
    """
    Visualiza os detalhes de um contrato
    """
    contrato = Contrato.query.get_or_404(id)
    return render_template('contratos/visualizar.html', contrato=contrato)

@contrato_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """
    Exclui um contrato
    """
    contrato = Contrato.query.get_or_404(id)
    
    try:
        # Aqui você pode adicionar verificações adicionais antes de excluir
        nome_contrato = contrato.nome
        
        db.session.delete(contrato)
        db.session.commit()
        
        # Verificar se é requisição AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Contrato "{nome_contrato}" excluído com sucesso!'
            })
        
        flash(f'Contrato "{nome_contrato}" excluído com sucesso.', 'success')
        return redirect(url_for('contrato.index'))
    except Exception as e:
        db.session.rollback()
        error_msg = f'Erro ao excluir contrato: {str(e)}'
        
        # Verificar se é requisição AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        flash(error_msg, 'danger')
        return redirect(url_for('contrato.index')) 