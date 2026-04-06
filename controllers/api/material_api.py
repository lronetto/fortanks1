import binascii
import logging
from datetime import datetime

from flask import abort, jsonify, make_response, request, url_for
from flask_login import current_user, login_required

from models.database import db
from models.material import Materiais
from models.upload import Upload
from models.unidade import Unidades
from utils.material_imagem_upload import (
    PAI_MATERIAL,
    TIPO_IMAGEM_MATERIAL,
    get_imagem_upload_id,
    guess_image_mime_from_bytes,
    remover_upload_material_se_existir,
    salvar_imagem_material,
    set_imagem_upload_id,
)
from models.estoque import Estoque, EstoqueMovimentacoes

logger = logging.getLogger(__name__)


def register(material_bp):
    """
    Registra endpoints de API (JSON/AJAX) do domínio Material no blueprint `material_bp`.
    Mantém as URLs originais para não quebrar o front.
    """

    @material_bp.route("/upload/<int:upload_id>/imagem")
    @login_required
    def material_imagem_inline(upload_id):
        """
        Exibe imagem em Upload. Usa mimetype do registro; se não for image/* (ex.: colagem
        com application/octet-stream), infere JPEG/PNG/WebP/GIF pelos primeiros bytes.
        """
        u = Upload.query.get_or_404(upload_id)
        try:
            data = u.get_blob()
        except (binascii.Error, ValueError, TypeError) as e:
            logger.warning("Upload %s: blob inválido: %s", upload_id, e)
            abort(404)
        if not data:
            abort(404)
        mt = (u.mimetype or "").strip().lower()
        if mt.startswith("image/"):
            content_type = u.mimetype or "image/jpeg"
        else:
            guessed = guess_image_mime_from_bytes(data[:64])
            if not guessed:
                abort(404)
            content_type = guessed
        resp = make_response(data)
        resp.headers["Content-Type"] = content_type
        resp.headers["Content-Disposition"] = f'inline; filename="{u.filename}"'
        return resp

    @material_bp.route("/listar-json")
    @login_required
    def listar_json():
        # Verificar se deve filtrar apenas materiais sem estoque
        apenas_sem_estoque = request.args.get('sem_estoque', 'false').lower() == 'true'
        
        query = Materiais.query.filter_by(ativo=True).order_by(Materiais.nome)
        
        if apenas_sem_estoque:
            # Buscar IDs de materiais que já têm estoque
            materiais_com_estoque = db.session.query(Estoque.material_id).filter(
                Estoque.material_id.isnot(None),
                Estoque.tipo_item == 'material'
            ).distinct().all()
            
            ids_com_estoque = [m[0] for m in materiais_com_estoque]
            
            # Filtrar materiais que NÃO estão na lista de materiais com estoque
            if ids_com_estoque:
                query = query.filter(~Materiais.id.in_(ids_com_estoque))
        
        materiais = query.all()
        resultado = []
        for material in materiais:
            resultado.append(
                {
                    "id": material.id,
                    "codigo": material.codigo or "",
                    "codigo_erp": str(material.codigo_erp).strip() if material.codigo_erp not in (None, "") else "",
                    "nome": material.nome or "",
                    "unidade": material.unidade_obj.nome if material.unidade_obj else "",
                }
            )
        return jsonify(resultado)

    @material_bp.route("/api/materiais")
    @login_required
    def api_materiais():
        query = Materiais.query

        plano_conta = request.args.get("plano_conta")
        if plano_conta:
            query = query.filter_by(plano_conta=plano_conta)

        search = request.args.get("q")
        if search:
            query = query.filter(db.or_(Materiais.codigo.like(f"%{search}%"), Materiais.nome.like(f"%{search}%")))

        sort_by = request.args.get("sort_by", "codigo")
        sort_dir = request.args.get("sort_dir", "asc")
        if sort_by in ["codigo", "nome", "categoria", "plano_conta"]:
            if sort_dir == "desc":
                query = query.order_by(db.desc(getattr(Materiais, sort_by)))
            else:
                query = query.order_by(getattr(Materiais, sort_by))

        limit = request.args.get("limit", 100, type=int)
        query = query.limit(limit)
        materiais = query.all()

        result = []
        for m in materiais:
            result.append(
                {
                    "id": m.id,
                    "codigo": m.codigo,
                    "nome": m.nome,
                    "descricao": m.descricao,
                    "categoria": m.categoria,
                    "plano_conta": m.plano_conta,
                    "mascara": m.mascara,
                    "unidade": m.unidade,
                    "criado_em": m.criado_em.strftime("%d/%m/%Y %H:%M") if m.criado_em else None,
                }
            )
        return jsonify(result)

    @material_bp.route("/api/buscar-semelhantes", methods=["GET"])
    @login_required
    def api_buscar_semelhantes():
        """
        Mantido do legado. Busca materiais semelhantes a item de NF por código/descrição/NCM.
        """
        try:
            codigo = request.args.get("codigo", "").strip()
            descricao = request.args.get("descricao", "").strip()
            ncm = request.args.get("ncm", "").strip()

            if not codigo and not descricao and not ncm:
                return jsonify({"success": True, "materiais": []})

            materiais_encontrados = []

            if codigo:
                material_codigo_exato = Materiais.query.filter_by(codigo=codigo, ativo=True).first()
                if material_codigo_exato:
                    materiais_encontrados.append({"material": material_codigo_exato, "pontuacao": 100, "motivo": "Código exato"})

                materiais_codigo_similar = (
                    Materiais.query.filter(Materiais.codigo.ilike(f"%{codigo}%"), Materiais.codigo != codigo, Materiais.ativo.is_(True))
                    .limit(5)
                    .all()
                )
                for mat in materiais_codigo_similar:
                    if not any(m["material"].id == mat.id for m in materiais_encontrados):
                        materiais_encontrados.append({"material": mat, "pontuacao": 70, "motivo": "Código similar"})

            if ncm:
                materiais_ncm = Materiais.query.filter(Materiais.ncm == ncm, Materiais.ativo.is_(True)).limit(5).all()
                for mat in materiais_ncm:
                    if not any(m["material"].id == mat.id for m in materiais_encontrados):
                        materiais_encontrados.append({"material": mat, "pontuacao": 80, "motivo": "NCM igual"})

            if descricao:
                palavras = descricao.split()[:3]
                for palavra in palavras:
                    if len(palavra) >= 3:
                        materiais_nome = (
                            Materiais.query.filter(
                                db.or_(Materiais.nome.ilike(f"%{palavra}%"), Materiais.descricao.ilike(f"%{palavra}%")),
                                Materiais.ativo.is_(True),
                            )
                            .limit(10)
                            .all()
                        )
                        for mat in materiais_nome:
                            existente = next((m for m in materiais_encontrados if m["material"].id == mat.id), None)
                            if existente:
                                existente["pontuacao"] += 10
                                if "nome" not in existente["motivo"]:
                                    existente["motivo"] += ", Nome similar"
                            else:
                                nome_lower = mat.nome.lower() if mat.nome else ""
                                desc_lower = mat.descricao.lower() if mat.descricao else ""
                                palavras_match = sum(1 for p in palavras if p.lower() in nome_lower or p.lower() in desc_lower)
                                pontuacao = 30 + (palavras_match * 15)
                                materiais_encontrados.append({"material": mat, "pontuacao": pontuacao, "motivo": "Nome/Descrição similar"})

            materiais_encontrados.sort(key=lambda x: x["pontuacao"], reverse=True)
            top_3 = materiais_encontrados[:3]

            resultado = []
            for item in top_3:
                mat = item["material"]
                resultado.append(
                    {
                        "id": mat.id,
                        "codigo": mat.codigo,
                        "nome": mat.nome,
                        "descricao": mat.descricao,
                        "categoria": mat.categoria,
                        "ncm": mat.ncm,
                        "unidade": mat.unidade_obj.nome if mat.unidade_obj else None,
                        "pontuacao": item["pontuacao"],
                        "motivo": item["motivo"],
                    }
                )

            return jsonify({"success": True, "materiais": resultado})
        except Exception as e:
            logger.error(f"Erro ao buscar materiais semelhantes: {str(e)}")
            return jsonify({"success": False, "message": f"Erro ao buscar materiais semelhantes: {str(e)}", "materiais": []}), 500

    @material_bp.route("/api/criar", methods=["POST"])
    @login_required
    def api_criar():
        """
        Cria material via JSON (usado por fluxos integrados com NF).
        """
        try:
            data = request.get_json() or {}

            if not data.get("nome"):
                return jsonify({"success": False, "message": "Nome do material é obrigatório"}), 400
            if not data.get("categoria"):
                return jsonify({"success": False, "message": "Categoria do material é obrigatória"}), 400

            codigo = data.get("codigo")
            if codigo and Materiais.query.filter_by(codigo=codigo).first():
                return jsonify({"success": False, "message": f"Já existe um material com o código {codigo}"}), 400

            unidade_id = data.get("unidade_id")
            if not unidade_id and data.get("unidade_nome"):
                unidade = Unidades.obter_por_nome(data.get("unidade_nome"))
                if unidade:
                    unidade_id = unidade.id

            material = Materiais(
                codigo=codigo,
                nome=data.get("nome"),
                descricao=data.get("descricao", ""),
                categoria=data.get("categoria"),
                plano_conta=data.get("plano_conta"),
                codigo_erp=data.get("codigo_erp"),
                unidade_id=unidade_id,
                mascara=data.get("mascara"),
                ncm=data.get("ncm"),
                formula_calculo=data.get("formula_calculo") if data.get("formula_calculo") else None,
            )
            material.save()

            return jsonify(
                {
                    "success": True,
                    "message": "Material criado com sucesso!",
                    "material": {"id": material.id, "codigo": material.codigo, "nome": material.nome, "ncm": material.ncm},
                }
            )
        except Exception as e:
            logger.error(f"Erro ao criar material via API: {str(e)}")
            db.session.rollback()
            return jsonify({"success": False, "message": f"Erro ao criar material: {str(e)}"}), 500

    @material_bp.route("/editar-material-ajax/<int:id>", methods=["GET", "POST"])
    @login_required
    def editar_material_ajax(id):
        """
        Mantido do legado (usado pelo modal). Requer CSRF no POST.
        """
        material = Materiais.query.get_or_404(id)

        if request.method == "POST":
            csrf_token = request.form.get("csrf_token")
            if not csrf_token:
                return jsonify({"success": False, "message": "CSRF token não fornecido"}), 400

            data = request.form
            codigo = data.get("edit_codigo", "")
            nome = data.get("edit_nome", "")
            descricao = data.get("edit_descricao", "")
            categoria = data.get("edit_categoria", "")
            plano_conta = data.get("edit_plano_conta", "")
            codigo_erp = data.get("edit_codigo_erp", "")
            unidade = data.get("edit_unidade", "")
            mascara = data.get("edit_mascara", "")
            formula_calculo = data.get("edit_formula_calculo", "").strip()
            
            # Campos de quantidade
            quantidade = data.get("edit_quantidade", "")
            quantidade_minima = data.get("edit_quantidade_minima", "")
            quantidade_maxima = data.get("edit_quantidade_maxima", "")

            if not nome or not categoria:
                return jsonify({"success": False, "message": "Nome e categoria são campos obrigatórios!"})

            if codigo and codigo != material.codigo:
                existente = Materiais.query.filter_by(codigo=codigo).first()
                if existente and existente.id != material.id:
                    return jsonify({"success": False, "message": f"Já existe um material com o código {codigo}!"})

            try:
                material.codigo = codigo
                material.nome = nome
                material.descricao = descricao
                material.categoria = categoria
                material.plano_conta = plano_conta
                material.codigo_erp = codigo_erp
                material.unidade_id = unidade
                material.mascara = mascara
                material.formula_calculo = formula_calculo if formula_calculo else None
                material.data_atualizacao = datetime.now()
                if hasattr(current_user, "id"):
                    material.usuario_id = current_user.id

                remover_img = data.get("remover_imagem_material") == "1"
                arquivo_img = request.files.get("imagem_material")
                if remover_img:
                    old_uid = get_imagem_upload_id(material.dados_adicionais)
                    if old_uid:
                        remover_upload_material_se_existir(old_uid, material.id)
                    material.dados_adicionais = set_imagem_upload_id(material.dados_adicionais, None)
                elif arquivo_img and arquivo_img.filename:
                    old_uid = get_imagem_upload_id(material.dados_adicionais)
                    new_uid = salvar_imagem_material(material.id, arquivo_img)
                    if new_uid:
                        if old_uid and old_uid != new_uid:
                            remover_upload_material_se_existir(old_uid, material.id)
                        material.dados_adicionais = set_imagem_upload_id(material.dados_adicionais, new_uid)
                
                # Atualizar ou criar estoque
                from decimal import Decimal
                estoque = Estoque.query.filter_by(material_id=material.id, tipo_item='material').first()
                
                if quantidade or quantidade_minima or quantidade_maxima:
                    quantidade_anterior = None
                    if not estoque:
                        # Criar novo registro de estoque
                        estoque = Estoque(
                            material_id=material.id,
                            tipo_item='material',
                            quantidade=Decimal(str(quantidade)) if quantidade else Decimal('0'),
                            quantidade_minima=Decimal(str(quantidade_minima)) if quantidade_minima else Decimal('0'),
                            quantidade_maxima=Decimal(str(quantidade_maxima)) if quantidade_maxima else Decimal('0'),
                            usuario_id=current_user.id if hasattr(current_user, "id") else None
                        )
                        db.session.add(estoque)
                    else:
                        quantidade_anterior = estoque.quantidade
                        # Atualizar quantidades
                        if quantidade:
                            estoque.quantidade = Decimal(str(quantidade))
                        if quantidade_minima:
                            estoque.quantidade_minima = Decimal(str(quantidade_minima))
                        if quantidade_maxima:
                            estoque.quantidade_maxima = Decimal(str(quantidade_maxima))
                        estoque.usuario_id = current_user.id if hasattr(current_user, "id") else estoque.usuario_id
                    
                    # Criar movimentação de ajuste se a quantidade foi alterada
                    if estoque and quantidade and quantidade_anterior is not None:
                        nova_quantidade = Decimal(str(quantidade))
                        if nova_quantidade != quantidade_anterior:
                            movimentacao = EstoqueMovimentacoes(
                                estoque_id=estoque.id,
                                tipo_movimento='ajuste',
                                quantidade=nova_quantidade,
                                observacao='Ajuste manual via edição de material',
                                usuario_id=current_user.id if hasattr(current_user, "id") else None
                            )
                            db.session.add(movimentacao)
                
                db.session.commit()
                return jsonify({"success": True, "message": "Material atualizado com sucesso!", "redirect": url_for("material.index")})
            except Exception as db_error:
                db.session.rollback()
                logger.error(f"Erro ao salvar material: {str(db_error)}", exc_info=True)
                return jsonify({"success": False, "message": f"Erro ao salvar material: {str(db_error)}"})

        img_id = get_imagem_upload_id(material.dados_adicionais)
        return jsonify(
            {
                "id": material.id,
                "codigo": material.codigo or "",
                "nome": material.nome,
                "descricao": material.descricao or "",
                "categoria": material.categoria,
                "plano_conta": material.plano_conta or "",
                "codigo_erp": material.codigo_erp or "",
                "unidade": material.unidade_obj.nome if material.unidade_obj else "",
                "mascara": material.mascara or "",
                "formula_calculo": material.formula_calculo or "",
                "imagem_upload_id": img_id,
            }
        )

    @material_bp.route("/obter/<int:id>", methods=["GET"])
    @login_required
    def obter_material(id):
        material = Materiais.query.get(id)
        if not material:
            return jsonify({"success": False, "error": "Material não encontrado"})
        img_id = get_imagem_upload_id(material.dados_adicionais)
        response = jsonify(
            {
                "success": True,
                "material": {
                    "id": material.id,
                    "codigo": material.codigo or "",
                    "codigo_erp": material.codigo_erp or "",
                    "nome": material.nome or "",
                    "descricao": material.descricao or "",
                    "categoria": material.categoria or "",
                    "plano_conta": material.plano_conta or "",
                    "unidade": material.unidade or "",
                    "mascara": material.mascara or "",
                    "formula_calculo": material.formula_calculo or "",
                    "imagem_upload_id": img_id,
                },
            }
        )
        response.headers["Content-Type"] = "application/json"
        return response

    @material_bp.route("/obter-ajax/<int:id>", methods=["GET"])
    @login_required
    def obter_material_ajax(id):
        material = Materiais.query.get(id)
        if not material:
            response = jsonify({"success": False, "error": "Material não encontrado"})
            response.headers["Content-Type"] = "application/json; charset=utf-8"
            return response

        img_id = get_imagem_upload_id(material.dados_adicionais)
        response = jsonify(
            {
                "success": True,
                "material": {
                    "id": material.id,
                    "codigo": material.codigo or "",
                    "codigo_erp": material.codigo_erp or "",
                    "nome": material.nome or "",
                    "descricao": material.descricao or "",
                    "categoria": material.categoria or "",
                    "plano_conta": material.plano_conta or "",
                    "unidade": material.unidade or "",
                    "mascara": material.mascara or "",
                    "formula_calculo": material.formula_calculo or "",
                    "imagem_upload_id": img_id,
                },
            }
        )
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @material_bp.route("/diagnostico/<int:id>", methods=["GET"])
    @login_required
    def diagnostico_material(id):
        try:
            material = Materiais.query.get(id)
            if not material:
                resposta = {"status": "erro", "mensagem": f"Material com ID {id} não encontrado"}
            else:
                resposta = {"status": "sucesso", "material_id": material.id, "material_nome": material.nome}
            return f"""
            Diagnóstico do Material:

            {resposta}

            Cabeçalhos da requisição:
            {dict(request.headers)}

            URL da requisição:
            {request.url}

            Método da requisição:
            {request.method}

            Autenticação:
            {current_user.is_authenticated if current_user else False}
            """
        except Exception as e:
            return f"Erro no diagnóstico: {str(e)}"


