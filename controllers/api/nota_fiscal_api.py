from flask import jsonify, request
from flask_login import login_required

from models.material import Materiais
from models.nota_fiscal import NotaFiscal
from models.unidade import comparar_unidades, get_conversao_unidade


def register_api(api_bp):
    """
    APIs centralizadas no blueprint global `api_bp` (prefixo /api)
    para endpoints compartilhados de Nota Fiscal.
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
                    "data_importacao_estoque": item.data_importacao_estoque.isoformat() if item.data_importacao_estoque else None,
                    "fator_conversao_aplicado": item.fator_conversao_aplicado,
                }
            )
        return jsonify({"itens": items, "success": True})

    @api_bp.route("/notas-fiscais/comparar-unidades", methods=["POST"])
    @login_required
    def api_comparar_unidades_centralizado():
        data = request.get_json() or {}
        unidade_nota = data.get("unidadeNota", "").strip()
        unidade_material = data.get("unidadeMaterial", "").strip()

        if not unidade_nota or not unidade_material:
            return jsonify({"success": False, "message": "Unidades não fornecidas"}), 400

        sao_iguais = comparar_unidades(unidade_nota, unidade_material)
        if sao_iguais:
            return jsonify({"success": True, "fator_conversao": 1.0})

        fator = get_conversao_unidade(unidade_nota, unidade_material)
        if fator:
            return jsonify({"success": True, "fator_conversao": fator})

        return jsonify({"success": False, "fator_conversao": None})

