"""
Rotas do módulo Protocolos de Notas Fiscais.
Tabela com data e número; ao criar protocolo, modal para importar PDFs
com renomeação automática (chave de acesso) e opção de renomear manualmente.
"""
import base64
import json
import logging
from datetime import datetime

from flask import jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import func
from sqlalchemy.orm import defer

from models.database import db
from models.protocolo import Protocolo
from models.upload import Upload

from .. import nota_fiscal_bp
from ..services.renomear_pdf_protocolo import processar_pdf_protocolo

logger = logging.getLogger(__name__)

TIPO_UPLOAD_PROTOCOLO = 2


def _uploads_do_protocolo(protocolo_id):
    """Retorna lista de Upload (tipo=2) cujo dados_adicionais contém protocolo_id.
    O blob não é carregado para não pesar na consulta; será carregado sob demanda se acessado.
    """
    uploads = (
        Upload.query.options(defer(Upload.blob))
        .filter_by(tipo=TIPO_UPLOAD_PROTOCOLO)
        .filter(Upload.dados_adicionais.isnot(None))
        .filter(func.json_extract(Upload.dados_adicionais, "$.protocolo_id") == protocolo_id)
        .all()
    )
    return uploads


@nota_fiscal_bp.route("/protocolos")
@login_required
def protocolos_index():
    return render_template("notas_fiscais/protocolos/index.html")


@nota_fiscal_bp.route("/protocolos/api/datatables", methods=["GET"])
@login_required
def protocolos_datatables():
    """Retorna dados para DataTables (colunas: data, numero)."""
    try:
        draw = request.args.get("draw", 1, type=int)
        start = request.args.get("start", 0, type=int)
        length = request.args.get("length", 25, type=int)
        search_value = request.args.get("search[value]", "").strip()
        order_col = request.args.get("order[0][column]", "0", type=str)
        order_dir = request.args.get("order[0][dir]", "desc")

        query = Protocolo.query

        if search_value:
            query = query.filter(
                db.or_(
                    func.cast(Protocolo.data, db.String).ilike(f"%{search_value}%"),
                    Protocolo.numero.ilike(f"%{search_value}%"),
                )
            )

        order_col_index = int(order_col) if order_col.isdigit() else 0
        order_cols = [Protocolo.data, Protocolo.numero]
        order_col_idx = min(order_col_index, len(order_cols) - 1)
        col = order_cols[order_col_idx]
        if order_dir == "asc":
            query = query.order_by(col.asc())
        else:
            query = query.order_by(col.desc())

        total_records = Protocolo.query.count()
        total_filtered = query.count()
        items = query.offset(start).limit(length).all()

        data = []
        for p in items:
            qtd_arquivos = len(_uploads_do_protocolo(p.id))
            data.append({
                "id": p.id,
                "data": p.data.strftime("%d/%m/%Y") if p.data else "",
                "numero": p.numero,
                "qtd_arquivos": qtd_arquivos,
            })

        return jsonify({
            "draw": draw,
            "recordsTotal": total_records,
            "recordsFiltered": total_filtered,
            "data": data,
        })
    except Exception as e:
        logger.exception("Erro ao listar protocolos")
        return jsonify({"draw": 1, "recordsTotal": 0, "recordsFiltered": 0, "data": [], "error": str(e)}), 500


@nota_fiscal_bp.route("/protocolos", methods=["POST"])
@login_required
def protocolos_create():
    """Cria um novo protocolo (data, numero). Retorna id para abrir modal de importação."""
    try:
        data_str = request.form.get("data") or request.json.get("data") if request.is_json else request.form.get("data")
        numero = request.form.get("numero") or (request.json.get("numero") if request.is_json else None)

        if not data_str or not numero:
            return jsonify({"success": False, "message": "Data e número são obrigatórios."}), 400

        if isinstance(data_str, str):
            try:
                data_prot = datetime.strptime(data_str, "%Y-%m-%d").date()
            except ValueError:
                try:
                    data_prot = datetime.strptime(data_str, "%d/%m/%Y").date()
                except ValueError:
                    return jsonify({"success": False, "message": "Data inválida."}), 400
        else:
            data_prot = data_str

        protocolo = Protocolo(data=data_prot, numero=numero.strip())
        db.session.add(protocolo)
        db.session.commit()
        return jsonify({"success": True, "id": protocolo.id, "message": "Protocolo criado."})
    except Exception as e:
        logger.exception("Erro ao criar protocolo")
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@nota_fiscal_bp.route("/protocolos/<int:protocolo_id>/importar-pdfs", methods=["POST"])
@login_required
def protocolos_importar_pdfs(protocolo_id):
    """
    Recebe PDFs, processa cada um (chave -> NotaFiscal -> nome sugerido),
    salva como Upload(NotaFiscal, tipo=2). Retorna lista com nome sugerido,
    upload_id, nota_id e se foi identificado; não identificados podem ser renomeados depois.
    """
    try:
        protocolo = Protocolo.query.get_or_404(protocolo_id)
        files = request.files.getlist("pdfs") or request.files.getlist("pdfs[]")
        if not files:
            return jsonify({"success": False, "message": "Nenhum arquivo PDF enviado."}), 400

        dados_adicionais = json.dumps({"protocolo_id": protocolo_id})
        resultados = []
        pai_id = 0
        mimetype = "application/pdf"

        for f in files:
            if not f or not f.filename or not f.filename.lower().endswith(".pdf"):
                continue
            payload = f.read()
            if not payload:
                continue

            nome_original = f.filename
            nome_sugerido, nota_id, identificado = processar_pdf_protocolo(payload, nome_original)
            nid = nota_id if nota_id else 0

            if not nome_sugerido.endswith(".pdf"):
                nome_sugerido = f"{nome_sugerido}.pdf"

            filename_final = nome_sugerido
            stem = filename_final[:-4] if filename_final.lower().endswith(".pdf") else filename_final
            cont = 1
            while Upload.query.filter_by(
                pai="NotaFiscal", pai_id=nid, tipo=TIPO_UPLOAD_PROTOCOLO,
                filename=filename_final, mimetype=mimetype
            ).first() is not None:
                cont += 1
                filename_final = f"{stem}_proto{protocolo_id}_{cont}.pdf"

            u = Upload(
                pai="NotaFiscal",
                pai_id=nid,
                tipo=TIPO_UPLOAD_PROTOCOLO,
                filename=filename_final,
                mimetype=mimetype,
                blob=base64.b64encode(payload).decode("utf-8"),
                dados_adicionais=dados_adicionais,
            )
            # Upload.__init__ chama save() ao final do branch else

            resultados.append({
                "upload_id": u.id,
                "original": nome_original,
                "suggested_name": filename_final,
                "nota_id": nota_id,
                "identificado": identificado,
            })

        db.session.commit()
        return jsonify({"success": True, "resultados": resultados, "message": f"{len(resultados)} arquivo(s) processado(s)."})
    except Exception as e:
        logger.exception("Erro ao importar PDFs do protocolo")
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@nota_fiscal_bp.route("/protocolos/upload/<int:upload_id>/renomear", methods=["POST"])
@login_required
def protocolos_upload_renomear(upload_id):
    """Atualiza o filename de um Upload de protocolo (para documentos não identificados)."""
    try:
        upload = Upload.query.filter_by(id=upload_id, tipo=TIPO_UPLOAD_PROTOCOLO).first()
        if not upload:
            return jsonify({"success": False, "message": "Upload não encontrado."}), 404

        nome = None
        if request.is_json:
            nome = (request.json or {}).get("filename")
        else:
            nome = request.form.get("filename")

        if not nome or not nome.strip():
            return jsonify({"success": False, "message": "Nome do arquivo é obrigatório."}), 400

        nome = nome.strip()
        if not nome.endswith(".pdf"):
            nome = f"{nome}.pdf"

        upload.filename = nome
        db.session.commit()
        return jsonify({"success": True, "filename": nome})
    except Exception as e:
        logger.exception("Erro ao renomear upload")
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@nota_fiscal_bp.route("/protocolos/<int:protocolo_id>/arquivos", methods=["GET"])
@login_required
def protocolos_listar_arquivos(protocolo_id):
    """Lista os uploads (PDFs) vinculados ao protocolo para visualização/edição."""
    try:
        protocolo = Protocolo.query.get_or_404(protocolo_id)
        uploads = _uploads_do_protocolo(protocolo_id)
        lista = [
            {
                "id": u.id,
                "filename": u.filename or "",
                "uploaded_at": u.uploaded_at.isoformat() if u.uploaded_at else None,
            }
            for u in uploads
        ]
        return jsonify({
            "success": True,
            "protocolo_numero": protocolo.numero,
            "arquivos": lista,
        })
    except Exception as e:
        logger.exception("Erro ao listar arquivos do protocolo")
        return jsonify({"success": False, "message": str(e)}), 500


@nota_fiscal_bp.route("/protocolos/<int:protocolo_id>/enviar-email", methods=["POST"])
@login_required
def protocolos_enviar_email(protocolo_id):
    """
    Envia e-mail com assunto "Protocolo {numero}" e corpo com a lista dos
    arquivos (nomes sem extensão). Destinatários vêm no body.
    """
    try:
        protocolo = Protocolo.query.get_or_404(protocolo_id)
        payload = request.get_json(silent=True) or {}
        destinatarios = payload.get("destinatarios") or request.form.getlist("destinatarios")
        if isinstance(destinatarios, str):
            destinatarios = [e.strip() for e in destinatarios.replace(";", ",").split(",") if e.strip()]
        if not destinatarios:
            return jsonify({"success": False, "message": "Informe ao menos um destinatário."}), 400

        uploads = _uploads_do_protocolo(protocolo_id)
        nomes_sem_extensao = []
        anexos = []
        nomes_vistos = {}
        for u in uploads:
            fn = (u.filename or "").strip()
            if not fn.lower().endswith(".pdf"):
                fn = f"{fn}.pdf"
            if fn.replace(".pdf", ""):
                nomes_sem_extensao.append(fn[:-4])
            blob = u.get_blob() if hasattr(u, "get_blob") else None
            if blob:
                if fn in nomes_vistos:
                    nomes_vistos[fn] += 1
                    base, ext = fn.rsplit(".", 1) if "." in fn else (fn, "pdf")
                    fn = f"{base}_{nomes_vistos[fn]}.{ext}"
                else:
                    nomes_vistos[fn] = 1
                anexos.append((fn, "application/pdf", blob))

        assunto = f"Protocolo {protocolo.numero}"
        corpo_linhas = "\n".join(nomes_sem_extensao) if nomes_sem_extensao else "(Nenhum arquivo no protocolo)"
        corpo_html = f"<p>Segue a lista de arquivos do protocolo:</p><pre>{corpo_linhas}</pre>"
        if anexos:
            corpo_html += f"<p><em>Total de {len(anexos)} arquivo(s) em anexo.</em></p>"
        corpo_texto = corpo_linhas

        try:
            from utils.email_utils import enviar_email
            ok = enviar_email(destinatarios, assunto, corpo_html, corpo_texto, anexos=anexos)
        except Exception:
            try:
                from utils.email_utils import enviar_email_gmail
                ok = enviar_email_gmail(destinatarios, assunto, corpo_html, corpo_texto, anexos=anexos)
            except Exception as e:
                logger.exception("Erro ao enviar e-mail do protocolo")
                return jsonify({"success": False, "message": str(e)}), 500

        if not ok:
            return jsonify({"success": False, "message": "Falha ao enviar e-mail. Verifique a configuração de e-mail."}), 500
        return jsonify({"success": True, "message": "E-mail enviado com sucesso."})
    except Exception as e:
        logger.exception("Erro ao enviar e-mail do protocolo")
        return jsonify({"success": False, "message": str(e)}), 500


@nota_fiscal_bp.route("/protocolos/<int:protocolo_id>", methods=["DELETE"])
@login_required
def protocolos_delete(protocolo_id):
    """Exclui o protocolo e todos os arquivos (uploads) anexados a ele."""
    try:
        protocolo = Protocolo.query.get_or_404(protocolo_id)
        uploads = _uploads_do_protocolo(protocolo_id)
        for u in uploads:
            db.session.delete(u)
        db.session.delete(protocolo)
        db.session.commit()
        return jsonify({"success": True, "message": "Protocolo e arquivos excluídos com sucesso."})
    except Exception as e:
        logger.exception("Erro ao excluir protocolo")
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
