"""Consultas auxiliares de tanques e transportadoras."""

from __future__ import annotations

import json

from models.tanque import Tanques, TanquesPecas


def tanques_ordenados_por_nome():
    return Tanques.query.order_by(Tanques.nome).all()


def listar_transportadoras_distintas():
    pecas = TanquesPecas.query.all()
    transportadoras = []
    for p in pecas:
        qualidade = p.qualidade or "{}"
        qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
        if "transporte" in qualidade_dict and "transportadora" in qualidade_dict["transporte"]:
            transportadoras.append(qualidade_dict["transporte"]["transportadora"])
    return list(set(transportadoras))
