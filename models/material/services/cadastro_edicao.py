"""
Regras de cadastro e edição de material a partir de campos de formulário (HTTP-agnóstico).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from utils.parser import ToInt
from utils.utils import dump_dados_json, parse_dados_json

if TYPE_CHECKING:
    from ..entities.materiais import Materiais


def _resolver_unidade_id(unidade: Optional[str], unidade_texto: str) -> Optional[str]:
    u = (unidade or "").strip() if unidade is not None else ""
    if not u and (unidade_texto or "").strip():
        return unidade_texto.strip()
    return unidade if unidade else None


def _extras_codigos_criacao(codigo: str, codigo_alterdata: str, codigo_mega: str) -> Dict[str, Any]:
    extras: Dict[str, Any] = {}
    if codigo:
        extras["codigo_sox"] = codigo
    if codigo_alterdata:
        extras["codigo_alterdata"] = codigo_alterdata
    if codigo_mega:
        extras["codigo_mega"] = codigo_mega
        extras["cod_mega"] = codigo_mega
    return extras


def _extras_codigos_edicao(
    extras: Dict[str, Any],
    codigo: Optional[str],
    codigo_alterdata: Optional[str],
    codigo_mega: Optional[str],
) -> Dict[str, Any]:
    out = dict(extras)
    if codigo:
        out["codigo_sox"] = codigo
    else:
        out.pop("codigo_sox", None)
    if codigo_alterdata:
        out["codigo_alterdata"] = codigo_alterdata
    else:
        out.pop("codigo_alterdata", None)
    if codigo_mega:
        out["codigo_mega"] = codigo_mega
        out["cod_mega"] = codigo_mega
    else:
        out.pop("codigo_mega", None)
        out.pop("cod_mega", None)
    return out


def construir_material_novo(
    *,
    nome: Optional[str],
    descricao: Optional[str],
    categoria: Optional[str],
    plano_conta: Optional[str],
    unidade: Optional[str],
    unidade_texto: str = "",
    mascara_raw: Optional[str],
    formula_calculo: str = "",
    codigo_raw: Optional[str],
    codigo_alterdata_raw: Optional[str] = None,
    codigo_erp_raw: Optional[str] = None,
    codigo_mega_raw: Optional[str],
) -> "Materiais":
    """Valida campos, monta `dados_adicionais` e instância **sem** persistir."""
    from ..entities.materiais import Materiais

    nome = (nome or "").strip()
    categoria = (categoria or "").strip()
    if not nome or not categoria:
        raise ValueError("Nome e categoria são campos obrigatórios!")

    codigo = ToInt(codigo_raw)
    codigo_alterdata = ToInt(codigo_alterdata_raw or codigo_erp_raw)
    codigo_mega = ToInt(codigo_mega_raw)
    mascara = ToInt(mascara_raw)

    unidade_resolvida = _resolver_unidade_id(unidade, unidade_texto)
    unidade_id = unidade_resolvida if unidade_resolvida not in ("", None) else None

    extras = _extras_codigos_criacao(codigo, codigo_alterdata, codigo_mega)
    dados_adicionais = dump_dados_json(extras) if extras else None

    formula = (formula_calculo or "").strip()

    return Materiais(
        nome=nome.upper(),
        descricao=descricao,
        categoria=categoria,
        plano_conta=plano_conta,
        unidade_id=unidade_id,
        mascara=ToInt(mascara),
        formula_calculo=formula if formula else None,
        dados_adicionais=dados_adicionais,
    )


def aplicar_edicao_formulario(
    material: "Materiais",
    *,
    nome: str,
    descricao: Optional[str],
    categoria: str,
    plano_conta: Optional[str],
    unidade: Optional[str],
    mascara_raw: Optional[str],
    formula_calculo: str = "",
    codigo_raw: Optional[str],
    codigo_alterdata_raw: Optional[str] = None,
    codigo_erp_raw: Optional[str] = None,
    codigo_mega_raw: Optional[str] = None,
) -> None:
    """Atribui campos e `dados_adicionais` ao material já carregado; não faz commit."""
    nome = (nome or "").strip()
    categoria = (categoria or "").strip()
    if not nome or not categoria:
        raise ValueError("Nome e categoria são campos obrigatórios!")

    codigo = ToInt(codigo_raw)
    codigo_alterdata = ToInt(codigo_alterdata_raw or codigo_erp_raw)
    codigo_mega = ToInt(codigo_mega_raw)
    m_txt = ToInt(mascara_raw)

    material.nome = nome.upper()
    material.descricao = descricao
    material.categoria = categoria
    material.plano_conta = plano_conta
    material.unidade_id = unidade if (unidade not in ("", None)) else None
    if not m_txt:
        material.mascara = None
    else:
        try:
            material.mascara = int(float(str(m_txt).replace(",", ".")))
        except (TypeError, ValueError):
            material.mascara = None

    formula = (formula_calculo or "").strip()
    material.formula_calculo = formula if formula else None

    extras = parse_dados_json(material.dados_adicionais)
    extras = _extras_codigos_edicao(extras, codigo, codigo_alterdata, codigo_mega)
    material.dados_adicionais = dump_dados_json(extras) if extras else None
