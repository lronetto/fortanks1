import logging
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required
from sqlalchemy import or_

from models.database import db
from models.material import Material
from models.plano_conta import PlanoConta
from models.unidade import Unidade

from .. import material_bp

logger = logging.getLogger(__name__)


@material_bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    search_term = request.args.get("search", "").strip()
    category_filter = request.args.get("category", "").strip()
    per_page = current_app.config.get("PER_PAGE", 20)

    query = Material.query
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.filter(or_(Material.nome.ilike(search_pattern), Material.codigo.ilike(search_pattern)))
    if category_filter:
        query = query.filter(Material.categoria == category_filter)
    query = query.order_by(Material.nome)

    materiais_paginados = query.paginate(page=page, per_page=per_page, error_out=False)
    materiais = materiais_paginados.items

    planos_conta = PlanoConta.query.filter_by(ativo=True).all()
    unidades = Unidade.query.filter_by(ativo=True).order_by(Unidade.nome).all()
    todas_categorias = db.session.query(Material.categoria).distinct().order_by(Material.categoria).all()
    categorias_filtro = [cat[0] for cat in todas_categorias if cat[0]]

    return render_template(
        "materiais/index.html",
        materiais=materiais,
        pagination=materiais_paginados,
        planos_conta=planos_conta,
        unidades=unidades,
        categorias_filtro=categorias_filtro,
        search_term=search_term,
        category_filter=category_filter,
    )


@material_bp.route("/novo", methods=["GET"])
@login_required
def novo_get():
    return redirect(url_for("material.index"))


@material_bp.route("/novo", methods=["POST"])
@login_required
def novo():
    planos_conta = PlanoConta.query.filter_by(ativo=True).order_by(PlanoConta.indice).all()
    unidades = Unidade.query.filter_by(ativo=True).order_by(Unidade.nome).all()

    try:
        codigo = request.form.get("codigo")
        nome = request.form.get("nome")
        descricao = request.form.get("descricao")
        categoria = request.form.get("categoria")
        plano_conta = request.form.get("plano_conta")
        codigo_erp = request.form.get("codigo_erp")
        unidade = request.form.get("unidade")
        mascara = request.form.get("mascara")
        formula_calculo = request.form.get("formula_calculo", "").strip()

        unidade_texto = request.form.get("unidade_texto", "")
        if not unidade and unidade_texto:
            unidade = unidade_texto

        from_modal = request.referrer and "index" in request.referrer

        if not nome or not categoria:
            flash("Nome e categoria são campos obrigatórios!", "danger")
            if from_modal:
                return redirect(url_for("material.index"))
            return render_template("materiais/novo.html", planos_conta=planos_conta, unidades=unidades)

        if codigo and Material.query.filter_by(codigo=codigo).first():
            flash(f"Já existe um material com o código {codigo}!", "danger")
            if from_modal:
                return redirect(url_for("material.index"))
            return render_template("materiais/novo.html", planos_conta=planos_conta, unidades=unidades)

        material = Material(
            codigo=codigo,
            nome=nome,
            descricao=descricao,
            categoria=categoria,
            plano_conta=plano_conta,
            codigo_erp=codigo_erp,
            unidade_id=unidade,
            mascara=mascara,
            formula_calculo=formula_calculo if formula_calculo else None,
        )
        material.usuario_id = current_user.id
        material.save()
        flash("Material cadastrado com sucesso!", "success")
        return redirect(url_for("material.index"))
    except Exception as e:
        flash(f"Erro ao cadastrar material: {str(e)}", "danger")
        return redirect(url_for("material.index"))


@material_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar(id):
    """
    Mantém fluxo de página (HTML). A parte AJAX/JSON foi centralizada em `controllers/api/material_api.py`.
    """
    material = Material.query.get_or_404(id)
    unidades = Unidade.query.filter_by(ativo=True).order_by(Unidade.nome).all()

    if request.method == "POST":
        try:
            codigo = request.form.get("codigo", "")
            nome = request.form.get("nome", "")
            descricao = request.form.get("descricao", "")
            categoria = request.form.get("categoria", "")
            plano_conta = request.form.get("plano_conta", "")
            codigo_erp = request.form.get("codigo_erp", "")
            unidade = request.form.get("unidade", "")
            mascara = request.form.get("mascara", "")
            formula_calculo = request.form.get("formula_calculo", "").strip()

            if not nome or not categoria:
                flash("Nome e categoria são campos obrigatórios!", "danger")
                return render_template(
                    "materiais/editar.html",
                    material=material,
                    planos_conta=PlanoConta.query.filter_by(ativo=True).all(),
                    unidades=unidades,
                )

            if codigo and codigo != material.codigo and Material.query.filter_by(codigo=codigo).first():
                flash(f"Já existe um material com o código {codigo}!", "danger")
                return render_template(
                    "materiais/editar.html",
                    material=material,
                    planos_conta=PlanoConta.query.filter_by(ativo=True).all(),
                    unidades=unidades,
                )

            if not codigo:
                codigo = f"AUTO-{id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            material.codigo = codigo
            material.nome = nome
            material.descricao = descricao
            material.categoria = categoria
            material.plano_conta = plano_conta
            material.codigo_erp = codigo_erp
            material.unidade_id = unidade
            material.mascara = mascara
            material.formula_calculo = formula_calculo if formula_calculo else None

            db.session.add(material)
            db.session.commit()
            flash("Material atualizado com sucesso!", "success")
            return redirect(url_for("material.visualizar", id=material.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao atualizar material: {str(e)}", "danger")
            return redirect(url_for("material.index"))

    planos_conta = PlanoConta.query.filter_by(ativo=True).all()
    return render_template("materiais/editar.html", material=material, planos_conta=planos_conta, unidades=unidades)


@material_bp.route("/visualizar/<int:id>")
@login_required
def visualizar(id):
    material = Material.query.get_or_404(id)
    return render_template("materiais/visualizar.html", material=material)


@material_bp.route("/excluir/<int:id>", methods=["POST"])
@login_required
def excluir(id):
    try:
        material = Material.query.get_or_404(id)
        has_itens = False
        try:
            has_itens = len(material.itens_solicitacao) > 0
        except Exception:
            has_itens = False

        if has_itens:
            flash("Este material não pode ser excluído pois está vinculado a solicitações!", "danger")
            return redirect(url_for("material.visualizar", id=material.id))

        nome = material.nome
        db.session.delete(material)
        db.session.commit()
        flash(f'Material "{nome}" excluído com sucesso!', "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir material: {str(e)}", "danger")
    return redirect(url_for("material.index"))


