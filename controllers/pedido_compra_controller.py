import base64
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required
from sqlalchemy import func, or_

from models.database import db
from models.fornecedor import Fornecedor
from models.material import Materiais
from models.pedido_compra import PedidoCompra, PedidoCompraItem, PedidoCompraEntrada
from models.upload import Upload
from models.centro_custo import CentroCusto


pedido_compra_bp = Blueprint('pedido_compra', __name__)


def _normalizar_cnpj(value: str) -> str:
    if not value:
        return ''
    return ''.join([c for c in str(value) if c.isdigit()])


@pedido_compra_bp.route('/')
@login_required
def index():
    return render_template('pedidos_compra/index.html')


@pedido_compra_bp.route('/visualizar/<int:id>')
@login_required
def visualizar(id):
    pedido = PedidoCompra.query.get_or_404(id)
    return render_template('pedidos_compra/visualizar.html', pedido=pedido)


@pedido_compra_bp.route('/datatables', methods=['POST'])
@login_required
def datatables():
    draw = int(request.form.get('draw', 1))
    start = int(request.form.get('start', 0))
    length = int(request.form.get('length', 10))
    search_value = request.form.get('search[value]', '').strip()

    query = PedidoCompra.query.join(Fornecedor, PedidoCompra.fornecedor_id == Fornecedor.id)

    records_total = query.count()

    if search_value:
        query = query.filter(
            or_(
                PedidoCompra.numero.like(f'%{search_value}%'),
                Fornecedor.nome.like(f'%{search_value}%'),
                Fornecedor.cnpj.like(f'%{search_value}%'),
            )
        )

    records_filtered = query.count()

    # Ordenação
    order_col_index = request.form.get('order[0][column]', '0')
    order_dir = request.form.get('order[0][dir]', 'asc')
    col_map = {
        '0': PedidoCompra.numero,
        '1': Fornecedor.nome,
        '2': PedidoCompra.data_liberacao,
    }
    order_col = col_map.get(str(order_col_index), PedidoCompra.numero)
    if order_dir == 'desc':
        query = query.order_by(order_col.desc())
    else:
        query = query.order_by(order_col.asc())

    pedidos = query.offset(start).limit(length).all()

    data = []
    for p in pedidos:
        data.append(p.to_dict(incluir_itens=True))

    return jsonify({
        'draw': draw,
        'recordsTotal': records_total,
        'recordsFiltered': records_filtered,
        'data': data,
    })


@pedido_compra_bp.route('/get', methods=['GET'])
@login_required
def get():
    pedido_id = request.args.get('id', type=int)
    if not pedido_id:
        return jsonify({'error': 'ID não informado'}), 400
    pedido = PedidoCompra.query.get_or_404(pedido_id)
    return jsonify(pedido.to_dict(incluir_itens=True))


@pedido_compra_bp.route('/salvar', methods=['POST'])
@login_required
def salvar():
    pedido_id = request.form.get('id', type=int)
    numero = (request.form.get('numero') or '').strip()
    fornecedor_id = request.form.get('fornecedor_id', type=int)
    centro_custo_id = request.form.get('centro_custo_id', type=int)
    data_liberacao_raw = (request.form.get('data_liberacao') or '').strip()

    if not numero or not fornecedor_id:
        return jsonify({'success': False, 'message': 'Número e fornecedor são obrigatórios.'}), 400

    # Parse data
    data_liberacao = None
    if data_liberacao_raw:
        try:
            data_liberacao = datetime.strptime(data_liberacao_raw, '%Y-%m-%d')
        except ValueError:
            data_liberacao = None

    try:
        # Verificar número duplicado sem forçar autoflush
        with db.session.no_autoflush:
            q_dup = PedidoCompra.query.filter(PedidoCompra.numero == numero)
            if pedido_id:
                q_dup = q_dup.filter(PedidoCompra.id != pedido_id)
            if q_dup.first():
                return jsonify({'success': False, 'message': 'Já existe um pedido com este número.'}), 400

        # Criar/atualizar pedido
        if pedido_id:
            pedido = PedidoCompra.query.get_or_404(pedido_id)
        else:
            pedido = PedidoCompra()
            db.session.add(pedido)

        pedido.numero = numero
        pedido.fornecedor_id = fornecedor_id
        pedido.centro_custo_id = centro_custo_id if centro_custo_id else None
        pedido.data_liberacao = data_liberacao

        db.session.flush()

        # Itens (listas por chave repetida)
        materiais_ids = request.form.getlist('itens[][material_id]')
        unidades = request.form.getlist('itens[][unidade]')
        quantidades = request.form.getlist('itens[][quantidade]')
        valores = request.form.getlist('itens[][valor_unitario]')

        # Limpar itens existentes e recriar (simples e previsível)
        PedidoCompraItem.query.filter_by(pedido_id=pedido.id).delete()
        db.session.flush()

        total_itens = max(len(materiais_ids), len(quantidades), len(valores), len(unidades))
        for i in range(total_itens):
            material_id = int(materiais_ids[i]) if i < len(materiais_ids) and str(materiais_ids[i]).strip() else None
            if not material_id:
                continue

            unidade = unidades[i] if i < len(unidades) else None

            try:
                quantidade = Decimal(str(quantidades[i])) if i < len(quantidades) and str(quantidades[i]).strip() else Decimal('0')
            except Exception:
                quantidade = Decimal('0')

            try:
                valor_unitario = Decimal(str(valores[i])) if i < len(valores) and str(valores[i]).strip() else Decimal('0')
            except Exception:
                valor_unitario = Decimal('0')

            item = PedidoCompraItem(
                pedido_id=pedido.id,
                material_id=material_id,
                unidade=unidade,
                quantidade=quantidade,
                valor_unitario=valor_unitario,
            )
            db.session.add(item)

        # Anexos: criar Uploads (pai='PedidoCompra')
        arquivos = request.files.getlist('anexos')
        for i, file in enumerate(arquivos):
            if not file or not getattr(file, 'filename', None):
                continue
            filename = file.filename
            mimetype = file.mimetype or 'application/octet-stream'
            blob_bytes = file.read()
            filename = 'PedidoCompra_'+str(pedido.id)+'_'+str(i+1)+'.pdf'
            Upload(pai='PedidoCompra', pai_id=pedido.id, tipo=7, filename=filename, mimetype=mimetype, blob=blob_bytes)
            

        db.session.commit()
        return jsonify({'success': True, 'id': pedido.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@pedido_compra_bp.route('/excluir', methods=['POST'])
@login_required
def excluir():
    data = request.get_json(silent=True) or {}
    pedido_id = data.get('id')
    if not pedido_id:
        return jsonify({'success': False, 'message': 'ID não informado.'}), 400

    pedido = PedidoCompra.query.get_or_404(int(pedido_id))
    try:
        # Remover anexos
        Upload.query.filter_by(pai='PedidoCompra', pai_id=pedido.id).delete()
        # Itens com cascade também; mas garantimos deletando o pedido
        db.session.delete(pedido)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@pedido_compra_bp.route('/fornecedores', methods=['GET'])
@login_required
def fornecedores():
    fornecedores = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome).all()
    return jsonify({
        'fornecedores': [{
            'id': f.id,
            'nome': f.nome,
            'cnpj': f.cnpj,
        } for f in fornecedores]
    })


@pedido_compra_bp.route('/centros-custo', methods=['GET'])
@login_required
def centros_custo():
    centros = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.codigo).all()
    return jsonify({
        'centros_custo': [{
            'id': c.id,
            'codigo': c.codigo,
            'nome': c.nome,
        } for c in centros]
    })


@pedido_compra_bp.route('/materiais', methods=['GET'])
@login_required
def materiais():
    materiais = Materiais.query.filter_by(ativo=True).order_by(Materiais.nome).all()
    return jsonify([m.to_dict() for m in materiais])


@pedido_compra_bp.route('/anexo/<int:anexo_id>/download', methods=['GET'])
@login_required
def download_anexo(anexo_id):
    upload = Upload.query.get_or_404(anexo_id)
    if upload.pai != 'PedidoCompra':
        return jsonify({'error': 'Anexo inválido'}), 404

    blob = upload.get_blob()
    if not blob:
        return jsonify({'error': 'Arquivo não encontrado'}), 404

    return send_file(
        BytesIO(blob),
        download_name=upload.filename,
        mimetype=upload.mimetype,
        as_attachment=True,
    )


@pedido_compra_bp.route('/api/pedidos-disponiveis', methods=['GET'])
@login_required
def api_pedidos_disponiveis():
    """
    Retorna pedidos de compra disponíveis para um fornecedor (por CNPJ),
    considerando apenas pedidos com pelo menos um item com saldo > 0.
    """
    cnpj = _normalizar_cnpj(request.args.get('cnpj') or '')
    if not cnpj:
        return jsonify({'success': True, 'pedidos': []})

    fornecedor = Fornecedor.query.filter(Fornecedor.cnpj == cnpj).first()
    if not fornecedor:
        return jsonify({'success': True, 'pedidos': []})

    pedidos = PedidoCompra.query.filter_by(fornecedor_id=fornecedor.id).order_by(PedidoCompra.id.desc()).all()

    pedidos_disponiveis = []
    for p in pedidos:
        itens = p.itens.all()
        tem_saldo = any([(it.get_saldo() or 0) > 0 for it in itens])
        if tem_saldo:
            pedidos_disponiveis.append({
                'id': p.id,
                'numero': p.numero,
                'fornecedor_id': p.fornecedor_id,
                'fornecedor_nome': fornecedor.nome,
            })

    return jsonify({'success': True, 'pedidos': pedidos_disponiveis})


@pedido_compra_bp.route('/api/itens-disponiveis', methods=['GET'])
@login_required
def api_itens_disponiveis():
    """
    Retorna itens com saldo > 0 para um pedido de compra.
    """
    pedido_id = request.args.get('pedido_id', type=int)
    if not pedido_id:
        return jsonify({'success': True, 'itens': []})

    pedido = PedidoCompra.query.get_or_404(pedido_id)
    itens = []
    for it in pedido.itens.all():
        entradas_total = it.get_quantidade_entrada_total()
        saldo = it.get_saldo()
        if (saldo or 0) <= 0:
            continue
        itens.append({
            'id': it.id,
            'material_id': it.material_id,
            'material_nome': it.material.nome if it.material else None,
            'unidade': it.unidade,
            'quantidade': float(it.quantidade) if it.quantidade is not None else 0.0,
            'entradas_total': float(entradas_total) if entradas_total is not None else 0.0,
            'saldo': float(saldo) if saldo is not None else 0.0,
        })

    return jsonify({'success': True, 'itens': itens})


@pedido_compra_bp.route('/item/<int:item_id>/definir-saldo', methods=['POST'])
@login_required
def definir_saldo_item(item_id):
    """
    Define a quantidade já entregue inicial do item (ajusta o saldo disponível).
    Espera: csrf_token, quantidade_entregue_inicial (opcional, default 0).
    """
    item = PedidoCompraItem.query.get_or_404(item_id)
    try:
        qtd_str = request.form.get('quantidade_entregue_inicial') or (request.get_json(silent=True) or {}).get('quantidade_entregue_inicial')
    except Exception:
        qtd_str = None
    if qtd_str is None or (isinstance(qtd_str, str) and not qtd_str.strip()):
        quantidade_entregue_inicial = Decimal('0')
    else:
        try:
            quantidade_entregue_inicial = Decimal(str(qtd_str))
        except Exception:
            return jsonify({'success': False, 'message': 'Quantidade entregue inicial inválida.'}), 400
    if quantidade_entregue_inicial < 0:
        return jsonify({'success': False, 'message': 'Quantidade entregue inicial não pode ser negativa.'}), 400
    total_entradas = item.get_quantidade_entrada_total()
    # total_entradas já inclui quantidade_entregue_inicial atual; para checar limite use apenas entradas registradas
    entradas_registradas = float(
        db.session.query(func.coalesce(func.sum(PedidoCompraEntrada.quantidade_entrada), 0))
        .filter(PedidoCompraEntrada.pedido_item_id == item.id)
        .scalar() or 0
    )
    max_inicial = float(item.quantidade or 0) - entradas_registradas
    if quantidade_entregue_inicial > max_inicial:
        return jsonify({
            'success': False,
            'message': f'Quantidade entregue inicial não pode ser maior que {max_inicial} (quantidade do item menos entradas já registradas).'
        }), 400
    item.quantidade_entregue_inicial = quantidade_entregue_inicial
    db.session.add(item)
    db.session.commit()
    saldo = item.get_saldo()
    return jsonify({
        'success': True,
        'message': 'Saldo do item atualizado.',
        'quantidade_entregue_inicial': float(item.quantidade_entregue_inicial or 0),
        'saldo': float(saldo),
    })

