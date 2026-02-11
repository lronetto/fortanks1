import base64
import io
import logging
import zipfile
from datetime import datetime

from flask import flash, jsonify, make_response, redirect, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func

from models.arquivei import Arquivei
from models.database import db
from models.nota_fiscal import NotaFiscal
from models.upload import Upload

from .. import nota_fiscal_bp
from ..services.query_notas import api_get_dados_notas_fiscais

logger = logging.getLogger(__name__)


@nota_fiscal_bp.route("/pdf/<int:id>", methods=["GET"])
@login_required
def gerar_pdf(id):
    """
    Retorna um PDF (Upload) inline. Observação: historicamente a UI chama esta rota com
    `notaId` em alguns lugares. Mantemos comportamento original (buscar Upload por ID).
    """
    try:
        upload = Upload.query.get_or_404(id)
        response = make_response(base64.b64decode(upload.blob))
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f"inline; filename=documento_{upload.id}.pdf"
        return response
    except Exception as e:
        logger.error(f"Erro ao gerar PDF: {str(e)}")
        flash(f"Erro ao gerar PDF: {str(e)}", "danger")
        return redirect(url_for("nota_fiscal.index"))


@nota_fiscal_bp.route("/api/documentos/<int:nota_id>", methods=["GET"])
@login_required
def api_listar_documentos(nota_id):
    try:
        documentos = (
            db.session.query(Upload.id, Upload.filename, Upload.tipo, Upload.uploaded_at)
            .filter_by(pai="NotaFiscal", pai_id=nota_id)
            .all()
        )
        resultado = []
        nota = NotaFiscal.query.get(nota_id)
        if nota:
            resultado.append(
                {
                    "id": nota.id,
                    "filename": f"nf {nota.numero_nf}.xml",
                    "tipo": 10,
                    "uploaded_at": nota.data_importacao.isoformat() if nota.data_importacao else None,
                }
            )
            # Tentar buscar PDF no Arquivei caso não tenha uploads
            if not documentos:
                try:
                    nota.get_pdf()
                    print(f'nota.pdf: {nota.pdf}')
                except Exception as e:
                    print(f'Erro ao buscar PDF no Arquivei: {str(e)}')
                    pass

        for doc in documentos:
            resultado.append(
                {
                    "id": doc[0],
                    "filename": doc[1],
                    "tipo": doc[2],
                    "uploaded_at": doc[3].isoformat() if doc[3] else None,
                }
            )
        return jsonify({"documentos": resultado, "success": True})
    except Exception as e:
        logger.error(f"Erro ao listar documentos: {str(e)}")
        return jsonify({"error": f"Erro ao listar documentos: {str(e)}", "success": False}), 500


@nota_fiscal_bp.route("/api/documentos", methods=["POST"])
@login_required
def api_adicionar_documento():
    try:
        nota_id = request.form.get("nota_fiscal_id")
        tipo = request.form.get("tipo")
        arquivo = request.files.get("arquivo")

        if not nota_id or not tipo or not arquivo:
            return jsonify({"success": False, "message": "Dados incompletos"}), 400

        nota = NotaFiscal.query.get(nota_id)
        if not nota:
            return jsonify({"success": False, "message": "Nota fiscal não encontrada"}), 404

        arquivo_bytes = arquivo.read()
        arquivo_b64 = base64.b64encode(arquivo_bytes).decode("utf-8")

        upload = Upload(
            pai="NotaFiscal",
            pai_id=nota_id,
            tipo=tipo,
            filename=arquivo.filename,
            mimetype=arquivo.content_type,
            blob=arquivo_b64,
        )
        upload.save()
        return jsonify({"success": True, "message": "Documento adicionado com sucesso"})
    except Exception as e:
        logger.error(f"Erro ao adicionar documento: {str(e)}")
        return jsonify({"success": False, "message": f"Erro ao adicionar documento: {str(e)}"}), 500


@nota_fiscal_bp.route("/api/documentos/<int:doc_id>", methods=["DELETE"])
@login_required
def api_excluir_documento(doc_id):
    try:
        documento = Upload.query.get_or_404(doc_id)
        documento.delete()
        return jsonify({"success": True, "message": "Documento excluído com sucesso"})
    except Exception as e:
        logger.error(f"Erro ao excluir documento: {str(e)}")
        return jsonify({"success": False, "message": f"Erro ao excluir documento: {str(e)}"}), 500


@nota_fiscal_bp.route("/api/documentos/<int:doc_id>/visualizar")
@login_required
def api_visualizar_documento(doc_id):
    try:
        documento = Upload.query.get_or_404(doc_id)
        response = make_response(base64.b64decode(documento.blob))
        response.headers["Content-Type"] = documento.mimetype
        response.headers["Content-Disposition"] = f"inline; filename={documento.filename}"
        return response
    except Exception as e:
        logger.error(f"Erro ao visualizar documento: {str(e)}")
        return jsonify({"error": f"Erro ao visualizar documento: {str(e)}"}), 500


@nota_fiscal_bp.route("/api/documentos/<int:doc_id>/download")
@login_required
def api_download_documento(doc_id):
    try:
        documento = Upload.query.filter(Upload.id == doc_id).first()
        response = make_response(base64.b64decode(documento.blob))
        response.headers["Content-Type"] = documento.mimetype
        response.headers["Content-Disposition"] = f"attachment; filename={documento.filename}"
        return response
    except Exception as e:
        logger.error(f"Erro ao fazer download do documento: {str(e)}")
        return jsonify({"error": f"Erro ao fazer download do documento: {str(e)}"}), 500


@nota_fiscal_bp.route("/estatisticas-pdfs", methods=["GET"])
@login_required
def estatisticas_pdfs():
    """
    Estatísticas para o modal de exportação ZIP.
    """
    try:
        query = api_get_dados_notas_fiscais(request)
        nota_ids = [nf.id for nf in query.with_entities(NotaFiscal.id).all()]
        if not nota_ids:
            return jsonify(
                {
                    "total_pdfs_originais": 0,
                    "total_pdfs_protocolo": 0,
                    "total_sem_protocolo": 0,
                    "total_pdfs_reembolso": 0,
                    "total_notas": 0,
                    "notas_sem_original_ids": [],
                }
            )

        stats = (
            db.session.query(
                func.sum(case((Upload.tipo == 1, 1), else_=0)).label("total_pdfs_originais"),
                func.sum(case((Upload.tipo == 2, 1), else_=0)).label("total_pdfs_protocolo"),
                func.sum(case((Upload.tipo == 3, 1), else_=0)).label("total_pdfs_reembolso"),
                func.count(func.distinct(case((Upload.tipo == 2, Upload.pai_id), else_=None))).label("notas_com_protocolo"),
            )
            .filter(Upload.pai == "NotaFiscal", Upload.pai_id.in_(nota_ids))
            .first()
        )

        total_pdfs_originais = stats.total_pdfs_originais or 0
        total_pdfs_protocolo = stats.total_pdfs_protocolo or 0
        total_pdfs_reembolso = stats.total_pdfs_reembolso or 0
        notas_com_protocolo = stats.notas_com_protocolo or 0

        total_notas = len(nota_ids)
        total_sem_protocolo = total_notas - notas_com_protocolo

        notas_sem_original = (
            db.session.query(NotaFiscal.id)
            .filter(
                NotaFiscal.id.in_(nota_ids),
                ~db.session.query(Upload.id)
                .filter(Upload.pai == "NotaFiscal", Upload.pai_id == NotaFiscal.id, Upload.tipo == 1)
                .exists(),
            )
            .all()
        )
        notas_sem_original_ids = [row[0] for row in notas_sem_original]

        return jsonify(
            {
                "total_pdfs_originais": total_pdfs_originais,
                "total_pdfs_protocolo": total_pdfs_protocolo,
                "total_sem_protocolo": total_sem_protocolo,
                "total_pdfs_reembolso": total_pdfs_reembolso,
                "total_notas": total_notas,
                "notas_sem_original_ids": notas_sem_original_ids,
            }
        )
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas de PDFs: {str(e)}")
        return jsonify({"error": "Erro ao obter estatísticas"}), 500


@nota_fiscal_bp.route("/download-pdfs-sem-protocolo", methods=["GET"])
@login_required
def download_pdfs_sem_protocolo():
    """
    Baixa ZIP com PDFs originais (tipo=1) das notas filtradas que NÃO têm protocolo (tipo=2).
    Se não existir PDF original no banco, tenta baixar do Arquivei e salvar.
    """
    try:
        query = api_get_dados_notas_fiscais(request)
        notas = query.all()

        zip_buffer = io.BytesIO()
        pdfs_adicionados = 0
        pdfs_baixados = 0
        erros = []

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for nota_row in notas:
                # A query retorna KeyedTuple (NotaFiscal + colunas calculadas)
                nota = getattr(nota_row, "NotaFiscal", None) or nota_row[0]
                try:
                    tem_protocolo = (
                        db.session.query(Upload.id)
                        .filter(Upload.pai == "NotaFiscal", Upload.pai_id == nota.id, Upload.tipo == 2)
                        .first()
                        is not None
                    )
                    if tem_protocolo:
                        continue

                    upload_original = (
                        db.session.query(Upload)
                        .filter(Upload.pai == "NotaFiscal", Upload.pai_id == nota.id, Upload.tipo == 1)
                        .first()
                    )

                    pdf_bytes = None
                    if not upload_original:
                        if not nota.chave_acesso:
                            erros.append(f"Nota {nota.numero_nf}: sem chave de acesso")
                            continue
                        try:
                            arquivei = Arquivei(chave_acesso=nota.chave_acesso)
                            if arquivei.pdf:
                                pdf_bytes = base64.b64decode(arquivei.pdf)
                                filename = f"{nota.chave_acesso}.pdf"
                                upload_original = Upload(
                                    pai="NotaFiscal",
                                    pai_id=nota.id,
                                    tipo=1,
                                    filename=filename,
                                    mimetype="application/pdf",
                                    blob=arquivei.pdf,
                                )
                                db.session.add(upload_original)
                                db.session.commit()
                                pdfs_baixados += 1
                            else:
                                erros.append(f"Nota {nota.numero_nf}: PDF não encontrado no Arquivei")
                                continue
                        except Exception as e:
                            db.session.rollback()
                            erros.append(f"Nota {nota.numero_nf}: Erro ao baixar PDF - {str(e)}")
                            continue
                    else:
                        try:
                            pdf_bytes = base64.b64decode(upload_original.blob)
                        except Exception:
                            erros.append(f"Nota {nota.numero_nf}: Erro ao decodificar PDF")
                            continue

                    if pdf_bytes:
                        data_emissao = nota.data_emissao.strftime("%Y%m%d") if nota.data_emissao else "semdata"
                        nome_arquivo = f"{nota.numero_nf}_{data_emissao}_{nota.chave_acesso}.pdf"
                        zipf.writestr(nome_arquivo, pdf_bytes)
                        pdfs_adicionados += 1
                except Exception as e:
                    erros.append(f"Nota {getattr(nota, 'numero_nf', 'N/A')}: {str(e)}")
                    continue

        if pdfs_adicionados == 0:
            mensagem = "Nenhum PDF original sem protocolo foi encontrado com os filtros aplicados."
            if erros:
                mensagem += f" Erros: {', '.join(erros[:5])}"
            flash(mensagem, "warning")
            return redirect(url_for("nota_fiscal.index"))

        if pdfs_baixados > 0:
            flash(f"{pdfs_adicionados} PDF(s) no ZIP. {pdfs_baixados} baixado(s) do Arquivei.", "success")
        else:
            flash(f"{pdfs_adicionados} PDF(s) no ZIP.", "success")

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            download_name=f"pdfs_sem_protocolo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            as_attachment=True,
            mimetype="application/zip",
        )
    except Exception as e:
        logger.error(f"Erro ao gerar ZIP de PDFs: {str(e)}")
        flash("Erro ao gerar arquivo ZIP. Por favor, tente novamente.", "danger")
        return redirect(url_for("nota_fiscal.index"))


