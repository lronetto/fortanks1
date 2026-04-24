"""Rotas de página de orçamentos."""

from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased, joinedload

from models.contrato import Contrato
from models.orcamento import Orcamento
from models.database import db
from models.material import Materiais
from models.orcamento import ItemOrcamentoReferenciaMaterial

from .. import orcamento_bp
from ..services.edicao import payload_modal_edicao_orcamento
from ..services.importacao import importar_planilha_orcamento
from ..services.resumo import calcular_resumo_valores_orcamento


@orcamento_bp.route("/", methods=["GET"])
@login_required
def index():
    orcamento_pai = aliased(Orcamento)
    grupo_orcamento_id = func.coalesce(
        orcamento_pai.vinculado_a_orcamento_id,
        Orcamento.vinculado_a_orcamento_id,
        Orcamento.id,
    )
    ordem_no_grupo = case(
        (Orcamento.vinculado_a_orcamento_id.is_(None), 0),
        else_=1,
    )
    orcamentos_recentes = (
        Orcamento.query.outerjoin(orcamento_pai, orcamento_pai.id == Orcamento.vinculado_a_orcamento_id)
        .order_by(grupo_orcamento_id.asc(), ordem_no_grupo.asc(), Orcamento.id.asc())
        .limit(300)
        .all()
    )
    return render_template(
        "cadastros/orcamentos/index.html",
        orcamentos_recentes=orcamentos_recentes,
    )


@orcamento_bp.route("/importar", methods=["POST"])
@login_required
def importar():
    arquivo = request.files.get("arquivo_orcamento")
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo para importar.", "warning")
        return redirect(url_for("orcamento.index"))

    orcamento_id_existente = None
    raw_oid = (request.form.get("orcamento_id_existente") or "").strip()
    if raw_oid:
        try:
            orcamento_id_existente = int(raw_oid)
        except (TypeError, ValueError):
            flash("ID do orçamento existente inválido.", "warning")
            return redirect(url_for("orcamento.index"))

    try:
        resultado = importar_planilha_orcamento(
            arquivo,
            usuario_id=current_user.id,
            orcamento_id_existente=orcamento_id_existente,
        )
        if resultado.get("vinculado_a_existente"):
            flash(
                f'Itens importados para o orçamento #{resultado["orcamento_id"]} '
                f'("{resultado["nome"]}"): {resultado["itens_importados"]}.',
                "success",
            )
        else:
            flash(
                f'Orçamento "{resultado["nome"]}" importado com sucesso. '
                f'Itens importados: {resultado["itens_importados"]}.',
                "success",
            )
    except Exception as exc:
        flash(f"Erro ao importar orçamento: {exc}", "danger")

    return redirect(url_for("orcamento.index"))


@orcamento_bp.route("/novo", methods=["POST"])
@login_required
def novo():
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do orçamento.", "warning")
        return redirect(url_for("orcamento.index"))
    nome = nome[:100]

    data_orc = None
    data_raw = (request.form.get("data") or "").strip()
    if data_raw:
        try:
            data_orc = datetime.strptime(data_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Data inválida.", "warning")
            return redirect(url_for("orcamento.index"))

    descricao = (request.form.get("descricao") or "").strip() or None

    orcamento = Orcamento(
        nome=nome,
        data=data_orc,
        descricao=descricao,
        usuario_id=current_user.id,
    )
    db.session.add(orcamento)
    db.session.commit()
    flash("Orçamento criado.", "success")
    return redirect(url_for("orcamento.visualizar", orcamento_id=orcamento.id))


@orcamento_bp.route("/<int:orcamento_id>/excluir", methods=["POST"])
@login_required
def excluir(orcamento_id):
    orcamento = Orcamento.query.get_or_404(orcamento_id)
    nome = orcamento.nome
    try:
        db.session.delete(orcamento)
        db.session.commit()
        flash(f'Orçamento "{nome}" apagado.', "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao apagar orçamento: {exc}", "danger")
    return redirect(url_for("orcamento.index"))


@orcamento_bp.route("/<int:orcamento_id>/editar/dados", methods=["GET"])
@login_required
def editar_dados(orcamento_id):
    orcamento = Orcamento.query.get_or_404(orcamento_id)
    return jsonify(payload_modal_edicao_orcamento(orcamento))


def _redirect_apos_edicao_orcamento(orcamento_id: int):
    retorno = (request.form.get("retorno") or "").strip()
    if retorno == "lista":
        return redirect(url_for("orcamento.index"))
    return redirect(url_for("orcamento.visualizar", orcamento_id=orcamento_id))


@orcamento_bp.route("/<int:orcamento_id>/editar", methods=["POST"])
@login_required
def editar(orcamento_id):
    orcamento = Orcamento.query.get_or_404(orcamento_id)

    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do orçamento.", "warning")
        return _redirect_apos_edicao_orcamento(orcamento.id)
    nome = nome[:100]

    status = (request.form.get("status") or "").strip() or orcamento.status
    descricao = (request.form.get("descricao") or "").strip() or None

    data_orc = None
    data_raw = (request.form.get("data") or "").strip()
    if data_raw:
        try:
            data_orc = datetime.strptime(data_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Data inválida.", "warning")
            return _redirect_apos_edicao_orcamento(orcamento.id)

    contrato_id = None
    contrato_raw = (request.form.get("contrato_id") or "").strip()
    if contrato_raw:
        try:
            contrato_id = int(contrato_raw)
        except (TypeError, ValueError):
            flash("Contrato inválido.", "warning")
            return _redirect_apos_edicao_orcamento(orcamento.id)
        if not Contrato.query.get(contrato_id):
            flash("Contrato não encontrado.", "warning")
            return _redirect_apos_edicao_orcamento(orcamento.id)

    vinculado_a = None
    v_raw = (request.form.get("vinculado_a_orcamento_id") or "").strip()
    if v_raw:
        try:
            vinculado_a = int(v_raw)
        except (TypeError, ValueError):
            flash("Orçamento de vínculo inválido.", "warning")
            return _redirect_apos_edicao_orcamento(orcamento.id)
        if vinculado_a == orcamento.id:
            flash("Não é possível vincular o orçamento a ele mesmo.", "warning")
            return _redirect_apos_edicao_orcamento(orcamento.id)
        if not Orcamento.query.get(vinculado_a):
            flash("Orçamento de vínculo não encontrado.", "warning")
            return _redirect_apos_edicao_orcamento(orcamento.id)

    orcamento.nome = nome
    orcamento.data = data_orc
    orcamento.descricao = descricao
    orcamento.status = status[:20] if status else orcamento.status
    orcamento.contrato_id = contrato_id
    orcamento.vinculado_a_orcamento_id = vinculado_a

    try:
        db.session.commit()
        flash("Orçamento atualizado.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao salvar: {exc}", "danger")

    return _redirect_apos_edicao_orcamento(orcamento.id)


@orcamento_bp.route("/<int:orcamento_id>", methods=["GET"])
@login_required
def visualizar(orcamento_id):
    orcamento = Orcamento.query.get_or_404(orcamento_id)
    resumo_valores = calcular_resumo_valores_orcamento(orcamento.id)
    return render_template(
        "cadastros/orcamentos/visualizar.html",
        orcamento=orcamento,
        resumo_valores=resumo_valores,
    )


@orcamento_bp.route("/referencias", methods=["GET"])
@login_required
def referencias():
    busca = (request.args.get("q") or "").strip()
    query = ItemOrcamentoReferenciaMaterial.query.options(
        joinedload(ItemOrcamentoReferenciaMaterial.material)
    )

    if busca:
        query = query.filter(ItemOrcamentoReferenciaMaterial.texto_item.ilike(f"%{busca}%"))

    referencias = query.order_by(ItemOrcamentoReferenciaMaterial.id.desc()).all()
    materiais = Materiais.query.filter_by(ativo=True).order_by(Materiais.nome.asc()).all()
    return render_template(
        "cadastros/orcamentos/referencias.html",
        referencias=referencias,
        materiais=materiais,
        busca=busca,
    )


@orcamento_bp.route("/referencias/<int:referencia_id>/vincular", methods=["POST"])
@login_required
def vincular_referencia(referencia_id):
    referencia = ItemOrcamentoReferenciaMaterial.query.get_or_404(referencia_id)
    busca = (request.form.get("q") or "").strip()
    material_id_raw = (request.form.get("material_id") or "").strip()

    material_id = None
    if material_id_raw:
        try:
            material_id = int(material_id_raw)
        except (TypeError, ValueError):
            flash("Material inválido para vínculo.", "warning")
            return redirect(url_for("orcamento.referencias", q=busca))

        material = Materiais.query.get(material_id)
        if not material:
            flash("Material informado não existe.", "warning")
            return redirect(url_for("orcamento.referencias", q=busca))

    referencia.material_id = material_id

    try:
        db.session.commit()
        flash("Referência atualizada com sucesso.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Já existe uma referência igual para este texto e material.", "warning")
    except Exception as exc:
        db.session.rollback()
        flash(f"Falha ao atualizar referência: {exc}", "danger")

    return redirect(url_for("orcamento.referencias", q=busca))
