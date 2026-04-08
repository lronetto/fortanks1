import json
import logging
from datetime import datetime

from flask import flash
from sqlalchemy import Integer, and_, case, exists, func, not_, or_, select

from models.centro_custo import CentroCusto
from models.contrato import Contrato
from models.database import db
from models.dados_analiticos import DadoAnalitico
from models.reembolso import ReembolsosDocumentos,Reembolsos
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
from models.tanque import Tanques
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
        json_filtros = request
    busca = json_filtros.get("busca", "")
    item_nome = json_filtros.get("item_nome", "")
    status_importacao = json_filtros.get("status_importacao", "")
    emitente = json_filtros.get("emitente", "") # Matriz, Filiais, Terceiros, Matriz_Filiais
    destinatario = json_filtros.get("destinatario", "") # Matriz, Filiais, Terceiros, Matriz_Filiais
    status_pagamento = json_filtros.get("status_pagamento", "")

    pagamento = json_filtros.get("pagamento", "")
    reembolso_upload = json_filtros.get("reembolso_upload", "")

    print(f'status_pagamento: {status_pagamento}')
    pagamento_5percent = json_filtros.get("pagamento_5percent", False)
    data_emissao_inicio = json_filtros.get("data_emissao_inicio", "")
    data_emissao_fim = json_filtros.get("data_emissao_fim", "")
    tipo_nfe = json_filtros.get("tipo_nfe", "")
    origem = json_filtros.get("origem", "")
    destino = json_filtros.get("destino", "")
    remetente = json_filtros.get("remetente", "")
    status_upload = json_filtros.get("status_upload", "")
    tipo_operacao = json_filtros.get("tipo_operacao", "") # Venda, Compra, Transferência
    cnpj_emitente = (json_filtros.get("cnpj_emitente", "") or "").strip()
    cnpj_destinatario = (json_filtros.get("cnpj_destinatario", "") or "").strip()
    status_liberacao = json_filtros.get("status_liberacao", "")
    valor_minimo = json_filtros.get("valor_minimo", "")
    valor_maximo = json_filtros.get("valor_maximo", "")
    valor_exato = json_filtros.get("valor_exato", "")
    plano_conta_id = json_filtros.get("plano_conta_id", "")
    notas_selecionadas = json_filtros.get("notas_selecionadas", [])
    centro_custo_ids = json_filtros.get("centro_custo_ids", [])
    cancelada = json_filtros.get("cancelada", "nao_canceladas")
    liberada = json_filtros.get("liberada", "")
    reembolso_id = json_filtros.get("reembolso_id", "")
    reembolso = json_filtros.get("reembolso", "")
    if reembolso_id:
        try:
            reembolso_id = int(reembolso_id)
        except (ValueError, TypeError):
            reembolso_id = None
    else:
        reembolso_id = None

    # Subquery pagamento - retorna a data de pagamento se houver, NULL caso contrário
    documento_normalizado = func.cast(func.replace(DadoAnalitico.documento, ".", ""), Integer)
    numero_nf_normalizado = func.cast(NotaFiscal.numero_nf, Integer)
    if True:
        pagamento_column = (
            select(DadoAnalitico.data_pagamento)
            .select_from(DadoAnalitico)
            .where(
                and_(
                    NotaFiscal.data_emissao <= DadoAnalitico.data_pagamento,
                    DadoAnalitico.valor >= NotaFiscal.valor_total*0.95,
                    DadoAnalitico.valor <= NotaFiscal.valor_total*1.05,
                    documento_normalizado == numero_nf_normalizado,
                )
            )
            .limit(1)
            .correlate(NotaFiscal)
            .scalar_subquery()
            .label("pagamento")
        )
        if pagamento_5percent:
            pc_column = (
                select(DadoAnalitico.plano_conta_id)
                .select_from(DadoAnalitico)
                .where(
                    and_(
                        NotaFiscal.data_emissao <= DadoAnalitico.data_pagamento,
                        DadoAnalitico.valor >= NotaFiscal.valor_total*0.95,
                        DadoAnalitico.valor <= NotaFiscal.valor_total*1.05,
                        documento_normalizado == numero_nf_normalizado,
                    )
                )
                .limit(1)
                .correlate(NotaFiscal)
                .scalar_subquery()
                .label("pc")
            )
        else:
            pc_column = (
                select(DadoAnalitico.plano_conta_id)
                .select_from(DadoAnalitico)
                .where(
                    and_(
                        NotaFiscal.data_emissao <= DadoAnalitico.data_pagamento,
                        NotaFiscal.valor_total == DadoAnalitico.valor,
                        documento_normalizado == numero_nf_normalizado,
                    )
                )
                .limit(1)
                .correlate(NotaFiscal)
                .scalar_subquery()
                .label("pc")
            )
        # Subquery centro de custo - retorna o ID do centro de custo se houver relação, NULL caso contrário
        # Para notas de material (tipo 0 ou 1): via NotaFiscalItem -> Tanques -> Contrato
        
        
        # Expressão reutilizável: conf contém cnpj em cnpjs_associados (evita mix de collations)
        # json_extract retorna o array inteiro; LIKE no texto garante match por CNPJ e collation uniforme
        _conf_cnpjs = func.json_extract(Contrato.conf, '$.cnpjs_associados')
        _cnpj_pattern = func.concat('%"', NotaFiscal.cnpj_destinatario, '"%')
        _conf_cnpjs_c = _conf_cnpjs.collate('utf8mb4_unicode_ci')
        _cnpj_pattern_c = _cnpj_pattern.collate('utf8mb4_unicode_ci')

        # Subquery para notas de material (tipo 0, 1) via CNPJs associados
        # Destinatário deve estar em cnpjs_associados do contrato
        centro_custo_column_material_cnpj = (
            select(CentroCusto.id)
            .select_from(Contrato)
            .join(CentroCusto, CentroCusto.id == Contrato.centro_custo_id)
            .where(
                and_(
                    NotaFiscal.tipo.in_([0, 1]),
                    Contrato.conf.isnot(None),
                    _conf_cnpjs_c.like(_cnpj_pattern_c)
                )
            )
            .limit(1)
            .correlate(NotaFiscal)
            .scalar_subquery()
        )

        # Subquery para notas de serviço (tipo 3) via CNPJs associados
        # Mesmo critério: cnpj_destinatario contido em cnpjs_associados (json_extract retorna array, usa LIKE)
        centro_custo_column_servico = (
            select(CentroCusto.id)
            .select_from(Contrato)
            .join(CentroCusto, CentroCusto.id == Contrato.centro_custo_id)
            .where(
                and_(
                    NotaFiscal.tipo == 3,
                    Contrato.conf.isnot(None),
                    _conf_cnpjs_c.like(_cnpj_pattern_c)
                )
            )
            .limit(1)
            .correlate(NotaFiscal)
            .scalar_subquery()
        )
        
        # Combinar: material (itens) -> material (cnpj destinatário) -> serviço (cnpj)
        centro_custo_column = func.coalesce(

            centro_custo_column_material_cnpj,
            centro_custo_column_servico
        ).label("centro_custo")
        # Subquery centro de custo via EXISTS (verifica se item da NF está em Tanques.item_nf)
    
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

        # Status de liberação extraído de dados_adicionais
        # Usa CASE para tratar valores booleanos/numéricos do JSON
        # Verifica se o campo liberada existe e é verdadeiro (1, true, ou "true")
        liberada_column = (
            case(
                (
                    and_(
                        NotaFiscal.dados_adicionais.isnot(None),
                        or_(
                            func.cast(func.json_extract(NotaFiscal.dados_adicionais, "$.liberada"), Integer) == 1,
                            func.json_extract(NotaFiscal.dados_adicionais, "$.liberada") == 'true',
                        ),
                    ),
                    1,
                ),
                else_=0,
            )
            .cast(Integer)
            .label("liberada")
        )
        # JSON reembolso extraído de dados_adicionais (um objeto por nota)
        reembolso_column = func.json_extract(NotaFiscal.dados_adicionais, "$.reembolso").label("reembolso")
        # Indicação de pagamento manual em dados_adicionais.pagamento_manual.indicado
        pagamento_manual_expr = and_(
            NotaFiscal.dados_adicionais.isnot(None),
            or_(
                func.cast(
                    func.json_extract(NotaFiscal.dados_adicionais, "$.pagamento_manual.indicado"),
                    Integer,
                )
                == 1,
                func.json_extract(NotaFiscal.dados_adicionais, "$.pagamento_manual.indicado") == "true",
            ),
        )
    query = (
        db.session.query(
            NotaFiscal,
            pagamento_column,
            centro_custo_column,
            upload_column,
            upload_protocolo_column,
            upload_reembolso_column,
            upload_arquivei_column,
            percentual_importacao_column,
            reembolso_column,
            liberada_column,
            pc_column,
        )
        .select_from(NotaFiscal)
    )
    if cancelada == "canceladas":
        query = query.filter(NotaFiscal.status_processamento == "cancelada")
    elif cancelada == "nao_canceladas":
        query = query.filter(NotaFiscal.status_processamento != "cancelada")
    # cancelada == "" (todos): sem filtro por cancelamento
    if reembolso_upload == True:
        query = query.filter(upload_reembolso_column == 1)
    elif reembolso_upload == False:
        query = query.filter(upload_reembolso_column == 0)
    if reembolso == True:
        query = query.filter(
            func.json_extract(NotaFiscal.dados_adicionais, "$.reembolso.enviado") == 1
        )
    elif reembolso == False:
        query = query.filter(
            or_(
                func.json_extract(NotaFiscal.dados_adicionais, "$.reembolso").is_(None),
                func.json_extract(NotaFiscal.dados_adicionais, "$.reembolso.enviado") == 0
            )
        )
    if liberada:
        if liberada == "liberada":
            query = query.filter(liberada_column == 1)
        elif liberada == "nao_liberada":
            query = query.filter(or_(liberada_column == 0, liberada_column.is_(None)))

    if pagamento == True:
        query = query.filter(or_(pagamento_column.isnot(None)))
    elif pagamento == False:
        query = query.filter(
            and_(pagamento_column.is_(None))
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

    if plano_conta_id:
        query = query.filter(pc_column == plano_conta_id)
    if item_nome:
        query = query.join(NotaFiscalItem).filter(NotaFiscalItem.descricao.ilike(f"%{item_nome}%"))

    if tipo_operacao:
        if tipo_operacao == "compra":
            cfops_lista = [str(cfop) for cfop in CFOPS_COMPRA]
            query = query.filter(NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(cfops_lista)))
        elif tipo_operacao == "venda":
            cfops_lista = [str(cfop) for cfop in CFOPS_VENDA]
            # Incluir notas de serviço (tipo 3) além das notas de material com CFOP de venda
            query = query.filter(
                or_(
                    NotaFiscal.itens.any(NotaFiscalItem.cfop.in_(cfops_lista)),
                    NotaFiscal.tipo == 3  # Notas de serviço são sempre de venda
                )
            )
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
            query = query.filter(or_(
                and_(NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ), NotaFiscal.tipo < 2), 
                and_(NotaFiscal.tipo == 2, NotaFiscal.dados_adicionais.isnot(None),
                func.json_extract(NotaFiscal.dados_adicionais, "$.remetente.cnpj").in_(CNPJS_MATRIZ))))
        elif emitente == "Filiais":
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_FILIAIS))
        elif emitente == "Matriz_Filiais":
            query = query.filter(NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ_FILIAIS))

    if destinatario:
        if destinatario == "Terceiros":
            query = query.filter(~NotaFiscal.cnpj_destinatario.in_(CNPJS_MATRIZ_FILIAIS))
        elif destinatario == "Matriz":
                 query = query.filter(or_(
                and_(NotaFiscal.cnpj_destinatario.in_(CNPJS_MATRIZ), NotaFiscal.tipo !=2), 
                and_(NotaFiscal.tipo == 2, NotaFiscal.dados_adicionais.isnot(None),
                func.json_extract(NotaFiscal.dados_adicionais, "$.remetente.cnpj").in_(CNPJS_MATRIZ))))
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
        elif tipo_nfe == "4":
            tipo = [1,3]
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
        #0 - nao definido
        #1 - arquivei
        #2 - protocolo
        #3 - reembolso
        #4 - avulso
        #5 - certificado
        if status_upload == "1":
            query = query.filter(_upload_exists(1))
        elif status_upload == "2":
            query = query.filter(_upload_exists(2))
        elif status_upload == "3":
            query = query.filter(_upload_exists(3))
        elif status_upload == "3nao":
            query = query.filter(~_upload_exists(3))
        elif status_upload == "4":
            query = query.filter(~_upload_exists(2))
        elif status_upload == "5":
            query = query.filter(~_upload_exists())

    # Filtro por status de liberação
    if status_liberacao:
        if status_liberacao == "liberada":
            query = query.filter(liberada_column == 1)
        elif status_liberacao == "nao_liberada":
            query = query.filter(or_(liberada_column == 0, liberada_column.is_(None)))

    if valor_minimo:
        query = query.filter(NotaFiscal.valor_total >= valor_minimo)
    if valor_maximo:
        query = query.filter(NotaFiscal.valor_total <= valor_maximo)
    if valor_exato:
        query = query.filter(NotaFiscal.valor_total == valor_exato)

    # Filtro por centro de custo (via subquery)
    if centro_custo_ids:
        centro_custo_ids_int = [int(cc_id) for cc_id in centro_custo_ids if cc_id]
        if centro_custo_ids_int:
            print(f'centro_custo_ids_int: {centro_custo_ids_int}')
            query = query.filter(centro_custo_column.in_(centro_custo_ids_int))

    if status_pagamento:
        if status_pagamento == "pago":
            query = query.filter(or_(pagamento_column.isnot(None)))
        elif status_pagamento == "nao_pago":
            query = query.filter(
                and_(pagamento_column.is_(None))
            )
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
                pagamento_column.is_(None),
                not_(pagamento_manual_expr),
            )
        elif status_pagamento == "apenas_reembolso":
            query = query.filter(upload_reembolso_column == 1)
        elif status_pagamento == "reembolso_e_nao_pago":
            query = query.filter(
                upload_reembolso_column == 1,
                pagamento_column.is_(None),
                not_(pagamento_manual_expr),
            )
        elif status_pagamento == "selecionados":
            query = query.filter(
                func.json_extract(NotaFiscal.dados_adicionais, "$.reembolso").isnot(None),
                func.cast(func.json_extract(NotaFiscal.dados_adicionais, "$.reembolso.id"), Integer) == int(reembolso_id)
            )
        elif status_pagamento == "reembolso_e_nao_pago_e_nao_selecionados":
            nsel = [item.get("id") for item in notas_selecionadas if item.get("id")]
            query = query.filter(
                upload_reembolso_column == 1,
                pagamento_column.is_(None),
                not_(pagamento_manual_expr),
                func.json_extract(NotaFiscal.dados_adicionais, "$.reembolso").is_(None),
            )

    # Ordenação
    order_by = json_filtros.get("order_by", "data_emissao")
    order_dir = json_filtros.get("order_dir", "desc")
    order_mapping = {
        "numero_nf": NotaFiscal.numero_nf,
        "tipo": NotaFiscal.tipo,
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


