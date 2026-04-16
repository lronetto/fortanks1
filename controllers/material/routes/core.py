import logging
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required
from sqlalchemy import text

from models.database import db
from models.material import Materiais, MateriaisGrupos
from models.plano_conta import PlanoConta
from models.tanque import TanquesPecas
from models.unidade import Unidades, UnidadesConversao
from models.nota_fiscal import NotaFiscalItem
from models.estoque import Estoque
from models.orcamento import Orcamento, ItemOrcamento
from models.concreto import ConcretoUsinagensMateriais
from models.epi import Epi
from utils.material_imagem_upload import (
    dump_dados_json,
    parse_dados_json,
    salvar_imagem_material,
    set_imagem_upload_id,
)

from .. import material_bp

logger = logging.getLogger(__name__)


def _normalizar_codigo_inteiro(valor):
    txt = str(valor or "").strip()
    if not txt:
        return ""
    txt = txt.replace(",", ".")
    try:
        return str(int(float(txt)))
    except (TypeError, ValueError):
        if "." in txt:
            return txt.split(".", 1)[0]
        return txt


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

    try:
        codigo = _normalizar_codigo_inteiro(request.form.get("codigo"))
        nome = request.form.get("nome")
        descricao = request.form.get("descricao")
        categoria = request.form.get("categoria")
        plano_conta = request.form.get("plano_conta")
        codigo_alterdata = _normalizar_codigo_inteiro(request.form.get("codigo_alterdata") or request.form.get("codigo_erp"))
        codigo_mega = _normalizar_codigo_inteiro(request.form.get("codigo_mega"))
        unidade = request.form.get("unidade")
        mascara = _normalizar_codigo_inteiro(request.form.get("mascara"))
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

        # A coluna `codigo` foi removida do banco; o valor do usuário é salvo em dados_adicionais["codigo_sox"].

        extras = parse_dados_json(None)
        if codigo:
            extras["codigo_sox"] = codigo
        if codigo_alterdata:
            extras["codigo_alterdata"] = codigo_alterdata
        if codigo_mega:
            extras["codigo_mega"] = codigo_mega
            extras["cod_mega"] = codigo_mega

        material = Materiais(
            nome=nome.upper(),
            descricao=descricao,
            categoria=categoria,
            plano_conta=plano_conta,
            unidade_id=unidade,
            mascara=mascara,
            formula_calculo=formula_calculo if formula_calculo else None,
            dados_adicionais=dump_dados_json(extras) if extras else None,
        )
        material.usuario_id = current_user.id
        material.save()

        arquivo_img = request.files.get("imagem_material")
        if arquivo_img and arquivo_img.filename:
            uid = salvar_imagem_material(material.id, arquivo_img)
            if uid:
                material.dados_adicionais = set_imagem_upload_id(material.dados_adicionais, uid)
                db.session.add(material)
                db.session.commit()

        flash("Material cadastrado com sucesso!", "success")
        return redirect(url_for("material.index"))
    except Exception as e:
        flash(f"Erro ao cadastrar material: {str(e)}", "danger")
        return redirect(url_for("material.index"))


@material_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar(id):
    if not current_user.is_permissao('material', 'editar'):
        flash('Você não tem permissão para editar este material.', 'danger')
        return redirect(url_for('material.index'))
    """
    Mantém fluxo de página (HTML). A parte AJAX/JSON foi centralizada em `controllers/api/material_api.py`.
    """
    material = Materiais.query.get_or_404(id)
    unidades = Unidades.query.filter_by(ativo=True).order_by(Unidades.nome).all()

    if request.method == "POST":
        try:
            codigo = _normalizar_codigo_inteiro(request.form.get("codigo", ""))
            nome = request.form.get("nome", "")
            descricao = request.form.get("descricao", "")
            categoria = request.form.get("categoria", "")
            plano_conta = request.form.get("plano_conta", "")
            codigo_alterdata = _normalizar_codigo_inteiro(
                request.form.get("codigo_alterdata") or request.form.get("codigo_erp", "")
            )
            unidade = request.form.get("unidade", "")
            mascara = _normalizar_codigo_inteiro(request.form.get("mascara", ""))
            formula_calculo = request.form.get("formula_calculo", "").strip()

            if not nome or not categoria:
                flash("Nome e categoria são campos obrigatórios!", "danger")
                return render_template(
                    "materiais/editar.html",
                    material=material,
                    planos_conta=PlanoConta.query.filter_by(ativo=True).all(),
                    unidades=unidades,
                )

            # A coluna `codigo` foi removida do banco; salvamos em dados_adicionais["codigo_sox"].
            material.nome = nome.upper()
            material.descricao = descricao
            material.categoria = categoria
            material.plano_conta = plano_conta
            material.unidade_id = unidade
            material.mascara = mascara
            material.formula_calculo = formula_calculo if formula_calculo else None

            extras = parse_dados_json(material.dados_adicionais)
            if codigo:
                extras["codigo_sox"] = codigo
            if codigo_alterdata:
                extras["codigo_alterdata"] = codigo_alterdata
            else:
                extras.pop("codigo_alterdata", None)
            material.dados_adicionais = dump_dados_json(extras) if extras else None

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
        
        # Verificar todos os relacionamentos que podem impedir a exclusão
        bloqueios = []
        
        # Verificar grupos de materiais (tabela de associação many-to-many)
        try:
            # Verificar diretamente na tabela de associação
            result = db.session.execute(
                text("SELECT COUNT(*) FROM materiais_grupos WHERE material_id = :material_id"),
                {'material_id': material.id}
            ).scalar()
            if result and result > 0:
                bloqueios.append(f"{result} grupo(s) de material")
        except Exception as e:
            logger.warning(f"Erro ao verificar grupos de material: {str(e)}")
            # Tentar usar o relacionamento como fallback
            try:
                if hasattr(material, 'grupos') and material.grupos:
                    count = len(material.grupos)
                    if count > 0:
                        bloqueios.append(f"{count} grupo(s) de material")
            except Exception:
                pass
        # Verificar solicitações
        try:
            if hasattr(material, 'solicitacoes_itens') and material.solicitacoes_itens:
                count = len(material.solicitacoes_itens)
                if count > 0:
                    bloqueios.append(f"{count} solicitação(ões)")
        except Exception:
            pass
        
        # Verificar itens de nota fiscal
        try:
            itens_nf = NotaFiscalItem.query.filter_by(material_id=material.id).count()
            if itens_nf > 0:
                bloqueios.append(f"{itens_nf} item(ns) de nota fiscal")
        except Exception:
            pass
        
        # Verificar estoque
        try:
            estoques = Estoque.query.filter_by(material_id=material.id).count()
            if estoques > 0:
                bloqueios.append(f"{estoques} registro(s) de estoque")
        except Exception:
            pass
        
        # Verificar orçamentos
        try:
            orcamentos = Orcamento.query.filter_by(material_id=material.id).count()
            if orcamentos > 0:
                bloqueios.append(f"{orcamentos} orçamento(s)")
        except Exception:
            pass
        
        # Verificar itens de orçamento
        try:
            itens_orcamento = Orcamento.query.filter_by(material_id=material.id).count()
            if orcamentos > 0:
                bloqueios.append(f"{orcamentos} orçamento(s)")
        except Exception:
            pass
        
        # Verificar EPIs
        try:
            epis = Epi.query.filter_by(material_id=material.id).count()
            if epis > 0:
                bloqueios.append(f"{epis} epi(s)")
        except Exception:
            pass
        
        # Verificar conversões de unidade
        try:
            conversoes = UnidadesConversao.query.filter_by(material_id=material.id).count()
            if conversoes > 0:
                bloqueios.append(f"{conversoes} conversão(ões)")
        except Exception:
            pass
        
        # Se houver bloqueios, informar ao usuário
        if bloqueios:
            mensagem = f"Este material não pode ser excluído pois está vinculado a: {', '.join(bloqueios)}"
            flash(mensagem, "danger")
            return redirect(url_for("material.index"))

        # Se não houver bloqueios, remover associações e excluir o material
        nome = material.nome
        

        # Agora pode excluir o material
        material.delete()
        db.session.commit()
        flash(f'Material "{nome}" excluído com sucesso!', "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir material {id}: {str(e)}", exc_info=True)
        flash(f"Erro ao excluir material: {str(e)}", "danger")
    return redirect(url_for("material.index"))


