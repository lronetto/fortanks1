from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import or_, func
import json

from models.database import db
from models.contrato import Contrato
from models.centro_custo import CentroCusto
from models.cliente import Cliente
from models.dados_analiticos import (
    DadoAnalitico,
    PL_0207,
    PL_CONTA_ROYALTIES,
    PL_CONTA_INVESTIMENTOS,
)
from models.tanque import Tanques
from models.nota_fiscal import NotaFiscal, NotaFiscalItem, CFOPS_VENDA
from utils.decorators import criar_verificacao_permissao

contrato_bp = Blueprint('contrato', __name__)
contrato_bp.before_request(login_required(criar_verificacao_permissao('gerente')))


def _float_form_br(form, field: str, default: float = 0.0) -> float:
    """Converte valor monetário no padrão do formulário (R$ 1.234,56) para float."""
    raw = (form.get(field) or '').strip()
    if not raw:
        return default
    raw = raw.replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _indicadores_from_form(form) -> dict:
    return {
        'material': {
            'venda': _float_form_br(form, 'fin_mat_venda'),
            'custo': _float_form_br(form, 'fin_mat_custo'),
        },
        'servico': {
            'venda': _float_form_br(form, 'fin_ser_venda'),
            'custo': _float_form_br(form, 'fin_ser_custo'),
        },
        'geral': {
            'impostos': _float_form_br(form, 'fin_ger_impostos'),
            'royalties': _float_form_br(form, 'fin_ger_royalties'),
            'investimentos': _float_form_br(form, 'fin_ger_investimentos'),
        },
    }


def _safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _indicadores_para_api(contrato: Contrato) -> dict:
    """Lê indicadores de conf ou usa valor_mat/valor_ser como venda padrão."""
    base_mat = float(contrato.valor_mat) if contrato.valor_mat is not None else 0.0
    base_ser = float(contrato.valor_ser) if contrato.valor_ser is not None else 0.0
    out = {
        'material': {'venda': base_mat, 'custo': 0.0},
        'servico': {'venda': base_ser, 'custo': 0.0},
        'geral': {'impostos': 0.0, 'royalties': 0.0, 'investimentos': 0.0},
    }
    if not contrato.conf:
        return out
    try:
        conf_data = json.loads(contrato.conf)
        if not isinstance(conf_data, dict):
            return out
        ind = conf_data.get('indicadores')
        if not isinstance(ind, dict):
            return out
        for tipo in ('material', 'servico'):
            sub = ind.get(tipo)
            if not isinstance(sub, dict):
                continue
            for campo in ('venda', 'custo'):
                if campo in sub and sub[campo] is not None:
                    out[tipo][campo] = _safe_float(sub[campo])

        geral_saved = ind.get('geral')
        if isinstance(geral_saved, dict):
            for campo in ('impostos', 'royalties', 'investimentos'):
                if campo in geral_saved and geral_saved[campo] is not None:
                    out['geral'][campo] = _safe_float(geral_saved[campo])

        # Migração: layout antigo com impostos/royalties por material e serviço
        if not geral_saved:
            mat = ind.get('material') if isinstance(ind.get('material'), dict) else {}
            ser = ind.get('servico') if isinstance(ind.get('servico'), dict) else {}
            li = _safe_float(mat.get('impostos')) + _safe_float(ser.get('impostos'))
            lr = _safe_float(mat.get('royalties')) + _safe_float(ser.get('royalties'))
            if li:
                out['geral']['impostos'] = li
            if lr:
                out['geral']['royalties'] = lr
    except (json.JSONDecodeError, TypeError):
        pass
    return out


def _aditivos_from_form(form) -> list:
    """Lista de aditivos a partir do campo JSON `aditivos_json`."""
    raw = (form.get('aditivos_json') or '').strip() or '[]'
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        data_str = (item.get('data') or '').strip()[:32]
        desc = (item.get('descricao') or '').strip()[:4000]
        valor = _safe_float(item.get('valor'))
        if not data_str and not desc and valor == 0:
            continue
        out.append({'data': data_str, 'valor': valor, 'descricao': desc})
    return out


def _aditivos_para_api(contrato: Contrato) -> list:
    """Lê aditivos salvos em conf."""
    if not contrato.conf:
        return []
    try:
        conf_data = json.loads(contrato.conf)
        if not isinstance(conf_data, dict):
            return []
        ad = conf_data.get('aditivos')
        if not isinstance(ad, list):
            return []
        out = []
        for item in ad:
            if not isinstance(item, dict):
                continue
            out.append({
                'data': (item.get('data') or '').strip()[:32],
                'valor': _safe_float(item.get('valor')),
                'descricao': (item.get('descricao') or '').strip()[:4000],
            })
        return out
    except (json.JSONDecodeError, TypeError):
        return []


def _cnpjs_associados_contrato(contrato: Contrato) -> list:
    """CNPJs em conf.cnpjs_associados (mesma origem usada em relatórios de notas)."""
    if not contrato or not contrato.conf:
        return []
    try:
        conf_data = json.loads(contrato.conf)
        if not isinstance(conf_data, dict):
            return []
        raw = conf_data.get('cnpjs_associados') or []
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, list):
            return []
        return [str(x).strip() for x in raw if x]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _sum_valor_total_notas(nf_ids) -> float:
    if not nf_ids:
        return 0.0
    q = (
        db.session.query(func.coalesce(func.sum(NotaFiscal.valor_total), 0))
        .filter(
            NotaFiscal.id.in_(nf_ids),
            NotaFiscal.status_processamento != 'cancelada',
        )
    )
    return float(q.scalar() or 0)


def _nf_ids_venda_material_contrato(contrato_id: int) -> set:
    """
    NFe (tipo 0 ou 1): vínculo por item (CFOP venda) + tanque do contrato,
    ou por CNPJ destinatário nos cnpjs_associados quando não há vínculo por tanque
    (alinhado a controllers/relatorios/notas_controller._processar_notas_fiscais).
    """
    contrato = Contrato.query.get(contrato_id)
    if not contrato:
        return set()
    ids_tanque = set(
        row[0]
        for row in (
            db.session.query(NotaFiscal.id)
            .join(NotaFiscalItem, NotaFiscalItem.nf_id == NotaFiscal.id)
            .join(
                Tanques,
                Tanques.sql_codigo_nf_igual_item_nf_colunas(
                    NotaFiscalItem.codigo, Tanques.item_nf
                ),
            )
            .filter(
                Tanques.contrato_id == contrato_id,
                NotaFiscal.tipo.in_([0, 1]),
                NotaFiscal.status_processamento != 'cancelada',
                NotaFiscalItem.cfop.in_(CFOPS_VENDA),
            )
            .distinct()
            .all()
        )
    )
    cnpjs = _cnpjs_associados_contrato(contrato)
    ids_cnpj = set()
    if cnpjs:
        q2 = db.session.query(NotaFiscal.id).filter(
            NotaFiscal.tipo.in_([0, 1]),
            NotaFiscal.status_processamento != 'cancelada',
            NotaFiscal.cnpj_destinatario.in_(cnpjs),
        )
        if ids_tanque:
            q2 = q2.filter(~NotaFiscal.id.in_(ids_tanque))
        ids_cnpj.update(row[0] for row in q2.distinct().all())
    return ids_tanque | ids_cnpj


def _nf_ids_venda_servico_contrato(contrato_id: int) -> set:
    """NFSe (tipo 3): emitente ou destinatário nos CNPJs do contrato."""
    contrato = Contrato.query.get(contrato_id)
    if not contrato:
        return set()
    cnpjs = _cnpjs_associados_contrato(contrato)
    if not cnpjs:
        return set()
    return set(
        row[0]
        for row in (
            db.session.query(NotaFiscal.id)
            .filter(
                NotaFiscal.tipo == 3,
                NotaFiscal.status_processamento != 'cancelada',
                or_(
                    NotaFiscal.cnpj_emitente.in_(cnpjs),
                    NotaFiscal.cnpj_destinatario.in_(cnpjs),
                ),
            )
            .distinct()
            .all()
        )
    )


def _sum_executado_por_planos(centro_custo_id, plano_conta_ids: list) -> float:
    """Soma valores em DadosAnaliticos para o centro de custo e lista de planos de conta (ids)."""
    if not centro_custo_id or not plano_conta_ids:
        return 0.0
    from models.plano_conta import PlanoConta
    q = (
        db.session.query(func.coalesce(func.sum(DadoAnalitico.valor), 0))
        .join(PlanoConta, DadoAnalitico.plano_conta_id == PlanoConta.id)
        .filter(
            DadoAnalitico.centro_custo_id == centro_custo_id,
            PlanoConta.codigo.in_(plano_conta_ids),
        )
    )
    return float(q.scalar() or 0)


@contrato_bp.route('/')
def index():
    """
    Lista todos os contratos
    """
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    clientes = Cliente.query.filter_by(ativo=True).all()
    return render_template('cadastros/contratos/index.html', centros_custo=centros_custo, clientes=clientes)

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
            acoes_html = (
                f'<div class="ft-acoes-dropdown dropdown">'
                f'<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false" title="Ações"><i class="fas fa-ellipsis-v"></i></button>'
                f'<ul class="dropdown-menu dropdown-menu-end">'
                f'<li><a class="dropdown-item" href="{url_for("contrato.visualizar", id=contrato.id)}"><i class="fas fa-eye text-info"></i> Visualizar</a></li>'
                f'<li><button type="button" class="dropdown-item btn-editar-contrato" data-id="{contrato.id}"><i class="fas fa-edit text-primary"></i> Editar</button></li>'
                f'<li><button type="button" class="dropdown-item btn-resumo-orcado-exec" data-id="{contrato.id}"><i class="fas fa-balance-scale text-success"></i> Orçado x Executado</button></li>'
                f'<li><hr class="dropdown-divider"></li>'
                f'<li><button type="button" class="dropdown-item text-danger btn-excluir-contrato" data-id="{contrato.id}" data-nome="{contrato.nome}"><i class="fas fa-trash text-danger"></i> Excluir</button></li>'
                f'</ul></div>'
            )
            
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


@contrato_bp.route('/api/resumo-orcado-executado/<int:contrato_id>', methods=['GET'])
def api_resumo_orcado_executado(contrato_id):
    """
    Orçado (conf/indicadores) x executado.
    Vendas: soma de NotaFiscal (NFe vs NFSe conforme models/nota_fiscal e vínculo ao contrato).
    Demais linhas: DadosAnaliticos por centro de custo (PL_0207, contas 141 e 168).
    """
    contrato = Contrato.query.get_or_404(contrato_id)
    cc_id = contrato.centro_custo_id
    ind = _indicadores_para_api(contrato)

    exec_venda_mat = _sum_valor_total_notas(_nf_ids_venda_material_contrato(contrato_id))
    exec_venda_ser = _sum_valor_total_notas(_nf_ids_venda_servico_contrato(contrato_id))

    def linha(item, orcado, executado, ref):
        dif = executado - orcado
        return {
            'item': item,
            'orcado': round(orcado, 2),
            'executado': round(executado, 2),
            'diferenca': round(dif, 2),
            'ref_execucao': ref,
        }

    linhas = [
        linha(
            'Venda NF material',
            ind['material']['venda'],
            exec_venda_mat,
            'NFe (tipo 0/1): item+tanque ou CNPJ dest.',
        ),
        linha(
            'Venda NF serviço',
            ind['servico']['venda'],
            exec_venda_ser,
            'NFSe (tipo 3): CNPJ emit./dest. em conf',
        ),
        linha(
            'Impostos',
            ind['geral']['impostos'],
            _sum_executado_por_planos(cc_id, PL_0207),
            'PL_0207',
        ),
        linha(
            'Royalties',
            ind['geral']['royalties'],
            _sum_executado_por_planos(cc_id, PL_CONTA_ROYALTIES),
            'Conta 141',
        ),
        linha(
            'Investimentos',
            ind['geral']['investimentos'],
            _sum_executado_por_planos(cc_id, PL_CONTA_INVESTIMENTOS),
            'Conta 168',
        ),
    ]

    centro_txt = None
    if contrato.centro_custo:
        centro_txt = f"{contrato.centro_custo.codigo} - {contrato.centro_custo.nome}"

    return jsonify({
        'contrato_id': contrato.id,
        'contrato_nome': contrato.nome,
        'centro_custo_id': cc_id,
        'centro_custo': centro_txt,
        'sem_centro_custo': cc_id is None,
        'linhas': linhas,
    })


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
        data_base = request.form.get('data_base', '0')
        cnpjs_associados = request.form.get('cnpjs_associados', '[]')
        indicadores = _indicadores_from_form(request.form)
        aditivos = _aditivos_from_form(request.form)
        
        # Validação básica
        if not centro_custo_id or not nome:
            flash('Por favor, preencha todos os campos obrigatórios.', 'danger')
            return render_template('cadastros/contratos/novo.html', centros_custo=centros_custo, clientes=clientes)
        
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
            
            valor_material_float = indicadores['material']['venda']
            valor_servico_float = indicadores['servico']['venda']
            contrato.valor_mat = valor_material_float
            contrato.valor_ser = valor_servico_float
            contrato.valor_total = valor_material_float + valor_servico_float

            conf_data: dict = {'indicadores': indicadores}
            try:
                cnpjs_list = json.loads(cnpjs_associados) if cnpjs_associados else []
            except (json.JSONDecodeError, TypeError):
                cnpjs_list = []
            if isinstance(cnpjs_list, list) and len(cnpjs_list) > 0:
                conf_data['cnpjs_associados'] = cnpjs_list
            if aditivos:
                conf_data['aditivos'] = aditivos
            contrato.conf = json.dumps(conf_data)
            
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
    
    return render_template('cadastros/contratos/novo.html', centros_custo=centros_custo, clientes=clientes)

@contrato_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """
    Edita um contrato existente
    """
    contrato = Contrato.query.get_or_404(id)
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    clientes = Cliente.query.filter_by(ativo=True).all()
    if request.method == 'POST':
        centro_custo_id = request.form.get('centro_custo_id')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        estado = request.form.get('estado')
        cidade = request.form.get('cidade')
        cliente_direto_id = request.form.get('cliente_direto_id')
        cliente_final_id = request.form.get('cliente_final_id')
        data_base = request.form.get('data_base', '0')
        cnpjs_associados = request.form.get('cnpjs_associados', '[]')
        indicadores = _indicadores_from_form(request.form)
        aditivos = _aditivos_from_form(request.form)
        # Validação básica
        if not centro_custo_id or not nome:
            flash('Por favor, preencha todos os campos obrigatórios.', 'danger')
            return render_template('cadastros/contratos/editar.html', contrato=contrato, centros_custo=centros_custo, clientes=clientes)
        
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
            
            valor_material_float = indicadores['material']['venda']
            valor_servico_float = indicadores['servico']['venda']
            contrato.valor_mat = valor_material_float
            contrato.valor_ser = valor_servico_float
            contrato.valor_total = valor_material_float + valor_servico_float

            conf_data = {}
            if contrato.conf:
                try:
                    conf_data = json.loads(contrato.conf)
                    if not isinstance(conf_data, dict):
                        conf_data = {}
                except Exception:
                    conf_data = {}

            try:
                cnpjs_list = json.loads(cnpjs_associados) if cnpjs_associados else []
            except Exception:
                cnpjs_list = []

            if isinstance(cnpjs_list, list) and len(cnpjs_list) > 0:
                conf_data['cnpjs_associados'] = cnpjs_list
            else:
                conf_data.pop('cnpjs_associados', None)

            conf_data['indicadores'] = indicadores
            if aditivos:
                conf_data['aditivos'] = aditivos
            else:
                conf_data.pop('aditivos', None)
            contrato.conf = json.dumps(conf_data) if conf_data else None
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
        
        ind_api = _indicadores_para_api(contrato)
        aditivos_api = _aditivos_para_api(contrato)
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
                'indicadores': ind_api,
                'aditivos': aditivos_api,
                'cnpjs_associados': json.dumps(cnpjs_associados) if cnpjs_associados else ''
            },
            'centros_custo': [{'id': cc.id, 'codigo': cc.codigo, 'nome': cc.nome} for cc in centros_custo],
            'clientes': [{'id': c.id, 'nome': c.nome, 'cnpj': c.cnpj} for c in clientes]
        })
    
    return render_template('cadastros/contratos/editar.html', contrato=contrato, centros_custo=centros_custo, clientes=clientes)

@contrato_bp.route('/visualizar/<int:id>')
def visualizar(id):
    """
    Visualiza os detalhes de um contrato
    """
    contrato = Contrato.query.get_or_404(id)
    return render_template('cadastros/contratos/visualizar.html', contrato=contrato)

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