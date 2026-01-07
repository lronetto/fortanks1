import base64
import logging
from datetime import datetime

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
            dados_adicionais = json.loads(item.dados_adicionais) if item.dados_adicionais else None
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
        data = request.get_json() or {}
        unidade_nota = data.get("unidadeNota", "").strip()
        unidade_material = data.get("unidadeMaterial", "").strip()

        fator = get_conversao_unidade(unidade_nota, unidade_material)   
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



