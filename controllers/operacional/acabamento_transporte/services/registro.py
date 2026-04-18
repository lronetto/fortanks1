"""Persistência de acabamento e transporte no JSON qualidade das peças."""

from __future__ import annotations

import json
from datetime import datetime

from models.concreto import qualidade_peca_remover_data_producao_de_dados_adicionais
from models.database import db
from models.tanque import TanquesPecas, TanquesTransportes
from utils.transporte_foto_upload import salvar_foto_transporte


def registrar_acabamento_em_lote(tanque_id, peca_ids, data_acabamento):
    """
    Grava data de acabamento em qualidade das peças do tanque.
    Retorna (payload dict, status_http).
    """
    if not data_acabamento:
        data_acabamento = datetime.now().strftime("%Y-%m-%d")
    pecas = TanquesPecas.query.filter(TanquesPecas.id.in_(peca_ids), TanquesPecas.tanque_id == tanque_id).all()
    if not pecas:
        return {"success": False, "message": "Nenhuma peça encontrada"}, 404
    for peca in pecas:
        qualidade = peca.qualidade or "{}"
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        qualidade_dict["acabamento"] = data_acabamento
        qualidade_peca_remover_data_producao_de_dados_adicionais(qualidade_dict)
        peca.qualidade = json.dumps(qualidade_dict)
        peca.save()
    return {"success": True, "pecas_afetadas": [p.id for p in pecas]}, 200


def registrar_transporte_em_lote(
    peca_ids,
    nota_fiscal,
    placa_carreta,
    data_transporte,
    transportadora,
    cte=None,
    *,
    observacao=None,
    enviar_whatsapp=False,
    foto_file=None,
):
    """Atualiza transporte em qualidade + data_entrega e grava registro em TanquesTransportes."""
    if not data_transporte:
        data_transporte = datetime.now().strftime("%Y-%m-%d")
    pecas = TanquesPecas.query.filter(TanquesPecas.id.in_(peca_ids)).all()
    ids_afetadas = []
    for peca in pecas:
        qualidade = peca.qualidade or "{}"
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        nota_gravacao = TanquesTransportes.parse_nota_int(nota_fiscal)
        qualidade_dict["transporte"] = {
            "data_transporte": data_transporte,
            "nota": nota_gravacao if nota_gravacao is not None else nota_fiscal,
            "placa_carreta": placa_carreta,
            "transportadora": transportadora,
        }
        qualidade_peca_remover_data_producao_de_dados_adicionais(qualidade_dict)
        peca.qualidade = json.dumps(qualidade_dict)
        peca.data_entrega = data_transporte
        peca.save()
        ids_afetadas.append(peca.id)

    obs_txt = (observacao or "").strip()
    dados_adicionais = {
        "placa_carreta": placa_carreta or "",
        "observacao": obs_txt,
        "enviar_whatsapp": bool(enviar_whatsapp),
    }
    if cte:
        dados_adicionais["cte"] = str(cte).strip()

    registro = TanquesTransportes(
        nota=TanquesTransportes.parse_nota_int(nota_fiscal),
        cte=str(cte).strip() if cte else None,
        transportadora=(transportadora or "").strip() or None,
        data_transporte=TanquesTransportes.parse_data_transporte(data_transporte),
        dados_adicionais=json.dumps(dados_adicionais, ensure_ascii=False),
    )
    registro.definir_pecas_ids(ids_afetadas)
    db.session.add(registro)
    db.session.commit()

    upload_id = None
    if foto_file is not None and getattr(foto_file, "filename", None):
        upload_id = salvar_foto_transporte(registro.id, foto_file)
        if upload_id:
            merged = registro.dados_adicionais_dict()
            merged["foto_upload_id"] = upload_id
            registro.dados_adicionais = json.dumps(merged, ensure_ascii=False)
            db.session.commit()

    return {"success": True, "pecas_afetadas": ids_afetadas, "transporte_id": registro.id}, 200
