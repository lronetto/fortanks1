"""Consultas e montagem de dados para listagens de usinagens (sem Flask request)."""

import json
from datetime import datetime

from models.concreto import ConcretoUsinagens, ConcretoUsinagensRompimentos


def obter_linhas_datatable_usinagens(
    data_inicial_str: str,
    data_final_str: str,
    filtro_produzido: str,
) -> list[dict]:
    """
    Retorna linhas no formato esperado pelo endpoint /api/listar-usinagens (DataTables).
    """
    query = ConcretoUsinagens.query

    if data_inicial_str:
        try:
            data_inicial = datetime.strptime(data_inicial_str, '%Y-%m-%d')
            query = query.filter(ConcretoUsinagens.data_usinagem >= data_inicial)
        except ValueError:
            pass

    if data_final_str:
        try:
            data_final_dt_obj = datetime.strptime(data_final_str, '%Y-%m-%d')
            data_final_para_query = datetime.combine(data_final_dt_obj.date(), datetime.max.time())
            query = query.filter(ConcretoUsinagens.data_usinagem <= data_final_para_query)
        except ValueError:
            pass

    usinagens = query.order_by(ConcretoUsinagens.data_usinagem.desc()).all()
    now = datetime.now()

    def _parse_dados_adicionais(raw):
        if raw is None:
            return {}, ''
        if isinstance(raw, dict):
            return raw, json.dumps(raw, ensure_ascii=False)
        if isinstance(raw, str):
            trimmed = raw.strip()
            if not trimmed:
                return {}, ''
            try:
                parsed = json.loads(trimmed)
                return (parsed if isinstance(parsed, dict) else {}), json.dumps(parsed, ensure_ascii=False)
            except Exception:
                return {}, trimmed
        try:
            return {}, json.dumps(raw, ensure_ascii=False)
        except Exception:
            return {}, ''

    def _badge(label, cls, usinagem_id, idade):
        return (
            f'<span class="badge {cls} rompimento-badge" '
            f'data-bs-toggle="tooltip" data-bs-html="true" '
            f'data-usinagem-id="{usinagem_id}" data-idade="{idade}" '
            f'title="Detalhes dos rompimentos/idade: {idade}">{label}</span>'
        )

    data = []
    for us in usinagens:
        idade = (now - us.data_usinagem) if us.data_usinagem else None
        idade_days = idade.days if idade is not None else 0

        rompimentos = ConcretoUsinagensRompimentos.query.filter_by(numero_serie=us.serie).all()
        tem_24h = False
        tem_28d = False
        for r in rompimentos:
            if r.data_rompimento and us.data_usinagem:
                delta_days = (r.data_rompimento - us.data_usinagem).days
                if delta_days <= 3:
                    tem_24h = True
                if delta_days >= 27:
                    tem_28d = True

        status_badges = []
        if rompimentos:
            if tem_24h:
                status_badges.append(_badge('24H', 'bg-success', us.id, '24H'))

            if tem_28d:
                status_badges.append(_badge('28D', 'bg-success', us.id, '28D'))
            else:
                if idade_days <= 28:
                    status_badges.append(_badge('28D', 'bg-warning', us.id, '28D'))
                else:
                    status_badges.append(_badge('28D', 'bg-danger', us.id, '28D'))
        else:
            if idade_days <= 0:
                status_badges.append(_badge('24H', 'bg-warning', us.id, '24H'))
            elif idade_days > 3:
                status_badges.append(_badge('24H', 'bg-danger', us.id, '24H'))

            if idade_days < 28:
                status_badges.append(_badge('28D', 'bg-warning', us.id, '28D'))
            else:
                status_badges.append(_badge('28D', 'bg-danger', us.id, '28D'))

        dados_obj, dados_json = _parse_dados_adicionais(us.dados_adicionais)
        produzida = bool(dados_obj.get('data_producao')) if isinstance(dados_obj, dict) else False
        data_producao = dados_obj.get('data_producao') if isinstance(dados_obj, dict) else None

        if filtro_produzido == 'sim' and not produzida:
            continue
        if filtro_produzido == 'nao' and produzida:
            continue

        producao_badge = (
            '<span class="badge bg-success ms-1" title="Produção processada">'
            '<i class="fas fa-check-circle"></i> Produzida</span>'
            if produzida
            else '<span class="badge bg-secondary ms-1" title="Pendente de produção">'
                 '<i class="fas fa-minus"></i> Não produzida</span>'
        )

        data.append({
            'id': us.id,
            'serie': us.serie,
            'data_usinagem_iso': us.data_usinagem.strftime('%Y-%m-%dT%H:%M:%S') if us.data_usinagem else '',
            'data_usinagem_display': us.data_usinagem.strftime('%d/%m/%Y %H:%M') if us.data_usinagem else '-',
            'data_usinagem_datetime_local': us.data_usinagem.strftime('%Y-%m-%dT%H:%M') if us.data_usinagem else '',
            'traco_nome': us.produto_composto.nome if us.produto_composto else '-',
            'volume': float(us.volume) if us.volume is not None else None,
            'flow': us.flow or '',
            'nf': us.nota or '',
            'produto_composto_id': us.produtoCompostoId,
            'dados_adicionais_json': dados_json or '',
            'produzida': produzida,
            'data_producao': data_producao,
            'status_html': ' '.join(status_badges) + ' ' + producao_badge,
        })

    return data
