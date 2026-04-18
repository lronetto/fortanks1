"""Listagem e filtros de peças (qualidade JSON acabamento/transporte)."""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime

from sqlalchemy import func

from models.concreto import montar_mapa_pista_por_peca
from models.tanque import Tanques, TanquesPecas, TanquesTransportes

# Substituições em expressão SQL (lower já aplicado) — alinhadas ao efeito de normalizar_texto_busca para PT/Latin.
_MAP_ACENTOS_NOME_SQL = (
    ("á", "a"),
    ("à", "a"),
    ("â", "a"),
    ("ã", "a"),
    ("ä", "a"),
    ("å", "a"),
    ("ā", "a"),
    ("ă", "a"),
    ("ą", "a"),
    ("é", "e"),
    ("è", "e"),
    ("ê", "e"),
    ("ë", "e"),
    ("ē", "e"),
    ("ĕ", "e"),
    ("ė", "e"),
    ("ę", "e"),
    ("ě", "e"),
    ("í", "i"),
    ("ì", "i"),
    ("î", "i"),
    ("ï", "i"),
    ("ī", "i"),
    ("ĭ", "i"),
    ("į", "i"),
    ("ó", "o"),
    ("ò", "o"),
    ("ô", "o"),
    ("õ", "o"),
    ("ö", "o"),
    ("ō", "o"),
    ("ŏ", "o"),
    ("ő", "o"),
    ("ú", "u"),
    ("ù", "u"),
    ("û", "u"),
    ("ü", "u"),
    ("ū", "u"),
    ("ŭ", "u"),
    ("ů", "u"),
    ("ű", "u"),
    ("ý", "y"),
    ("ÿ", "y"),
    ("ñ", "n"),
    ("ç", "c"),
)


def normalizar_texto_busca(texto):
    """NFKD + remove marcas combinantes + minúsculas + espaços internos colapsados."""
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


def _expr_sql_nome_normalizado(coluna):
    """Nome em minúsculas sem acentos (aproximação MySQL compatível com normalizar_texto_busca)."""
    x = func.lower(coluna)
    for antigo, novo in _MAP_ACENTOS_NOME_SQL:
        x = func.replace(x, antigo, novo)
    return x


def _escape_like_mysql(valor):
    """Evita que % e _ do usuário funcionem como curingas no LIKE."""
    return valor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\")


def parse_data_filtro(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    texto = str(valor).strip()
    if not texto:
        return None
    if "T" in texto:
        texto = texto.split("T", 1)[0]
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def numeros_nf_ja_usados_em_transporte(excluir_peca_id=None):
    """Números de NF já usados em transporte (tabela TanquesTransportes + legado em qualidade JSON)."""
    usados = set()
    for row in TanquesTransportes.query.filter(TanquesTransportes.nota.isnot(None)):
        try:
            ids = row.pecas_ids()
        except (TypeError, ValueError):
            ids = []
        outros = [i for i in ids if i != excluir_peca_id]
        if excluir_peca_id is not None and excluir_peca_id in ids and len(outros) == 0:
            continue
        if row.nota is not None:
            # NotaFiscal.numero_nf é String — comparar com o mesmo formato.
            usados.add(str(row.nota))
    qry = TanquesPecas.query.filter(TanquesPecas.qualidade.isnot(None))
    if excluir_peca_id is not None:
        qry = qry.filter(TanquesPecas.id != excluir_peca_id)
    for peca in qry.all():
        try:
            q = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else (peca.qualidade or {})
        except (json.JSONDecodeError, TypeError):
            continue
        transporte = q.get("transporte") or {}
        if not isinstance(transporte, dict):
            continue
        nota = transporte.get("nota")
        if nota is None or str(nota).strip() in ("", "null"):
            continue
        usados.add(str(nota).strip())
    return usados


def _tanque_ids_do_filtro_api(filtros):
    """Lista de int (vários tanques), ex.: query `tanque_ids=1,2` do modal Select2."""
    raw = filtros.get("tanque_ids")
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        seq = raw
    else:
        seq = str(raw).split(",")
    out = []
    for x in seq:
        s = str(x).strip()
        if not s:
            continue
        try:
            out.append(int(s))
        except ValueError:
            continue
    return out


def get_pecas(filtros):
    filtro = filtros.get("filtro", "todos")
    nome_norm = normalizar_texto_busca(filtros.get("nome_peca") or filtros.get("nome") or "")
    tanque_id = filtros.get("tanque_id", "todos")
    inicio_acabamento = parse_data_filtro(filtros.get("inicio_acabamento"))
    termino_acabamento = parse_data_filtro(filtros.get("termino_acabamento"))
    inicio_transporte = parse_data_filtro(filtros.get("inicio_transporte"))
    termino_transporte = parse_data_filtro(filtros.get("termino_transporte"))
    pecas_query = TanquesPecas.query.join(Tanques)
    if nome_norm:
        pat = f"%{_escape_like_mysql(nome_norm)}%"
        pecas_query = pecas_query.filter(
            _expr_sql_nome_normalizado(TanquesPecas.nome).like(pat, escape="\\")
        )
    ids_varios = _tanque_ids_do_filtro_api(filtros)
    if ids_varios:
        pecas_query = pecas_query.filter(TanquesPecas.tanque_id.in_(ids_varios))
    elif tanque_id and str(tanque_id) != "todos":
        try:
            tanque_id_int = int(tanque_id)
            pecas_query = pecas_query.filter(TanquesPecas.tanque_id == tanque_id_int)
        except (TypeError, ValueError):
            pass
    if str(filtros.get("apenas_acabadas", "")).strip().lower() in ("1", "true", "yes"):
        pecas_query = pecas_query.filter(
            TanquesPecas.qualidade.isnot(None),
            func.json_extract(TanquesPecas.qualidade, "$.acabamento").isnot(None),
        )
    if filtro == "acabadas":
        pecas_query = pecas_query.filter(
            TanquesPecas.qualidade.isnot(None),
            func.json_extract(TanquesPecas.qualidade, "$.acabamento").isnot(None),
        )
    elif filtro == "transportadas":
        pecas_query = pecas_query.filter(
            TanquesPecas.qualidade.isnot(None),
            func.json_extract(TanquesPecas.qualidade, "$.transporte.data_transporte").notin_(None, "null", "None"),
        )
    elif filtro == "acabada_nao_transportada":
        pecas_query = pecas_query.filter(
            TanquesPecas.qualidade.isnot(None),
            func.json_extract(TanquesPecas.qualidade, "$.acabamento").isnot(None),
            func.json_extract(TanquesPecas.qualidade, "$.transporte.data_transporte").in_(None, "null", "None"),
        )
    pecas_query = pecas_query.all()
    pista_por_peca = montar_mapa_pista_por_peca(pecas_query)
    pecas = []
    for peca in pecas_query:
        qualidade = peca.qualidade or "{}"
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        if "acabamento" in qualidade_dict:
            peca.acabamento = qualidade_dict["acabamento"]
        else:
            peca.acabamento = None
        if "transporte" in qualidade_dict and "data_transporte" in qualidade_dict["transporte"]:
            peca.transporte = qualidade_dict["transporte"]["data_transporte"]
        else:
            peca.transporte = None
        if "transporte" in qualidade_dict and "transportadora" in qualidade_dict["transporte"]:
            peca.transportadora = qualidade_dict["transporte"]["transportadora"]
        else:
            peca.transportadora = None
        if "transporte" in qualidade_dict and "placa_carreta" in qualidade_dict["transporte"]:
            peca.placa_carreta = qualidade_dict["transporte"]["placa_carreta"]
        else:
            peca.placa_carreta = None
        if "transporte" in qualidade_dict and "nota" in qualidade_dict["transporte"]:
            peca.nota_fiscal = qualidade_dict["transporte"]["nota"]
        else:
            peca.nota_fiscal = None
        peca.pista = pista_por_peca.get(peca.id)

        data_acabamento_peca = parse_data_filtro(peca.acabamento)
        data_transporte_peca = parse_data_filtro(peca.transporte)

        if inicio_acabamento and (not data_acabamento_peca or data_acabamento_peca < inicio_acabamento):
            continue
        if termino_acabamento and (not data_acabamento_peca or data_acabamento_peca > termino_acabamento):
            continue
        if inicio_transporte and (not data_transporte_peca or data_transporte_peca < inicio_transporte):
            continue
        if termino_transporte and (not data_transporte_peca or data_transporte_peca > termino_transporte):
            continue

        pecas.append(peca)

    return pecas


def serializar_pecas_para_api(pecas):
    """Lista de dicts para Select2 / JSON (TanquesPecas não é serializável direto)."""
    saida = []
    for p in pecas:
        tanque = getattr(p, "tanque", None)
        saida.append(
            {
                "id": p.id,
                "nome": p.nome or "",
                "numero_sequencial": p.numero_sequencial,
                "tanque_id": p.tanque_id,
                "tanque_nome": tanque.nome if tanque else "",
            }
        )
    return saida
