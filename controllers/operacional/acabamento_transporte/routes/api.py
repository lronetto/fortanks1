"""Endpoints JSON auxiliares (peças, tanques, NF-e, CT-e)."""

from flask import jsonify, request

from models.tanque import Tanques

from .. import acabamento_transporte_bp
from ..services.notas_transporte import (
    buscar_ctes_por_chave_nf,
    buscar_notas_venda_matriz,
    buscar_transporte_registrado_por_nota,
)
from ..services.pecas import get_pecas, serializar_pecas_para_api
from ..services.tanques_aux import listar_transportadoras_distintas


@acabamento_transporte_bp.route("/api/pecas", methods=["GET"])
def api_pecas():
    """Retorna peças filtradas por tanques e nome (AJAX)"""
    filtros = request.args.to_dict()
    pecas = get_pecas(filtros)
    return jsonify(serializar_pecas_para_api(pecas))


@acabamento_transporte_bp.route("/api/transportadoras", methods=["POST"])
def api_transportadoras():
    """Retorna transportadoras já utilizadas (AJAX)"""
    return jsonify(listar_transportadoras_distintas())


@acabamento_transporte_bp.route("/api/tanques", methods=["GET"])
def api_tanques():
    """Lista tanques (AJAX)"""
    tanques = Tanques.query.all()
    return jsonify([tanque.to_dict() for tanque in tanques])


@acabamento_transporte_bp.route("/api/notas-venda-matriz", methods=["GET"])
def api_notas_venda_matriz():
    """
    Busca notas fiscais de venda emitidas pela matriz (NFe tipo 0 ou 1, cnpj_emitente matriz).
    Parâmetro: q (texto para filtrar por número da NF ou chave). Se vazio, retorna as mais recentes.
    Opcional: tanque_id — restringe a NFs que possuem item com código igual ao item_nf do tanque.
    Opcional: peca_id — ao excluir NFs já usadas, ignora a própria peça (ex.: reabertura do modal).
    """
    q = (request.args.get("q") or "").strip()
    tanque_id = request.args.get("tanque_id", type=int)
    peca_id = request.args.get("peca_id", type=int)
    return jsonify(buscar_notas_venda_matriz(q, tanque_id=tanque_id, peca_id=peca_id))


@acabamento_transporte_bp.route("/api/cte-por-nota", methods=["GET"])
def api_cte_por_nota():
    """
    Busca CT-e (frete) vinculado à nota fiscal pela chave da NFe.
    Parâmetro: chave_nf (chave de 44 caracteres da NFe).
    """
    chave_nf = (request.args.get("chave_nf") or "").strip()
    return jsonify(buscar_ctes_por_chave_nf(chave_nf))


@acabamento_transporte_bp.route("/api/transporte-por-nota", methods=["GET"])
def api_transporte_por_nota():
    """
    Busca dados de transporte já registrados para uma nota fiscal.
    Retorna placa, transportadora e data caso a nota já tenha sido usada.
    """
    nota = (request.args.get("nota_fiscal") or "").strip()
    prev = buscar_transporte_registrado_por_nota(nota)
    return jsonify(prev)
