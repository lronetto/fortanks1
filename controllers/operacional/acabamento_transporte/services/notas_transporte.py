"""Consultas NF-e de venda (matriz) e CT-e ligados ao fluxo de transporte."""

from __future__ import annotations

import json

from sqlalchemy import func

from models.database import db
from models.nota_fiscal import CNPJS_MATRIZ, NotaFiscal, NotaFiscalItem
from models.tanque import Tanques, TanquesPecas, TanquesTransportes

from .pecas import numeros_nf_ja_usados_em_transporte


def buscar_notas_venda_matriz(q, tanque_id=None, peca_id=None):
    query = NotaFiscal.query.filter(
        NotaFiscal.tipo.in_([0, 1]),
        NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ),
        NotaFiscal.status_processamento != "cancelada",
    )

    if tanque_id:
        tanque = Tanques.query.get(tanque_id)
        if not tanque or tanque.item_nf is None:
            return []
        nf_ids_com_item = (
            db.session.query(NotaFiscalItem.nf_id)
            .filter(Tanques.sql_codigo_nf_igual_item_nf_valor(NotaFiscalItem.codigo, tanque.item_nf))
            .distinct()
        )
        query = query.filter(NotaFiscal.id.in_(nf_ids_com_item))

        usados = numeros_nf_ja_usados_em_transporte(excluir_peca_id=peca_id)
        if usados:
            query = query.filter(~NotaFiscal.numero_nf.in_(list(usados)))

    if q:
        termo = f"%{q}%"
        query = query.filter((NotaFiscal.numero_nf.ilike(termo)) | (NotaFiscal.chave_acesso.ilike(termo)))
    query = query.order_by(NotaFiscal.data_emissao.desc()).limit(30)
    notas = query.all()
    return [
        {
            "id": n.id,
            "numero_nf": str(n.numero_nf) if n.numero_nf is not None else "",
            "chave_acesso": n.chave_acesso or "",
            "valor_total": float(n.valor_total) if n.valor_total else 0,
            "data_emissao": n.data_emissao.strftime("%d/%m/%Y") if n.data_emissao else "",
            "nome_destinatario": (n.nome_destinatario or "")[:100],
        }
        for n in notas
    ]


def buscar_ctes_por_chave_nf(chave_nf):
    if not chave_nf or len(chave_nf) < 10:
        return []
    ctes = (
        NotaFiscal.query.filter(
            NotaFiscal.tipo == 2,
            NotaFiscal.status_processamento != "cancelada",
            func.json_unquote(func.json_extract(NotaFiscal.dados_adicionais, "$.chave_nf")) == chave_nf,
        )
        .order_by(NotaFiscal.data_emissao.desc())
        .all()
    )
    resultado = []
    for cte in ctes:
        dados = {}
        if cte.dados_adicionais:
            try:
                dados = json.loads(cte.dados_adicionais) if isinstance(cte.dados_adicionais, str) else cte.dados_adicionais
            except Exception:
                pass
        resultado.append(
            {
                "id": cte.id,
                "numero_nf": cte.numero_nf,
                "chave_acesso": cte.chave_acesso,
                "valor_total": float(cte.valor_total) if cte.valor_total else 0,
                "data_emissao": cte.data_emissao.strftime("%d/%m/%Y") if cte.data_emissao else "",
                "nome_emitente": cte.nome_emitente or "",
                "placa": (dados.get("placa") or "").strip(),
                "motorista": (dados.get("motorista") or "").strip(),
            }
        )
    return resultado


def buscar_transporte_registrado_por_nota(nota):
    if not nota:
        return None
    nota_s = str(nota).strip()
    nota_int = TanquesTransportes.parse_nota_int(nota)
    row = None
    if nota_int is not None:
        row = (
            TanquesTransportes.query.filter(TanquesTransportes.nota == nota_int)
            .order_by(TanquesTransportes.updated_at.desc())
            .first()
        )
    if row:
        dados = row.dados_adicionais_dict()
        dt = row.data_transporte
        return {
            "placa_carreta": dados.get("placa_carreta", ""),
            "transportadora": row.transportadora or "",
            "data_transporte": dt.strftime("%Y-%m-%d") if dt else "",
        }
    pecas = TanquesPecas.query.filter(TanquesPecas.qualidade.isnot(None)).all()
    for peca in pecas:
        try:
            q = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else (peca.qualidade or {})
        except (json.JSONDecodeError, TypeError):
            continue
        transporte = q.get("transporte")
        if transporte and str(transporte.get("nota", "")) == nota_s:
            return {
                "placa_carreta": transporte.get("placa_carreta", ""),
                "transportadora": transporte.get("transportadora", ""),
                "data_transporte": transporte.get("data_transporte", ""),
            }
    return None
