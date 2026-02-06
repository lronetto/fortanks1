import base64
import io
import json
import logging
import zipfile
from datetime import datetime

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user
from flask_login import login_required
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from models.database import db
from models.estoque import EstoqueMovimentacoes
from models.logs import Logs
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.upload import Upload
from scripts.processar_email1 import processar_emails

from .. import nota_fiscal_bp

logger = logging.getLogger(__name__)


@nota_fiscal_bp.route("/reprocessar-importacao")
@login_required
def reprocessar_importacao():
    NotaFiscalItem.query.update(
        {"importado_estoque": False, "movimentacao_estoque_id": None, "data_importacao_estoque": None},
        synchronize_session=False,
    )
    EstoqueMovimentacoes.query.filter(EstoqueMovimentacoes.origem_tipo == "NotaFiscal").delete()
    db.session.commit()
    importar_todas_pendentes()
    return jsonify({"success": True, "message": "Importação reprocessada com sucesso"}), 200


@nota_fiscal_bp.route("/importar-arquivei", methods=["POST"])
@login_required
def importar_arquivei():
    """
    Importa notas fiscais da API do Arquivei (modal).
    """
    try:
        csrf_token = request.form.get("csrf_token")
        if not csrf_token:
            flash("Token CSRF não fornecido", "danger")
            return redirect(url_for("nota_fiscal.index"))

        data_inicial = request.form.get("data_inicial")
        data_final = request.form.get("data_final")
        tipo_documento = request.form.get("tipo_documento", "nfe")

        if not data_inicial or not data_final:
            flash("Datas inicial e final são obrigatórias!", "danger")
            return redirect(url_for("nota_fiscal.index"))

        if tipo_documento == "todos":
            NotaFiscal.importar_arquivei(data_inicial, data_final, "nfe")
            NotaFiscal.importar_arquivei(data_inicial, data_final, "cte")
            NotaFiscal.importar_arquivei(data_inicial, data_final, "nfse")
        else:
            NotaFiscal.importar_arquivei(data_inicial, data_final, tipo_documento)

        return jsonify({"success": True, "message": "Notas fiscais importadas com sucesso!"})
    except Exception as e:
        logger.error(f"Erro ao importar notas fiscais: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": f"Erro ao importar notas fiscais: {str(e)}"}), 500


@nota_fiscal_bp.route("/importar-xml", methods=["POST"])
@login_required
def importar_xml():
    """
    Importa notas fiscais a partir de arquivos XML ou ZIP enviados pelo modal.
    """
    mensagens = []
    total_importadas = 0
    total_erros = 0
    try:
        csrf_token = request.form.get("csrf_token")
        if not csrf_token:
            return jsonify({"success": False, "message": "Token CSRF não fornecido."})

        arquivos = request.files.getlist("xml_zip_files")
        if not arquivos:
            return jsonify({"success": False, "message": "Nenhum arquivo enviado."})

        
        for arquivo in arquivos:
            filename = secure_filename(arquivo.filename)
            if filename.lower().endswith(".zip"):
                with zipfile.ZipFile(arquivo) as z:
                    for zipinfo in z.infolist():
                        if zipinfo.filename.lower().endswith(".xml"):
                            with z.open(zipinfo) as xmlfile:
                                xml_bytes = xmlfile.read()
                                xml_b64 = base64.b64encode(xml_bytes).decode("utf-8")
                                nf = NotaFiscal(xml_data=xml_b64)
                                if nf and nf.id:
                                    total_importadas += 1
                                else:
                                    mensagens.append(f"Erro ao importar {zipinfo.filename}")
            elif filename.lower().endswith(".xml"):
                print("teste")
                xml_bytes = arquivo.read()
                xml_b64 = base64.b64encode(xml_bytes).decode("utf-8")
                nf = NotaFiscal(xml_data=xml_b64)
                if nf and nf.id:
                    total_importadas += 1
                else:
                    total_erros += 1
            else:
                total_erros += 1
        return jsonify({"success": True, "message": f"{total_importadas} nota(s) fiscal(is) importada(s) com sucesso!", "total_erros": total_erros}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Erro ao importar XML: {str(e)}", "total_erros": 0}), 500


@nota_fiscal_bp.route("/importar-todas-pendentes", methods=["GET"])
@login_required
def importar_todas_pendentes():
    """
    Importa automaticamente para o estoque todos os itens de notas fiscais
    que não foram importados e que já possuem material vinculado.
    """
    try:
        notas_fiscais = (
            NotaFiscal.query.filter(NotaFiscal.status_processamento != "cancelada", NotaFiscalItem.material_id != None)
            .join(NotaFiscalItem, NotaFiscal.id == NotaFiscalItem.nf_id)
            .all()
        )

        itens_importados = 0
        notas_processadas = 0
        notas_importadas = 0
        notas_canceladas = 0

        total_notas = len(notas_fiscais)

        for nota_fiscal in notas_fiscais:
            notas_processadas += 1
            nota_fiscal.importar_itens_para_estoque()
            if nota_fiscal.estatisticas.get("total_importados", 0) > 0:
                notas_importadas += 1
                itens_importados += nota_fiscal.estatisticas["total_importados"]

        if itens_importados > 0:
            flash(
                f"{itens_importados} itens de {notas_processadas} notas fiscais foram importados automaticamente para o estoque.",
                "success",
            )
        else:
            flash("Não foram encontrados itens pendentes com materiais vinculados para importação.", "info")

        log = {
            "itens_importados": itens_importados,
            "notas_processadas": notas_processadas,
            "notas_importadas": notas_importadas,
            "notas_canceladas": notas_canceladas,
            "total_notas": total_notas,
        }
        Logs(local="importar_todas_pendentes", data=datetime.now(), texto=json.dumps(log))
        return redirect(url_for("nota_fiscal.index"))
    except Exception as e:
        logger.error(f"Erro ao importar notas pendentes: {str(e)}")
        flash(f"Erro ao processar importação automática: {str(e)}", "danger")
        return redirect(url_for("nota_fiscal.index"))

@nota_fiscal_bp.route("/importar-item-estoque-todas-notas/<int:item_id>", methods=["POST"])
@login_required
def importar_item_estoque_todas_notas(item_id):
    item = NotaFiscalItem.query.get_or_404(item_id)
    if not item.material_id:
        return jsonify({"success": False, "message": "Este item não está vinculado a um material do sistema"}), 400

    centro_custo_id = request.form.get("centro_custo_id")
    observacao = request.form.get("observacao")
    
    sucesso, mensagem, estatisticas = item.vincular_e_importar_estoque_todos(
        usuario_id=current_user.id,
        centro_custo_id=centro_custo_id if centro_custo_id else None,
        observacao=observacao or f"Importação da NF {item.nota_fiscal.numero_nf if item.nota_fiscal else 'N/A'}",
    )
    Logs(local="importar_item_estoque", data=datetime.now(), texto=json.dumps(estatisticas))
    return jsonify({"success": bool(sucesso), "message": mensagem})

# Rotas de diagnóstico antigas removidas:
# - /teste, /teste1, /teste2, /teste3


