import io
import os
from datetime import datetime

import pandas as pd
from flask import jsonify, render_template, request, send_file
from weasyprint import CSS, HTML

from . import acabamento_pecas_bp
from .services import (
    agrupar_por_mes,
    agrupar_por_semana,
    agrupar_por_semana_por_pista,
    calcular_total_metros_placas,
    get_dados_acabamento,
    listar_tanques_json,
    listar_tanques_para_filtro,
    montar_dados_grafico_semana,
    obter_contratos_ativos,
    obter_nomes_filtros,
    parse_periodo,
)


@acabamento_pecas_bp.route("/")
def index():
    data_inicio_padrao, data_fim_padrao = parse_periodo(usar_padrao=True)
    data_inicio_str = request.args.get("data_inicio", data_inicio_padrao.strftime("%Y-%m-%d"))
    data_fim_str = request.args.get("data_fim", data_fim_padrao.strftime("%Y-%m-%d"))
    tanque_id = request.args.get("tanque_id", type=int)
    contrato_id = request.args.get("contrato_id", type=int)

    data_inicio, data_fim = parse_periodo(data_inicio_str, data_fim_str, usar_padrao=True)

    dados = get_dados_acabamento(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
    )
    dados_semana, pistas = agrupar_por_semana_por_pista(dados)
    labels_semana, dados_por_pista, medias_diarias_por_pista = montar_dados_grafico_semana(dados_semana, pistas)
    total_metros_placas = calcular_total_metros_placas(dados)

    tanques = listar_tanques_para_filtro(contrato_id=contrato_id)
    contratos = obter_contratos_ativos()

    return render_template(
        "relatorios/acabamento_pecas/index.html",
        dados_semana=dados_semana,
        labels_semana=labels_semana,
        dados_por_pista=dados_por_pista,
        medias_diarias_por_pista=medias_diarias_por_pista,
        pistas=pistas,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
        tanques=tanques,
        contratos=contratos,
        total_pecas=len(dados),
        total_metros_placas=round(total_metros_placas, 2),
    )


@acabamento_pecas_bp.route("/api/tanques-por-projeto")
def api_tanques_por_projeto():
    contrato_id = request.args.get("contrato_id", type=int)
    return jsonify({"tanques": listar_tanques_json(contrato_id=contrato_id)})


@acabamento_pecas_bp.route("/api/dados")
def api_dados():
    data_inicio_str = request.args.get("data_inicio")
    data_fim_str = request.args.get("data_fim")
    tanque_id = request.args.get("tanque_id", type=int)
    contrato_id = request.args.get("contrato_id", type=int)

    data_inicio, data_fim = parse_periodo(data_inicio_str, data_fim_str)
    dados = get_dados_acabamento(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
    )
    dados_semana, pistas = agrupar_por_semana_por_pista(dados)
    labels_semana, dados_por_pista, medias_diarias_por_pista = montar_dados_grafico_semana(dados_semana, pistas)
    total_metros_placas = calcular_total_metros_placas(dados)

    return jsonify(
        {
            "semana": {
                "labels": labels_semana,
                "pistas": pistas,
                "dados_por_pista": dados_por_pista,
                "medias_diarias_por_pista": medias_diarias_por_pista,
            },
            "total": len(dados),
            "total_metros_placas": round(total_metros_placas, 2),
            "data_inicio": data_inicio_str,
            "data_fim": data_fim_str,
        }
    )


@acabamento_pecas_bp.route("/exportar_excel")
def exportar_excel():
    data_inicio_str = request.args.get("data_inicio")
    data_fim_str = request.args.get("data_fim")
    tanque_id = request.args.get("tanque_id", type=int)
    contrato_id = request.args.get("contrato_id", type=int)

    data_inicio, data_fim = parse_periodo(data_inicio_str, data_fim_str)
    dados = get_dados_acabamento(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
    )
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)

    excel_data = []
    for item in dados:
        excel_data.append(
            {
                "Data Acabamento": item["data_acabamento"].strftime("%d/%m/%Y"),
                "Projeto": item.get("contrato_nome", ""),
                "Tanque": item["tanque_nome"],
                "Peça": item["nome"],
                "Número Sequencial": item["numero_sequencial"],
                "Tipo": item["tipo"],
                "Data Concretagem": item["data_concretagem"].strftime("%d/%m/%Y") if item["data_concretagem"] else "",
            }
        )
    df_detalhes = pd.DataFrame(excel_data)

    resumo_mes = []
    for valor in dados_mes.values():
        resumo_mes.append(
            {
                "Mês/Ano": f"{valor['mes']:02d}/{valor['ano']}",
                "Quantidade": valor["quantidade"],
                "Metros de Placas": round(valor.get("metros_placas", 0), 2),
            }
        )
    df_mes = pd.DataFrame(resumo_mes)

    resumo_semana = []
    for valor in dados_semana.values():
        resumo_semana.append(
            {
                "Semana": f"Sem {valor['semana']}/{valor['ano']}",
                "Início": valor["inicio_semana"].strftime("%d/%m/%Y"),
                "Fim": valor["fim_semana"].strftime("%d/%m/%Y"),
                "Quantidade": valor["quantidade"],
                "Metros de Placas": round(valor.get("metros_placas", 0), 2),
            }
        )
    df_semana = pd.DataFrame(resumo_semana)

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        df_detalhes.to_excel(writer, index=False, sheet_name="Detalhamento")
        df_mes.to_excel(writer, index=False, sheet_name="Resumo Mensal")
        df_semana.to_excel(writer, index=False, sheet_name="Resumo Semanal")

    excel_buffer.seek(0)
    nome_arquivo = f"relatorio_acabamento_pecas_{data_inicio_str or 'todos'}_{data_fim_str or 'todos'}.xlsx"

    return send_file(
        excel_buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nome_arquivo,
    )


@acabamento_pecas_bp.route("/exportar_pdf")
def exportar_pdf():
    data_inicio_str = request.args.get("data_inicio")
    data_fim_str = request.args.get("data_fim")
    tanque_id = request.args.get("tanque_id", type=int)
    contrato_id = request.args.get("contrato_id", type=int)

    data_inicio, data_fim = parse_periodo(data_inicio_str, data_fim_str)
    dados = get_dados_acabamento(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_id=tanque_id,
        contrato_id=contrato_id,
    )
    dados_mes = agrupar_por_mes(dados)
    dados_semana = agrupar_por_semana(dados)
    tanque_nome, projeto_nome = obter_nomes_filtros(tanque_id=tanque_id, contrato_id=contrato_id)
    total_metros_placas = calcular_total_metros_placas(dados)

    logo_path = os.path.abspath(os.path.join("static", "img", "logo.png"))
    logo_path_uri = "file:///" + logo_path.replace("\\", "/")

    html = render_template(
        "relatorios/acabamento_pecas/pdf.html",
        dados=dados,
        dados_mes=dados_mes,
        dados_semana=dados_semana,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tanque_nome=tanque_nome,
        projeto_nome=projeto_nome,
        total_pecas=len(dados),
        total_metros_placas=round(total_metros_placas, 2),
        logo_path=logo_path_uri,
        data_geracao=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    )

    pdf_bytes = HTML(string=html).write_pdf(
        stylesheets=[
            CSS(
                string="""
            @page {
                margin: 2cm;
                size: A4;
            }
            body {
                font-family: Arial, sans-serif;
                font-size: 10pt;
                color: #333;
            }
            .header {
                text-align: center;
                margin-bottom: 20px;
                border-bottom: 2px solid #3a72ab;
                padding-bottom: 10px;
            }
            .logo {
                max-width: 150px;
            }
            .section {
                margin-bottom: 20px;
            }
            .section-title {
                background-color: #3a72ab;
                color: white;
                padding: 8px;
                margin-bottom: 10px;
                font-weight: bold;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 15px;
                font-size: 9pt;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 6px;
                text-align: left;
            }
            th {
                background-color: #f5f5f5;
                font-weight: bold;
            }
            .total-row {
                font-weight: bold;
                background-color: #f8f9fa;
            }
            .footer {
                text-align: center;
                margin-top: 30px;
                font-size: 8pt;
                color: #666;
            }
            """
            )
        ]
    )

    pdf_io = io.BytesIO(pdf_bytes)
    pdf_io.seek(0)
    nome_arquivo = f"relatorio_acabamento_pecas_{data_inicio_str or 'todos'}_{data_fim_str or 'todos'}.pdf"

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome_arquivo,
    )

