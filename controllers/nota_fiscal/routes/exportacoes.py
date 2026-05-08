import base64
import io
import logging
import zipfile
from datetime import datetime

import pandas as pd
from flask import request, send_file
from flask_login import login_required

from models.nota_fiscal import NotaFiscal, CFOPS_VENDA, CFOPS_TRANSFERENCIA, CNPJS_MATRIZ_FILIAIS
from models.upload import Upload

from .. import nota_fiscal_bp
from ..services.query_notas import api_get_dados_notas_fiscais

logger = logging.getLogger(__name__)


def _status_upload_from_row(row):
    """Monta o texto de Status Upload a partir das colunas upload_arquivei, upload_protocolo, upload_reembolso do row."""
    upload_arquivei = getattr(row, "upload_arquivei", None) if hasattr(row, "upload_arquivei") else (row[6] if len(row) > 6 else None)
    upload_protocolo = getattr(row, "upload_protocolo", None) if hasattr(row, "upload_protocolo") else (row[4] if len(row) > 4 else None)
    upload_reembolso = getattr(row, "upload_reembolso", None) if hasattr(row, "upload_reembolso") else (row[5] if len(row) > 5 else None)
    status_u = []
    if upload_arquivei:
        status_u.append("Arquivei")
    if upload_protocolo:
        status_u.append("Protocolo")
    if upload_reembolso:
        status_u.append("Reembolso")
    if not status_u:
        status_u.append("Nenhum")
    return ", ".join(status_u)


@nota_fiscal_bp.route("/exportar-excel")
@login_required
def exportar_excel():
    """
    Exporta as notas fiscais filtradas para um arquivo Excel (botão na tela principal).
    Usa o mesmo serviço de query da tela principal (query_notas) para manter filtros consistentes.
    """
    print(f"request: {request.args}")
    query = api_get_dados_notas_fiscais(request)
    rows = query.all()

    dados_cte = []
    dados_nfe = []
    dados_nfs = []
    for row in rows:
        nota = getattr(row, "NotaFiscal", None) or row[0]
        status_u = _status_upload_from_row(row)
        linha = {
            "Data": nota.data_emissao.strftime("%d/%m/%Y") if nota.data_emissao else "",
            "Número": nota.numero_nf,
            "Fornecedor": nota.nome_emitente,
            "Valor": float(nota.valor_total) if nota.valor_total is not None else 0.0,
            "Status Upload": status_u,
            "Status": nota.status_processamento,
            "Chave de Acesso": nota.chave_acesso,
        }
        if nota.tipo == 2:
            dados_cte.append(linha)
        elif nota.tipo in [0, 1]:
            dados_nfe.append(linha)
        else:
            dados_nfs.append(linha)

    colunas = ["Fornecedor", "Número", "Chave de Acesso", "Data", "Valor", "Status Upload", "Status"]
    output = io.BytesIO()
    print(f"dados_cte: {len(dados_cte)}")
    print(f"dados_nfe: {len(dados_nfe)}")
    print(f"dados_nfs: {len(dados_nfs)}")
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        if dados_cte:
            pd.DataFrame(dados_cte).to_excel(writer, index=False, sheet_name="CTE")
        if dados_nfe:
            pd.DataFrame(dados_nfe).to_excel(writer, index=False, sheet_name="NFe")
        if dados_nfs:
            pd.DataFrame(dados_nfs).to_excel(writer, index=False, sheet_name="NFS")
        if not dados_cte and not dados_nfe and not dados_nfs:
            pd.DataFrame(columns=colunas).to_excel(writer, index=False, sheet_name="Notas Fiscais")
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
            xd = nota.get_xml_data()
            xml_bytes = base64.b64decode(xd) if xd else b""
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


