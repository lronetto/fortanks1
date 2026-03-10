import base64
import io
import logging
import zipfile
from datetime import datetime

import pandas as pd
from flask import request, send_file
from flask_login import login_required
from sqlalchemy import or_

from models.database import db
from models.nota_fiscal import NotaFiscal, NotaFiscalItem, CFOPS_VENDA, CFOPS_TRANSFERENCIA, CNPJS_MATRIZ_FILIAIS
from models.upload import Upload

from .. import nota_fiscal_bp
from ..services.query_notas import api_get_dados_notas_fiscais

logger = logging.getLogger(__name__)


@nota_fiscal_bp.route("/exportar-excel")
@login_required
def exportar_excel():
    """
    Exporta as notas fiscais filtradas para um arquivo Excel (botão na tela principal).
    """
    busca = request.args.get("busca", "")
    item_nome = request.args.get("item_nome", "")
    status_importacao = request.args.get("status_importacao", "")
    data_emissao_inicio = request.args.get("data_emissao_inicio", "")
    data_emissao_fim = request.args.get("data_emissao_fim", "")
    tipo_nfe = request.args.get("tipo_nfe", "")
    status_upload = request.args.get("status_upload", "")
    cnpj_emitente_val = (request.args.get("cnpj_emitente", "") or "").strip()
    cnpj_destinatario_val = (request.args.get("cnpj_destinatario", "") or "").strip()

    query = NotaFiscal.query.filter(NotaFiscal.status_processamento != "cancelada")

    if busca:
        busca_like = f"%{busca}%"
        query = query.filter(
            or_(
                NotaFiscal.numero_nf.ilike(busca_like),
                NotaFiscal.nome_emitente.ilike(busca_like),
                NotaFiscal.chave_acesso.ilike(busca_like),
            )
        )
    if item_nome:
        query = query.join(NotaFiscalItem).filter(NotaFiscalItem.descricao.ilike(f"%{item_nome}%"))
    if status_importacao == "pendentes":
        query = query.filter(~NotaFiscal.itens.any(NotaFiscalItem.importado_estoque.is_(True)))
    if cnpj_emitente_val:
        query = query.filter(NotaFiscal.cnpj_emitente == cnpj_emitente_val)
    if cnpj_destinatario_val:
        query = query.filter(NotaFiscal.cnpj_destinatario == cnpj_destinatario_val)
    if data_emissao_inicio:
        query = query.filter(NotaFiscal.data_emissao >= datetime.strptime(data_emissao_inicio, "%Y-%m-%d"))
    if data_emissao_fim:
        query = query.filter(NotaFiscal.data_emissao <= datetime.strptime(data_emissao_fim, "%Y-%m-%d"))
    if tipo_nfe:
        if tipo_nfe == "0":
            tipos = [0, 1]
        elif tipo_nfe == "2":
            tipos = [2]
        elif tipo_nfe == "3":
            tipos = [3]
        else:
            tipos = None
        if tipos is not None:
            query = query.filter(NotaFiscal.tipo.in_(tipos))

    if status_upload:
        if status_upload == "1":
            query = query.filter(
                db.session.query(Upload.id)
                .filter(Upload.pai == "NotaFiscal", Upload.pai_id == NotaFiscal.id, Upload.tipo == 1)
                .exists()
            )
        elif status_upload == "2":
            query = query.filter(
                db.session.query(Upload.id)
                .filter(Upload.pai == "NotaFiscal", Upload.pai_id == NotaFiscal.id, Upload.tipo == 2)
                .exists()
            )
        elif status_upload == "3":
            query = query.filter(
                db.session.query(Upload.id)
                .filter(Upload.pai == "NotaFiscal", Upload.pai_id == NotaFiscal.id, Upload.tipo == 3)
                .exists()
            )
        elif status_upload == "4":
            query = query.filter(
                ~db.session.query(Upload.id)
                .filter(Upload.pai == "NotaFiscal", Upload.pai_id == NotaFiscal.id, Upload.tipo == 2)
                .exists()
            )

    query = query.order_by(NotaFiscal.data_emissao.desc(), NotaFiscal.numero_nf.desc())
    notas = query.all()

    dados = []
    for nf in notas:
        uploads = db.session.query(Upload.tipo).filter_by(pai_id=nf.id, pai="NotaFiscal").all()
        status_u = []
        if uploads:
            tipos = [u[0] for u in uploads]
            if 1 in tipos:
                status_u.append("Arquivei")
            if 2 in tipos:
                status_u.append("Protocolo")
            if 3 in tipos:
                status_u.append("Reembolso")
        else:
            status_u.append("Nenhum")
        dados.append(
            {
                "Fornecedor": nf.nome_emitente,
                "Número": nf.numero_nf,
                "Tipo": "NFe" if nf.tipo in [0, 1] else ("CTE" if nf.tipo == 2 else "NFSe"),
                "Chave de Acesso": nf.chave_acesso,
                "Data": nf.data_emissao.strftime("%d/%m/%Y") if nf.data_emissao else "",
                "Valor": float(nf.valor_total) if nf.valor_total is not None else 0.0,
                "Status Upload": ", ".join(status_u),
                "Status": nf.status_processamento,
            }
        )

    df = pd.DataFrame(dados)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Notas Fiscais")
    output.seek(0)

    return send_file(
        output,
        download_name="notas_fiscais.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@nota_fiscal_bp.route("/exportar-zip", methods=["GET"])
@login_required
def exportar_zip():
    """
    Exporta ZIP com XMLs filtrados + planilha.
    """
    query = api_get_dados_notas_fiscais(request)
    notas = query.all()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        excel_cte_data = []
        excel_nfe_data = []
        excel_nfe_vendas_data = []
        excel_transfer_data = []
        for row in notas:
            nota = getattr(row, "NotaFiscal", None) or row[0]
            pagamento = getattr(row, "pagamento", None) or row[1]
            tipo = "NFe" if nota.tipo in [0, 1] else ("CTe" if nota.tipo == 2 else "NFSe")
            xml_bytes = base64.b64decode(nota.xml_data) if nota.xml_data else b""
            data_emissao = nota.data_emissao.strftime("%d_%m_%Y") if nota.data_emissao else ""
            zipf.writestr(f"{tipo} {data_emissao}_{nota.nome_emitente}_{nota.numero_nf}.xml", xml_bytes)
            upload = Upload.query.filter_by(pai="NotaFiscal", pai_id=nota.id).order_by(Upload.tipo).all()
            if upload:
                # Filtra apenas uploads válidos (com blob) e conta por tipo
                uploads_validos = [u for u in upload if u.blob]
                contagem_por_tipo = {}
                for u in uploads_validos:
                    if u.tipo in [1, 2, 3]:
                        contagem_por_tipo[u.tipo] = contagem_por_tipo.get(u.tipo, 0) + 1
                
                # Contador para evitar nomes duplicados no ZIP
                pdf_counters = {1: 0, 2: 0, 3: 0}
                base_name = f"{tipo} {data_emissao}_{nota.nome_emitente}_{nota.numero_nf}"
                
                for u in uploads_validos:
                    if u.tipo not in [1, 2, 3]:
                        continue
                    
                    # Usa o método get_blob() que já faz a decodificação corretamente
                    blob_bytes = u.get_blob()
                    if not blob_bytes:
                        logger.warning(f"Erro ao decodificar blob do upload {u.id} (tipo {u.tipo}) da nota {nota.numero_nf}. Pulando...")
                        continue
                    
                    # Incrementa contador antes de gerar nome
                    pdf_counters[u.tipo] += 1
                    
                    # Gera nome do arquivo com sufixo se houver múltiplos uploads do mesmo tipo
                    if contagem_por_tipo.get(u.tipo, 0) > 1:
                        filename = f"{base_name}_{pdf_counters[u.tipo]}.pdf"
                    else:
                        filename = f"{base_name}.pdf"
                    
                    zipf.writestr(filename, blob_bytes)
            excel={
                "Data": nota.data_emissao.strftime("%d/%m/%Y") if nota.data_emissao else "",
                "Fornecedor": nota.nome_emitente,
                "Número": nota.numero_nf,
                "Tipo": tipo ,
                "Valor": float(nota.valor_total) if nota.valor_total is not None else 0.0,
                "Chave de Acesso": nota.chave_acesso,
                "cnpj_emitente": nota.cnpj_emitente,
                "cnpj_destinatario": nota.cnpj_destinatario,
                "Protocolo": "sim" if 2 in [u.tipo for u in upload] else "nao",
                "Pagamento": "sim" if pagamento == 1 else "nao",
            }
            if tipo == "CTe":
                excel_cte_data.append(excel)
            elif tipo == "NFe":
                # Verifica se é venda (emitente é matriz/filial e tem CFOP de venda)
                if nota.cnpj_emitente in CNPJS_MATRIZ_FILIAIS:
                    tem_cfop_venda = any(i.cfop in CFOPS_VENDA for i in nota.itens)
                    tem_cfop_transferencia = any(i.cfop in CFOPS_TRANSFERENCIA for i in nota.itens)
                    
                    if tem_cfop_venda:
                        excel_nfe_vendas_data.append(excel)
                    elif tem_cfop_transferencia or (nota.cnpj_destinatario in CNPJS_MATRIZ_FILIAIS):
                        # Transferência entre matriz/filiais
                        excel_transfer_data.append(excel)
                    else:
                        # Outros casos (ex: devoluções, etc)
                        excel_nfe_data.append(excel)
                else:
                    # Compra externa
                    excel_nfe_data.append(excel)

        # Usa ExcelWriter para escrever múltiplas sheets no mesmo arquivo
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            if excel_cte_data:
                df_cte = pd.DataFrame(excel_cte_data)
                df_cte.to_excel(writer, index=False, sheet_name="CTE")
            if excel_nfe_data:
                df_nfe = pd.DataFrame(excel_nfe_data)
                df_nfe.to_excel(writer, index=False, sheet_name="NFe")
            if excel_nfe_vendas_data:
                df_nfe_vendas = pd.DataFrame(excel_nfe_vendas_data)
                df_nfe_vendas.to_excel(writer, index=False, sheet_name="NFe Vendas")
            if excel_transfer_data:
                df_transfer = pd.DataFrame(excel_transfer_data)
                df_transfer.to_excel(writer, index=False, sheet_name="Transferência")
        
        excel_buffer.seek(0)
        zipf.writestr("notas_fiscais.xlsx", excel_buffer.read())

    zip_buffer.seek(0)
    return send_file(zip_buffer, download_name="notas_fiscais.zip", as_attachment=True, mimetype="application/zip")


