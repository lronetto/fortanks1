import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.database import db
from models.estoque import Estoque
from models.material import Materiais
from models.produto_composto import ProdutoComposto

logger = logging.getLogger(__name__)


def resolver_estoque_id_para_componente(estoque_id_raw, usuario_id: Optional[int] = None) -> int:
    """
    Resolve o identificador vindo do Select2:
    - "123" / 123   -> estoque_id (int) existente
    - "material:45" -> cria/busca Estoque(tipo_item='material') e retorna estoque_id (int)
    """
    if estoque_id_raw is None:
        raise ValueError("estoque_id não informado")

    estoque_id_txt = str(estoque_id_raw).strip()
    if estoque_id_txt.startswith("material:"):
        material_id_txt = estoque_id_txt.split("material:", 1)[1].strip()
        if not material_id_txt.isdigit():
            raise ValueError("material_id inválido no estoque_id")
        material_id = int(material_id_txt)

        material = Materiais.query.get_or_404(material_id)
        estoque = Estoque.query.filter_by(material_id=material.id, tipo_item="material").first()
        if not estoque:
            estoque = Estoque(
                material_id=material.id,
                tipo_item="material",
                quantidade=0,
                localizacao="Estoque Matriz",
                usuario_id=usuario_id,
            )
            db.session.add(estoque)
            db.session.flush()
        return int(estoque.id)

    if not estoque_id_txt.isdigit():
        raise ValueError("estoque_id inválido")
    return int(estoque_id_txt)


def sanitizar_nome_aba_excel(nome: str) -> str:
    """
    Sanitiza o nome para ser usado como nome de aba no Excel.
    Remove caracteres inválidos e limita o tamanho.
    """
    nome = (nome or "").strip().strip("'").strip('"')
    nome = re.sub(r"[\[\]:*?/\\]", "", nome)
    if len(nome) > 31:
        nome = nome[:28] + "..."
    if not nome or nome.strip() == "":
        nome = "Produto"
    return nome


def expandir_componentes_produto_composto(
    produto_id: int,
    quantidade_base: float = 1.0,
    caminho_atual: Optional[List[int]] = None,
    data_movimento: Any = None,
) -> List[Dict[str, Any]]:
    """
    Função recursiva para expandir todos os componentes de um produto composto
    até chegar apenas em materiais, considerando produtos compostos aninhados.
    Usa caminho_atual para evitar loops infinitos (mesmo produto na mesma cadeia).
    Considera datas de início e término dos componentes se data_movimento for fornecida.
    """
    if caminho_atual is None:
        caminho_atual = []

    if produto_id in caminho_atual:
        logger.warning(f"Loop detectado no produto composto {produto_id}. Caminho: {caminho_atual}")
        return []

    novo_caminho = caminho_atual + [produto_id]

    produto = ProdutoComposto.query.get(produto_id)
    if not produto:
        return []

    from datetime import date as date_type

    if data_movimento is None:
        data_movimento_norm = None
    elif isinstance(data_movimento, datetime):
        data_movimento_norm = data_movimento.date()
    elif isinstance(data_movimento, str):
        try:
            data_movimento_norm = datetime.strptime(data_movimento, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            data_movimento_norm = None
    elif isinstance(data_movimento, date_type):
        data_movimento_norm = data_movimento
    else:
        data_movimento_norm = None

    componentes_materiais: List[Dict[str, Any]] = []

    for componente in produto.componentes:
        if not componente.estoque:
            continue

        if componente.dados_adicionais and data_movimento_norm:
            try:
                dados_adicionais = json.loads(componente.dados_adicionais)
                datainicio = dados_adicionais.get("data_inicio")
                if datainicio:
                    if isinstance(datainicio, str):
                        datainicio = datetime.strptime(datainicio, "%Y-%m-%d").date()
                    elif isinstance(datainicio, datetime):
                        datainicio = datainicio.date()
                    elif isinstance(datainicio, date_type):
                        pass
                    else:
                        datainicio = None
                    if datainicio and datainicio > data_movimento_norm:
                        continue

                datatermino = dados_adicionais.get("data_termino")
                if datatermino:
                    if isinstance(datatermino, str):
                        datatermino = datetime.strptime(datatermino, "%Y-%m-%d").date()
                    elif isinstance(datatermino, datetime):
                        datatermino = datatermino.date()
                    elif isinstance(datatermino, date_type):
                        pass
                    else:
                        datatermino = None
                    if datatermino and datatermino <= data_movimento_norm:
                        continue
            except (ValueError, TypeError) as e:
                logger.warning(f"Erro ao processar datas do componente {componente.id}: {str(e)}")

        quantidade_componente = float(componente.quantidade) * float(quantidade_base)

        if componente.estoque.tipo_item == "material" and componente.estoque.material:
            componentes_materiais.append(
                {
                    "material_id": componente.estoque.material.id,
                    "material_nome": componente.estoque.material.nome,
                    "quantidade": quantidade_componente,
                    "unidade": componente.estoque.material.unidade_obj.nome
                    if (componente.estoque.material.unidade_obj and hasattr(componente.estoque.material.unidade_obj, "nome"))
                    else "",
                }
            )
            continue

        if componente.estoque.tipo_item == "produto_composto" and componente.estoque.ProdComp_id:
            produto_composto_id = componente.estoque.ProdComp_id
            componentes_aninhados = expandir_componentes_produto_composto(
                produto_composto_id,
                quantidade_componente,
                novo_caminho,
                data_movimento_norm,
            )
            componentes_materiais.extend(componentes_aninhados)

    return componentes_materiais

