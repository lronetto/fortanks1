import json
import logging
import os
from io import BytesIO
from datetime import datetime

import openpyxl
import pandas as pd
from flask import flash, redirect, request, send_file, url_for
from flask_login import login_required

from models.estoque import Estoque
from models.material import Materiais
from models.nota_fiscal import NotaFiscalItem
from models.database import db
from sqlalchemy import or_

from .. import material_bp

logger = logging.getLogger(__name__)

# Constantes usadas no exportar_mega (mantidas do legado)
MEGA_MP = ["8", "9", "10", "11", "12", "13", "14", "20", "34", "72", "78", "79", "25", "37", "36", "38", "26", "76"]
MEGA_UC = ["17", "18", "31", "32", "33", "39", "19", "40", "41", "42", "73", "74", "75", "77", "23", "43", "44", "45", "46", "24", "47"]
MEGA_PA = ["48", "49", "51", "50", "52"]
MEGA_IM = ["21", "27", "28", "29", "30", "22", "81", "82", "83"]


@material_bp.route("/exportar-excel")
@login_required
def exportar_excel():
    """
    Exportação completa (legada). Mantida em formato reduzido.
    """
    try:
        search_term = request.args.get("search", "").strip()
        category_filters = [
            c.strip() for c in request.args.getlist("category") if c and str(c).strip()
        ]
        query = Materiais.query
        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.filter(
                or_(Materiais.nome.ilike(search_pattern), Materiais.dados_adicionais.ilike(search_pattern))
            )
        if category_filters:
            query = query.filter(Materiais.categoria.in_(category_filters))
        materiais = query.all()
        dados_exportacao = []
        for mat in materiais:
            itens = NotaFiscalItem.query.filter_by(material_id=mat.id).all()
            ncms_unicos = set(item.ncm.strip() if item.ncm and item.ncm.strip() else None for item in itens)
            ncms_validos = {ncm for ncm in ncms_unicos if ncm is not None}
            ncm_unico = list(ncms_validos)[0] if len(ncms_validos) == 1 else None
            ncm_iguais = "Sim" if len(ncms_validos) <= 1 else "Não"
            json_obj = json.loads(mat.dados_adicionais) if mat.dados_adicionais else {}
            codigo_mega = json_obj.get('codigo_mega', '')
            codigo_alterdata = json_obj.get('codigo_alterdata', '')
            codigo_sox = json_obj.get('codigo_sox', '')
          
            itens_por_ncm = {}
            for item in itens:
                ncm_item = item.ncm.strip() if item.ncm and item.ncm.strip() else None
                if not ncm_item:
                    continue
                itens_por_ncm.setdefault(ncm_item, []).append(
                    {
                        "numero_nf": item.nota_fiscal.numero_nf if item.nota_fiscal else None,
                        "fornecedor": item.nota_fiscal.nome_emitente if item.nota_fiscal else None,
                        "nome_item": item.descricao,
                    }
                )

            dados_exportacao.append(
                {
                    "ID": mat.id,
                    "Máscara": mat.mascara,
                    "Código SOX": codigo_sox,
                    "Código Mega": codigo_mega,
                    "Código Alterdata": codigo_alterdata,
                    "Nome": mat.nome,
 #                   "Descrição": mat.descricao,
                    "Categoria": mat.categoria,
                    "Unidade": mat.unidade_obj.nome if mat.unidade_obj else "",
                    "NCM": (mat.ncm if mat.ncm != "0" else (ncm_unico or "")),
                    "Plano de Conta": mat.plano_conta,
                    "Data Criação": mat.data_criacao.strftime("%Y-%m-%d %H:%M:%S") if mat.data_criacao else "",
                    "Quantidade Importada": len(itens),
                    "ncn iguais": ncm_iguais,
                    "ncm unicos": len(ncms_validos),
                    "ncms unico": ncm_unico,
                    "itens_por_ncm": json.dumps(itens_por_ncm, ensure_ascii=False),
                }
            )

        df = pd.DataFrame(dados_exportacao)
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Materiais")
        output.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"materiais_{timestamp}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.error(f"Erro ao exportar materiais para Excel: {e}")
        flash("Ocorreu um erro ao gerar o arquivo Excel.", "danger")
        return redirect(url_for("material.index"))

@material_bp.route("/exportar-excel1")
@login_required
def exportar_excel1():
    """
    Exportação completa (legada). Mantida em formato reduzido.
    """
    try:
        materiais = Materiais.query.all()
        dados_exportacao = []
        print(f"materiais: {len(materiais)}")
        i=0
        for mat in materiais:
            estoque = Estoque.query.filter_by(material_id=mat.id).first()
            if estoque:
                estoque_atual = estoque.get_estoque_atual()
            else:
                estoque_atual = 0
            print(f"material: {i}/{len(materiais)}")
            i+=1
            json_obj = json.loads(mat.dados_adicionais) if mat.dados_adicionais else {}
            codigo_alterdata = str(json_obj.get("codigo_alterdata") or "").replace(".0", "")
            dados_exportacao.append(
                {
                    "ID": mat.id,
 #                   "Máscara": mat.mascara,
 #                   "Código SOX": mat.codigo,
                    "Nome": mat.nome,
 #                   "Descrição": mat.descricao,
 #                   "Categoria": mat.categoria,
                    "Unidade": mat.unidade_obj.nome if mat.unidade_obj else "",
 #                   "NCM": (mat.ncm if mat.ncm != "0" else (ncm_unico or "")),
 #                   "Plano de Conta": mat.plano_conta,
                    "Código Alterdata": codigo_alterdata,
                    "estoque": str(estoque_atual).replace(".", ","),
 #                   "Data Criação": mat.data_criacao.strftime("%Y-%m-%d %H:%M:%S") if mat.data_criacao else "",
 #                   "Quantidade Importada": len(itens),
 #                   "ncn iguais": ncm_iguais,
 #                   "ncm unicos": len(ncms_validos),
 #                   "ncms unico": ncm_unico,
 #                   "itens_por_ncm": json.dumps(itens_por_ncm, ensure_ascii=False),
                }
            )

        df = pd.DataFrame(dados_exportacao)
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Materiais")
        output.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"materiais_{timestamp}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.error(f"Erro ao exportar materiais para Excel: {e}")
        flash("Ocorreu um erro ao gerar o arquivo Excel.", "danger")
        return redirect(url_for("material.index"))

@material_bp.route("/exportar-mega")
@login_required
def exportar_mega():
    """
    Exporta materiais para o Mega usando o template CADASTRO DE INSUMOS.xlsx.
    """
    try:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        template_path = os.path.join(base_path, 'templates_excel', 'MATERIAL_CADASTRO_DE_INSUMOS_MEGA.xlsx')
        print(f"template_path: {template_path}")
        if not os.path.exists(template_path):
            flash("Arquivo template não encontrado. Entre em contato com o administrador.", "danger")
            return redirect(url_for("material.index"))

        wb = openpyxl.load_workbook(template_path)
        ws = wb.active

        materiais = Materiais.query.filter_by(ativo=True).order_by(Materiais.nome).all()
        linha_atual = 7

        for material in materiais:
            json_obj = json.loads(material.dados_adicionais) if material.dados_adicionais else {}
            mega = json_obj.get('cod_mega', '')
            if mega:
                continue
            codigo_grupo = material.mascara if material.mascara else ""
            ws.cell(row=linha_atual, column=1, value=codigo_grupo)
            ws.cell(row=linha_atual, column=2, value=material.nome or "")

            def_item = "MP" if material.mascara in MEGA_MP else "MT" if material.mascara in MEGA_UC else "PA" if material.mascara in MEGA_PA else "EQ" if material.mascara in MEGA_IM else ""
            ws.cell(row=linha_atual, column=3, value=def_item)
            ws.cell(row=linha_atual, column=4, value="N")

            unidade = material.unidade_obj.nome if material.unidade_obj else "UN"
            ws.cell(row=linha_atual, column=5, value=unidade)

            def_fiscal = "01" if material.mascara in MEGA_MP else "07" if material.mascara in MEGA_UC else "04" if material.mascara in MEGA_PA else "08" if material.mascara in MEGA_IM else ""
            ws.cell(row=linha_atual, column=6, value=def_fiscal)

            ws.cell(row=linha_atual, column=7, value="Comprado")
            ws.cell(row=linha_atual, column=8, value=unidade)
            ws.cell(row=linha_atual, column=9, value="EM")
            ws.cell(row=linha_atual, column=10, value="NC")

            ws.cell(row=linha_atual, column=11, value=material.id)
            ws.cell(row=linha_atual, column=13, value="")
            if material.descricao:
                ws.cell(row=linha_atual, column=14, value=material.descricao)
            ws.cell(row=linha_atual, column=15, value="S")
            ws.cell(row=linha_atual, column=18, value="")
            ws.cell(row=linha_atual, column=19, value="")
            ws.cell(row=linha_atual, column=20, value=codigo_grupo)

            ncm = material.ncm if material.ncm else ""
            ws.cell(row=linha_atual, column=22, value=ncm)

            codigo_aplicacao = "401" if material.mascara in MEGA_MP else "468" if material.mascara in MEGA_UC else "601" if material.mascara in MEGA_PA else "105" if material.mascara in MEGA_IM else ""
            ws.cell(row=linha_atual, column=24, value=codigo_aplicacao)

            ws.cell(row=linha_atual, column=27, value="NCM")
            ws.cell(row=linha_atual, column=41, value=material.mascara)

            controle_estoque = "S" if material.mascara in (MEGA_MP + MEGA_PA + MEGA_IM) else "N"
            ws.cell(row=linha_atual, column=43, value=controle_estoque)
            ws.cell(row=linha_atual, column=53, value="S")
            ws.cell(row=linha_atual, column=100, value=material.mascara)

            linha_atual += 1

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"CADASTRO_DE_INSUMOS_{timestamp}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.error(f"Erro ao exportar materiais para Mega: {e}", exc_info=True)
        flash(f"Ocorreu um erro ao gerar o arquivo Excel para o Mega: {str(e)}", "danger")
        return redirect(url_for("material.index"))


