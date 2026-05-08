import base64
import io
import json
import logging
import zipfile
from datetime import datetime
from decimal import Decimal

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
from models.arquivei import Arquivei
from scripts.email import processar_emails

from .. import nota_fiscal_bp
from utils.utils import json_dumps_safe
logger = logging.getLogger(__name__)
from scripts.email import processar_anexo_pdf_pagina




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
        logs = []
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
            log=None
            log=NotaFiscal.importar_arquivei(data_inicial, data_final, "nfe")
            logs.append(log)
            log=None
            log=NotaFiscal.importar_arquivei(data_inicial, data_final, "cte")
            logs.append(log)
            log=None
            log=NotaFiscal.importar_arquivei(data_inicial, data_final, "nfse")
            logs.append(log)
        else:
            log=None
            log=NotaFiscal.importar_arquivei(data_inicial, data_final, tipo_documento)
            logs.append(log)
        Logs(local="importar_arquivei", data=datetime.now(), texto=json_dumps_safe(logs))
        return jsonify({"success": True, "message": "Notas fiscais importadas com sucesso!", "logs": logs}), 200
    except Exception as e:
        logger.error(f"Erro ao importar notas fiscais: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": f"Erro ao importar notas fiscais: {str(e)}"}), 500


@nota_fiscal_bp.route("/atualizar-notas-documento-sefaz", methods=["POST"])
@login_required
def atualizar_notas_documento_sefaz():
    """
    Promove XMLs já persistidos em `documentos_sefaz` para `NotaFiscal`
    (ver `executar_importacao_desde_documento_sefaz`).
    """
    try:
        csrf_token = request.form.get("csrf_token")
        if not csrf_token:
            return jsonify({"success": False, "message": "Token CSRF não fornecido."}), 400

        limite_raw = (request.form.get("limite") or "").strip()
        limite = None
        if limite_raw:
            try:
                limite = int(limite_raw)
            except ValueError:
                return jsonify({"success": False, "message": "Limite inválido."}), 400
            if limite < 1:
                return jsonify({"success": False, "message": "Limite deve ser ≥ 1 ou deixar em branco."}), 400

        from models.nota_fiscal.services import executar_importacao_desde_documento_sefaz

        resumo = executar_importacao_desde_documento_sefaz(limite=limite)
        Logs(
            local="atualizar_notas_documento_sefaz",
            data=datetime.now(),
            texto=json_dumps_safe(resumo),
        )
        n_err = len(resumo.get("erros") or [])
        msg_parts = [
            f"XMLs processados nesta rodada: {resumo.get('processados', 0)}.",
            f"Marcados como inseridos no SEFAZ: {resumo.get('marcados_inserido', 0)}.",
        ]
        if n_err:
            msg_parts.append(f"Avisos/erros: {n_err}.")
        mensagem = " ".join(msg_parts)
        return jsonify({"success": True, "message": mensagem, "resumo": resumo}), 200
    except Exception as e:
        logger.exception("Erro ao atualizar notas a partir de documento_sefaz: %s", e)
        return (
            jsonify(
                {"success": False, "message": f"Erro ao atualizar notas: {str(e)}"}
            ),
            500,
        )


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

        logs = []
        for i, arquivo in enumerate(arquivos):
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
                print(f"processando {i}/{len(arquivos)}")
                xml_bytes = arquivo.read()
                xml_b64 = base64.b64encode(xml_bytes).decode("utf-8")
                nf = NotaFiscal(xml_data=xml_b64)
                if nf and nf.id:
                    total_importadas += 1
                else:
                    total_erros += 1
            elif filename.lower().endswith(".pdf"):
                print(f"processando {i}/{len(arquivos)}")
                pdf_bytes = arquivo.read()
                anexo = {
                    'filename': filename,
                    'tamanho_mb': '',
                    'codbarras': {'qtd': 0, 'codigos': []},
                    'db': [],
                    'upload': False,
                    'nao_identificados': 0
                }
                out = processar_anexo_pdf_pagina(anexo, filename, pdf_bytes, 1)
                logs.append(anexo)
                #print(f"log: {anexo}")
                if not out:
                    total_erros += 1
        print(f"logs: {logs}")
        #Logs(local="importar_xml", data=datetime.now(), texto=json_dumps_safe(logs))

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
        Logs(local="importar_todas_pendentes", data=datetime.now(), texto=json_dumps_safe(log))
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
    Logs(local="importar_item_estoque", data=datetime.now(), texto=json_dumps_safe(estatisticas))
    return jsonify({"success": bool(sucesso), "message": mensagem})


@nota_fiscal_bp.route("/verificar-notas-canceladas", methods=["GET"])
@login_required
def verificar_notas_canceladas():
    """
    Verifica no Arquivei quais notas do período do filtro estão canceladas
    e atualiza status_processamento para 'cancelada' quando for o caso.
    Usa data_emissao_inicio e data_emissao_fim do filtro (query string).
    """
    try:
        data_inicio = request.args.get("data_emissao_inicio", "").strip()
        data_fim = request.args.get("data_emissao_fim", "").strip()
        if not data_inicio or not data_fim:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Informe o período do filtro (Data Emissão Início e Fim) para verificar notas canceladas.",
                    }
                ),
                400,
            )
        try:
            dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
            dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        except ValueError:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Datas inválidas. Use o formato AAAA-MM-DD.",
                    }
                ),
                400,
            )
        if dt_inicio > dt_fim:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Data início não pode ser maior que data fim.",
                    }
                ),
                400,
            )

        # Notas do período que ainda não estão marcadas como canceladas
        LIMITE_VERIFICACAO = 500
        notas = (
            NotaFiscal.query.filter(
                NotaFiscal.status_processamento != "cancelada",
                NotaFiscal.data_emissao >= dt_inicio,
                NotaFiscal.data_emissao <= dt_fim,
            )
            .order_by(NotaFiscal.data_emissao)
            .limit(LIMITE_VERIFICACAO)
            .all()
        )

        verificadas = 0
        marcadas_canceladas = 0
        erros = []

        # Mapeamento NotaFiscal.tipo (int) -> Arquivei tipo (str)
        tipo_arquivei_map = {0: "nfe", 2: "cte", 3: "nfse"}

        for nota in notas:
            try:
                tipo_arq = tipo_arquivei_map.get(nota.tipo, "nfe")
                arquivei = Arquivei(
                    chave_acesso=nota.chave_acesso,
                    cancelamento=True,
                    tipo=tipo_arq,
                )
                verificadas += 1
                if getattr(arquivei, "cancelada", False):
                    nota.status_processamento = "cancelada"
                    marcadas_canceladas += 1
            except Exception as e:
                erros.append({"chave": nota.chave_acesso, "erro": str(e)})

        if marcadas_canceladas > 0:
            db.session.commit()

        log = {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "verificadas": verificadas,
            "marcadas_canceladas": marcadas_canceladas,
            "erros": erros,
        }
        Logs(local="verificar_notas_canceladas", data=datetime.now(), texto=json_dumps_safe(log))

        msg = f"Verificação concluída: {verificadas} nota(s) verificada(s), {marcadas_canceladas} marcada(s) como cancelada(s)."
        if erros:
            msg += f" {len(erros)} erro(s) (ver logs)."
        if len(notas) >= LIMITE_VERIFICACAO:
            msg += f" Limite de {LIMITE_VERIFICACAO} notas por execução; refine o período se necessário."

        return jsonify(
            {
                "success": True,
                "message": msg,
                "verificadas": verificadas,
                "marcadas_canceladas": marcadas_canceladas,
                "erros_count": len(erros),
            }
        )
    except Exception as e:
        logger.error(f"Erro ao verificar notas canceladas: {str(e)}", exc_info=True)
        return (
            jsonify({"success": False, "message": f"Erro ao verificar notas canceladas: {str(e)}"}),
            500,
        )


# Rotas de diagnóstico antigas removidas:
# - /teste, /teste1, /teste2, /teste3


