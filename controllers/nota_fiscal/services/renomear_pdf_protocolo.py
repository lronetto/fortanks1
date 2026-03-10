"""
Serviço para processar PDFs de protocolo: extrai chave de acesso, identifica
NotaFiscal e sugere nome do arquivo (baseado no script teste/renomear pdfs/main.py).
"""
import json
import re
from datetime import datetime, timedelta
from typing import Tuple

from models.nota_fiscal import NotaFiscal
from utils.utils import extrair_chave_do_pdf


def _tipo_label(tipo):
    """Retorna CTE, NF ou NFS conforme tipo da nota."""
    if tipo in (0, 1):
        return "NF"
    if tipo == 2:
        return "CTE"
    if tipo == 3:
        return "NFS"
    return "NF"


def _nome_arquivo_seguro(nome):
    """Remove caracteres inválidos para nome de arquivo e limita tamanho."""
    if not nome:
        return "emitente"
    s = re.sub(r'[<>:"/\\|?*]', "_", str(nome).strip())
    s = re.sub(r"\s+", " ", s).strip()
    return s[:80] if len(s) > 80 else s or "emitente"


def _nome_nota_fiscal(nota):
    """Monta o nome: TIPO numero_nf nome_emitente."""
    tipo_str = _tipo_label(nota.tipo)
    nome_safe = _nome_arquivo_seguro(nota.nome_emitente)
    return f"{tipo_str} {nota.numero_nf} {nome_safe}.pdf"


def _nome_por_nota_e_vencimento(nota, vencimento):
    """Monta o nome: dd-mm-aa TIPO numero_nf nome_emitente."""
    if hasattr(vencimento, "strftime"):
        dd_mm_aa = vencimento.strftime("%d-%m-%y")
    else:
        dd_mm_aa = vencimento
    return f"{dd_mm_aa} {_nome_nota_fiscal(nota)}"


def _obter_vencimento_dados_adicionais(nota):
    """Obtém vencimento de dados_adicionais (fatura ou faturamento)."""
    if not nota.dados_adicionais:
        return None
    try:
        dados = (
            json.loads(nota.dados_adicionais)
            if isinstance(nota.dados_adicionais, str)
            else nota.dados_adicionais
        )
        if not isinstance(dados, dict):
            return None
        for key in ("fatura", "faturamento"):
            fat = dados.get(key)
            if isinstance(fat, dict):
                venc = fat.get("vencimento")
                if venc:
                    return datetime.strptime(venc, "%Y-%m-%d")
    except (ValueError, TypeError, KeyError):
        pass
    return None


def processar_pdf_protocolo(
    payload: bytes, nome_original: str
) -> Tuple[str, int | None, bool]:
    """
    Processa um PDF de protocolo: extrai chave, busca NotaFiscal e sugere nome.

    Args:
        payload: bytes do PDF
        nome_original: nome original do arquivo (para fallback)

    Returns:
        Tupla (nome_sugerido, nota_id ou None, identificado).
        identificado=True quando a nota foi encontrada no banco.
    """
    if not payload or len(payload) < 100:
        return (nome_original if nome_original.endswith(".pdf") else f"{nome_original}.pdf", None, False)

    chave = extrair_chave_do_pdf(payload)
    if not chave:
        base = nome_original if nome_original.endswith(".pdf") else f"{nome_original}.pdf"
        return (base, None, False)

    nota = NotaFiscal.query.filter_by(chave_acesso=chave).first()
    if not nota:
        return (f"{chave}.pdf", None, False)

    vencimento = _obter_vencimento_dados_adicionais(nota) or nota.get_vencimento()
    if vencimento:
        if isinstance(vencimento, str) and len(vencimento) == 10:
            try:
                vencimento = datetime.strptime(vencimento, "%Y-%m-%d")
            except ValueError:
                vencimento = None
        if vencimento:
            nome_sugerido = _nome_por_nota_e_vencimento(nota, vencimento)
        else:
            nome_sugerido = _nome_nota_fiscal(nota)
    else:
        vencimento_fallback = (nota.data_emissao + timedelta(days=30)) if nota.data_emissao else None
        if vencimento_fallback:
            nome_sugerido = _nome_por_nota_e_vencimento(nota, vencimento_fallback)
        else:
            nome_sugerido = _nome_nota_fiscal(nota)

    if not nome_sugerido.endswith(".pdf"):
        nome_sugerido = f"{nome_sugerido}.pdf"
    return (nome_sugerido, nota.id, True)
