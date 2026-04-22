import logging
import os
import tempfile
import uuid
from datetime import datetime
from io import BytesIO

import pandas as pd
from flask import current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from sqlalchemy import or_

from models.database import db
from models.material import Materiais
from models.unidade import Unidades
from models.plano_conta import PlanoConta
from utils.utils import dump_dados_json, parse_dados_json

from .. import material_bp

logger = logging.getLogger(__name__)


@material_bp.route("/importar", methods=["GET"])
@login_required
def importar():
    """
    Renderiza a página de importação de materiais.
    Permite ao usuário fazer upload de um arquivo Excel para importação.
    """
    return render_template("materiais/importar.html")


@material_bp.route("/importar/upload", methods=["POST"])
@login_required
def upload_arquivo():
    if "arquivo" not in request.files:
        flash("Nenhum arquivo enviado", "danger")
        return redirect(url_for("material.importar"))

    arquivo = request.files["arquivo"]
    if arquivo.filename == "":
        flash("Nenhum arquivo selecionado", "danger")
        return redirect(url_for("material.importar"))

    if not arquivo.filename.endswith(".xlsx"):
        flash("Apenas arquivos Excel (.xlsx) são permitidos", "danger")
        return redirect(url_for("material.importar"))

    from_modal = request.referrer and "index" in request.referrer
    try:
        nome_arquivo = f"{uuid.uuid4().hex}.xlsx"
        caminho_temp = os.path.join(current_app.config["UPLOAD_FOLDER"], nome_arquivo)
        arquivo.save(caminho_temp)

        df = pd.read_excel(caminho_temp)
        if df.empty or len(df.columns) == 0:
            os.remove(caminho_temp)
            flash("O arquivo enviado está vazio ou não contém dados válidos", "danger")
            return redirect(url_for("material.index" if from_modal else "material.importar"))

        flash("Arquivo recebido com sucesso. Por favor, verifique o mapeamento das colunas.", "success")
        return redirect(url_for("material.selecionar_planilha", arquivo=nome_arquivo))
    except Exception as e:
        flash(f"Erro ao processar o arquivo: {str(e)}", "danger")
        return redirect(url_for("material.index" if from_modal else "material.importar"))


@material_bp.route("/importar/selecionar-planilha", methods=["GET"])
@login_required
def selecionar_planilha():
    try:
        temp_file = request.args.get("arquivo")
        planilha = request.args.get("planilha")

        caminho_completo = os.path.join(current_app.config["UPLOAD_FOLDER"], temp_file)
        if not temp_file or not os.path.isfile(caminho_completo):
            flash("Arquivo temporário não encontrado. Por favor, faça o upload novamente.", "danger")
            return redirect(url_for("material.importar"))

        xls = pd.ExcelFile(caminho_completo)
        planilhas = xls.sheet_names
        if planilha and planilha not in planilhas:
            flash(f"Planilha '{planilha}' não encontrada no arquivo.", "danger")
            planilha = planilhas[0]
        if not planilha:
            planilha = planilhas[0]

        df = pd.read_excel(caminho_completo, sheet_name=planilha)
        colunas = df.columns.tolist()
        preview_data = df.head(5).values.tolist()
        
        # Mapeamento automático de colunas com nomes iguais ou similares
        mapeamento_automatico = {}
        
        # Dicionário de mapeamento: campo_sistema -> possíveis_nomes_no_excel
        campos_mapeamento = {
            'col_id': ['id', 'ID', 'Id', 'codigo', 'Código', 'CÓDIGO', 'cod', 'COD'],
            'col_mascara': ['mascara', 'Máscara', 'MÁSCARA', 'masc', 'MASC'],
            'col_codigo_sox': ['codigo_sox', 'Código SOX', 'CÓDIGO SOX', 'codigo sox', 'Código Sox', 'sox', 'SOX'],
            'col_codigo_mega': ['codigo_mega', 'Código Mega', 'CÓDIGO MEGA', 'codigo mega', 'Código Mega', 'mega', 'MEGA'],
            'col_codigo_alterdata': ['codigo_alterdata', 'Código Alterdata', 'CÓDIGO ALTERDATA', 'codigo alterdata', 'Código Alterdata', 'alterdata', 'ALTERDATA'],
            'col_nome': ['nome', 'Nome', 'NOME', 'descricao', 'Descrição', 'DESCRIÇÃO', 'desc', 'DESC', 'material', 'Material', 'MATERIAL'],
            'col_categoria': ['categoria', 'Categoria', 'CATEGORIA', 'cat', 'CAT', 'tipo', 'Tipo', 'TIPO'],
            'col_plano_conta': ['plano_conta', 'Plano de Conta', 'PLANO DE CONTA', 'plano de conta', 'Plano Conta', 'conta', 'Conta', 'CONTA'],
            'col_unidade': ['unidade', 'Unidade', 'UNIDADE', 'und', 'UND', 'un', 'UN'],
            
            'col_ncm': ['ncm', 'NCM', 'Ncm'],
        }
        
        # Normalizar colunas do Excel (remover espaços, converter para minúsculo)
        colunas_normalizadas = {col.strip().lower(): col for col in colunas}
        
        # Fazer o mapeamento automático
        for campo, possiveis_nomes in campos_mapeamento.items():
            for nome_possivel in possiveis_nomes:
                nome_normalizado = nome_possivel.strip().lower()
                if nome_normalizado in colunas_normalizadas:
                    mapeamento_automatico[campo] = colunas_normalizadas[nome_normalizado]
                    break  # Usa a primeira correspondência encontrada

        return render_template(
            "materiais/mapear_colunas.html",
            temp_file=caminho_completo,
            colunas=colunas,
            planilhas=planilhas,
            planilha_atual=planilha,
            preview_data=preview_data,
            mapeamento_automatico=mapeamento_automatico,
        )
    except Exception as e:
        logger.error(f"Erro ao processar planilha: {str(e)}")
        flash(f"Erro ao processar a planilha: {str(e)}", "danger")
        return redirect(url_for("material.importar"))


@material_bp.route("/importar/confirmar", methods=["POST"])
@login_required
def confirmar_importacao():
    """
    Processa a importação de materiais a partir do arquivo Excel com mapeamento de colunas.
    """
    try:
        # Obter dados do formulário
        temp_file = request.form.get("temp_file")
        planilha = request.form.get("planilha", "")
        opcao_atualizacao = request.form.get("opcao_atualizacao") == "atualizar"
        
        # Obter mapeamento de colunas
        col_id = request.form.get("col_id", "").strip()
        col_nome = request.form.get("col_nome", "").strip()
        col_categoria = request.form.get("col_categoria", "").strip()
        col_codigo_sox = request.form.get("col_codigo_sox", "").strip()
        col_codigo_mega = request.form.get("col_codigo_mega", "").strip()
        col_codigo_alterdata = request.form.get("col_codigo_alterdata", "").strip()
        col_plano_conta = request.form.get("col_plano_conta", "").strip()
        col_unidade = request.form.get("col_unidade", "").strip()
        col_mascara = request.form.get("col_mascara", "").strip()
        col_ncm = request.form.get("col_ncm", "").strip()
        
        # Validar campos obrigatórios
        if not col_nome or not col_categoria:
            flash("Os campos Nome e Categoria são obrigatórios no mapeamento.", "danger")
            return redirect(url_for("material.importar"))
        
        # Validar arquivo temporário
        if not temp_file or not os.path.isfile(temp_file):
            flash("Arquivo temporário não encontrado. Por favor, faça o upload novamente.", "danger")
            return redirect(url_for("material.importar"))
        
        # Ler o arquivo Excel
        try:
            df = pd.read_excel(temp_file, sheet_name=planilha if planilha else 0)
            if df.empty:
                flash("O arquivo está vazio ou não contém dados válidos.", "danger")
                return redirect(url_for("material.importar"))
        except Exception as e:
            logger.error(f"Erro ao ler arquivo Excel: {str(e)}")
            flash(f"Erro ao ler o arquivo Excel: {str(e)}", "danger")
            return redirect(url_for("material.importar"))
        
        # Validar se as colunas mapeadas existem no arquivo
        colunas_arquivo = df.columns.tolist()
        colunas_obrigatorias = [col_nome, col_categoria]
        colunas_opcionais = [
            col
            for col in [
                col_id,
                col_codigo_sox,
                col_codigo_mega,
                col_codigo_alterdata,
                col_plano_conta,
                col_unidade,
                col_mascara,
                col_ncm,
            ]
            if col
        ]
        
        for col in colunas_obrigatorias + colunas_opcionais:
            if col and col not in colunas_arquivo:
                flash(f"A coluna '{col}' não foi encontrada no arquivo.", "danger")
                return redirect(url_for("material.importar"))
        
        # Processar importação
        resultados = {
            "inseridos": 0,
            "atualizados": 0,
            "erros": 0,
            "detalhes_erros": []
        }
        
        # Processar cada linha
        for idx, row in df.iterrows():
            linha_numero = idx + 2  # +2 porque começa em 0 e tem cabeçalho
            
            try:
                # Extrair valores das colunas mapeadas
                nome = str(row[col_nome]).strip() if pd.notna(row.get(col_nome)) else ""
                categoria = str(row[col_categoria]).strip() if pd.notna(row.get(col_categoria)) else ""
                
                # Validar campos obrigatórios
                if not nome or not categoria:
                    resultados["erros"] += 1
                    resultados["detalhes_erros"].append({
                        "linha": linha_numero,
                        "erro": "Nome ou Categoria vazios",
                        "dados": f"Nome: {nome}, Categoria: {categoria}"
                    })
                    continue
                
                # Extrair valores opcionais
                codigo = str(row[col_id]).strip() if col_id and pd.notna(row.get(col_id)) else None
                codigo_sox = str(row[col_codigo_sox]).strip() if col_codigo_sox and pd.notna(row.get(col_codigo_sox)) else None
                codigo_mega = str(row[col_codigo_mega]).strip() if col_codigo_mega and pd.notna(row.get(col_codigo_mega)) else None
                codigo_alterdata = str(row[col_codigo_alterdata]).strip() if col_codigo_alterdata and pd.notna(row.get(col_codigo_alterdata)) else None
                plano_conta_texto = str(row[col_plano_conta]).strip() if col_plano_conta and pd.notna(row.get(col_plano_conta)) else None
                unidade_nome = str(row[col_unidade]).strip() if col_unidade and pd.notna(row.get(col_unidade)) else None
                mascara = str(row[col_mascara]).strip() if col_mascara and pd.notna(row.get(col_mascara)) else None
                ncm = str(row[col_ncm]).strip() if col_ncm and pd.notna(row.get(col_ncm)) else None
                
                # Limpar valores "nan" ou "None"
                if codigo and codigo.lower() in ["nan", "none", ""]:
                    codigo = None
                if codigo_sox and codigo_sox.lower() in ["nan", "none", ""]:
                    codigo_sox = None
                if codigo_mega and codigo_mega.lower() in ["nan", "none", ""]:
                    codigo_mega = None
                if codigo_alterdata and codigo_alterdata.lower() in ["nan", "none", ""]:
                    codigo_alterdata = None
                if plano_conta_texto and plano_conta_texto.lower() in ["nan", "none", ""]:
                    plano_conta_texto = None
                if unidade_nome and unidade_nome.lower() in ["nan", "none", ""]:
                    unidade_nome = None
                if mascara and mascara.lower() in ["nan", "none", ""]:
                    mascara = None
                if ncm and ncm.lower() in ["nan", "none", ""]:
                    ncm = None
                
                # Buscar ou criar unidade
                unidade_id = None
                if unidade_nome:
                    unidade = Unidades.obter_por_nome(unidade_nome)
                    if not unidade:
                        # Tentar criar unidade se não existir
                        try:
                            unidade = Unidades(nome=unidade_nome.upper(), descricao=unidade_nome, ativo=True)
                            db.session.add(unidade)
                            db.session.flush()
                            unidade_id = unidade.id
                        except Exception as e:
                            logger.warning(f"Erro ao criar unidade '{unidade_nome}': {str(e)}")
                            unidade_id = None
                    else:
                        unidade_id = unidade.id
                
                # Buscar plano de conta
                plano_conta_id = None
                plano_conta_string = None
                if plano_conta_texto:
                    # Tentar buscar por descrição ou índice
                    plano_conta = PlanoConta.query.filter(
                        or_(
                            PlanoConta.descricao.ilike(f"%{plano_conta_texto}%"),
                            PlanoConta.indice.ilike(f"%{plano_conta_texto}%")
                        ),
                        PlanoConta.ativo == True
                    ).first()
                    
                    if plano_conta:
                        plano_conta_id = plano_conta.id
                    else:
                        # Se não encontrar, usar como string
                        plano_conta_string = plano_conta_texto
                
                # Verificar se material já existe (por código ou nome)
                material_existente = None
                # Coluna `codigo` foi removida do banco; mantém fallback por nome exato.
                material_existente = Materiais.query.filter_by(nome=nome).first()
                
                if material_existente:
                    if opcao_atualizacao:
                        # Atualizar material existente
                        material_existente.nome = nome
                        material_existente.categoria = categoria
                        if codigo_sox:
                            extras = parse_dados_json(material_existente.dados_adicionais)
                            extras["codigo_sox"] = codigo_sox
                            material_existente.dados_adicionais = dump_dados_json(extras) if extras else None
                        if codigo_mega:
                            extras = parse_dados_json(material_existente.dados_adicionais)
                            extras["codigo_mega"] = codigo_mega
                            material_existente.dados_adicionais = dump_dados_json(extras) if extras else None
                        if codigo_alterdata:
                            extras = parse_dados_json(material_existente.dados_adicionais)
                            extras["codigo_alterdata"] = codigo_alterdata
                            material_existente.dados_adicionais = dump_dados_json(extras) if extras else None
                        if plano_conta_id:
                            material_existente.plano_conta_id = plano_conta_id
                        if plano_conta_string:
                            material_existente.plano_conta = plano_conta_string
                        if unidade_id:
                            material_existente.unidade_id = unidade_id
                        if mascara:
                            material_existente.mascara = mascara
                        if ncm:
                            material_existente.ncm = ncm
                        
                        db.session.add(material_existente)
                        resultados["atualizados"] += 1
                    else:
                        # Ignorar material existente
                        continue
                else:
                    # Criar novo material
                    extras = parse_dados_json(None)
                    if codigo_sox:
                        extras["codigo_sox"] = codigo_sox
                    if codigo_mega:
                        extras["codigo_mega"] = codigo_mega
                    if codigo_alterdata:
                        extras["codigo_alterdata"] = codigo_alterdata
                    novo_material = Materiais(
                        nome=nome,
                        categoria=categoria,
                        plano_conta=plano_conta_string,
                        plano_conta_id=plano_conta_id,
                        unidade_id=unidade_id,
                        mascara=mascara,
                        ncm=ncm,
                        ativo=True
                    )
                    novo_material.dados_adicionais = dump_dados_json(extras) if extras else None
                    db.session.add(novo_material)
                    resultados["inseridos"] += 1
                
            except Exception as e:
                logger.error(f"Erro ao processar linha {linha_numero}: {str(e)}")
                resultados["erros"] += 1
                resultados["detalhes_erros"].append({
                    "linha": linha_numero,
                    "erro": str(e),
                    "dados": str(row.to_dict())
                })
        
        # Commit das alterações
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao salvar importação: {str(e)}")
            flash(f"Erro ao salvar os dados no banco: {str(e)}", "danger")
            return redirect(url_for("material.importar"))
        
        # Limpar arquivo temporário
        try:
            if os.path.isfile(temp_file):
                os.remove(temp_file)
        except Exception as e:
            logger.warning(f"Erro ao remover arquivo temporário: {str(e)}")
        
        # Preparar mensagem de sucesso
        mensagem = f"Importação concluída: {resultados['inseridos']} inseridos"
        if resultados["atualizados"] > 0:
            mensagem += f", {resultados['atualizados']} atualizados"
        if resultados["erros"] > 0:
            mensagem += f", {resultados['erros']} erros"
        
        if resultados["erros"] > 0:
            flash(mensagem, "warning")
        else:
            flash(mensagem, "success")
        
        # Retornar para página de importação com resultados
        return render_template(
            "materiais/importar.html",
            resultados=resultados
        )
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao processar importação: {str(e)}", exc_info=True)
        flash(f"Erro ao processar a importação: {str(e)}", "danger")
        return redirect(url_for("material.importar"))


@material_bp.route("/download-modelo")
@login_required
def download_modelo():
    """
    Gera um Excel modelo simples para importação.
    """
    try:
        temp_file = os.path.join(tempfile.gettempdir(), "modelo_importacao_materiais.xlsx")
        with pd.ExcelWriter(temp_file, engine="openpyxl") as writer:
            df_principal = pd.DataFrame(
                columns=[
                    "ID",
                    "Nome",
                    "Categoria",
                    "Código SOX",
                    "Código Mega",
                    "Código Alterdata",
                    "Plano de Conta",
                    "Unidade",
                    "Máscara",
                    "NCM",
                ]
            )
            df_principal.loc[0] = [
                "1",
                "Cimento Portland CP-II",
                "Matéria-prima",
                "SOX001",
                "MEGA001",
                "ALT001",
                "Material Direto",
                "sc",
                "123",
                "1234567890",
            ]
            df_principal.to_excel(writer, sheet_name="Materiais", index=False)
        return send_file(
            temp_file,
            as_attachment=True,
            download_name="modelo_importacao_materiais.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        logger.error(f"Erro ao gerar arquivo modelo: {str(e)}", exc_info=True)
        flash(f"Erro ao gerar arquivo modelo: {str(e)}", "danger")
        return redirect(url_for("material.index"))


