import base64
import logging
from datetime import datetime
from decimal import Decimal

from flask import jsonify, make_response, request
from flask.wrappers import json
from flask_login import current_user, login_required
from sqlalchemy import Integer, and_, case, exists, func, select

from models.centro_custo import CentroCusto
from models.unidade import comparar_unidades, get_conversao_unidade, UnidadesConversao, Unidades
from models.dados_analiticos import DadoAnalitico
from models.database import db
from models.estoque import EstoqueMovimentacoes
from models.logs import Logs
from models.material import Materiais
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.upload import Upload
from models.pedido_compra import PedidoCompraEntrada, PedidoCompraItem
from controllers.nota_fiscal.services.query_notas import api_get_dados_notas_fiscais

logger = logging.getLogger(__name__)


def register(nota_fiscal_bp):
    """
    Registra endpoints de API do domínio Nota Fiscal no blueprint `nota_fiscal_bp`.

    Importante:
    - Mantém as mesmas URLs existentes (ex.: `/api/itens/<id>`, `/api/documentos` etc).
    - Apenas organiza o código em `controllers/api/`.
    """

    @nota_fiscal_bp.route("/api/notas-fiscais/ajax", methods=["GET", "POST"])
    @login_required
    def api_get_ajax_notas_fiscais():
        query = api_get_dados_notas_fiscais(request)
        return jsonify([nota.to_dict() for nota in query.all()])

    @nota_fiscal_bp.route("/api/notas-fiscais/datatables", methods=["GET"])
    @login_required
    def api_get_datatables_notas_fiscais():
        """
        Retorna dados formatados para DataTables via AJAX
        """
        from datetime import datetime
        from models.nota_fiscal import CNPJS_FILIAIS, CNPJS_MATRIZ
        
        # Parâmetros do DataTables
        draw = int(request.args.get('draw', 1))
        start = int(request.args.get('start', 0))
        length = int(request.args.get('length', 50))
        page = (start // length) + 1
        per_page = length

        # Processar ordenação do DataTables (coluna 0 = checkbox, não ordenável)
        # Índices (front): 0 checkbox, 1 número, 2 tipo, 3 emissão, 4 vencimento, ...
        order_column_index = int(request.args.get('order[0][column]', 3))
        order_dir = request.args.get('order[0][dir]', 'desc')
        
        # Mapear índice da coluna para campo de ordenação (0 = checkbox)
        column_mapping = {
            1: 'numero_nf',
            2: 'tipo',
            3: 'data_emissao',
            4: 'vencimento',
            5: 'cnpj_emitente',
            6: 'cnpj_destinatario',
            7: 'nome_emitente',
            8: 'valor_total'
        }
        
        order_by = column_mapping.get(order_column_index, 'data_emissao')
        
        # Criar um objeto request-like com os parâmetros modificados
        class ModifiedRequest:
            def __init__(self, original_request):
                self._original = original_request
                self._args = dict(original_request.args)
                self._args['order_by'] = order_by
                self._args['order_dir'] = order_dir
            
            def get(self, key, default=None):
                return self._args.get(key, default)
            
            def getlist(self, key):
                val = self._args.get(key, [])
                return val if isinstance(val, list) else [val] if val else []
            
            @property
            def args(self):
                return self
        
        # Obter query com filtros (usando request modificado)
        modified_request = ModifiedRequest(request)
        query = api_get_dados_notas_fiscais(modified_request)
        
        # Contar total de registros (antes da paginação)
        total_records = query.count()
        
        # Aplicar paginação
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        notas_fiscais_pagina = pagination.items

        # Processar dados
        data = []
        for nota in notas_fiscais_pagina:
            vencimento_str = getattr(nota.NotaFiscal, "vencimento", None) if hasattr(nota.NotaFiscal, "vencimento") else None
            vencimento_formatado = "-"
            if vencimento_str:
                try:
                    if isinstance(vencimento_str, str) and len(vencimento_str) == 10 and "-" in vencimento_str:
                        vencimento_date = datetime.strptime(vencimento_str, "%Y-%m-%d").date()
                        vencimento_formatado = vencimento_date.strftime("%d/%m/%Y")
                    else:
                        vencimento_formatado = str(vencimento_str)
                except (ValueError, AttributeError):
                    vencimento_formatado = str(vencimento_str) if vencimento_str else "-"

            emitente = (
                "Matriz"
                if nota.NotaFiscal.cnpj_emitente in CNPJS_MATRIZ
                else "Filiais"
                if nota.NotaFiscal.cnpj_emitente in CNPJS_FILIAIS
                else "Terceiros"
            )
            destinatario = (
                "Matriz"
                if nota.NotaFiscal.cnpj_destinatario in CNPJS_MATRIZ
                else "Filiais"
                if nota.NotaFiscal.cnpj_destinatario in CNPJS_FILIAIS
                else "Terceiros"
            )

            # Calcular percentual de importação
            percentual = getattr(nota, "percentual_importacao", 0) if hasattr(nota, "percentual_importacao") else 0
            if percentual is None:
                percentual = -1

            # Status de liberação
            liberada = getattr(nota, "liberada", 0) if hasattr(nota, "liberada") else 0
            if liberada is None:
                liberada = 0

            # Status badge (cancelada ou não + demais status)
            status_html = ""
            nf_cancelada = nota.NotaFiscal.status_processamento == 'cancelada'
            if nf_cancelada:
                status_html = '<span class="badge bg-danger">Cancelada</span>'
            else:
                status_html = ''
                if percentual == 0:
                    status_html += '<span class="badge bg-danger">Pend</span>'
                elif percentual == 100:
                    status_html += '<span class="badge bg-success">Impo</span>'
                elif percentual > 0:
                    status_html += f'<span class="badge bg-warning">Parc ({int(percentual)}%)</span>'
                else:
                    status_html += '<span class="badge bg-secondary">N/A</span>'

                # Badge de liberação
                if liberada == 1:
                    status_html += ' <span class="badge bg-primary ms-1" title="Liberada"><i class="fas fa-check-circle"></i> Lib</span>'
                else:
                    status_html += ' <span class="badge bg-secondary ms-1" title="Não Liberada"><i class="fas fa-times-circle"></i> NLib</span>'

                # Upload badges
                upload = getattr(nota, "upload", 0)
                if upload > 0:
                    upload_protocolo = getattr(nota, "upload_protocolo", 0)
                    upload_arquivei = getattr(nota, "upload_arquivei", 0)
                    upload_reembolso = getattr(nota, "upload_reembolso", 0)
                    
                    if upload_protocolo == 1:
                        status_html += ' <span class="badge bg-info ms-1" title="protocolo"><i class="fas fa-paperclip" style="color: green;"></i></span>'
                    if upload_arquivei == 1:
                        status_html += ' <span class="badge bg-info ms-1" title="arquivei"><i class="fas fa-paperclip"></i></span>'
                    if upload_reembolso == 1:
                        status_html += ' <span class="badge bg-info ms-1" title="reembolso"><i class="fas fa-paperclip" style="color: red;"></i></span>'

                pagamento = getattr(nota, "pagamento", 0)
                if pagamento == 1:
                    status_html += ' <span class="badge bg-success ms-1" title="Pago"><i class="fas fa-check"></i></span>'

            # Status de liberação para o botão
            liberada = getattr(nota, "liberada", 0) if hasattr(nota, "liberada") else 0
            if liberada is None:
                liberada = 0
            
            # Botões de ação
            btn_liberar_class = "btn-info" if liberada == 0 else "btn-primary"
            btn_liberar_icon = "fa-unlock" if liberada == 0 else "fa-lock"
            btn_liberar_title = "Liberar" if liberada == 0 else "Desliberar"
            btn_cancelar_class = "btn-danger" if not nf_cancelada else "btn-outline-danger"
            btn_cancelar_icon = "fa-ban" if not nf_cancelada else "fa-undo"
            btn_cancelar_title = "Cancelar nota fiscal" if not nf_cancelada else "Reverter cancelamento da nota fiscal"
            
            acoes_html = f'''
                <div class="btn-group">
                    <button type="button" class="btn btn-sm btn-primary visualizar-itens" data-id="{nota.NotaFiscal.id}" title="Visualizar Itens">
                        <i class="fas fa-list"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-success importar-itens" data-id="{nota.NotaFiscal.id}" title="Importar para Estoque">
                        <i class="fas fa-file-import"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-warning vincular-material" data-id="{nota.NotaFiscal.id}" title="Vincular Material">
                        <i class="fas fa-link"></i>
                    </button>
                    <button type="button" class="btn btn-sm {btn_liberar_class} liberar-nota" data-id="{nota.NotaFiscal.id}" data-numero="{nota.NotaFiscal.numero_nf}" data-liberada="{liberada}" title="{btn_liberar_title}">
                        <i class="fas {btn_liberar_icon}"></i>
                    </button>
                    <button type="button" class="btn btn-sm {btn_cancelar_class} cancelar-nota" data-id="{nota.NotaFiscal.id}" data-numero="{nota.NotaFiscal.numero_nf}" data-cancelada="{1 if nf_cancelada else 0}" title="{btn_cancelar_title}">
                        <i class="fas {btn_cancelar_icon}"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-danger excluir-nota" data-id="{nota.NotaFiscal.id}" data-numero="{nota.NotaFiscal.numero_nf}" title="Excluir">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            '''

            fornecedor_html = f'''
                <a href="javascript:void(0);" class="visualizar-docs" data-id="{nota.NotaFiscal.id}" data-numero="{nota.NotaFiscal.numero_nf}" title="Visualizar Documentos">
                    {nota.NotaFiscal.nome_emitente or '-'}
                </a>
            '''

            checkbox_html = (
                f'<input type="checkbox" class="form-check-input nf-checkbox" '
                f'value="{nota.NotaFiscal.id}" data-id="{nota.NotaFiscal.id}" '
                f'aria-label="Selecionar nota {nota.NotaFiscal.numero_nf}">'
            )

            tipo_doc = getattr(nota.NotaFiscal, "tipo", None)
            if tipo_doc == 2:
                tipo_doc_label = "CTE"
            elif tipo_doc == 3:
                tipo_doc_label = "NFS"
            else:
                tipo_doc_label = "NFE"

            data.append([
                checkbox_html,
                nota.NotaFiscal.numero_nf or '',
                tipo_doc_label,
                nota.NotaFiscal.data_emissao.strftime('%d/%m/%Y') if nota.NotaFiscal.data_emissao else '',
                vencimento_formatado,
                emitente,
                destinatario,
                fornecedor_html,
                f'R$ {nota.NotaFiscal.valor_total:.2f}' if nota.NotaFiscal.valor_total else 'R$ 0.00',
                status_html,
                acoes_html
            ])

        return jsonify({
            "draw": draw,
            "recordsTotal": total_records,
            "recordsFiltered": total_records,
            "data": data
        })

    @nota_fiscal_bp.route("/api/visualizar/<int:id>")
    @login_required
    def api_visualizar(id):
        nota_fiscal = NotaFiscal.query.get_or_404(id)
        itens = []
        for item in nota_fiscal.itens:
            itens.append(
                {
                    "id": item.id,
                    "codigo": item.codigo,
                    "descricao": item.descricao,
                    "quantidade": float(item.quantidade) if item.quantidade is not None else 0.0,
                    "valor_unitario": float(item.valor_unitario) if item.valor_unitario is not None else 0.0,
                    "valor_total": float(item.valor_total) if item.valor_total is not None else 0.0,
                    "ncm": item.ncm,
                    "cfop": item.cfop,
                    "unidade": item.unidade,
                }
            )

        data = {
            "id": nota_fiscal.id,
            "numero_nf": nota_fiscal.numero_nf,
            "chave_acesso": nota_fiscal.chave_acesso,
            "data_emissao": nota_fiscal.data_emissao.strftime("%d/%m/%Y") if nota_fiscal.data_emissao else None,
            "valor_total": float(nota_fiscal.valor_total) if nota_fiscal.valor_total is not None else 0.0,
            "cnpj_emitente": nota_fiscal.cnpj_emitente,
            "nome_emitente": nota_fiscal.nome_emitente,
            "cnpj_destinatario": nota_fiscal.cnpj_destinatario,
            "nome_destinatario": nota_fiscal.nome_destinatario,
            "status_processamento": nota_fiscal.status_processamento,
            "xml_data": nota_fiscal.xml_data,
            "data_importacao": nota_fiscal.data_importacao.strftime("%d/%m/%Y %H:%M:%S")
            if nota_fiscal.data_importacao
            else None,
            "data_atualizacao": nota_fiscal.data_atualizacao.strftime("%d/%m/%Y %H:%M:%S")
            if nota_fiscal.data_atualizacao
            else None,
            "itens": itens,
        }
        return jsonify(data)

    @nota_fiscal_bp.route("/xml/<int:id>", methods=["GET"])
    @login_required
    def gerar_xml(id):
        nota = NotaFiscal.query.get_or_404(id)
        return jsonify({"xml": base64.b64decode(nota.xml_data).decode("utf-8")})

    @nota_fiscal_bp.route("/total-notas", methods=["GET"])
    @login_required
    def total_notas():
        query = api_get_dados_notas_fiscais(request)
        return jsonify({"total_notas": query.count()})

    @nota_fiscal_bp.route("/total-valor-notas", methods=["GET"])
    @login_required
    def total_valor_notas():
        query = api_get_dados_notas_fiscais(request)
        nota_ids = [row[0] for row in query.with_entities(func.distinct(NotaFiscal.id)).all()]
        if not nota_ids:
            return jsonify({"valor_total": 0.0})
        resultado = db.session.query(func.sum(NotaFiscal.valor_total)).filter(NotaFiscal.id.in_(nota_ids)).scalar()
        return jsonify({"valor_total": float(resultado) if resultado is not None else 0.0})

    @nota_fiscal_bp.route("/api/itens/<int:nf_id>", methods=["GET"])
    @login_required
    def api_itens(nf_id):
        nota_fiscal = NotaFiscal.query.get_or_404(nf_id)
        items = []
        for item in nota_fiscal.itens:
            material = Materiais.query.get(item.material_id) if item.material_id else None
            try:
                dados_adicionais = json.loads(item.dados_adicionais) if item.dados_adicionais else None
            except Exception as e:
                dados_adicionais = None
            if dados_adicionais:
                xPed = dados_adicionais.get('xPed')
                nItemPed = dados_adicionais.get('nItemPed')
                infAdProd = dados_adicionais.get('infAdProd')
                impostos = dados_adicionais.get('impostos')
            else:
                xPed = None
                nItemPed = None
                infAdProd = None
                impostos = None
            items.append(
                {
                    "id": item.id,
                    "codigo": item.codigo,
                    "cfop": item.cfop,
                    "descricao": item.descricao,
                    "infAdProd": infAdProd if infAdProd else None,
                    "quantidade": float(item.quantidade) if item.quantidade is not None else 0.0,
                    "unidade": item.unidade,
                    "valor_unitario": float(item.valor_unitario) if item.valor_unitario is not None else 0.0,
                    "valor_total": float(item.valor_total) if item.valor_total is not None else 0.0,
                    "ncm": item.ncm,
                    "material_id": item.material_id,
                    "material_unidade": material.unidade_obj.nome if material and material.unidade_obj else None,
                    "material_nome": material.nome if material else None,
                    "importado_estoque": bool(item.importado_estoque),
                    "data_importacao_estoque": item.data_importacao_estoque.isoformat()
                    if item.data_importacao_estoque
                    else None,
                    "fator_conversao_aplicado": item.fator_conversao_aplicado,
                }
            )
        return jsonify({"itens": items, "success": True})

    @nota_fiscal_bp.route("/api/materiais", methods=["GET"])
    @login_required
    def api_materiais():
        termo = request.args.get("termo", "")
        if not termo or len(termo) < 3:
            return jsonify({"materiais": [], "success": True})

        termo_busca = f"%{termo}%"
        materiais = (
            Materiais.query.filter(
                Materiais.ativo.is_(True),
                db.or_(
                    Materiais.codigo.ilike(termo_busca),
                    Materiais.descricao.ilike(termo_busca),
                    Materiais.nome.ilike(termo_busca),
                ),
            )
            .order_by(Materiais.nome)
            .all()
        )

        resultado = []
        for material in materiais:
            unidade = material.unidade_obj.nome if hasattr(material, "unidade_obj") else (material.unidade_obj.nome or "-")
            unidade_sigla = (
                material.unidade_obj.nome if hasattr(material, "unidade_obj") else (material.unidade_obj.nome or "-")
            )
            tem_conversoes = material.tem_conversoes() if hasattr(material, "tem_conversoes") else False
            resultado.append(
                {
                    "id": material.id,
                    "nome": material.nome,
                    "codigo": material.codigo or "",
                    "descricao": material.descricao or "",
                    "unidade": unidade,
                    "unidade_sigla": unidade_sigla,
                    "tem_conversoes": tem_conversoes,
                }
            )
        return jsonify({"materiais": resultado, "success": True})

    @nota_fiscal_bp.route("/api/centros-custo", methods=["GET"])
    @login_required
    def api_centros_custo():
        centros = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.codigo).all()
        items = [{"id": c.id, "codigo": c.codigo, "nome": c.nome} for c in centros]
        return jsonify({"centros_custo": items, "success": True})

    @nota_fiscal_bp.route("/api/unidades", methods=["GET"])
    @login_required
    def api_unidades():
        unidades = Unidades.query.order_by(Unidades.nome).all()
        return jsonify([{"id": u.id, "codigo": u.codigo, "nome": u.nome, "simbolo": u.simbolo} for u in unidades])

    @nota_fiscal_bp.route("/api/comparar-unidades", methods=["POST"])
    @login_required
    def api_comparar_unidades():
        """
        Compara duas unidades e retorna se são iguais ou se existe fator de conversão.
        Espera JSON: {unidadeNota: str, unidadeMaterial: str}
        Retorna: {success: bool, fator_conversao: float|None}
        """
        print('api_comparar_unidades', request.get_json());
        data = request.get_json() or {}
        unidade_nota = data.get("unidadeNota", "").strip()
        unidade_material = data.get("unidadeMaterial", "").strip()

        fator = get_conversao_unidade(unidade_entrada=unidade_nota, unidade_saida=unidade_material)   
        if fator:
            return jsonify({"success": True, "fator_conversao": fator})
        # Não são iguais e não há conversão disponível
        return jsonify({"success": False, "fator_conversao": None})

    @nota_fiscal_bp.route("/api/vincular-material/<int:item_id>", methods=["POST"])
    @login_required
    def api_vincular_material(item_id):
        item = NotaFiscalItem.query.get_or_404(item_id)
        material_id_str = request.form.get("material_id")
        fator_conversao_fornecido = request.form.get("fator_conversao")

        if not material_id_str:
            return jsonify({"success": False, "message": "ID do material não fornecido"}), 400

        try:
            material_id = int(material_id_str)
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": f"ID do material inválido: {material_id_str}"}), 400

        material = Materiais.query.get(material_id)
        if not material:
            return jsonify({"success": False, "message": f"Material com ID {material_id} não encontrado"}), 404

        if fator_conversao_fornecido:
            try:
                item.fator_conversao_aplicado = float(fator_conversao_fornecido)
            except (ValueError, TypeError):
                item.fator_conversao_aplicado = None
        else:
            fator = get_conversao_unidade(item.unidade, material.unidade_obj.nome)
            if not fator and not comparar_unidades(item.unidade, material.unidade_obj.nome):
                return jsonify(
                    {
                        "success": False,
                        "message": f"Fator de conversão não encontrado para as unidades: {item.unidade} e {material.unidade_obj.nome}",
                    }
                )
            item.fator_conversao_aplicado = fator or 1

        item.vincular(item.fator_conversao_aplicado, material_id)
        return jsonify(
            {
                "success": True,
                "message": f"Material {material.nome} vinculado com sucesso ao item",
                "fator_conversao": item.fator_conversao_aplicado,
            }
        )

    
    @nota_fiscal_bp.route("/api/importar_itens", methods=["POST"])
    @login_required
    def importar_itens():
        data = request.get_json() or {}
        itens = data.get("itens") or []
        centro_custo_id = data.get("centro_custo_id")
        observacao = data.get("observacao")

        if not itens:
            return jsonify({"success": False, "message": "Nenhum item selecionado para importação."}), 400

        itens_ja_importados = 0
        itens_importados = 0
        itens_com_erro = []

        for item_data in itens:
            item_id = item_data.get("item_id")
            material_id = item_data.get("material_id")
            fator_conversao = item_data.get("fator_conversao")

            item = NotaFiscalItem.query.get_or_404(item_id)
            if item.importado_estoque:
                itens_ja_importados += 1
                continue

            if not material_id:
                itens_com_erro.append(
                    {"item_id": item_id, "descricao": item.descricao, "erro": "Item não possui material vinculado"}
                )
                continue

            material = Materiais.query.get_or_404(material_id)
            if not fator_conversao:
                if comparar_unidades(item.unidade, material.unidade_obj.nome):
                    fator_conversao = 1
                else:
                    fator_conversao = get_conversao_unidade(item.unidade, material.unidade_obj.nome)

            if not item.material_id:
                item.vincular(fator_conversao, material_id)

            try:
                sucesso, mensagem, _ = item.importar_para_estoque(
                    usuario_id=current_user.id,
                    centro_custo_id=centro_custo_id if centro_custo_id else None,
                    observacao=observacao
                    or f"Importação da NF {item.nota_fiscal.numero_nf if item.nota_fiscal else 'N/A'}",
                )
                if sucesso:
                    itens_importados += 1
                else:
                    itens_com_erro.append({"item_id": item_id, "descricao": item.descricao, "erro": mensagem})
            except Exception as e:
                itens_com_erro.append({"item_id": item_id, "descricao": item.descricao, "erro": str(e)})

        mensagem = "Importação concluída!\n\n"
        mensagem += f"• Itens já importados: {itens_ja_importados}\n"
        mensagem += f"• Itens importados agora: {itens_importados}"
        if itens_com_erro:
            mensagem += f"\n• Itens com erro: {len(itens_com_erro)}"

        return jsonify(
            {
                "success": True,
                "message": mensagem,
                "itens_importados": itens_importados,
                "itens_ja_importados": itens_ja_importados,
                "itens_com_erro": len(itens_com_erro),
                "total_itens_selecionados": len(itens),
            }
        )

    @nota_fiscal_bp.route("/api/importar-pendentes-com-material", methods=["POST"])
    @login_required
    def api_importar_pendentes_com_material():
        data = request.get_json() or {}
        nf_id = data.get("nf_id")
        centro_custo_id = data.get("centro_custo_id")
        observacao = data.get("observacao")
        if not nf_id:
            return jsonify({"success": False, "message": "ID da nota fiscal não fornecido"}), 400

        nota_fiscal = NotaFiscal.query.get_or_404(int(nf_id))
        estatisticas = nota_fiscal.importar_pendentes_com_material(
            usuario_id=current_user.id,
            centro_custo_id=centro_custo_id,
            observacao=observacao,
        )

        mensagens = []
        if estatisticas.get("total_itens_vinculados", 0) > 0:
            mensagens.append(f'{estatisticas["total_itens_vinculados"]} item(ns) vinculado(s) em outras notas.')
        if estatisticas.get("total_itens_importados", 0) > 0:
            mensagens.append(f'{estatisticas["total_itens_importados"]} item(ns) importado(s) para o estoque.')
        if estatisticas.get("itens_com_erro"):
            mensagens.append(f'{len(estatisticas["itens_com_erro"])} item(ns) com erro na importação.')

        return jsonify(
            {
                "success": True,
                "message": " ".join(mensagens) if mensagens else "Nenhum item foi processado.",
                "itens_vinculados": estatisticas.get("total_itens_vinculados", 0),
                "itens_ja_vinculados": estatisticas.get("total_itens_ja_vinculados", 0),
                "itens_importados": estatisticas.get("total_itens_importados", 0),
                "itens_ja_importados": estatisticas.get("total_itens_ja_importados", 0),
                "itens_com_erro": len(estatisticas.get("itens_com_erro") or []),
                "total_pendentes": len([i for i in nota_fiscal.itens if (not i.importado_estoque and i.material_id)]),
            }
        )

    @nota_fiscal_bp.route("/api/desvincular-material/<int:item_id>", methods=["POST"])
    @login_required
    def api_desvincular_material(item_id):
        item = NotaFiscalItem.query.get_or_404(item_id)
        if not item.material_id:
            return jsonify({"success": False, "message": "Item não possui material vinculado"}), 400

        if item.movimentacao_estoque_id:
            mov = EstoqueMovimentacoes.query.get(item.movimentacao_estoque_id)
            if mov:
                db.session.delete(mov)

        item.material_id = None
        item.fator_conversao_aplicado = None
        item.movimentacao_estoque_id = None
        item.importado_estoque = False
        item.data_importacao_estoque = None
        item.usuario_importacao_id = None
        item.status_importacao = "Pendente"
        db.session.add(item)
        db.session.commit()

        return jsonify({"success": True, "message": "Material desvinculado com sucesso do item", "itens_processados": 1})

    @nota_fiscal_bp.route("/api/buscar-materiais-outras-notas", methods=["GET"])
    @login_required
    def api_buscar_materiais_outras_notas():
        codigo = (request.args.get("codigo", "") or "").strip()
        descricao = (request.args.get("descricao", "") or "").strip()
        if not codigo and not descricao:
            return jsonify({"success": False, "message": "Código ou descrição do item é obrigatório"}), 400

        materiais_encontrados = []

        def _add_item(it):
            if it.material_id and it.material and not any(m["material_id"] == it.material_id for m in materiais_encontrados):
                materiais_encontrados.append(
                    {
                        "material_id": it.material_id,
                        "material_nome": it.material.nome if it.material else "N/A",
                        "unidade": it.material.unidade_obj.nome if it.material and it.material.unidade_obj else "N/A",
                        "fator_conversao": str(it.fator_conversao_aplicado) if it.fator_conversao_aplicado else "1",
                        "nota_fiscal_numero": it.nota_fiscal.numero_nf if it.nota_fiscal else "N/A",
                        "data_importacao": it.data_importacao_estoque.strftime("%d/%m/%Y")
                        if it.data_importacao_estoque
                        else "N/A",
                    }
                )

        if codigo:
            itens = (
                NotaFiscalItem.query.join(NotaFiscal, NotaFiscalItem.nf_id == NotaFiscal.id)
                .filter(
                    NotaFiscalItem.codigo == codigo,
                    NotaFiscalItem.material_id.isnot(None),
                    NotaFiscalItem.importado_estoque.is_(True),
                )
                .order_by(NotaFiscalItem.data_importacao_estoque.desc())
                .limit(10)
                .all()
            )
            for it in itens:
                _add_item(it)

        if descricao:
            itens = (
                NotaFiscalItem.query.filter(
                    NotaFiscalItem.descricao == descricao,
                    NotaFiscalItem.material_id.isnot(None),
                    NotaFiscalItem.importado_estoque.is_(True),
                )
                .order_by(NotaFiscalItem.data_importacao_estoque.desc())
                .limit(10)
                .all()
            )
            for it in itens:
                _add_item(it)

        return jsonify({"success": True, "materiais": materiais_encontrados})

    @nota_fiscal_bp.route("/api/vincular-material-outras-notas", methods=["POST"])
    @login_required
    def api_vincular_material_outras_notas():
        data = request.get_json() or {}
        nf_id = data.get("nf_id")
        item_id = data.get("item_id")
        material_id = data.get("material_id")
        fator_conversao = data.get("fator_conversao")
        codigo = (data.get("codigo") or "").strip()
        descricao = (data.get("descricao") or "").strip()

        if not nf_id or not item_id or not material_id:
            return jsonify({"success": False, "message": "Parâmetros obrigatórios não fornecidos"}), 400

        item_original = NotaFiscalItem.query.get_or_404(item_id)
        material = Materiais.query.get_or_404(material_id)

        itens_similares = []
        if codigo:
            itens_similares.extend(
                NotaFiscalItem.query.filter(
                    NotaFiscalItem.nf_id == nf_id,
                    NotaFiscalItem.codigo == codigo,
                    NotaFiscalItem.unidade == item_original.unidade,
                    NotaFiscalItem.material_id.is_(None),
                ).all()
            )
        if descricao:
            itens_desc = NotaFiscalItem.query.filter(
                NotaFiscalItem.nf_id == nf_id,
                NotaFiscalItem.descricao == descricao,
                NotaFiscalItem.unidade == item_original.unidade,
                NotaFiscalItem.material_id.is_(None),
            ).all()
            for it in itens_desc:
                if it not in itens_similares:
                    itens_similares.append(it)

        if item_original not in itens_similares:
            itens_similares.append(item_original)

        itens_vinculados = 0
        for it in itens_similares:
            fator = (
                fator_conversao
                or get_conversao_unidade(it.unidade, material.unidade_obj.nome)
                or (1 if comparar_unidades(it.unidade, material.unidade_obj.nome) else None)
            )
            it.vincular(fator, material_id)
            itens_vinculados += 1

        return jsonify(
            {
                "success": True,
                "message": f'Material "{material.nome}" vinculado com sucesso a {itens_vinculados} item(ns)!',
                "itens_vinculados": itens_vinculados,
            }
        )

    @nota_fiscal_bp.route("/api/vincular-itens-similares-todas-notas", methods=["POST"])
    @login_required
    def api_vincular_itens_similares_todas_notas():
        data = request.get_json() or {}
        item_id = data.get("item_id")
        material_id = data.get("material_id")
        fator_conversao = data.get("fator_conversao")
        codigo = (data.get("codigo") or "").strip()
        descricao = (data.get("descricao") or "").strip()

        if not item_id or not material_id:
            return jsonify({"success": False, "message": "Parâmetros obrigatórios não fornecidos"}), 400

        item_original = NotaFiscalItem.query.get_or_404(item_id)
        material = Materiais.query.get_or_404(material_id)

        q = NotaFiscalItem.query.filter(NotaFiscalItem.id != item_id)
        if codigo:
            q = q.filter(NotaFiscalItem.codigo == codigo)
        if descricao:
            q = q.filter(NotaFiscalItem.descricao == descricao)
        q = q.filter(NotaFiscalItem.unidade == item_original.unidade)

        itens = q.all()
        itens_vinculados = 0
        itens_ja_vinculados = 0
        for it in itens:
            if it.material_id:
                itens_ja_vinculados += 1
                continue
            fator = fator_conversao
            if fator:
                try:
                    fator = float(fator)
                except (ValueError, TypeError):
                    fator = None
            if fator is None:
                fator = get_conversao_unidade(it.unidade, material.unidade_obj.nome) or (
                    1 if comparar_unidades(it.unidade, material.unidade_obj.nome) else None
                )
            it.material_id = material_id
            it.fator_conversao_aplicado = fator
            it.save()
            itens_vinculados += 1

        return jsonify(
            {
                "success": True,
                "message": f'Material "{material.nome}" vinculado com sucesso!\n\n• Itens já vinculados: {itens_ja_vinculados}\n• Itens vinculados agora: {itens_vinculados}',
                "itens_vinculados": itens_vinculados,
                "itens_ja_vinculados": itens_ja_vinculados,
                "total_itens_similares": len(itens),
            }
        )

    @nota_fiscal_bp.route("/api/excluir", methods=["POST"])
    @login_required
    def api_excluir_nota_fiscal():
        """Exclui uma nota fiscal e retorna JSON"""
        # Validar CSRF token
        csrf_token = request.form.get('csrf_token') or (request.json.get('csrf_token') if request.is_json else None)
        if csrf_token:
            try:
                from flask_wtf.csrf import validate_csrf
                validate_csrf(csrf_token)
            except Exception as e:
                logger.warning(f"Erro de validação CSRF: {str(e)}")
                return jsonify({"success": False, "message": "Token CSRF inválido"}), 403

        nf_id = request.form.get("nf_id") or (request.json.get("nf_id") if request.is_json else None)
        if not nf_id:
            return jsonify({"success": False, "message": "ID da nota fiscal não fornecido"}), 400

        try:
            nota_fiscal = NotaFiscal.query.get(int(nf_id))
            if not nota_fiscal:
                return jsonify({"success": False, "message": "Nota fiscal não encontrada"}), 404

            numero_nf = nota_fiscal.numero_nf
            nota_fiscal.delete()
            
            usuario_nome = getattr(current_user, 'nome', None) or getattr(current_user, 'email', 'Usuário desconhecido')
            logger.info(f"Nota fiscal {numero_nf} (ID: {nf_id}) excluída por {usuario_nome}")
            return jsonify({"success": True, "message": f"Nota fiscal {numero_nf} excluída com sucesso"})
        except ValueError:
            return jsonify({"success": False, "message": "ID da nota fiscal inválido"}), 400
        except Exception as e:
            logger.error(f"Erro ao excluir nota fiscal: {str(e)}")
            return jsonify({"success": False, "message": f"Erro ao excluir nota fiscal: {str(e)}"}), 500

    @nota_fiscal_bp.route("/api/liberar", methods=["POST"])
    @login_required
    def api_liberar_nota_fiscal():
        """Alterna o status de liberação da nota fiscal"""
        import json
        from datetime import datetime

        # Validar CSRF token
        csrf_token = request.form.get('csrf_token') or (request.json.get('csrf_token') if request.is_json else None)
        if csrf_token:
            try:
                from flask_wtf.csrf import validate_csrf
                validate_csrf(csrf_token)
            except Exception as e:
                logger.warning(f"Erro de validação CSRF: {str(e)}")
                return jsonify({"success": False, "message": "Token CSRF inválido"}), 403

        nf_id_raw = request.form.get("nf_id") or (request.json.get("nf_id") if request.is_json else None)
        nf_id = (nf_id_raw or "").strip() if nf_id_raw is not None else None
        if not nf_id:
            logger.warning("api/liberar: nf_id não fornecido")
            return jsonify({"success": False, "message": "ID da nota fiscal não fornecido"}), 400

        try:
            nf_id_int = int(nf_id)
        except ValueError:
            logger.warning("api/liberar: nf_id inválido: %s", repr(nf_id_raw))
            return jsonify({"success": False, "message": "ID da nota fiscal inválido (deve ser um número)."}), 400

        try:
            nota_fiscal = NotaFiscal.query.get(nf_id_int)
            if not nota_fiscal:
                return jsonify({"success": False, "message": "Nota fiscal não encontrada"}), 404

            # Carregar dados_adicionais existentes ou criar novo dict
            dados_adicionais = {}
            if nota_fiscal.dados_adicionais:
                try:
                    dados_adicionais = json.loads(nota_fiscal.dados_adicionais) if isinstance(nota_fiscal.dados_adicionais, str) else nota_fiscal.dados_adicionais
                except (json.JSONDecodeError, TypeError):
                    dados_adicionais = {}
            if not isinstance(dados_adicionais, dict):
                dados_adicionais = {}

            # Alternar status de liberação
            liberada = dados_adicionais.get('liberada', False)
            dados_adicionais['liberada'] = not liberada

            # Ao liberar: receber e gravar tipo de item (MP/UC/IM) e pedido de compra
            if dados_adicionais['liberada']:
                tipo_item = request.form.get('tipo_item') or (request.json.get('tipo_item') if request.is_json else None)
                pedido_compra = request.form.get('pedido_compra') or (request.json.get('pedido_compra') if request.is_json else None)
                pedido_id = request.form.get('pedido_id') or (request.json.get('pedido_id') if request.is_json else None)
                itens_entrada_raw = request.form.get('itens_entrada') or (request.json.get('itens_entrada') if request.is_json else None)
                pedido_item_id_raw = request.form.get('pedido_item_id') or (request.json.get('pedido_item_id') if request.is_json else None)
                quantidade_entrada_raw = request.form.get('quantidade_entrada') or (request.json.get('quantidade_entrada') if request.is_json else None)
                # Tratar string vazia como não informado (liberar sem vincular pedido)
                pedido_item_id = (pedido_item_id_raw or "").strip() or None
                quantidade_entrada = (quantidade_entrada_raw or "").strip() or None
                if tipo_item:
                    dados_adicionais['tipo_item'] = tipo_item.strip()
                if pedido_compra is not None and str(pedido_compra).strip():
                    dados_adicionais['pedido_compra'] = str(pedido_compra).strip()
                if pedido_id is not None and str(pedido_id).strip():
                    dados_adicionais['pedido_id'] = str(pedido_id).strip()
                dados_adicionais['liberada_por'] = getattr(current_user, 'nome', None) or getattr(current_user, 'email', 'Usuário desconhecido')
                dados_adicionais['liberada_em'] = datetime.now().isoformat()

                itens_entrada = []
                if itens_entrada_raw:
                    try:
                        itens_entrada = json.loads(itens_entrada_raw) if isinstance(itens_entrada_raw, str) else itens_entrada_raw
                    except Exception:
                        logger.warning("api/liberar: itens_entrada inválido: %s", repr(itens_entrada_raw))
                        return jsonify({"success": False, "message": "Lista de itens de entrada inválida."}), 400

                    if not isinstance(itens_entrada, list):
                        return jsonify({"success": False, "message": "Lista de itens de entrada inválida."}), 400

                # Compatibilidade com payload antigo (1 item)
                if not itens_entrada and pedido_item_id and quantidade_entrada:
                    itens_entrada = [{
                        "pedido_item_id": pedido_item_id,
                        "quantidade_entrada": quantidade_entrada
                    }]

                # Só registrar entrada se houver itens informados
                for item_entrada in itens_entrada:
                    if not isinstance(item_entrada, dict):
                        return jsonify({"success": False, "message": "Item de entrada inválido."}), 400

                    pedido_item_id_val = item_entrada.get("pedido_item_id")
                    quantidade_entrada_val = item_entrada.get("quantidade_entrada")
                    if pedido_item_id_val in (None, "") or quantidade_entrada_val in (None, ""):
                        return jsonify({"success": False, "message": "Preencha item do pedido e quantidade de entrada."}), 400

                    try:
                        qtd = Decimal(str(quantidade_entrada_val))
                    except Exception:
                        logger.warning("api/liberar: quantidade_entrada inválida: %s", repr(quantidade_entrada_val))
                        return jsonify({"success": False, "message": "Quantidade de entrada inválida."}), 400

                    if qtd <= 0:
                        logger.warning("api/liberar: quantidade de entrada <= 0")
                        return jsonify({"success": False, "message": "Quantidade de entrada deve ser maior que zero."}), 400

                    try:
                        pedido_item_id_int = int(pedido_item_id_val)
                    except ValueError:
                        logger.warning("api/liberar: pedido_item_id inválido: %s", repr(pedido_item_id_val))
                        return jsonify({"success": False, "message": "Item do pedido inválido."}), 400

                    item = PedidoCompraItem.query.get(pedido_item_id_int)
                    if not item:
                        return jsonify({"success": False, "message": "Item do pedido não encontrado."}), 404

                    # Validar fornecedor (cnpj do fornecedor vs cnpj emitente da NF)
                    def _norm_cnpj(v):
                        return ''.join([c for c in str(v or '') if c.isdigit()])

                    cnpj_nf = _norm_cnpj(nota_fiscal.cnpj_emitente)
                    cnpj_fornecedor = _norm_cnpj(item.pedido.fornecedor.cnpj if item.pedido and item.pedido.fornecedor else '')
                    if cnpj_nf and cnpj_fornecedor and cnpj_nf != cnpj_fornecedor:
                        logger.warning("api/liberar: CNPJ NF não corresponde ao fornecedor do pedido")
                        return jsonify({"success": False, "message": "Fornecedor da NF não corresponde ao fornecedor do pedido selecionado."}), 400

                    saldo = item.get_saldo()
                    if qtd > (saldo or 0):
                        logger.warning("api/liberar: quantidade %s > saldo %s", qtd, saldo)
                        return jsonify({"success": False, "message": f"Quantidade de entrada ({qtd}) maior que o saldo do item ({saldo})."}), 400

                    entrada = PedidoCompraEntrada(
                        pedido_item_id=item.id,
                        nota_fiscal_id=nota_fiscal.id,
                        quantidade_entrada=qtd,
                    )
                    db.session.add(entrada)
            else:
                dados_adicionais['desliberada_por'] = getattr(current_user, 'nome', None) or getattr(current_user, 'email', 'Usuário desconhecido')
                dados_adicionais['desliberada_em'] = datetime.now().isoformat()

                # Ao desliberar, remover entradas vinculadas a esta nota fiscal
                PedidoCompraEntrada.query.filter_by(nota_fiscal_id=nota_fiscal.id).delete()

            # Salvar dados_adicionais atualizados
            nota_fiscal.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)
            db.session.commit()

            status_texto = "liberada" if dados_adicionais['liberada'] else "desliberada"
            usuario_nome = getattr(current_user, 'nome', None) or getattr(current_user, 'email', 'Usuário desconhecido')
            logger.info(f"Nota fiscal {nota_fiscal.numero_nf} (ID: {nf_id_int}) {status_texto} por {usuario_nome}")

            return jsonify({
                "success": True,
                "message": f"Nota fiscal {nota_fiscal.numero_nf} {status_texto} com sucesso",
                "liberada": dados_adicionais['liberada']
            })
        except Exception as e:
            logger.error(f"Erro ao alterar status de liberação: {str(e)}", exc_info=True)
            return jsonify({"success": False, "message": f"Erro ao alterar status de liberação: {str(e)}"}), 500

    @nota_fiscal_bp.route("/api/cancelar", methods=["POST"])
    @login_required
    def api_cancelar_nota_fiscal():
        """Alterna o status de cancelamento da nota fiscal (cancelar / descancelar)"""
        import json
        from datetime import datetime

        # Validar CSRF token
        csrf_token = request.form.get("csrf_token") or (request.json.get("csrf_token") if request.is_json else None)
        if csrf_token:
            try:
                from flask_wtf.csrf import validate_csrf

                validate_csrf(csrf_token)
            except Exception as e:
                logger.warning(f"Erro de validação CSRF: {str(e)}")
                return jsonify({"success": False, "message": "Token CSRF inválido"}), 403

        nf_id = request.form.get("nf_id") or (request.json.get("nf_id") if request.is_json else None)
        if not nf_id:
            return jsonify({"success": False, "message": "ID da nota fiscal não fornecido"}), 400

        try:
            nota_fiscal = NotaFiscal.query.get(int(nf_id))
            if not nota_fiscal:
                return jsonify({"success": False, "message": "Nota fiscal não encontrada"}), 404

            # Carregar dados_adicionais existentes ou criar novo dict
            dados_adicionais = {}
            if nota_fiscal.dados_adicionais:
                try:
                    dados_adicionais = (
                        json.loads(nota_fiscal.dados_adicionais)
                        if isinstance(nota_fiscal.dados_adicionais, str)
                        else nota_fiscal.dados_adicionais
                    )
                except (json.JSONDecodeError, TypeError):
                    dados_adicionais = {}

            # Alternar status de cancelamento
            estava_cancelada = nota_fiscal.status_processamento == "cancelada"
            if estava_cancelada:
                # Descancelar: volta para 'importado' ou para o status anterior, se existir em dados_adicionais
                status_anterior = dados_adicionais.get("status_antes_cancelamento") or "importado"
                nota_fiscal.status_processamento = status_anterior
                dados_adicionais["cancelada_por"] = getattr(current_user, "nome", None) or getattr(
                    current_user, "email", "Usuário desconhecido"
                )
                dados_adicionais["cancelada_revertida_em"] = datetime.now().isoformat()
            else:
                # Cancelar: guarda status atual e marca como cancelada
                dados_adicionais["status_antes_cancelamento"] = nota_fiscal.status_processamento
                nota_fiscal.status_processamento = "cancelada"
                dados_adicionais["cancelada_por"] = getattr(current_user, "nome", None) or getattr(
                    current_user, "email", "Usuário desconhecido"
                )
                dados_adicionais["cancelada_em"] = datetime.now().isoformat()

            nota_fiscal.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)
            db.session.commit()

            usuario_nome = getattr(current_user, "nome", None) or getattr(
                current_user, "email", "Usuário desconhecido"
            )
            acao = "descancelada" if estava_cancelada else "cancelada"
            logger.info(f"Nota fiscal {nota_fiscal.numero_nf} (ID: {nf_id}) {acao} manualmente por {usuario_nome}")

            return jsonify(
                {
                    "success": True,
                    "message": f"Nota fiscal {nota_fiscal.numero_nf} {acao} com sucesso",
                    "cancelada": nota_fiscal.status_processamento == "cancelada",
                }
            )
        except ValueError:
            return jsonify({"success": False, "message": "ID da nota fiscal inválido"}), 400
        except Exception as e:
            logger.error(f"Erro ao alterar status de cancelamento: {str(e)}")
            return jsonify(
                {"success": False, "message": f"Erro ao alterar status de cancelamento: {str(e)}"}
            ), 500


def register_api(api_bp):
    """
    Registra as mesmas APIs no blueprint global `api_bp` (prefixo /api),
    com rotas sob /api/notas-fiscais/... para centralização.

    Observação: mantemos o `register(nota_fiscal_bp)` para compatibilidade com o front
    que chama /notas-fiscais/api/...
    """

    @api_bp.route("/notas-fiscais/itens/<int:nf_id>", methods=["GET"])
    @login_required
    def api_nf_itens(nf_id):
        nota_fiscal = NotaFiscal.query.get_or_404(nf_id)
        items = []
        for item in nota_fiscal.itens:
            material = Materiais.query.get(item.material_id) if item.material_id else None
            items.append(
                {
                    "id": item.id,
                    "codigo": item.codigo,
                    "cfop": item.cfop,
                    "descricao": item.descricao,
                    "quantidade": float(item.quantidade) if item.quantidade is not None else 0.0,
                    "unidade": item.unidade,
                    "valor_unitario": float(item.valor_unitario) if item.valor_unitario is not None else 0.0,
                    "valor_total": float(item.valor_total) if item.valor_total is not None else 0.0,
                    "ncm": item.ncm,
                    "material_id": item.material_id,
                    "material_unidade": material.unidade_obj.nome if material and material.unidade_obj else None,
                    "material_nome": material.nome if material else None,
                    "importado_estoque": bool(item.importado_estoque),
                    "data_importacao_estoque": item.data_importacao_estoque.isoformat()
                    if item.data_importacao_estoque
                    else None,
                    "fator_conversao_aplicado": item.fator_conversao_aplicado,
                }
            )
        return jsonify({"itens": items, "success": True})

    @api_bp.route("/notas-fiscais/comparar-unidades", methods=["POST"])
    @login_required
    def api_comparar_unidades_centralizado():
        """
        Compara duas unidades e retorna se são iguais ou se existe fator de conversão.
        Versão centralizada no api_bp (prefixo /api).
        Espera JSON: {unidadeNota: str, unidadeMaterial: str}
        Retorna: {success: bool, fator_conversao: float|None}
        """
        data = request.get_json() or {}
        unidade_nota = data.get("unidadeNota", "").strip()
        unidade_material = data.get("unidadeMaterial", "").strip()

        if not unidade_nota or not unidade_material:
            return jsonify({"success": False, "message": "Unidades não fornecidas"}), 400

        # Verifica se são iguais usando a função comparar_unidades
        sao_iguais = comparar_unidades(unidade_nota, unidade_material)
        if sao_iguais:
            return jsonify({"success": True, "fator_conversao": 1.0})

        # Se não são iguais, tenta buscar fator de conversão
        fator = get_conversao_unidade(unidade_nota, unidade_material)
        if fator:
            return jsonify({"success": True, "fator_conversao": fator})

        # Não são iguais e não há conversão disponível
        return jsonify({"success": False, "fator_conversao": None})



