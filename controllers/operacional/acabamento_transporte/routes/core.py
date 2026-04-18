"""Página principal e modais de acabamento / transporte."""

from datetime import datetime

from flask import jsonify, render_template, request
from flask_wtf.csrf import generate_csrf

from .. import acabamento_transporte_bp
from ..services.registro import registrar_acabamento_em_lote, registrar_transporte_em_lote
from ..services.tanques_aux import tanques_ordenados_por_nome


@acabamento_transporte_bp.route("/")
def index():
    filtros = request.args.to_dict()
    tanques = tanques_ordenados_por_nome()
    filtro = filtros.get("filtro", "todos")
    nome_peca = filtros.get("nome_peca", "")
    tanque_id = filtros.get("tanque_id", "todos")
    inicio_acabamento = filtros.get("inicio_acabamento", "")
    termino_acabamento = filtros.get("termino_acabamento", "")
    inicio_transporte = filtros.get("inicio_transporte", "")
    termino_transporte = filtros.get("termino_transporte", "")
    return render_template(
        "operacional/acabamento_transporte/index.html",
        tanques=tanques,
        now=datetime.now().strftime("%Y-%m-%d"),
        filtro=filtro,
        nome_peca=nome_peca,
        tanque_id=tanque_id,
        inicio_acabamento=inicio_acabamento,
        termino_acabamento=termino_acabamento,
        inicio_transporte=inicio_transporte,
        termino_transporte=termino_transporte,
    )


@acabamento_transporte_bp.route("/acabamento", methods=["GET", "POST"])
def acabamento():
    """Registra acabamento de uma ou mais peças"""
    if request.method == "POST":
        tanque_id = request.form.get("acabamento-tanque_id")
        peca_ids = request.form.getlist("acabamento-peca_ids[]")
        data_acabamento = request.form.get("data_acabamento")
        try:
            payload, status = registrar_acabamento_em_lote(tanque_id, peca_ids, data_acabamento)
            return jsonify(payload), status
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    tanques = tanques_ordenados_por_nome()
    csrf_token = generate_csrf()
    return render_template(
        "operacional/acabamento_transporte/modais/acabamento.html",
        tanques=tanques,
        csrf_token=csrf_token,
        now=datetime.now().strftime("%Y-%m-%d"),
    )


@acabamento_transporte_bp.route("/transporte", methods=["GET", "POST"])
def transporte():
    """Registra transporte de peças"""
    if request.method == "POST":
        peca_ids = request.form.getlist("transporte-peca_ids[]")
        nota_fiscal = request.form.get("nota_fiscal")
        placa_carreta = request.form.get("placa_carreta")
        data_transporte = request.form.get("data_transporte")
        transportadora = request.form.get("transportadora")
        cte_frete = (request.form.get("cte_frete") or "").strip()
        observacao = request.form.get("observacao") or ""
        enviar_whatsapp = request.form.get("enviar_whatsapp") == "1"
        foto_transporte = request.files.get("foto_transporte")
        try:
            payload, status = registrar_transporte_em_lote(
                peca_ids,
                nota_fiscal,
                placa_carreta,
                data_transporte,
                transportadora,
                cte=cte_frete or None,
                observacao=observacao,
                enviar_whatsapp=enviar_whatsapp,
                foto_file=foto_transporte,
            )
            return jsonify(payload), status
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    tanques = tanques_ordenados_por_nome()
    csrf_token = generate_csrf()
    return render_template(
        "operacional/acabamento_transporte/modais/transporte.html",
        tanques=tanques,
        csrf_token=csrf_token,
        now=datetime.now().strftime("%Y-%m-%d"),
    )
