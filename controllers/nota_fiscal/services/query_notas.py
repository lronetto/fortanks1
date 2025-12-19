import json
import logging
from datetime import datetime

from flask import flash
from sqlalchemy import Integer, and_, case, exists, func, or_, select

from models.database import db
from models.dados_analiticos import DadoAnalitico
from models.nota_fiscal import (
    CFOPS_COMPRA,
    CFOPS_TRANSFERENCIA,
    CFOPS_VENDA,
    CNPJS_FILIAIS,
    CNPJS_MATRIZ,
    CNPJS_MATRIZ_FILIAIS,
    NotaFiscal,
    NotaFiscalItem,
)
from models.upload import Upload

logger = logging.getLogger(__name__)


def api_get_dados_notas_fiscais(request):
    """
    Monta a query base de notas fiscais usada pela tela principal (tabela via AJAX),
    respeitando filtros de `request.args` ou JSON.
    """
    json_filtros = request
    if hasattr(request, "args"):
        json_filtros = request.args
    else:
        json_filtros = request.get_json()

    busca = json_filtros.get("busca", "")
    item_nome = json_filtros.get("item_nome", "")
    status_importacao = json_filtros.get("status_importacao", "")
    emitente = json_filtros.get("emitente", "")
    destinatario = json_filtros.get("destinatario", "")
    status_pagamento = json_filtros.get("status_pagamento", "")
    data_emissao_inicio = json_filtros.get("data_emissao_inicio", "")
    data_emissao_fim = json_filtros.get("data_emissao_fim", "")
    tipo_nfe = json_filtros.get("tipo_nfe", "")
    origem = json_filtros.get("origem", "")
    destino = json_filtros.get("destino", "")
    remetente = json_filtros.get("remetente", "")
    status_upload = json_filtros.get("status_upload", "")
    tipo_operacao = json_filtros.get("tipo_operacao", "")
    cnpj_emitente = (json_filtros.get("cnpj_emitente", "") or "").strip()
    cnpj_destinatario = (json_filtros.get("cnpj_destinatario", "") or "").strip()
    valor_minimo = json_filtros.get("valor_minimo", "")
    valor_maximo = json_filtros.get("valor_maximo", "")
    valor_exato = json_filtros.get("valor_exato", "")
    notas_selecionadas = json_filtros.get("notas_selecionadas", [])

    # Subquery pagamento via EXISTS (evita multiplicação de linhas)
    documento_normalizado = func.cast(func.replace(DadoAnalitico.documento, ".", ""), Integer)
    numero_nf_normalizado = func.cast(NotaFiscal.numero_nf, Integer)
    subquery_pagamento_exists = exists(
        select(1)
        .select_from(DadoAnalitico)
        .where(
            and_(
                NotaFiscal.data_emissao <= DadoAnalitico.data_pagamento,
                DadoAnalitico.valor == NotaFiscal.valor_total,
                documento_normalizado == numero_nf_normalizado,
            )
        )
    )
    pagamento_column = case((subquery_pagamento_exists, 1), else_=0).label("pagamento")

    # Uploads via EXISTS
    def _upload_exists(tipo=None):
        conditions = [Upload.pai_id == NotaFiscal.id, Upload.pai == "NotaFiscal"]
        if tipo is not None:
            conditions.append(Upload.tipo == tipo)
        return exists(select(1).select_from(Upload).where(and_(*conditions)))

    upload_column = case((_upload_exists(), 1), else_=0).label("upload")
    upload_arquivei_column = case((_upload_exists(1), 1), else_=0).label("upload_arquivei")
    upload_protocolo_column = case((_upload_exists(2), 1), else_=0).label("upload_protocolo")
    upload_reembolso_column = case((_upload_exists(3), 1), else_=0).label("upload_reembolso")

    # Percentual de importação por NF
    percentual_importacao_column = (
        select(
            case(
                (
                    func.count(NotaFiscalItem.id) > 0,
                    (
                        func.sum(case((NotaFiscalItem.importado_estoque.is_(True), 1), else_=0)).cast(
                            db.Numeric(15, 2)
                        )
                        / func.count(NotaFiscalItem.id).cast(db.Numeric(15, 2))
                    )
                    * 100,
                ),
                else_=0,
            )
        )
        .select_from(NotaFiscalItem)
        .where(NotaFiscalItem.nf_id == NotaFiscal.id)
        .correlate(NotaFiscal)
        .scalar_subquery()
        .label("percentual_importacao")
    )

    query = (
        db.session.query(
            NotaFiscal,
            pagamento_column,
            upload_column,
            upload_protocolo_column,
            upload_reembolso_column,
            upload_arquivei_column,
            percentual_importacao_column,
        )
        .select_from(NotaFiscal)
        .filter(NotaFiscal.status_processamento != "cancelada")
    )

    if busca:
        busca_like = f"%{busca}%"
        query = query.filter(
            or_(
                NotaFiscal.numero_nf.ilike(busca_like),
                NotaFiscal.nome_emitente.ilike(busca_like),
                NotaFiscal.chave_acesso.ilike(busca_like),
            )
        )

    if item_nome:
        query = query.join(NotaFiscalItem).filter(NotaFiscalItem.descricao.ilike(f"%{item_nome}%"))

    if tipo_operacao:
        if tipo_operacao == "compra":
            cfops_lista = [str(cfop) for cfop in CFOPS_COMPRA]
            query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(cfops_lista)))
        elif tipo_operacao == "venda":
            cfops_lista = [str(cfop) for cfop in CFOPS_VENDA]
            query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(cfops_lista)))
        elif tipo_operacao == "transferencia":
            cfops_lista = [str(cfop) for cfop in CFOPS_TRANSFERENCIA]
            query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(cfops_lista)))

    # Status importação (mantendo comportamento existente)
    if status_importacao == "pendentes":
        query = query.filter(~NotaFiscal.itens.any(NotaFiscalItem.importado_estoque.is_(True)))
        flash(
            "Filtrando por notas pendentes (sem itens importados). Filtros 'Importadas' e 'Parciais' estão desativados com paginação.",
            "info",
        )
    elif status_importacao == "importadas":
        flash(
            f"Filtro por status '{status_importacao}' não está otimizado para paginação e foi desativado. Mostrando todos os status.",
            "warning",
        )
        status_importacao = ""
    elif status_importacao == "parciais":
        query = query.filter(percentual_importacao_column > 0, percentual_importacao_column < 100)
        flash(
            "Filtrando por notas parciais (com itens importados). Filtros 'Importadas' e 'Pendentes' estão desativados com paginação.",
            "info",
        )
    elif status_importacao == "nao_importadas":
        query = query.filter(percentual_importacao_column == 0)
        flash(
            "Filtrando por notas não importadas (sem itens importados). Filtros 'Importadas' e 'Parciais' estão desativados com paginação.",
            "info",
        )

    if emitente:
        if emitente == "Terceiros":
            query = query.filter(~NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ_FILIAIS))
        elif emitente == "Matriz":
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ))
        elif emitente == "Filiais":
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_FILIAIS))
        elif emitente == "Matriz_Filiais":
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ_FILIAIS))

    if destinatario:
        if destinatario == "Terceiros":
            query = query.filter(~NotaFiscal.cnpj_destinatario.in_(CNPJS_MATRIZ_FILIAIS))
        elif destinatario == "Matriz":
            query = query.filter(NotaFiscal.cnpj_destinatario.in_(CNPJS_MATRIZ))
        elif destinatario == "Filiais":
            query = query.filter(NotaFiscal.cnpj_destinatario.in_(CNPJS_FILIAIS))
        elif destinatario == "Matriz_Filiais":
            query = query.filter(NotaFiscal.cnpj_destinatario.in_(CNPJS_MATRIZ_FILIAIS))

    if cnpj_emitente:
        query = query.filter(NotaFiscal.cnpj_emitente == cnpj_emitente)
    if cnpj_destinatario:
        query = query.filter(NotaFiscal.cnpj_destinatario == cnpj_destinatario)

    if data_emissao_inicio:
        try:
            data_inicio = datetime.strptime(data_emissao_inicio, "%Y-%m-%d")
            query = query.filter(NotaFiscal.data_emissao >= data_inicio)
        except Exception:
            flash("Data de início inválida.", "warning")
    if data_emissao_fim:
        try:
            data_fim = datetime.strptime(data_emissao_fim, "%Y-%m-%d")
            query = query.filter(NotaFiscal.data_emissao <= data_fim)
        except Exception:
            flash("Data final inválida.", "warning")

    if tipo_nfe:
        if tipo_nfe == "0":
            tipo = [0, 1]
        elif tipo_nfe == "2":
            tipo = [2]
        elif tipo_nfe == "3":
            tipo = [3]
        else:
            tipo = None
        if tipo is not None:
            query = query.filter(NotaFiscal.tipo.in_(tipo))

        # Filtros extras para CTE
        if tipo_nfe == "2":
            if origem:
                query = query.filter(func.json_extract(NotaFiscal.dados_adicionais, "$.municipio_inicio") == origem)
            if destino:
                query = query.filter(func.json_extract(NotaFiscal.dados_adicionais, "$.municipio_destino") == destino)
            if remetente:
                query = query.filter(
                    func.json_extract(NotaFiscal.dados_adicionais, "$.remetente.nome").ilike(f"%{remetente}%")
                )

    if status_upload:
        if status_upload == "1":
            query = query.filter(_upload_exists(1))
        elif status_upload == "2":
            query = query.filter(_upload_exists(2))
        elif status_upload == "3":
            query = query.filter(_upload_exists(3))
        elif status_upload == "4":
            query = query.filter(~_upload_exists(2))
        elif status_upload == "5":
            query = query.filter(~_upload_exists())

    if valor_minimo:
        query = query.filter(NotaFiscal.valor_total >= valor_minimo)
    if valor_maximo:
        query = query.filter(NotaFiscal.valor_total <= valor_maximo)
    if valor_exato:
        query = query.filter(NotaFiscal.valor_total == valor_exato)

    if status_pagamento:
        if status_pagamento == "pago":
            query = query.filter(pagamento_column == 1)
        elif status_pagamento == "nao_pago":
            query = query.filter(pagamento_column == 0)
        elif status_pagamento == "com_faturamento":
            query = query.filter(NotaFiscal.vencimento.isnot(None))
        elif status_pagamento == "vencido":
            hoje_str = datetime.now().date().strftime("%Y-%m-%d")
            query = query.filter(NotaFiscal.vencimento.isnot(None), NotaFiscal.vencimento < hoje_str)
        elif status_pagamento == "vencido_nao_pago":
            hoje_str = datetime.now().date().strftime("%Y-%m-%d")
            query = query.filter(
                NotaFiscal.vencimento.isnot(None),
                NotaFiscal.vencimento < hoje_str,
                pagamento_column == 0,
            )
        elif status_pagamento == "apenas_reembolso":
            query = query.filter(upload_reembolso_column == 1)
        elif status_pagamento == "reembolso_e_nao_pago":
            query = query.filter(upload_reembolso_column == 1, pagamento_column == 0)
        elif status_pagamento == "selecionados":
            nsel = [item.get("id") for item in notas_selecionadas if item.get("id")]
            query = query.filter(NotaFiscal.id.in_(nsel))

    # Ordenação
    order_by = json_filtros.get("order_by", "data_emissao")
    order_dir = json_filtros.get("order_dir", "desc")
    order_mapping = {
        "numero_nf": NotaFiscal.numero_nf,
        "data_emissao": NotaFiscal.data_emissao,
        "vencimento": NotaFiscal.vencimento,
        "valor_total": NotaFiscal.valor_total,
        "nome_emitente": NotaFiscal.nome_emitente,
        "cnpj_emitente": NotaFiscal.cnpj_emitente,
        "cnpj_destinatario": NotaFiscal.cnpj_destinatario,
    }
    if order_by in order_mapping:
        order_column = order_mapping[order_by]
        if order_dir == "asc":
            query = query.order_by(order_column.asc(), NotaFiscal.id.asc())
        else:
            query = query.order_by(order_column.desc(), NotaFiscal.id.desc())
    else:
        query = query.order_by(NotaFiscal.data_emissao.desc(), NotaFiscal.numero_nf.desc())

    return query


