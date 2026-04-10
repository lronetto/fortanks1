import logging
from datetime import datetime
from decimal import Decimal

from flask import flash, render_template, request
from flask_login import login_required
from sqlalchemy import distinct, func, or_

from models.material import Materiais
from models.database import db
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.unidade import Unidades

from .. import nota_fiscal_bp

logger = logging.getLogger(__name__)


@nota_fiscal_bp.route("/analise")
@login_required
def analise():
    """Tela de análise de notas fiscais. Dados carregados via DataTables AJAX."""
    fornecedor = (request.args.get("fornecedor", "") or "").strip()
    data_inicio = (request.args.get("data_inicio", "") or "").strip()
    data_fim = (request.args.get("data_fim", "") or "").strip()
    termo_item = (request.args.get("termo_item", "") or "").strip()
    filtro_material = (request.args.get("filtro_material", "") or "").strip()
    agrupar_por = request.args.get("agrupar_por", "item_nf")

    fornecedores_lista = db.session.query(NotaFiscal.nome_emitente).distinct().order_by(NotaFiscal.nome_emitente).all()
    fornecedores = [f[0] for f in fornecedores_lista if f[0]]

    return render_template(
        "notas_fiscais/analise.html",
        fornecedores=fornecedores,
        filtro_fornecedor=fornecedor,
        filtro_data_inicio=data_inicio,
        filtro_data_fim=data_fim,
        filtro_termo_item=termo_item,
        filtro_material=filtro_material,
        agrupar_por=agrupar_por,
    )


def _build_analise_query(agrupar_por, fornecedor, data_inicio, data_fim, termo_item, filtro_material):
    """Monta a query agregada e aplica filtros comuns."""
    if agrupar_por == "material":
        query = (
            db.session.query(
                Materiais.id.label("material_id"),
                Materiais.nome.label("material_nome"),
                Unidades.nome.label("material_unidade"),
                func.sum(NotaFiscalItem.quantidade).label("quantidade_total"),
                func.sum(NotaFiscalItem.valor_total).label("valor_total_agregado"),
                func.group_concat(distinct(NotaFiscal.nome_emitente)).label("fornecedores"),
            )
            .join(NotaFiscalItem, Materiais.id == NotaFiscalItem.material_id)
            .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
            .outerjoin(Unidades, Unidades.id == Materiais.unidade_id)
            .filter(NotaFiscal.status_processamento != "cancelada")
        )
    else:
        query = (
            db.session.query(
                NotaFiscalItem.codigo,
                NotaFiscalItem.descricao,
                func.sum(NotaFiscalItem.quantidade).label("quantidade_total"),
                func.sum(NotaFiscalItem.valor_total).label("valor_total_agregado"),
                func.group_concat(distinct(NotaFiscal.nome_emitente)).label("fornecedores"),
                func.group_concat(distinct(Unidades.nome)).label("unidades"),
                func.group_concat(distinct(Materiais.nome)).label("materiais_vinculados"),
            )
            .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
            .outerjoin(Materiais, Materiais.id == NotaFiscalItem.material_id)
            .outerjoin(Unidades, Unidades.id == Materiais.unidade_id)
            .filter(NotaFiscal.status_processamento != "cancelada")
        )

    if fornecedor:
        query = query.filter(NotaFiscal.nome_emitente == fornecedor)
    if data_inicio:
        try:
            query = query.filter(NotaFiscal.data_emissao >= datetime.strptime(data_inicio, "%Y-%m-%d").date())
        except ValueError:
            pass
    if data_fim:
        try:
            query = query.filter(NotaFiscal.data_emissao <= datetime.strptime(data_fim, "%Y-%m-%d").date())
        except ValueError:
            pass
    if termo_item:
        termo_like = f"%{termo_item}%"
        query = query.filter(or_(NotaFiscalItem.codigo.ilike(termo_like), NotaFiscalItem.descricao.ilike(termo_like)))
    if filtro_material:
        query = query.filter(Materiais.nome.ilike(f"%{filtro_material}%"))

    return query


def _calc_total_geral(agrupar_por, fornecedor, data_inicio, data_fim, termo_item, filtro_material):
    """Calcula o valor total geral dos itens filtrados."""
    total_base = (
        db.session.query(func.sum(NotaFiscalItem.valor_total))
        .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
        .outerjoin(Materiais, Materiais.id == NotaFiscalItem.material_id)
        .filter(NotaFiscal.status_processamento != "cancelada")
    )
    if agrupar_por == "material":
        total_base = total_base.filter(NotaFiscalItem.material_id.isnot(None))
    if fornecedor:
        total_base = total_base.filter(NotaFiscal.nome_emitente == fornecedor)
    if data_inicio:
        try:
            total_base = total_base.filter(NotaFiscal.data_emissao >= datetime.strptime(data_inicio, "%Y-%m-%d").date())
        except ValueError:
            pass
    if data_fim:
        try:
            total_base = total_base.filter(NotaFiscal.data_emissao <= datetime.strptime(data_fim, "%Y-%m-%d").date())
        except ValueError:
            pass
    if termo_item:
        termo_like = f"%{termo_item}%"
        total_base = total_base.filter(or_(NotaFiscalItem.codigo.ilike(termo_like), NotaFiscalItem.descricao.ilike(termo_like)))
    if filtro_material:
        total_base = total_base.filter(Materiais.nome.ilike(f"%{filtro_material}%"))

    scalar = total_base.scalar()
    return float(scalar) if scalar is not None else 0.0


@nota_fiscal_bp.route("/analise/ajax")
@login_required
def analise_ajax():
    """Endpoint AJAX para DataTables server-side na tela de análise."""
    from flask import jsonify

    draw = request.args.get("draw", 1, type=int)
    start = request.args.get("start", 0, type=int)
    length = request.args.get("length", 25, type=int)
    search_value = (request.args.get("search[value]", "") or "").strip()

    agrupar_por = request.args.get("agrupar_por", "item_nf")
    fornecedor = (request.args.get("fornecedor", "") or "").strip()
    data_inicio = (request.args.get("data_inicio", "") or "").strip()
    data_fim = (request.args.get("data_fim", "") or "").strip()
    termo_item = (request.args.get("termo_item", "") or "").strip()
    filtro_material = (request.args.get("filtro_material", "") or "").strip()

    query = _build_analise_query(agrupar_por, fornecedor, data_inicio, data_fim, termo_item, filtro_material)

    if agrupar_por == "material":
        query = query.group_by(Materiais.id, Materiais.nome, Materiais.unidade_id)
    else:
        query = query.group_by(NotaFiscalItem.codigo, NotaFiscalItem.descricao)

    records_total_query = query.subquery()
    records_total = db.session.query(func.count()).select_from(records_total_query).scalar() or 0

    records_filtered = records_total

    if search_value:
        search_like = f"%{search_value}%"
        if agrupar_por == "material":
            query = query.having(
                or_(
                    Materiais.nome.ilike(search_like),
                    func.group_concat(distinct(NotaFiscal.nome_emitente)).ilike(search_like),
                )
            )
        else:
            query = query.having(
                or_(
                    NotaFiscalItem.codigo.ilike(search_like),
                    NotaFiscalItem.descricao.ilike(search_like),
                    func.group_concat(distinct(Materiais.nome)).ilike(search_like),
                    func.group_concat(distinct(NotaFiscal.nome_emitente)).ilike(search_like),
                )
            )
        filtered_sub = query.subquery()
        records_filtered = db.session.query(func.count()).select_from(filtered_sub).scalar() or 0

    order_col_idx = request.args.get("order[0][column]", type=int)
    order_dir = request.args.get("order[0][dir]", "desc")

    if agrupar_por == "material":
        col_map = {
            0: Materiais.nome,
            1: Unidades.nome,
            2: func.sum(NotaFiscalItem.quantidade),
            3: func.sum(NotaFiscalItem.valor_total),
            4: func.group_concat(distinct(NotaFiscal.nome_emitente)),
        }
    else:
        col_map = {
            0: NotaFiscalItem.codigo,
            1: NotaFiscalItem.descricao,
            2: func.group_concat(distinct(Materiais.nome)),
            3: func.sum(NotaFiscalItem.quantidade),
            4: func.group_concat(distinct(Unidades.nome)),
            5: func.sum(NotaFiscalItem.valor_total),
            6: func.group_concat(distinct(NotaFiscal.nome_emitente)),
        }

    order_column = col_map.get(order_col_idx, func.sum(NotaFiscalItem.valor_total))
    if order_dir == "asc":
        query = query.order_by(order_column.asc())
    else:
        query = query.order_by(order_column.desc())

    items = query.offset(start).limit(length).all()

    total_geral = _calc_total_geral(agrupar_por, fornecedor, data_inicio, data_fim, termo_item, filtro_material)

    data = []
    if agrupar_por == "material":
        for item in items:
            fornecedores_str = (item.fornecedores or "").replace(",", ", ") if item.fornecedores else "N/D"
            data.append([
                {
                    "nome": item.material_nome or "N/D",
                    "id": item.material_id,
                    "tipo": "material",
                },
                item.material_unidade or "N/D",
                f"{float(item.quantidade_total or 0):.2f}",
                f"{float(item.valor_total_agregado or 0):.2f}",
                fornecedores_str,
            ])
    else:
        for item in items:
            fornecedores_str = (item.fornecedores or "").replace(",", ", ") if item.fornecedores else "N/D"
            materiais_str = (item.materiais_vinculados or "").replace(",", ", ") if item.materiais_vinculados else "-"
            unidades_str = (item.unidades or "").replace(",", ", ") if item.unidades else "N/D"
            data.append([
                item.codigo or "N/D",
                {
                    "descricao": item.descricao or "N/D",
                    "codigo": item.codigo or "",
                    "tipo": "item_nf",
                },
                materiais_str,
                f"{float(item.quantidade_total or 0):.2f}",
                unidades_str,
                f"{float(item.valor_total_agregado or 0):.2f}",
                fornecedores_str,
            ])

    return jsonify({
        "draw": draw,
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
        "total_geral": f"{total_geral:.2f}",
    })


@nota_fiscal_bp.route("/analise-transferencias")
@login_required
def analise_transferencias():
    """
    Tela de análise de transferências (usada no menu).

    Obs: a versão completa (com cálculos por CNPJ, exportações e AJAX) existia no controller monolítico.
    Aqui mantemos uma implementação compatível para não quebrar navegação/URL.
    """
    page = request.args.get("page", 1, type=int)
    per_page = 25

    query = (
        db.session.query(
            NotaFiscal.numero_nf.label("numero_nf"),
            NotaFiscalItem.descricao.label("nome_item"),
            NotaFiscalItem.codigo.label("codigo_item"),
            NotaFiscal.cnpj_emitente,
            NotaFiscal.cnpj_destinatario,
            NotaFiscal.nome_emitente,
            NotaFiscal.nome_destinatario,
            NotaFiscal.tipo.label("tipo_nota"),
            NotaFiscalItem.quantidade,
            NotaFiscalItem.valor_total.label("valor"),
            NotaFiscal.data_emissao.label("data"),
        )
        .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
        .filter(NotaFiscal.status_processamento != "cancelada")
        .order_by(NotaFiscal.data_emissao.desc())
    )

    paginacao = query.paginate(page=page, per_page=per_page, error_out=False)
    transferencias = paginacao.items

    cnpjs_emitentes = [c[0] for c in db.session.query(NotaFiscal.cnpj_emitente).distinct().order_by(NotaFiscal.cnpj_emitente).all() if c[0]]
    cnpjs_destinatarios = [c[0] for c in db.session.query(NotaFiscal.cnpj_destinatario).distinct().order_by(NotaFiscal.cnpj_destinatario).all() if c[0]]

    materiais_vinculados = (
        db.session.query(Materiais)
        .join(NotaFiscalItem, Materiais.id == NotaFiscalItem.material_id)
        .filter(NotaFiscalItem.material_id.isnot(None))
        .distinct()
        .order_by(Materiais.nome)
        .all()
    )

    return render_template(
        "notas_fiscais/analise_transferencias.html",
        transferencias=transferencias,
        paginacao=paginacao,
        filtro_data_inicio=request.args.get("data_inicio", ""),
        filtro_data_fim=request.args.get("data_fim", ""),
        filtro_codigo_item=request.args.get("codigo_item", ""),
        filtro_nome_item=request.args.get("nome_item", ""),
        filtro_cnpj_emitente=request.args.getlist("cnpj_emitente"),
        filtro_cnpj_destinatario=request.args.getlist("cnpj_destinatario"),
        filtro_material_id=request.args.getlist("material_id"),
        cnpjs_emitentes=cnpjs_emitentes,
        cnpjs_destinatarios=cnpjs_destinatarios,
        materiais=materiais_vinculados,
    )


@nota_fiscal_bp.route("/analise-transferencias/ajax", methods=["GET", "POST"])
@login_required
def analise_transferencias_ajax():
    """
    Retorna apenas a tabela (HTML) para uso com AJAX.
    """
    # Para POST via AJAX (form urlencoded), os filtros vêm em request.form.
    # Para GET (fallback), vêm em request.args. `request.values` combina ambos.
    page = request.values.get("page", 1, type=int)
    per_page = 25

    # Filtros vindos do GET/POST (form). (ImmutableMultiDict não tem to_json)
    filtros = request.values.to_dict(flat=False)

    def _get_first(key, default=""):
        val = filtros.get(key, default)
        if isinstance(val, list):
            return val[0] if val else default
        return val

    def _get_list(key):
        val = filtros.get(key, [])
        if isinstance(val, list):
            return [v for v in val if v not in (None, "")]
        return [val] if val not in (None, "") else []

    data_inicio = (_get_first("data_inicio") or "").strip()
    data_fim = (_get_first("data_fim") or "").strip()
    codigo_item = (_get_first("codigo_item") or "").strip()
    nome_item = (_get_first("nome_item") or "").strip()
    cnpjs_emitente = _get_list("cnpj_emitente")
    cnpjs_destinatario = _get_list("cnpj_destinatario")
    materiais_ids = _get_list("material_id")
    query = (
        db.session.query(
            NotaFiscal.numero_nf.label("numero_nf"),
            NotaFiscalItem.descricao.label("nome_item"),
            NotaFiscalItem.codigo.label("codigo_item"),
            NotaFiscal.cnpj_emitente,
            NotaFiscal.cnpj_destinatario,
            NotaFiscal.nome_emitente,
            NotaFiscal.nome_destinatario,
            NotaFiscal.tipo.label("tipo_nota"),
            NotaFiscalItem.quantidade,
            NotaFiscalItem.valor_total.label("valor"),
            NotaFiscal.data_emissao.label("data"),
        )
        .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
        .filter(NotaFiscal.status_processamento != "cancelada")
    )

    if data_inicio:
        try:
            query = query.filter(NotaFiscal.data_emissao >= datetime.strptime(data_inicio, "%Y-%m-%d"))
        except Exception:
            pass
    if data_fim:
        try:
            query = query.filter(NotaFiscal.data_emissao <= datetime.strptime(data_fim, "%Y-%m-%d"))
        except Exception:
            pass
    if codigo_item:
        query = query.filter(NotaFiscalItem.codigo.ilike(f"%{codigo_item}%"))
    if nome_item:
        query = query.filter(NotaFiscalItem.descricao.ilike(f"%{nome_item}%"))
    if cnpjs_emitente:
        query = query.filter(NotaFiscal.cnpj_emitente.in_(cnpjs_emitente))
    if cnpjs_destinatario:
        query = query.filter(NotaFiscal.cnpj_destinatario.in_(cnpjs_destinatario))
    if materiais_ids:
        try:
            mids = [int(mid) for mid in materiais_ids if mid]
            if mids:
                query = query.filter(NotaFiscalItem.material_id.in_(mids))
        except Exception:
            pass

    query = query.order_by(NotaFiscal.data_emissao.desc())
    paginacao = query.paginate(page=page, per_page=per_page, error_out=False)
    transferencias = paginacao.items

    return render_template(
        "notas_fiscais/_tabela_transferencias.html",
        transferencias=transferencias,
        paginacao=paginacao,
        filtro_data_inicio=data_inicio,
        filtro_data_fim=data_fim,
        filtro_codigo_item=codigo_item,
        filtro_nome_item=nome_item,
        filtro_cnpj_emitente=cnpjs_emitente,
        filtro_cnpj_destinatario=cnpjs_destinatario,
    )


@nota_fiscal_bp.route("/analise-transferencias/modal-cnpj", methods=["GET"])
@login_required
def analise_transferencias_modal_cnpj():
    """
    Endpoint para alimentar o modal de análise por CNPJ.
    Implementação simplificada: retorna apenas a lista de CNPJs e transferências sem somatórias.
    """
    from flask import jsonify

    # Aplicar os mesmos filtros do formulário (GET)
    filtros = request.args.to_dict(flat=False)

    def _get_first(key, default=""):
        val = filtros.get(key, default)
        if isinstance(val, list):
            return val[0] if val else default
        return val

    def _get_list(key):
        val = filtros.get(key, [])
        if isinstance(val, list):
            return [v for v in val if v not in (None, "")]
        return [val] if val not in (None, "") else []

    data_inicio = (_get_first("data_inicio") or "").strip()
    data_fim = (_get_first("data_fim") or "").strip()
    codigo_item = (_get_first("codigo_item") or "").strip()
    nome_item = (_get_first("nome_item") or "").strip()
    cnpjs_emitente = _get_list("cnpj_emitente")
    cnpjs_destinatario = _get_list("cnpj_destinatario")
    materiais_ids = _get_list("material_id")

    query = (
        db.session.query(
            NotaFiscalItem.descricao.label("nome_item"),
            NotaFiscalItem.codigo.label("codigo_item"),
            NotaFiscal.numero_nf.label("numero_nf"),
            NotaFiscal.cnpj_emitente,
            NotaFiscal.cnpj_destinatario,
            NotaFiscal.tipo.label("tipo_nota"),
            NotaFiscalItem.quantidade,
            NotaFiscal.data_emissao.label("data"),
        )
        .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
        .filter(NotaFiscal.status_processamento != "cancelada")
    )

    if data_inicio:
        try:
            query = query.filter(NotaFiscal.data_emissao >= datetime.strptime(data_inicio, "%Y-%m-%d"))
        except Exception:
            pass
    if data_fim:
        try:
            query = query.filter(NotaFiscal.data_emissao <= datetime.strptime(data_fim, "%Y-%m-%d"))
        except Exception:
            pass
    if codigo_item:
        query = query.filter(NotaFiscalItem.codigo.ilike(f"%{codigo_item}%"))
    if nome_item:
        query = query.filter(NotaFiscalItem.descricao.ilike(f"%{nome_item}%"))
    if cnpjs_emitente:
        query = query.filter(NotaFiscal.cnpj_emitente.in_(cnpjs_emitente))
    if cnpjs_destinatario:
        query = query.filter(NotaFiscal.cnpj_destinatario.in_(cnpjs_destinatario))
    if materiais_ids:
        try:
            mids = [int(mid) for mid in materiais_ids if mid]
            if mids:
                query = query.filter(NotaFiscalItem.material_id.in_(mids))
        except Exception:
            pass

    query = query.order_by(NotaFiscal.data_emissao.desc())
    transferencias = query.limit(500).all()

    cnpjs = sorted({t.cnpj_emitente for t in transferencias if t.cnpj_emitente} | {t.cnpj_destinatario for t in transferencias if t.cnpj_destinatario})

    dados_transferencias = []
    for t in transferencias:
        dados_transferencias.append(
            {
                "data": t.data.isoformat() if t.data else None,
                "nome_item": t.nome_item or "",
                "codigo_item": t.codigo_item or "",
                "numero_nf": t.numero_nf or "",
                "cnpj_emitente": t.cnpj_emitente or "",
                "cnpj_destinatario": t.cnpj_destinatario or "",
                "tipo_nota": "Entrada" if t.tipo_nota == 0 else ("Saída" if t.tipo_nota == 1 else str(t.tipo_nota)),
                "quantidade": float(t.quantidade) if t.quantidade else 0.0,
            }
        )

    return jsonify({"success": True, "transferencias": dados_transferencias, "cnpjs": cnpjs, "somatorias": {}})


@nota_fiscal_bp.route("/analise-transferencias/exportar-excel", methods=["GET"])
@login_required
def analise_transferencias_exportar_excel():
    from flask import jsonify

    return jsonify({"success": False, "message": "Exportação Excel de transferências: não implementado nesta refatoração ainda."}), 501


@nota_fiscal_bp.route("/analise-transferencias/exportar-pdf", methods=["GET"])
@login_required
def analise_transferencias_exportar_pdf():
    from flask import jsonify

    return jsonify({"success": False, "message": "Exportação PDF de transferências: não implementado nesta refatoração ainda."}), 501


@nota_fiscal_bp.route("/api/historico-preco")
@login_required
def api_historico_preco():
    """
    API usada na tela de análise para buscar histórico de preço.

    Query params:
    - tipo: 'item_nf' (default) ou 'material'
    - material_id: int (quando tipo='material')
    - codigo: str (quando tipo='item_nf', opcional)
    - descricao: str (quando tipo='item_nf', recomendado)
    - data_inicio: 'YYYY-MM-DD' (opcional)
    - data_fim: 'YYYY-MM-DD' (opcional)

    Retorno:
    - { "historico": [ {quantidade, valor_unitario, unidade, data_emissao, numero_nf, nome_emitente, nota_id, conversao_aplicada} ] }
    """
    from flask import jsonify

    try:
        tipo = request.args.get("tipo", "item_nf")
        material_id = request.args.get("material_id", type=int)
        codigo = request.args.get("codigo", "") or ""
        descricao = request.args.get("descricao", "") or ""
        data_inicio_str = (request.args.get("data_inicio", "") or "").strip()
        data_fim_str = (request.args.get("data_fim", "") or "").strip()

        unidade_referencia = None
        if tipo == "material":
            if not material_id:
                return jsonify({"error": "material_id é obrigatório quando tipo=material"}), 400
            material = Materiais.query.get(material_id)
            if not material:
                return jsonify({"error": "Material não encontrado."}), 404
            unidade_referencia = material.unidade_obj.nome if material.unidade_obj else None

        query = (
            db.session.query(
                NotaFiscalItem.quantidade,
                NotaFiscalItem.valor_unitario,
                NotaFiscalItem.valor_total,
                NotaFiscalItem.unidade.label("unidade_item_nf"),
                NotaFiscalItem.fator_conversao_aplicado,
                NotaFiscal.data_emissao,
                NotaFiscal.numero_nf,
                NotaFiscal.nome_emitente,
                NotaFiscal.id.label("nota_id"),
                NotaFiscalItem.material_id,
                NotaFiscalItem.codigo,
                NotaFiscalItem.descricao,
            )
            .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
            .filter(NotaFiscal.status_processamento != "cancelada")
        )

        if data_inicio_str:
            try:
                dt_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
                query = query.filter(NotaFiscal.data_emissao >= dt_inicio)
            except ValueError:
                return jsonify({"error": "Formato de data inválido para Data Início."}), 400
        if data_fim_str:
            try:
                dt_fim = datetime.strptime(data_fim_str, "%Y-%m-%d").date()
                query = query.filter(NotaFiscal.data_emissao <= dt_fim)
            except ValueError:
                return jsonify({"error": "Formato de data inválido para Data Fim."}), 400

        if tipo == "material":
            query = query.filter(NotaFiscalItem.material_id == material_id)
        elif tipo == "item_nf":
            if codigo:
                query = query.filter(NotaFiscalItem.codigo == codigo)
            if descricao:
                query = query.filter(NotaFiscalItem.descricao == descricao)
            else:
                return jsonify({"error": "descricao é obrigatória quando tipo=item_nf"}), 400
        else:
            return jsonify({"error": "Parâmetro tipo inválido."}), 400

        query = query.order_by(NotaFiscal.data_emissao.desc())
        historico_cru = query.all()

        historico_formatado = []
        for item in historico_cru:
            quantidade_final = item.quantidade
            valor_unitario_final = item.valor_unitario
            unidade_final = item.unidade_item_nf
            conversao_aplicada = False

            # Conversão opcional para unidade padrão do material (quando tipo=material)
            if tipo == "material" and unidade_referencia and item.fator_conversao_aplicado is not None:
                try:
                    fator = Decimal(str(item.fator_conversao_aplicado))
                    if fator > 0 and item.quantidade is not None and item.valor_total is not None:
                        quantidade_conv = Decimal(str(item.quantidade)) * fator
                        if quantidade_conv > 0:
                            valor_unitario_conv = Decimal(str(item.valor_total)) / quantidade_conv
                            quantidade_final = quantidade_conv
                            valor_unitario_final = valor_unitario_conv
                            unidade_final = unidade_referencia
                            conversao_aplicada = True
                except Exception:
                    # Se falhar, mantém dados originais
                    pass

            historico_formatado.append(
                {
                    "quantidade": float(quantidade_final) if quantidade_final is not None else 0.0,
                    "valor_unitario": float(valor_unitario_final) if valor_unitario_final is not None else 0.0,
                    "unidade": unidade_final,
                    "data_emissao": item.data_emissao.strftime("%Y-%m-%d") if item.data_emissao else None,
                    "numero_nf": item.numero_nf,
                    "nome_emitente": item.nome_emitente,
                    "nota_id": item.nota_id,
                    "conversao_aplicada": conversao_aplicada,
                }
            )

        return jsonify({"historico": historico_formatado})
    except Exception as e:
        logger.error(f"Erro na API de histórico de preço: {str(e)}", exc_info=True)
        return jsonify({"error": "Erro interno ao buscar histórico de preços."}), 500

