import json

from flask import Blueprint, render_template, request, send_file, jsonify
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict
from flask_login import current_user, login_required
from flask_wtf.csrf import validate_csrf
from decimal import Decimal

import pandas as pd
from models.centro_custo import CentroCusto
from models.tanque import Tanques
from models.contrato import Contrato
from models.nota_fiscal import NotaFiscal, NotaFiscalItem, CFOPS_VENDA
from models.dados_analiticos import DadoAnalitico
from models.plano_conta import PlanoConta
from sqlalchemy import func, and_
from models.database import db
from weasyprint import HTML, CSS
from controllers.nota_fiscal.services.query_notas import api_get_dados_notas_fiscais
import os
import tempfile
import io
import zipfile
import base64
from models.upload import Upload
import time

notas_bp = Blueprint('relatorios_notas', __name__, url_prefix='/relatorios/notas')


def _extrair_pagamento_manual_de_texto(dados_adicionais_text):
    """Lê dados_adicionais (JSON) e retorna (indicado: bool, dict pagamento_manual ou None)."""
    if not dados_adicionais_text:
        return False, None
    try:
        da = (
            json.loads(dados_adicionais_text)
            if isinstance(dados_adicionais_text, str)
            else dados_adicionais_text
        )
    except (json.JSONDecodeError, TypeError):
        return False, None
    if not isinstance(da, dict):
        return False, None
    pm = da.get("pagamento_manual")
    if not isinstance(pm, dict):
        return False, None
    ind = pm.get("indicado")
    if ind in (True, 1, "1", "true", "True"):
        return True, pm
    return False, pm


def _label_pago_manual(pm_info):
    if not pm_info:
        return "Pago (manual)"
    di = pm_info.get("data_indicacao")
    if not di:
        return "Pago (manual)"
    try:
        s = str(di)
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt.strftime("%d/%m/%Y") + " (manual)"
        return s + " (manual)"
    except (ValueError, TypeError):
        return "Pago (manual)"


def login_required_decorator(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function



def _processar_notas_fiscais(query):
    """
    Processa a query de notas fiscais e retorna lista de dicionários no formato esperado.
    A query já retorna:
    - pagamento_column: data de pagamento (datetime.date) ou NULL
    - centro_custo_column: ID do centro de custo ou NULL
    """
    # Executar query e obter IDs das notas
    # Resultado da query: (NotaFiscal, pagamento_column, centro_custo_column, upload_column, ...)
    from sqlalchemy.orm import defer
    from models.nota_fiscal import NotaFiscal
    query = query.options(defer(NotaFiscal.xml_data))
    resultados = query.all()
    nf_ids = [resultado[0].id for resultado in resultados]
    
    if not nf_ids:
        return []


    # Separar notas de material (tipo 0, 1) e notas de serviço (tipo 3)
    notas_material_ids = [nf.id for nf in [r[0] for r in resultados] if nf.tipo in [0, 1]]
    notas_servico_ids = [nf.id for nf in [r[0] for r in resultados] if nf.tipo == 3]
    
    # Notas de material: para cada item da NF, se existir tanque do projeto com
    # codigo do item = item_nf do tanque, soma a quantidade do item (uma vez por item).
    nf_items_dict = {}
    if notas_material_ids:
        soma_por_nf = defaultdict(float)
        primeiro_vinculo_por_nf = {}
        itens_ja_somados = set()

        linhas_vinculo = (
            db.session.query(NotaFiscalItem, Tanques, Contrato)
            .join(
                Tanques,
                Tanques.sql_codigo_nf_igual_item_nf_colunas(
                    NotaFiscalItem.codigo, Tanques.item_nf
                ),
            )
            .join(Contrato, Contrato.id == Tanques.contrato_id)
            .filter(NotaFiscalItem.nf_id.in_(notas_material_ids))
            .all()
        )
        for item, tanque, contrato in linhas_vinculo:
            if item.id in itens_ja_somados:
                continue
            itens_ja_somados.add(item.id)
            try:
                qtd = float(item.quantidade or 0)
            except (TypeError, ValueError):
                qtd = 0.0
            soma_por_nf[item.nf_id] += qtd
            if item.nf_id not in primeiro_vinculo_por_nf:
                primeiro_vinculo_por_nf[item.nf_id] = (tanque, contrato)

        # Passo 2: itens ainda sem vínculo — mesmo critério usado em Tanques (codigo contém item_nf)
        itens_restantes_q = db.session.query(NotaFiscalItem).filter(
            NotaFiscalItem.nf_id.in_(notas_material_ids),
            NotaFiscalItem.codigo.isnot(None),
        )
        if itens_ja_somados:
            itens_restantes_q = itens_restantes_q.filter(
                NotaFiscalItem.id.notin_(list(itens_ja_somados))
            )
        tanques_projeto = (
            db.session.query(Tanques, Contrato)
            .join(Contrato, Contrato.id == Tanques.contrato_id)
            .filter(Tanques.item_nf.isnot(None))
            .all()
        )
        for item in itens_restantes_q.all():
            codigo = str(item.codigo).strip()
            if not codigo:
                continue
            for tanque, contrato in tanques_projeto:
                chave = str(tanque.item_nf).strip()
                if not chave:
                    continue
                if chave not in codigo:
                    continue
                try:
                    qtd = float(item.quantidade or 0)
                except (TypeError, ValueError):
                    qtd = 0.0
                soma_por_nf[item.nf_id] += qtd
                itens_ja_somados.add(item.id)
                if item.nf_id not in primeiro_vinculo_por_nf:
                    primeiro_vinculo_por_nf[item.nf_id] = (tanque, contrato)
                break

        for nf_id, total_qtd in soma_por_nf.items():
            tanque, contrato = primeiro_vinculo_por_nf.get(nf_id, (None, None))
            nf_items_dict[nf_id] = {
                'tanque': tanque,
                'contrato': contrato,
                'quantidade': total_qtd,
            }
    
    # Buscar todos os contratos que têm cnpjs_associados (usado para serviço e material por CNPJ)
    contratos_com_cnpjs = db.session.query(Contrato)\
        .filter(Contrato.conf.isnot(None))\
        .all()
    
    # Buscar contratos associados para notas de serviço (tipo 3) via CNPJs (emitente ou destinatário)
    nf_servico_contratos_dict = {}
    if notas_servico_ids:
        notas_servico = {nf.id: nf for nf in [r[0] for r in resultados] if nf.tipo == 3}
        for nf_id, nf in notas_servico.items():
            for contrato in contratos_com_cnpjs:
                if contrato.conf:
                    try:
                        conf_data = json.loads(contrato.conf) if isinstance(contrato.conf, str) else contrato.conf
                        cnpjs_associados = conf_data.get('cnpjs_associados', [])
                        if isinstance(cnpjs_associados, str):
                            cnpjs_associados = json.loads(cnpjs_associados)
                        if (nf.cnpj_emitente in cnpjs_associados or nf.cnpj_destinatario in cnpjs_associados):
                            nf_servico_contratos_dict[nf_id] = contrato
                            break
                    except (json.JSONDecodeError, TypeError):
                        continue
    
    # Buscar contratos para notas de material (tipo 0, 1) associadas apenas por CNPJ
    # Apenas destinatário: cnpj_destinatario deve estar em cnpjs_associados
    nf_material_contratos_dict = {}
    notas_material_sem_itens = [nf.id for nf in [r[0] for r in resultados] if nf.tipo in [0, 1] and nf.id not in nf_items_dict]
    for nf_id in notas_material_sem_itens:
        nf = next((r[0] for r in resultados if r[0].id == nf_id), None)
        if not nf:
            continue
        for contrato in contratos_com_cnpjs:
            if contrato.conf:
                try:
                    conf_data = json.loads(contrato.conf) if isinstance(contrato.conf, str) else contrato.conf
                    cnpjs_associados = conf_data.get('cnpjs_associados', [])
                    if isinstance(cnpjs_associados, str):
                        cnpjs_associados = json.loads(cnpjs_associados)
                    if nf.cnpj_destinatario in cnpjs_associados:
                        nf_material_contratos_dict[nf_id] = contrato
                        break
                except (json.JSONDecodeError, TypeError):
                    continue
    # Buscar todos os centros de custo de uma vez (otimização)
    centro_custo_ids_unicos = set()
    for resultado in resultados:
        centro_custo_id = resultado[2]  # centro_custo_column
        if centro_custo_id:
            centro_custo_ids_unicos.add(centro_custo_id)
    
    centros_custo_dict = {}
    if centro_custo_ids_unicos:
        centros_custo_query = db.session.query(CentroCusto)\
            .filter(CentroCusto.id.in_(list(centro_custo_ids_unicos)))\
            .all()
        for cc in centros_custo_query:
            centros_custo_dict[cc.id] = cc.nome
      
    # Processar resultados
    dados_relatorio = []
    nf_processadas = set()  # Para evitar duplicatas
    
    for resultado in resultados:
        nf = resultado[0]  # NotaFiscal
        data_pagamento = resultado[1]  # pagamento_column (data de pagamento ou NULL)
        centro_custo_id = resultado[2]  # centro_custo_column (ID do centro de custo ou NULL)
        centro_custo_codigo = 'Não definido'
        # Evitar processar a mesma NF múltiplas vezes
        if nf.id in nf_processadas:
            continue
        nf_processadas.add(nf.id)
        
        # Obter dados relacionados
        # Para notas de material: via itens -> tanques -> contrato OU via cnpj_destinatario em cnpjs_associados
        # Para notas de serviço: via CNPJs associados (emitente ou destinatário)
        if nf.tipo == 3:
            contrato = nf_servico_contratos_dict.get(nf.id)
            tanque = None
            quantidade = 0  # Notas de serviço não têm quantidade de placas
        else:
            # Nota de material: primeiro por itens, depois por CNPJ destinatário
            nf_data = nf_items_dict.get(nf.id, {})
            tanque = nf_data.get('tanque')
            contrato = nf_data.get('contrato') or nf_material_contratos_dict.get(nf.id)
            quantidade = nf_data.get('quantidade', 0)
        
        # Centro de custo: do contrato se houver, senão do resultado da query
        if contrato:
            centro_custo_codigo = contrato.centro_custo.codigo if contrato.centro_custo else 'Não definido'
        elif centro_custo_id and centro_custo_id in centros_custo_dict:
            centro_custo_codigo = centros_custo_dict[centro_custo_id]
        
        # Calcular data prevista
        data_prevista = None
        if contrato:
            if nf.tipo == 3:
                if contrato.prazo_pagamento_ser:
                    data_prevista = nf.data_emissao + timedelta(days=contrato.prazo_pagamento_ser)
            else:
                # Para notas de material (com ou sem tanque), usar prazo_pagamento_mat
                if contrato.prazo_pagamento_mat:
                    data_prevista = nf.data_emissao + timedelta(days=contrato.prazo_pagamento_mat)
        
        pm_indicado, pm_info = _extrair_pagamento_manual_de_texto(
            nf.dados_adicionais
        )

        # Usar data_pagamento diretamente da coluna; senão indicação manual em dados_adicionais
        pago_str = 'Não'
        if data_pagamento:
            if isinstance(data_pagamento, datetime):
                pago_str = data_pagamento.strftime('%d/%m/%Y')
            elif hasattr(data_pagamento, 'strftime'):
                pago_str = data_pagamento.strftime('%d/%m/%Y')
            else:
                # Se for string ou outro formato, tentar converter
                try:
                    if isinstance(data_pagamento, str):
                        data_pagamento_dt = datetime.strptime(data_pagamento, '%Y-%m-%d')
                        pago_str = data_pagamento_dt.strftime('%d/%m/%Y')
                    else:
                        pago_str = str(data_pagamento)
                except Exception:
                    pago_str = str(data_pagamento) if data_pagamento else 'Não'
        elif pm_indicado:
            pago_str = _label_pago_manual(pm_info)

        if nf.vencimento and nf.vencimento != 'null':
            data_prevista = datetime.strptime(nf.vencimento, '%Y-%m-%d').strftime('%d/%m/%Y')
        else:
            data_prevista = data_prevista.strftime('%d/%m/%Y') if data_prevista else 'Não definido'
        dados_relatorio.append({
            'id': nf.id,
            'data': nf.data_emissao.strftime('%d/%m/%Y'),
            'centro_custo': centro_custo_codigo,
            'nf': nf.numero_nf,
            'valor': float(Decimal(nf.valor_total)),  # Converter Decimal para float para JSON
            'quantidade': quantidade,
            'data_prevista': data_prevista,
            'pago': pago_str,
            'status': nf.status_processamento,
            'destinatario': nf.nome_destinatario,
            'tipo_nf': nf.tipo,  # Adicionar tipo da nota para separar material e serviço
            'pagamento_manual_indicado': pm_indicado,
        })
    
    return dados_relatorio

@notas_bp.route('/', methods=['GET'])
@login_required_decorator
def index():
    """Página principal do relatório de notas fiscais"""
    centros_custo = CentroCusto.query.order_by(CentroCusto.codigo).all()
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]
    
    # Criar um objeto request mock para api_get_dados_notas_fiscais
    #mock_request = _criar_mock_request(data_inicio, data_fim, centro_custo_ids_int if centro_custo_ids_int else None)
    #query = api_get_dados_notas_fiscais(mock_request)
    
    #dados_relatorio = _processar_notas_fiscais(query)
    
    return render_template(
        'relatorios/notas/index.html',
        #relatorio=dados_relatori,
        centros_custo=centros_custo
    )

@notas_bp.route('/api/dados', methods=['GET'])
@login_required_decorator
def api_dados():
    """Endpoint AJAX para buscar dados do relatório"""
    print(f'request.args: {request.args}')
    data_inicio = request.args.get('data_inicio', None)
    data_fim = request.args.get('data_fim', None)
    
    # Tentar getlist primeiro (para múltiplos valores)
    centro_custo_ids = request.args.getlist('centro_custo', [])
    # Se getlist retornar vazio, tentar get (para um único valor)
    if not centro_custo_ids:
        centro_custo_single = request.args.get('centro_custo', None)
        if centro_custo_single:
            centro_custo_ids = [centro_custo_single]
    status_pagamento = request.args.get('status_pagamento', None)
    tipo_nota = request.args.get('tipo_nota', None)

    
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]
    
    # Converter filtro tipo_nota para tipo_nfe
    tipo_nfe = '4'
    if tipo_nota == 'material':
        tipo_nfe = '0'  # Tipo 0 ou 1 (NFE)
    elif tipo_nota == 'servico':
        tipo_nfe = '3'  # Tipo 3 (NFSe)
    # Se tipo_nota for vazio ou None, tipo_nfe permanece None (inclui todos)
    
    print(f'centro_custo_ids: {centro_custo_ids}')
    json_request = {
        'data_emissao_inicio': data_inicio,
        'data_emissao_fim': data_fim,
        'centro_custo_ids': centro_custo_ids_int,
        'status_pagamento': status_pagamento,
        #'plano_conta_id': 44,
        'emitente': 'Matriz',
        'pagamento_5percent': True,
        'tipo_nfe': tipo_nfe  # Filtro de tipo de nota (None = todos, '0' = material, '3' = serviço)
    }
    print(f'json_request: {json_request}')
    query = api_get_dados_notas_fiscais(json_request)
   
    
    dados_relatorio = _processar_notas_fiscais(query)
    print(f'dados_relatorio: {dados_relatorio}')
    # Calcular totais por categoria
    total_valor = sum([d['valor'] if d['status'] != 'cancelada' else 0 for d in dados_relatorio])
    total_quantidade = sum([d['quantidade'] if d['status'] != 'cancelada' else 0 for d in dados_relatorio])
    
    # Calcular quantidade total de placas dos contratos (material)
    query_placas = db.session.query(
        func.sum((Tanques.placas_normais + Tanques.placas_fecho) * Tanques.quantidade)
    ).join(Contrato, Contrato.id == Tanques.contrato_id)
    
    if centro_custo_ids_int:
        query_placas = query_placas.filter(Contrato.centro_custo_id.in_(centro_custo_ids_int))
    
    total_placas_contratos = query_placas.scalar() or 0
    
    # Calcular valores faturados (emitidos) - inclui material e serviço
    valor_faturado = sum([d['valor'] if d['status'] != 'cancelada' else 0 for d in dados_relatorio])
    
    # Calcular valores recebidos (pagos)
    valor_recebido = sum([
        d['valor'] for d in dados_relatorio
        if d['pago'] != 'Não' and d['pago'] != 'Não definido' and d['status'] != 'cancelada'
    ])
    
    # Calcular quantidades de placas recebidas (pagos)
    quantidade_recebida = sum([
        d['quantidade'] for d in dados_relatorio
        if d['pago'] != 'Não' and d['pago'] != 'Não definido' and d['status'] != 'cancelada'
    ])
    
    # Buscar valores dos contratos separados por material e serviço
    query_contratos_total = db.session.query(func.sum(Contrato.valor_total))
    query_contratos_mat = db.session.query(func.sum(Contrato.valor_mat))
    query_contratos_ser = db.session.query(func.sum(Contrato.valor_ser))
    
    if centro_custo_ids_int:
        query_contratos_total = query_contratos_total.filter(Contrato.centro_custo_id.in_(centro_custo_ids_int))
        query_contratos_mat = query_contratos_mat.filter(Contrato.centro_custo_id.in_(centro_custo_ids_int))
        query_contratos_ser = query_contratos_ser.filter(Contrato.centro_custo_id.in_(centro_custo_ids_int))
    
    valor_total_contratos = float(query_contratos_total.scalar()) or 0
    valor_total_material = float(query_contratos_mat.scalar()) or 0
    valor_total_servico = float(query_contratos_ser.scalar()) or 0
    
    # Separar valores de material e serviço das notas fiscais
    valor_material_faturado = sum([
        d['valor'] for d in dados_relatorio
        if d['status'] != 'cancelada' and d.get('tipo_nf', None) in [0, 1]
    ])
    valor_servico_faturado = sum([
        d['valor'] for d in dados_relatorio
        if d['status'] != 'cancelada' and d.get('tipo_nf', None) == 3
    ])
    
    # Se não houver tipo_nf no dicionário (compatibilidade), usar valor_faturado como material
    if valor_material_faturado == 0 and valor_servico_faturado == 0:
        valor_material_faturado = float(valor_faturado)
        valor_servico_faturado = 0

    # Placas já faturadas (apenas NFE material), para "a faturar" = contrato − faturado
    quantidade_material_faturada = sum([
        d['quantidade'] for d in dados_relatorio
        
    ])
    print(f'quantidade_material_faturada: {quantidade_material_faturada}')
    valor_material_recebido = sum([
        d['valor'] for d in dados_relatorio
        if d['pago'] != 'Não' and d['pago'] != 'Não definido' and d['status'] != 'cancelada'
        and d.get('tipo_nf', None) in [0, 1]
    ])
    quantidade_material_recebida = sum([
        d['quantidade'] for d in dados_relatorio
        if d['pago'] != 'Não' and d['pago'] != 'Não definido' and d['status'] != 'cancelada'
        and d.get('tipo_nf', None) in [0, 1]
    ])
    print(f'quantidade_material_recebida: {quantidade_material_recebida}')
    # Calcular valores ainda não faturados
    valor_material_nao_faturado = float(valor_total_material) - float(valor_material_faturado)
    valor_servico_nao_faturado = float(valor_total_servico) - float(valor_servico_faturado)
    
    # Calcular quantidades de placas não faturadas (contrato − placas já faturadas em NFE)
    quantidade_material_nao_faturada = float(total_placas_contratos) - float(quantidade_material_faturada)

    # A faturar (valor e quantidade) = total do contrato − já faturado
    valor_material_a_faturar = float(valor_material_nao_faturado)
    quantidade_material_a_faturar = float(quantidade_material_nao_faturada)
    
    # Calcular percentuais para material
    percentual_material_faturado = (valor_material_faturado / valor_total_material * 100) if valor_total_material > 0 else 0
    percentual_material_recebido = (valor_material_recebido / valor_total_material * 100) if valor_total_material > 0 else 0
    percentual_material_a_faturar = (
        (valor_material_a_faturar / valor_total_material * 100) if valor_total_material > 0 else 0
    )
    percentual_material_nao_faturado = (valor_material_nao_faturado / valor_total_material * 100) if valor_total_material > 0 else 0
    
    # Calcular percentuais para serviço
    percentual_servico_faturado = (valor_servico_faturado / valor_total_servico * 100) if valor_total_servico > 0 else 0
    valor_servico_recebido = sum([
        d['valor'] for d in dados_relatorio
        if d['pago'] != 'Não' and d['pago'] != 'Não definido' and d['status'] != 'cancelada' and d.get('tipo_nf', None) == 3
    ])
    valor_servico_a_receber = float(valor_servico_faturado) - float(valor_servico_recebido)
    percentual_servico_recebido = (valor_servico_recebido / valor_total_servico * 100) if valor_total_servico > 0 else 0
    # A faturar serviço = valor contrato serviço − NFSe já emitidas
    valor_servico_a_faturar = float(valor_servico_nao_faturado)
    percentual_servico_a_faturar = (
        (valor_servico_a_faturar / valor_total_servico * 100) if valor_total_servico > 0 else 0
    )
    percentual_servico_a_receber = (
        (valor_servico_a_receber / valor_total_servico * 100) if valor_total_servico > 0 else 0
    )
    percentual_servico_nao_faturado = (valor_servico_nao_faturado / valor_total_servico * 100) if valor_total_servico > 0 else 0

    # Material: a receber (faturado e ainda não pago)
    valor_material_a_receber = float(valor_material_faturado) - float(valor_material_recebido)
    quantidade_material_a_receber = sum([
        d['quantidade'] for d in dados_relatorio
        if d['status'] != 'cancelada' and d.get('tipo_nf', None) in [0, 1]
        and (d['pago'] == 'Não' or d['pago'] == 'Não definido')
    ])
    percentual_material_a_receber = (
        (valor_material_a_receber / valor_total_material * 100) if valor_total_material > 0 else 0
    )
    
    dados_relatorio_aux = {
        'valor_total_material': valor_total_material,
        'total_placas_contratos': total_placas_contratos,
        'total_quantidade': total_quantidade,  # Quantidade de placas faturadas
        'quantidade_recebida': quantidade_recebida,
        'quantidade_material_recebida': float(quantidade_material_recebida),
        'quantidade_material_a_faturar': quantidade_material_a_faturar,
        'quantidade_material_faturada': float(quantidade_material_faturada),
        'quantidade_material_nao_faturada': quantidade_material_nao_faturada,
        'valor_faturado': valor_faturado,
        'valor_recebido': valor_recebido,
        'valor_material_a_faturar': valor_material_a_faturar,
        'valor_total_contratos': valor_total_contratos,
        'valor_total_servico': valor_total_servico,
        'valor_material_faturado': valor_material_faturado,
        'valor_servico_faturado': valor_servico_faturado,
        'valor_servico_a_faturar': valor_servico_a_faturar,
        'valor_material_nao_faturado': valor_material_nao_faturado,
        'valor_servico_nao_faturado': valor_servico_nao_faturado,
        'percentual_material_faturado': percentual_material_faturado,
        'percentual_material_recebido': percentual_material_recebido,
        'percentual_material_a_faturar': percentual_material_a_faturar,
        'percentual_material_nao_faturado': percentual_material_nao_faturado,
        'percentual_servico_faturado': percentual_servico_faturado,
        'percentual_servico_recebido': percentual_servico_recebido,
        'percentual_servico_a_faturar': percentual_servico_a_faturar,
        'percentual_servico_nao_faturado': percentual_servico_nao_faturado,
        'valor_material_recebido': float(valor_material_recebido),
        'valor_material_a_receber': float(valor_material_a_receber),
        'quantidade_material_a_receber': float(quantidade_material_a_receber),
        'percentual_material_a_receber': float(percentual_material_a_receber),
        'valor_servico_a_receber': float(valor_servico_a_receber),
        'percentual_servico_a_receber': float(percentual_servico_a_receber),
        }

    return jsonify({    
        'data': dados_relatorio,
        'recordsTotal': len(dados_relatorio),
        'recordsFiltered': len(dados_relatorio),
        'dados_relatorio_aux': dados_relatorio_aux
    })


@notas_bp.route('/api/nota/<int:nota_id>/pagamento-manual', methods=['POST'])
@login_required_decorator
def api_pagamento_manual(nota_id):
    """Grava ou remove indicação de pagamento manual em NotaFiscal.dados_adicionais (JSON)."""
    payload = request.get_json(silent=True) or {}
    csrf_token = payload.get('csrf_token') or request.form.get('csrf_token')
    if not csrf_token:
        return jsonify({'ok': False, 'error': 'Token CSRF obrigatório.'}), 400
    try:
        validate_csrf(csrf_token)
    except Exception:
        return jsonify({'ok': False, 'error': 'Token CSRF inválido.'}), 400

    indicado = payload.get('indicado', True)
    if isinstance(indicado, str):
        indicado = indicado.lower() in ('1', 'true', 'yes', 'sim')

    nf = NotaFiscal.query.get(nota_id)
    if not nf:
        return jsonify({'ok': False, 'error': 'Nota não encontrada.'}), 404

    da = {}
    if nf.dados_adicionais:
        try:
            da = (
                json.loads(nf.dados_adicionais)
                if isinstance(nf.dados_adicionais, str)
                else nf.dados_adicionais
            )
        except (json.JSONDecodeError, TypeError):
            da = {}
    if not isinstance(da, dict):
        da = {}

    agora = datetime.now().isoformat()
    uid = getattr(current_user, 'id', None)

    if indicado:
        da['pagamento_manual'] = {
            'indicado': True,
            'data_indicacao': agora,
            'usuario_id': uid,
        }
    else:
        da['pagamento_manual'] = {
            'indicado': False,
            'data_remocao': agora,
            'usuario_id': uid,
        }

    nf.dados_adicionais = json.dumps(da, ensure_ascii=False)
    nf.save()

    return jsonify({
        'ok': True,
        'pagamento_manual': da['pagamento_manual'],
        'pagamento_manual_indicado': bool(indicado),
    })


@notas_bp.route('/exportar/zip', methods=['GET'])
@login_required_decorator
def exportar_zip():
    """Exportar relatório em formato ZIP com PDFs e XMLs das notas"""
    tinicio = time.time()
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    status_pagamento = request.args.get('status_pagamento')
    tipo_nota = request.args.get('tipo_nota', None)
    
    # Converter filtro tipo_nota para tipo_nfe
    tipo_nfe = None
    if tipo_nota == 'material':
        tipo_nfe = '0'  # Tipo 0 ou 1 (NFE)
    elif tipo_nota == 'servico':
        tipo_nfe = '3'  # Tipo 3 (NFSe)
    
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]
    
    # Criar um objeto request mock para api_get_dados_notas_fiscais
    json_request = {
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'centro_custo_ids': centro_custo_ids_int,
        'status_pagamento': status_pagamento,
        'emitente': 'Matriz',
        'tipo_operacao': 'venda',
        'pagamento_5percent': True,
        'tipo_nfe': tipo_nfe  # Filtro de tipo de nota (None = todos, '0' = material, '3' = serviço)
    }
    query = api_get_dados_notas_fiscais(json_request)
    
    # Buscar dados do relatório (notas filtradas)
    dados_relatorio = _processar_notas_fiscais(query)
    
    # Criar ZIP em memória
    notas = []
    for d in dados_relatorio:
        nota = db.session.query(NotaFiscal, Upload).\
            join(Upload, Upload.pai_id == NotaFiscal.id and Upload.pai == 'NotaFiscal').\
            filter(NotaFiscal.id == d['id'], Upload.tipo == 1).first()
        if nota:
            notas.append(nota)
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Adicionar XML e PDF de cada nota
        total = 0
        for nota in notas:
            total += nota[0].valor_total
            # XML
            if nota[0].xml_data:
                xml_bytes = base64.b64decode(nota[0].xml_data)
                zipf.writestr(f'NF {nota[0].numero_nf}.xml', xml_bytes)
            # PDF
            if nota[1] and nota[1].blob:
                pdf_bytes = base64.b64decode(nota[1].blob)
                zipf.writestr(f'NF {nota[0].numero_nf}.pdf', pdf_bytes)
        
        # Gerar PDF da tabela
        logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
        logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
        html = render_template(
            'relatorios/notas/pdf.html',
            relatorio=dados_relatorio,
            total=total,
            now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            logo_path=logo_path_uri
        )
        pdf_bytes = HTML(string=html).write_pdf(
            stylesheets=[CSS(string='body { font-family: Arial, sans-serif;}')]
        )
        zipf.writestr('relatorio_notas.pdf', pdf_bytes)
        
        # Gerar Excel
        df = _get_dataframe(dados_relatorio)
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, sheet_name='Relatório Financeiro')
        excel_buffer.seek(0)
        zipf.writestr('relatorio_notas.xlsx', excel_buffer.read())
    
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='notas_exportadas.zip'
    )

@notas_bp.route('/exportar/pdf', methods=['GET'])
@login_required_decorator
def exportar_pdf():
    """Exportar relatório em formato PDF"""
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    status_pagamento = request.args.get('status_pagamento')
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]

    # Criar um objeto request mock para api_get_dados_notas_fiscais
    json_request = {
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'centro_custo_ids': centro_custo_ids_int,
        'status_pagamento': status_pagamento,
        'emitente': 'Matriz',
        'tipo_operacao': 'venda',
        'pagamento_5percent': True,
        'tipo_nfe': None  # Incluir todos os tipos (0, 1, 3)
    }
    query = api_get_dados_notas_fiscais(json_request)
    
    # Buscar dados do relatório (notas filtradas)
    dados_relatorio = _processar_notas_fiscais(query)

    notas = db.session.query(NotaFiscal).filter(
        NotaFiscal.id.in_([d['id'] for d in dados_relatorio])
    ).all()
    
    # Adicionar XML e PDF de cada nota
    total = 0
    for nota in notas:
        total += nota.valor_total
    
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
    logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
    html = render_template(
        'relatorios/notas/pdf.html',
        relatorio=dados_relatorio,
        total=total,
        now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        logo_path=logo_path_uri
    )
    pdf_bytes = HTML(string=html).write_pdf(
        stylesheets=[CSS(string='body { font-family: Arial, sans-serif;}')]
    )

    pdf_io = io.BytesIO(pdf_bytes)
    pdf_io.seek(0)
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='relatorio_notas.pdf'
    )

@notas_bp.route('/exportar/excel', methods=['GET'])
@login_required_decorator
def exportar_excel():
    """Exportar relatório em formato Excel"""
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    status_pagamento = request.args.get('status_pagamento')
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else None
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else None
    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]

    # Criar um objeto request mock para api_get_dados_notas_fiscais
    json_request = {
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'centro_custo_ids': centro_custo_ids_int,
        'status_pagamento': status_pagamento,
        'emitente': 'Matriz',
        'tipo_operacao': 'venda',
        'pagamento_5percent': True,
        'tipo_nfe': None  # Incluir todos os tipos (0, 1, 3)
    }
    query = api_get_dados_notas_fiscais(json_request)
    
    dados_relatorio = _processar_notas_fiscais(query)

    df = _get_dataframe(dados_relatorio)
    
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Relatório Financeiro')
    excel_buffer.seek(0)

    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='relatorio_notas.xlsx'
    )

@notas_bp.route('/exportar/faturamento-mes-excel', methods=['GET'])
@login_required_decorator
def exportar_faturamento_mes_excel():
    """Exportar faturamento mensal em formato Excel (agrupado por mês/ano de emissão)"""
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    centro_custo_ids = request.args.getlist('centro_custo')
    status_pagamento = request.args.get('status_pagamento')
    tipo_nota = request.args.get('tipo_nota', None)

    # Converter filtro tipo_nota para tipo_nfe (mesma regra usada em outros endpoints)
    tipo_nfe = None
    if tipo_nota == 'material':
        tipo_nfe = '0'  # Tipo 0 ou 1 (NFE)
    elif tipo_nota == 'servico':
        tipo_nfe = '3'  # Tipo 3 (NFSe)

    centro_custo_ids_int = [int(cid) for cid in centro_custo_ids if cid]

    json_request = {
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'centro_custo_ids': centro_custo_ids_int,
        'status_pagamento': status_pagamento,
        'emitente': 'Matriz',
        'tipo_operacao': 'venda',
        'pagamento_5percent': True,
        'tipo_nfe': tipo_nfe
    }

    query = api_get_dados_notas_fiscais(json_request)
    resultados = query.all()

    # Agrupar por ano/mês de emissão
    faturamento_mensal = {}
    for resultado in resultados:
        nf = resultado[0]
        # Ignorar notas canceladas
        if nf.status_processamento == 'cancelada':
            continue
        if not nf.data_emissao:
            continue
        ano = nf.data_emissao.year
        mes = nf.data_emissao.month
        chave = (ano, mes)
        if chave not in faturamento_mensal:
            faturamento_mensal[chave] = {
                'ANO': ano,
                'MES': mes,
                'MES/ANO': f'{mes:02d}/{ano}',
                'QTD_NOTAS': 0,
                'VALOR_TOTAL': 0.0
            }
        faturamento_mensal[chave]['QTD_NOTAS'] += 1
        faturamento_mensal[chave]['VALOR_TOTAL'] += float(Decimal(nf.valor_total))

    # Ordenar por ano e mês
    linhas = sorted(
        faturamento_mensal.values(),
        key=lambda x: (x['ANO'], x['MES'])
    )

    df = pd.DataFrame(linhas) if linhas else pd.DataFrame(
        columns=['ANO', 'MES', 'MES/ANO', 'QTD_NOTAS', 'VALOR_TOTAL']
    )

    # Formatar valor total como moeda em string para facilitar leitura no Excel
    if not df.empty:
        df['VALOR_TOTAL'] = df['VALOR_TOTAL'].apply(
            lambda x: 'R$ ' + '{:,.2f}'.format(x).replace(',', 'X').replace('.', ',').replace('X', '.')
        )

    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Faturamento Mensal')
    excel_buffer.seek(0)

    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='faturamento_mensal_notas.xlsx'
    )

def _get_dataframe(dados_relatorio):
    """Helper function para criar DataFrame do relatório"""
    df = pd.DataFrame(dados_relatorio)
    # Ordenar por data de emissão
    df['valor'] = df['valor'].apply(
        lambda x: 'R$ ' + '{:,.2f}'.format(x).replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    df['quantidade'] = df['quantidade'].apply(lambda x: int(x))
    df.rename(columns={
        'data_prevista': 'VENCIMENTO',
        'data': 'DATA EMISSÃO',
        'nf': 'NF',
        'quantidade': 'QTDE DE PLACA',
        'valor': 'VALOR',
        'status': 'STATUS',
        'pago': 'PAGO',
        'destinatario': 'DESTINATÁRIO'

    }, inplace=True)

    return df[['DATA EMISSÃO', 'NF', 'QTDE DE PLACA', 'VALOR', 'STATUS', 'VENCIMENTO', 'PAGO', 'DESTINATÁRIO']]


