import base64
import logging
from datetime import datetime
from decimal import Decimal

from flask import jsonify, request
from flask.wrappers import json
from flask_login import current_user, login_required
from sqlalchemy import func

from models.centro_custo import CentroCusto
from models.unidade import comparar_unidades, get_conversao_unidade, Unidades
from models.database import db
from models.estoque import EstoqueMovimentacoes
from models.material import Materiais
from utils.material_imagem_upload import parse_dados_json
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.pedido_compra import PedidoCompraEntrada, PedidoCompraItem
from ..services.query_notas import api_get_dados_notas_fiscais
from .. import nota_fiscal_bp

logger = logging.getLogger(__name__)

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
        "data_importacao": nota_fiscal.data_importacao.strftime("%d/%m/%Y %H:%M:%S") if nota_fiscal.data_importacao else None,
        "data_atualizacao": nota_fiscal.data_atualizacao.strftime("%d/%m/%Y %H:%M:%S") if nota_fiscal.data_atualizacao else None,
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
        except Exception:
            dados_adicionais = None
        if dados_adicionais:
            inf_ad_prod = dados_adicionais.get("infAdProd")
        else:
            inf_ad_prod = None
        items.append(
            {
                "id": item.id,
                "codigo": item.codigo,
                "cfop": item.cfop,
                "descricao": item.descricao,
                "infAdProd": inf_ad_prod if inf_ad_prod else None,
                "quantidade": float(item.quantidade) if item.quantidade is not None else 0.0,
                "unidade": item.unidade,
                "valor_unitario": float(item.valor_unitario) if item.valor_unitario is not None else 0.0,
                "valor_total": float(item.valor_total) if item.valor_total is not None else 0.0,
                "ncm": item.ncm,
                "material_id": item.material_id,
                "material_unidade": material.unidade_obj.nome if material and material.unidade_obj else None,
                "material_nome": material.nome if material else None,
                "importado_estoque": bool(item.importado_estoque),
                "data_importacao_estoque": item.data_importacao_estoque.isoformat() if item.data_importacao_estoque else None,
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
                Materiais.dados_adicionais.ilike(termo_busca),
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
        unidade_sigla = material.unidade_obj.nome if hasattr(material, "unidade_obj") else (material.unidade_obj.nome or "-")
        tem_conversoes = material.tem_conversoes() if hasattr(material, "tem_conversoes") else False
        resultado.append(
            {
                "id": material.id,
                "nome": material.nome,
                "codigo": parse_dados_json(material.dados_adicionais).get("codigo_sox") or "",
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
    data = request.get_json() or {}
    unidade_nota = data.get("unidadeNota", "").strip()
    unidade_material = data.get("unidadeMaterial", "").strip()
    fator = get_conversao_unidade(unidade_entrada=unidade_nota, unidade_saida=unidade_material)
    if fator:
        return jsonify({"success": True, "fator_conversao": fator})
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
            itens_com_erro.append({"item_id": item_id, "descricao": item.descricao, "erro": "Item não possui material vinculado"})
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
            sucesso, mensagem, _ = item.importar_para_estoque_automatico(
                usuario_id=current_user.id,
                centro_custo_id=centro_custo_id if centro_custo_id else None,
                observacao=observacao or f"Importação da NF {item.nota_fiscal.numero_nf if item.nota_fiscal else 'N/A'}",
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


@nota_fiscal_bp.route("/api/importar-item-estoque/<int:item_id>", methods=["POST"])
@login_required
def api_importar_item_estoque(item_id):
    observacao = (request.form.get("observacao") or "").strip() or None
    centro_raw = request.form.get("centro_custo_id")
    centro_custo_id = int(centro_raw) if centro_raw and str(centro_raw).isdigit() else None

    item = NotaFiscalItem.query.get_or_404(item_id)

    if item.importado_estoque:
        return jsonify(
            {
                "success": True,
                "message": "Item já estava importado para o estoque.",
                "itens_importados": 0,
                "itens_ja_importados": 1,
                "itens_similares_encontrados": 0,
                "itens_com_erro": 0,
            }
        )

    if not item.material_id:
        return jsonify({"success": False, "message": "Item não possui material vinculado."}), 400

    material = Materiais.query.get_or_404(item.material_id)

    fator_conversao = item.fator_conversao_aplicado
    if fator_conversao is None:
        if comparar_unidades(item.unidade, material.unidade_obj.nome):
            fator_conversao = 1
        else:
            fator_conversao = get_conversao_unidade(item.unidade, material.unidade_obj.nome)

    if not fator_conversao and not comparar_unidades(item.unidade, material.unidade_obj.nome):
        return jsonify(
            {
                "success": False,
                "message": f"Fator de conversão não encontrado para as unidades: {item.unidade} e {material.unidade_obj.nome}",
            }
        ), 400

    item.fator_conversao_aplicado = fator_conversao
    db.session.commit()

    try:
        sucesso, mensagem, _ = item.importar_para_estoque_automatico(
            usuario_id=current_user.id,
            centro_custo_id=centro_custo_id,
            observacao=observacao or f"Importação da NF {item.nota_fiscal.numero_nf if item.nota_fiscal else 'N/A'}",
        )
    except Exception:
        logger.exception("api_importar_item_estoque item_id=%s", item_id)
        return jsonify({"success": False, "message": "Erro ao importar item para o estoque."}), 500

    if not sucesso:
        return jsonify({"success": False, "message": mensagem or "Erro ao importar item."}), 400

    return jsonify(
        {
            "success": True,
            "message": mensagem or "Item importado com sucesso!",
            "itens_importados": 1,
            "itens_ja_importados": 0,
            "itens_similares_encontrados": 0,
            "itens_com_erro": 0,
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
                    "data_importacao": it.data_importacao_estoque.strftime("%d/%m/%Y") if it.data_importacao_estoque else "N/A",
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
        fator = fator_conversao or get_conversao_unidade(it.unidade, material.unidade_obj.nome) or (1 if comparar_unidades(it.unidade, material.unidade_obj.nome) else None)
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
            fator = get_conversao_unidade(it.unidade, material.unidade_obj.nome) or (1 if comparar_unidades(it.unidade, material.unidade_obj.nome) else None)
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

        numero_nf = nota_fiscal.numero_nf
        nota_fiscal.delete()

        usuario_nome = getattr(current_user, "nome", None) or getattr(current_user, "email", "Usuário desconhecido")
        logger.info(f"Nota fiscal {numero_nf} (ID: {nf_id}) excluída por {usuario_nome}")
        return jsonify({"success": True, "message": f"Nota fiscal {numero_nf} excluída com sucesso"})
    except ValueError:
        return jsonify({"success": False, "message": "ID da nota fiscal inválido"}), 400
    except Exception as e:
        logger.error(f"Erro ao excluir nota fiscal: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "Erro ao excluir nota fiscal. Tente novamente."}), 500


@nota_fiscal_bp.route("/api/liberar", methods=["POST"])
@login_required
def api_liberar_nota_fiscal():
    import json
    from datetime import datetime

    csrf_token = request.form.get("csrf_token") or (request.json.get("csrf_token") if request.is_json else None)
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

        dados_adicionais = {}
        if nota_fiscal.dados_adicionais:
            try:
                dados_adicionais = json.loads(nota_fiscal.dados_adicionais) if isinstance(nota_fiscal.dados_adicionais, str) else nota_fiscal.dados_adicionais
            except (json.JSONDecodeError, TypeError):
                dados_adicionais = {}
        if not isinstance(dados_adicionais, dict):
            dados_adicionais = {}

        liberada = dados_adicionais.get("liberada", False)
        dados_adicionais["liberada"] = not liberada

        if dados_adicionais["liberada"]:
            tipo_item = request.form.get("tipo_item") or (request.json.get("tipo_item") if request.is_json else None)
            pedido_compra = request.form.get("pedido_compra") or (request.json.get("pedido_compra") if request.is_json else None)
            pedido_id = request.form.get("pedido_id") or (request.json.get("pedido_id") if request.is_json else None)
            itens_entrada_raw = request.form.get("itens_entrada") or (request.json.get("itens_entrada") if request.is_json else None)
            pedido_item_id_raw = request.form.get("pedido_item_id") or (request.json.get("pedido_item_id") if request.is_json else None)
            quantidade_entrada_raw = request.form.get("quantidade_entrada") or (request.json.get("quantidade_entrada") if request.is_json else None)
            pedido_item_id = (pedido_item_id_raw or "").strip() or None
            quantidade_entrada = (quantidade_entrada_raw or "").strip() or None
            if tipo_item:
                dados_adicionais["tipo_item"] = tipo_item.strip()
            if pedido_compra is not None and str(pedido_compra).strip():
                dados_adicionais["pedido_compra"] = str(pedido_compra).strip()
            if pedido_id is not None and str(pedido_id).strip():
                dados_adicionais["pedido_id"] = str(pedido_id).strip()
            dados_adicionais["liberada_por"] = getattr(current_user, "nome", None) or getattr(current_user, "email", "Usuário desconhecido")
            dados_adicionais["liberada_em"] = datetime.now().isoformat()

            itens_entrada = []
            if itens_entrada_raw:
                try:
                    itens_entrada = json.loads(itens_entrada_raw) if isinstance(itens_entrada_raw, str) else itens_entrada_raw
                except Exception:
                    logger.warning("api/liberar: itens_entrada inválido: %s", repr(itens_entrada_raw))
                    return jsonify({"success": False, "message": "Lista de itens de entrada inválida."}), 400

                if not isinstance(itens_entrada, list):
                    return jsonify({"success": False, "message": "Lista de itens de entrada inválida."}), 400

            if not itens_entrada and pedido_item_id and quantidade_entrada:
                itens_entrada = [{"pedido_item_id": pedido_item_id, "quantidade_entrada": quantidade_entrada}]

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

                def _norm_cnpj(v):
                    return "".join([c for c in str(v or "") if c.isdigit()])

                cnpj_nf = _norm_cnpj(nota_fiscal.cnpj_emitente)
                cnpj_fornecedor = _norm_cnpj(item.pedido.fornecedor.cnpj if item.pedido and item.pedido.fornecedor else "")
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
            dados_adicionais["desliberada_por"] = getattr(current_user, "nome", None) or getattr(current_user, "email", "Usuário desconhecido")
            dados_adicionais["desliberada_em"] = datetime.now().isoformat()
            PedidoCompraEntrada.query.filter_by(nota_fiscal_id=nota_fiscal.id).delete()

        nota_fiscal.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)
        db.session.commit()

        status_texto = "liberada" if dados_adicionais["liberada"] else "desliberada"
        usuario_nome = getattr(current_user, "nome", None) or getattr(current_user, "email", "Usuário desconhecido")
        logger.info(f"Nota fiscal {nota_fiscal.numero_nf} (ID: {nf_id_int}) {status_texto} por {usuario_nome}")

        return jsonify(
            {
                "success": True,
                "message": f"Nota fiscal {nota_fiscal.numero_nf} {status_texto} com sucesso",
                "liberada": dados_adicionais["liberada"],
            }
        )
    except Exception as e:
        logger.error(f"Erro ao alterar status de liberação: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "Erro ao alterar status de liberação. Tente novamente."}), 500


@nota_fiscal_bp.route("/api/cancelar", methods=["POST"])
@login_required
def api_cancelar_nota_fiscal():
    import json
    from datetime import datetime

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

        dados_adicionais = {}
        if nota_fiscal.dados_adicionais:
            try:
                dados_adicionais = json.loads(nota_fiscal.dados_adicionais) if isinstance(nota_fiscal.dados_adicionais, str) else nota_fiscal.dados_adicionais
            except (json.JSONDecodeError, TypeError):
                dados_adicionais = {}

        estava_cancelada = nota_fiscal.status_processamento == "cancelada"
        if estava_cancelada:
            status_anterior = dados_adicionais.get("status_antes_cancelamento") or "importado"
            nota_fiscal.status_processamento = status_anterior
            dados_adicionais["cancelada_por"] = getattr(current_user, "nome", None) or getattr(current_user, "email", "Usuário desconhecido")
            dados_adicionais["cancelada_revertida_em"] = datetime.now().isoformat()
        else:
            dados_adicionais["status_antes_cancelamento"] = nota_fiscal.status_processamento
            nota_fiscal.status_processamento = "cancelada"
            dados_adicionais["cancelada_por"] = getattr(current_user, "nome", None) or getattr(current_user, "email", "Usuário desconhecido")
            dados_adicionais["cancelada_em"] = datetime.now().isoformat()

        nota_fiscal.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)
        db.session.commit()

        usuario_nome = getattr(current_user, "nome", None) or getattr(current_user, "email", "Usuário desconhecido")
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
        logger.error(f"Erro ao alterar status de cancelamento: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "Erro ao alterar status de cancelamento. Tente novamente."}), 500

