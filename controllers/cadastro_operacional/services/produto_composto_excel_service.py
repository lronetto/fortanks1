import logging
import os
import tempfile
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Tuple

import pandas as pd

from models.database import db
from models.estoque import Estoque
from models.material import Materiais
from models.produto_composto import ProdutoComposto, ProdutoCompostoItem
from utils.material_imagem_upload import parse_dados_json

from controllers.cadastro_operacional.services.produto_composto_componentes_service import (
    expandir_componentes_produto_composto,
    sanitizar_nome_aba_excel,
)

logger = logging.getLogger(__name__)


def exportar_produtos_compostos_para_excel(produtos: List[ProdutoComposto]) -> Tuple[BytesIO, str]:
    """
    Exporta uma lista de produtos compostos para um Excel (BytesIO).
    Retorna (arquivo_em_memoria, filename_sugerido).
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for produto in produtos:
            dados_componentes = []
            for componente in produto.componentes:
                estoque = componente.estoque
                if not estoque:
                    continue

                qtd_componente = float(componente.quantidade or 0)
                if estoque.material_id and estoque.material:
                    material = estoque.material
                    extras = parse_dados_json(material.dados_adicionais)
                    dados_componentes.append(
                        {
                            "ID Sfortanks": estoque.id,
                            "Tipo": "Material",
                            "Nome": material.nome,
                            "Código Alterdata": extras.get("codigo_alterdata") or "",
                            "Quantidade": qtd_componente,
                            "Unidade": material.unidade_obj.nome
                            if (material.unidade_obj and hasattr(material.unidade_obj, "nome"))
                            else "",
                        }
                    )
                    continue

                if estoque.tipo_item == "produto_composto" and estoque.ProdComp_id and estoque.produto_composto:
                    dados_componentes.append(
                        {
                            "ID Sfortanks": estoque.id,
                            "Tipo": "Produto Composto",
                            "Nome": estoque.produto_composto.nome,
                            "Código Alterdata": "",
                            "Quantidade": qtd_componente,
                            "Unidade": "",
                        }
                    )

                    materiais_expandidos = expandir_componentes_produto_composto(
                        estoque.ProdComp_id,
                        quantidade_base=qtd_componente,
                        caminho_atual=[produto.id],
                        data_movimento=None,
                    )
                    for mat in materiais_expandidos:
                        material_obj = Materiais.query.get(mat["material_id"])
                        extras = parse_dados_json(material_obj.dados_adicionais) if material_obj else {}
                        dados_componentes.append(
                            {
                                "ID Sfortanks": f"material:{mat['material_id']}",
                                "Tipo": "↳ Material",
                                "Nome": f"    {mat['material_nome']}",
                                "Código Alterdata": (extras.get("codigo_alterdata") if material_obj else ""),
                                "Quantidade": float(mat["quantidade"] or 0),
                                "Unidade": mat.get("unidade") or "",
                            }
                        )
                    continue

                dados_componentes.append(
                    {
                        "ID Sfortanks": estoque.id,
                        "Tipo": "Desconhecido",
                        "Nome": "Desconhecido",
                        "Código Alterdata": "",
                        "Quantidade": qtd_componente,
                        "Unidade": "",
                    }
                )

            dados_componentes.sort(key=lambda x: (x.get("Nome") or "").lower())
            if dados_componentes:
                df = pd.DataFrame(dados_componentes)
            else:
                df = pd.DataFrame(columns=["ID Sfortanks", "Tipo", "Nome", "Código Alterdata", "Quantidade", "Unidade"])

            nome_aba = sanitizar_nome_aba_excel(produto.nome)
            df.to_excel(writer, sheet_name=nome_aba, index=False)

            worksheet = writer.sheets[nome_aba]
            worksheet.set_column("A:A", 14)
            worksheet.set_column("B:B", 18)
            worksheet.set_column("C:C", 44)
            worksheet.set_column("D:D", 18)
            worksheet.set_column("E:E", 12)
            worksheet.set_column("F:F", 10)

    output.seek(0)
    data_export = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"produtos_compostos_{data_export}.xlsx"
    return output, filename


def salvar_upload_excel_temporario(file_storage) -> str:
    """Salva `werkzeug.FileStorage` em caminho temporário e retorna o path."""
    temp_dir = tempfile.gettempdir()
    filename = getattr(file_storage, "filename", "") or "import.xlsx"
    safe_name = os.path.basename(filename)
    temp_path = os.path.join(temp_dir, f"import_produtos_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}")
    file_storage.save(temp_path)
    return temp_path


def importar_produtos_compostos_de_excel(temp_path: str, sobrescrever: bool) -> Dict:
    """
    Importa produtos compostos de um arquivo Excel no caminho `temp_path`.
    Retorna estatísticas (criados/atualizados/erros + erros_detalhes).
    """
    excel_file = pd.ExcelFile(temp_path)

    contador_criados = 0
    contador_atualizados = 0
    contador_erros = 0
    erros_detalhes: List[str] = []

    for nome_aba in excel_file.sheet_names:
        try:
            df = pd.read_excel(excel_file, sheet_name=nome_aba)

            col_nome = None
            col_quantidade = None
            col_id_estoque = None
            col_material_produto = None

            for col in df.columns:
                col_lower = str(col).lower()
                if "nome" in col_lower and not col_nome:
                    col_nome = col
                elif "quantidade" in col_lower and not col_quantidade:
                    col_quantidade = col
                elif "id" in col_lower and "estoque" in col_lower and not col_id_estoque:
                    col_id_estoque = col
                elif ("material" in col_lower or "produto" in col_lower) and not col_material_produto:
                    col_material_produto = col

            nome_produto = (nome_aba or "").strip()
            if col_nome and not df[col_nome].empty:
                nomes_validos = df[col_nome].dropna()
                if not nomes_validos.empty:
                    nome_produto = str(nomes_validos.iloc[0]).strip()

            if not nome_produto:
                erros_detalhes.append(f"Aba '{nome_aba}': Nome do produto não encontrado")
                contador_erros += 1
                continue

            produto = ProdutoComposto.query.filter_by(nome=nome_produto).first()

            if produto and sobrescrever:
                for componente in produto.componentes:
                    db.session.delete(componente)
                db.session.flush()
            elif not produto:
                produto = ProdutoComposto(nome=nome_produto, status="Ativo")
                db.session.add(produto)
                db.session.flush()

                estoque_produto = Estoque(
                    produto_composto=produto,
                    quantidade=0,
                    tipo_item="produto_composto",
                    localizacao="Estoque Matriz",
                )
                db.session.add(estoque_produto)
                db.session.flush()
                contador_criados += 1
            else:
                contador_atualizados += 1

            if col_quantidade:
                for index, row in df.iterrows():
                    try:
                        quantidade = float(row[col_quantidade]) if pd.notna(row[col_quantidade]) else None
                        if quantidade is None or quantidade <= 0:
                            continue

                        estoque_id = None

                        if col_id_estoque and col_id_estoque in df.columns:
                            estoque_id_val = row[col_id_estoque]
                            if pd.notna(estoque_id_val):
                                try:
                                    estoque_id = int(estoque_id_val)
                                except Exception:
                                    estoque_id = None

                        if not estoque_id and col_material_produto and col_material_produto in df.columns:
                            nome_item = str(row[col_material_produto]).strip() if pd.notna(row[col_material_produto]) else None
                            if nome_item:
                                material = Materiais.query.filter_by(nome=nome_item).first()
                                if material:
                                    estoque = Estoque.query.filter_by(material_id=material.id, tipo_item="material").first()
                                    if estoque:
                                        estoque_id = estoque.id

                                if not estoque_id:
                                    produto_comp = ProdutoComposto.query.filter_by(nome=nome_item).first()
                                    if produto_comp:
                                        estoque = Estoque.query.filter_by(
                                            ProdComp_id=produto_comp.id, tipo_item="produto_composto"
                                        ).first()
                                        if estoque:
                                            estoque_id = estoque.id

                        if not estoque_id:
                            erros_detalhes.append(
                                f"Aba '{nome_aba}', linha {index+2}: Não foi possível identificar o estoque/material"
                            )
                            continue

                        estoque = Estoque.query.get(estoque_id)
                        if not estoque:
                            erros_detalhes.append(f"Aba '{nome_aba}', linha {index+2}: Estoque ID {estoque_id} não encontrado")
                            continue

                        observacao = None
                        col_obs = None
                        if "Observação" in df.columns:
                            col_obs = "Observação"
                        elif "observacao" in df.columns:
                            col_obs = "observacao"
                        if col_obs and pd.notna(row[col_obs]):
                            observacao = str(row[col_obs]).strip()

                        produto.adicionar_item(estoque, quantidade)

                        if observacao:
                            componente = ProdutoCompostoItem.query.filter_by(
                                produto_id=produto.id,
                                estoque_id=estoque_id,
                            ).first()
                            if componente:
                                componente.observacao = observacao
                    except Exception as e:
                        erros_detalhes.append(f"Aba '{nome_aba}', linha {index+2}: {str(e)}")
                        contador_erros += 1
                        continue

            db.session.commit()
        except Exception as e:
            logger.error(f"Erro ao processar aba '{nome_aba}': {str(e)}", exc_info=True)
            erros_detalhes.append(f"Aba '{nome_aba}': {str(e)}")
            contador_erros += 1
            db.session.rollback()
            continue

    return {
        "success": True,
        "criados": contador_criados,
        "atualizados": contador_atualizados,
        "erros": contador_erros,
        "erros_detalhes": erros_detalhes[:10],
    }

