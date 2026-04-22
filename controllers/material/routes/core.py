import logging

from flask import flash, redirect, render_template, request, url_for, jsonify
from flask_login import current_user, login_required

from models.database import db
from models.material import Materiais
from models.plano_conta import PlanoConta
from models.unidade import Unidades
from utils.utils import parse_dados_json
from utils.normalizar import normalizar_str_inteiro

from .. import material_bp

logger = logging.getLogger(__name__)


@material_bp.before_request
def before_request():
    if not current_user.is_permissao('material'):
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('dashboard.index'))

@material_bp.route("/")
@login_required
def index():
    search_term = request.args.get("search", "").strip()
    category_filters = [
        c.strip() for c in request.args.getlist("category") if c and str(c).strip()
    ]

    planos_conta = PlanoConta.query.filter_by(ativo=True).all()
    unidades = Unidades.query.filter_by(ativo=True).order_by(Unidades.nome).all()
    todas_categorias = db.session.query(Materiais.categoria).distinct().order_by(Materiais.categoria).all()
    categorias_filtro = [cat[0] for cat in todas_categorias if cat[0]]

    return render_template(
        "materiais/index.html",
        planos_conta=planos_conta,
        unidades=unidades,
        categorias_filtro=categorias_filtro,
        search_term=search_term,
        category_filters=category_filters,
    )


@material_bp.route("/novo", methods=["GET"])
@login_required
def novo_get():
    return redirect(url_for("material.index"))


@material_bp.route("/novo", methods=["POST"])
@login_required
def novo():
    planos_conta = PlanoConta.query.filter_by(ativo=True).order_by(PlanoConta.indice).all()
    unidades = Unidades.query.filter_by(ativo=True).order_by(Unidades.nome).all()

    from_modal = request.referrer and "index" in request.referrer

    try:
        material = Materiais.criar_desde_formulario(
            nome=request.form.get("nome"),
            descricao=request.form.get("descricao"),
            categoria=request.form.get("categoria"),
            plano_conta=request.form.get("plano_conta"),
            unidade=request.form.get("unidade"),
            unidade_texto=request.form.get("unidade_texto", ""),
            mascara_raw=request.form.get("mascara"),
            formula_calculo=request.form.get("formula_calculo", ""),
            codigo_raw=request.form.get("codigo"),
            codigo_alterdata_raw=request.form.get("codigo_alterdata"),
            codigo_erp_raw=request.form.get("codigo_erp"),
            codigo_mega_raw=request.form.get("codigo_mega"),
        )
        material.usuario_id = current_user.id
        material.save()

        arquivo_img = request.files.get("imagem_material")
        if arquivo_img and arquivo_img.filename:
            material.set_imagem_upload(arquivo_img)

        flash("Material cadastrado com sucesso!", "success")
        return redirect(url_for("material.index"))
    except ValueError as e:
        flash(str(e), "danger")
        if from_modal:
            return redirect(url_for("material.index"))
        return render_template("materiais/novo.html", planos_conta=planos_conta, unidades=unidades)
    except Exception as e:
        flash(f"Erro ao cadastrar material: {str(e)}", "danger")
        return redirect(url_for("material.index"))


@material_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar(id):
    from models.estoque import Estoque, EstoqueMovimentacoes
    material = Materiais.query.get_or_404(id)

    if request.method == "POST":
        csrf_token = request.form.get("csrf_token")
        if not csrf_token:
            return jsonify({"success": False, "message": "CSRF token não fornecido"}), 400

        data = request.form
        quantidade = data.get("edit_quantidade", "")
        quantidade_minima = data.get("edit_quantidade_minima", "")
        quantidade_maxima = data.get("edit_quantidade_maxima", "")

        try:
            material.aplicar_edicao_desde_formulario(
                nome=data.get("edit_nome", ""),
                descricao=data.get("edit_descricao", ""),
                categoria=data.get("edit_categoria", ""),
                plano_conta=data.get("edit_plano_conta", ""),
                unidade=data.get("edit_unidade", ""),
                mascara_raw=data.get("edit_mascara", ""),
                formula_calculo=data.get("edit_formula_calculo", ""),
                codigo_raw=data.get("edit_codigo", ""),
                codigo_alterdata_raw=data.get("edit_codigo_alterdata"),
                codigo_erp_raw=data.get("edit_codigo_erp"),
                codigo_mega_raw=data.get("edit_codigo_mega"),
            )

            remover_img = data.get("remover_imagem_material") == "1"
            arquivo_img = request.files.get("imagem_material")
            if remover_img:
                material.remover_imagem_upload()
            elif arquivo_img and arquivo_img.filename:
                material.set_imagem_upload(arquivo_img)

            from decimal import Decimal

            estoque = Estoque.query.filter_by(material_id=material.id, tipo_item="material").first()

            if quantidade or quantidade_minima or quantidade_maxima:
                quantidade_anterior = None
                if not estoque:
                    estoque = Estoque(
                        material_id=material.id,
                        tipo_item="material",
                        quantidade=Decimal(str(quantidade)) if quantidade else Decimal("0"),
                        quantidade_minima=Decimal(str(quantidade_minima)) if quantidade_minima else Decimal("0"),
                        quantidade_maxima=Decimal(str(quantidade_maxima)) if quantidade_maxima else Decimal("0"),
                        usuario_id=current_user.id if hasattr(current_user, "id") else None,
                    )
                    db.session.add(estoque)
                else:
                    quantidade_anterior = estoque.quantidade
                    if quantidade:
                        estoque.quantidade = Decimal(str(quantidade))
                    if quantidade_minima:
                        estoque.quantidade_minima = Decimal(str(quantidade_minima))
                    if quantidade_maxima:
                        estoque.quantidade_maxima = Decimal(str(quantidade_maxima))
                    estoque.usuario_id = (
                        current_user.id if hasattr(current_user, "id") else estoque.usuario_id
                    )

                if estoque and quantidade and quantidade_anterior is not None:
                    nova_quantidade = Decimal(str(quantidade))
                    if nova_quantidade != quantidade_anterior:
                        movimentacao = EstoqueMovimentacoes(
                            estoque_id=estoque.id,
                            tipo_movimento="ajuste",
                            quantidade=nova_quantidade,
                            observacao="Ajuste manual via edição de material",
                            usuario_id=current_user.id if hasattr(current_user, "id") else None,
                        )
                        db.session.add(movimentacao)

            db.session.commit()
            return jsonify(
                {"success": True, "message": "Material atualizado com sucesso!", "redirect": url_for("material.index")}
            )
        except ValueError as ve:
            db.session.rollback()
            return jsonify({"success": False, "message": str(ve)})
        except Exception as db_error:
            db.session.rollback()
            logger.error(f"Erro ao salvar material: {str(db_error)}", exc_info=True)
            return jsonify({"success": False, "message": f"Erro ao salvar material: {str(db_error)}"})

    img_id = material.get_imagem_upload_id()
    extras = parse_dados_json(material.dados_adicionais)
    return jsonify(
        {
            "id": material.id,
            "codigo": normalizar_str_inteiro(extras.get("codigo_sox")),
            "nome": material.nome,
            "descricao": material.descricao or "",
            "categoria": material.categoria,
            "plano_conta": material.plano_conta or "",
            "codigo_erp": normalizar_str_inteiro(extras.get("codigo_alterdata")),
            "codigo_alterdata": normalizar_str_inteiro(extras.get("codigo_alterdata")),
            "codigo_mega": normalizar_str_inteiro(extras.get("codigo_mega") or extras.get("cod_mega")),
            "unidade": material.unidade_obj.nome if material.unidade_obj else "",
            "mascara": normalizar_str_inteiro(material.mascara),
            "formula_calculo": material.formula_calculo or "",
            "imagem_upload_id": img_id,
        }
    )


@material_bp.route("/visualizar/<int:id>")
@login_required
def visualizar(id):
    material = Materiais.query.get_or_404(id)
    return render_template("materiais/visualizar.html", material=material)


@material_bp.route("/excluir/<int:id>", methods=["POST"])
@login_required
def excluir(id):
    if not current_user.is_permissao('material', 'excluir'):
        flash('Você não tem permissão para excluir este material.', 'danger')
        return redirect(url_for('material.index'))
    try:
        material = Materiais.query.get_or_404(id)
        msg = material.excluir_apos_validar_vinculos()
        flash(msg, "success")
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("material.index"))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir material {id}: {str(e)}", exc_info=True)
        flash(f"Erro ao excluir material: {str(e)}", "danger")
    return redirect(url_for("material.index"))


