"""
Cálculo da planilha PLR, linhas para DataTables e mapas auxiliares para Excel.
"""
from datetime import date, timedelta

from flask import jsonify

from utils.datatable_helper import DataTableParams

from models.database import db
from models.plr import PLRColaborador, EfetivoPLR, PlrAssiduidade
from models.colaborador import Colaborador

from models.plr.utils import (
    assiduidade_pct_por_faltas,
    nota_media_com_assiduidade,
    salario_base_plr,
    tempo_de_casa_meses,
)

from ..constantes import CRITERIOS_PADRAO_PLR
from .avaliacoes import valor_por_tipo as _valor_por_tipo


MESES_ABREV = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ']


def _titulo_aba_mes(mes, ano):
    """Retorna o título da aba do mês no formato 'AGO 2025', 'SET 2025', etc."""
    idx = int(mes) - 1
    mes_nome = MESES_ABREV[idx] if 0 <= idx < len(MESES_ABREV) else f'{mes:02d}'
    return f'{mes_nome} {ano}'


MIN_MESES_AVALIACAO_RESUMO = 3

# Títulos das colunas de avaliação com peso em % (cache)
CRITERIOS_HEADERS_COM_PESO = None


def _criterios_headers_com_peso():
    """Retorna lista [('Assiduidade', 'ASSIDUIDADE (30%)'), ...] com pesos do CRITERIOS_PADRAO_PLR (títulos em maiúsculas)."""
    global CRITERIOS_HEADERS_COM_PESO
    if CRITERIOS_HEADERS_COM_PESO is not None:
        return CRITERIOS_HEADERS_COM_PESO
    out = []
    for c in CRITERIOS_PADRAO_PLR:
        tipo = c.get('tipo', '')
        peso = c.get('peso')
        pct = int(round((peso * 100))) if peso is not None else ''
        label = f'{tipo.upper()} ({pct}%)' if pct != '' else tipo.upper()
        out.append((tipo, label))
    CRITERIOS_HEADERS_COM_PESO = out
    return out


def relatorio_planilha_calcular(ano_inicio, mes_inicio, ano_fim, mes_fim, modelo_plr_id,
                                equipe_filtro=None, departamentos_ids=None, salario_por_grupo=False):
    """
    Retorna (resultado, meses_colunas, data_fechamento) para o relatório planilha.
    Suporta períodos que abrangem anos diferentes.
    departamentos_ids: lista de IDs de departamento para filtrar (None ou vazia = todos).
    salario_por_grupo: mesmo critério da col. X (Sal. Atualizado) na exportação planilha MOD.
    """
    from .planilha_plr_template import salario_atualizado_exportacao
    mes_i = int(mes_inicio)
    mes_f = int(mes_fim)
    ano_i = int(ano_inicio)
    ano_f = int(ano_fim)
    data_inicio = date(ano_i, mes_i, 1)
    data_fechamento = date(ano_f, mes_f, 1) + timedelta(days=32)
    data_fechamento = data_fechamento.replace(day=1) - timedelta(days=1)

    meses_colunas = []
    cur_ano, cur_mes = ano_i, mes_i
    while (cur_ano < ano_f) or (cur_ano == ano_f and cur_mes <= mes_f):
        meses_colunas.append((cur_mes, cur_ano))
        cur_mes += 1
        if cur_mes > 12:
            cur_mes = 1
            cur_ano += 1

    q_av = PLRColaborador.query.filter(
        PLRColaborador.data >= data_inicio,
        PLRColaborador.data <= data_fechamento,
    )
    if modelo_plr_id:
        q_av = q_av.filter(PLRColaborador.PlrModelo_id == int(modelo_plr_id))
    avaliacoes_periodo = q_av.all()

    if equipe_filtro:
        avaliacoes_periodo = [
            av for av in avaliacoes_periodo
            if av.equipe_alocada and isinstance(av.equipe_alocada, list)
            and equipe_filtro in [str(e).strip() for e in av.equipe_alocada if e]
        ]

    ids_colab = list({av.colaborador_id for av in avaliacoes_periodo})
    if not ids_colab:
        colaboradores = (
            Colaborador.query.filter(Colaborador.data_admissao <= data_fechamento)
            .filter(
                (Colaborador.data_demissao.is_(None)) | (Colaborador.data_demissao >= data_inicio)
            )
            .order_by(Colaborador.nome)
            .all()
        )
    else:
        colaboradores = Colaborador.query.filter(Colaborador.id.in_(ids_colab)).order_by(Colaborador.nome).all()

    if departamentos_ids:
        departamentos_ids_set = set(int(x) for x in departamentos_ids if x is not None)
        colaboradores = [c for c in colaboradores if c.departamento_id and c.departamento_id in departamentos_ids_set]

    all_colab_ids = [c.id for c in colaboradores] or ids_colab
    assid_map = {}
    if all_colab_ids:
        for rec in PlrAssiduidade.query.filter(PlrAssiduidade.colaborador_id.in_(all_colab_ids)).all():
            assid_map[(rec.colaborador_id, rec.mes, rec.ano)] = assiduidade_pct_por_faltas(rec.faltas)

    av_por_colab_mes = {}
    for av in avaliacoes_periodo:
        cid = av.colaborador_id
        if cid not in av_por_colab_mes:
            av_por_colab_mes[cid] = {}
        mes_key = (av.data.month, av.data.year) if av.data else None
        if mes_key:
            assid_pct = assid_map.get((cid, mes_key[0], mes_key[1]))
            if assid_pct is not None:
                media = nota_media_com_assiduidade(av.avaliacao, assid_pct)
            else:
                media = av.nota_media_avaliacao()
            if media is not None:
                pct = min(100.0, max(0.0, float(media) * 10.0))
                if mes_key not in av_por_colab_mes[cid]:
                    av_por_colab_mes[cid][mes_key] = []
                av_por_colab_mes[cid][mes_key].append(pct)

    resultado = []
    for colab in colaboradores:
        if colab.data_admissao and colab.data_admissao > data_fechamento:
            continue
        data_ref = (
            colab.data_demissao
            if colab.data_demissao and colab.data_demissao <= data_fechamento
            else data_fechamento
        )
        tempo_meses = tempo_de_casa_meses(colab.data_admissao, data_ref)
        if tempo_meses < 3:
            continue
        dados_sal = salario_base_plr(colab, data_fechamento)
        salario_base_plr_val = dados_sal.get('salario_base_plr')

        pcts_meses = []
        soma_pct = 0.0
        for (m, a) in meses_colunas:
            mes_key = (m, a)
            listas_pct = av_por_colab_mes.get(colab.id, {}).get(mes_key, [])
            pct = sum(listas_pct) / len(listas_pct) if listas_pct else None
            pcts_meses.append(pct)
            if pct is not None:
                soma_pct += pct

        num_meses = len(meses_colunas)
        p_val = (soma_pct / num_meses) if num_meses and soma_pct is not None else None
        vpo = (salario_base_plr_val / 12.0) * 6 * (p_val / 100.0) if (
            salario_base_plr_val is not None and p_val is not None
        ) else None
        valor_total = vpo

        sal_at = salario_atualizado_exportacao(colab, data_fechamento, salario_por_grupo)

        resultado.append({
            'colaborador': colab,
            'tempo_casa_meses': tempo_meses,
            'data_fechamento': data_fechamento,
            'salario_base_plr': salario_base_plr_val,
            'meses_colunas': meses_colunas,
            'pcts_meses': pcts_meses,
            'soma': round(soma_pct, 2) if soma_pct else None,
            'p': round(p_val, 2) if p_val is not None else None,
            'salario_atualizado': sal_at,
            'vpo': round(vpo, 2) if vpo is not None else None,
            'valor_total': round(valor_total, 2) if valor_total is not None else None,
        })

    resultado.sort(key=lambda x: (x['colaborador'].nome if x['colaborador'] else ''))
    return resultado, meses_colunas, data_fechamento


def expandir_resultado_planilha_por_segmento_funcao(
    resultado: list[dict],
    data_inicio: date,
    data_fechamento: date,
    meses_colunas: list[tuple[int, int]],
    salario_por_grupo: bool,
) -> list[dict]:
    """
    Uma linha por segmento de função no período (mesma regra de ``segmentos_funcao_periodo``
    na exportação MOD). Percentuais por mês só aparecem nos meses em que o segmento cruza o mês;
    SOMA e P seguem a mesma lógica do cálculo único (soma só meses com valor; P = soma / N meses
    do relatório). Salário atualizado / base PLR / VPO alinham às fórmulas da aba PAGAMENTO MOD.
    """
    from .planilha_plr_template import (
        segmentos_funcao_periodo,
        segmento_intersecta_mes,
        _cargo_id_salario_atualizado,
        _salario_cargo_em,
        _cargo_por_id,
    )
    from models.colaborador.utils.mudanca_funcao import funcao_id_vigente_em

    num_meses = len(meses_colunas)
    out: list[dict] = []

    for base in resultado:
        colab = base.get('colaborador')
        if not colab:
            continue
        dados = colab.get_dados_adicionais_dict()
        pcts_full = list(base.get('pcts_meses') or [])
        while len(pcts_full) < num_meses:
            pcts_full.append(None)

        segs = segmentos_funcao_periodo(colab, data_inicio, data_fechamento)
        if not segs:
            row = dict(base)
            row.setdefault('segmento_ordem', 0)
            row.setdefault('segmento_inicio', data_inicio)
            row.setdefault('nome_funcao_planilha', (colab.cargo.nome if colab.cargo else '-'))
            out.append(row)
            continue

        if len(segs) == 1:
            seg = segs[0]
            ref_seg_fim = min(seg['fim'], data_fechamento)
            if colab.data_demissao and colab.data_demissao <= data_fechamento:
                ref_seg_fim = min(ref_seg_fim, colab.data_demissao)
            fid = funcao_id_vigente_em(dados, ref_seg_fim, cargo_id_padrao=colab.cargo_id)
            cargo = _cargo_por_id(fid)
            nome_funcao = cargo.nome if cargo else (colab.cargo.nome if colab.cargo else '-')
            out.append(
                {
                    **base,
                    'segmento_ordem': 0,
                    'segmento_inicio': seg['inicio'],
                    'segmento_fim': seg['fim'],
                    'nome_funcao_planilha': nome_funcao,
                }
            )
            continue

        for seg_ord, seg in enumerate(segs):
            seg_i_ini = seg['inicio']
            seg_i_fim = seg['fim']
            ref_seg_fim = min(seg_i_fim, data_fechamento)
            if colab.data_demissao and colab.data_demissao <= data_fechamento:
                ref_seg_fim = min(ref_seg_fim, colab.data_demissao)

            fid = funcao_id_vigente_em(dados, ref_seg_fim, cargo_id_padrao=colab.cargo_id)
            cargo = _cargo_por_id(fid)
            nome_funcao = cargo.nome if cargo else (colab.cargo.nome if colab.cargo else '-')

            pcts_seg: list = []
            soma_pct = 0.0
            for i, (m, a) in enumerate(meses_colunas):
                if not segmento_intersecta_mes(seg_i_ini, seg_i_fim, m, a):
                    pcts_seg.append(None)
                    continue
                p = pcts_full[i] if i < len(pcts_full) else None
                pcts_seg.append(p)
                if p is not None:
                    soma_pct += p

            p_val = (soma_pct / num_meses) if num_meses else None
            tempo_m = tempo_de_casa_meses(colab.data_admissao, ref_seg_fim)
            sal_cargo = _cargo_id_salario_atualizado(fid, salario_por_grupo)
            sal_x = _salario_cargo_em(sal_cargo, ref_seg_fim)
            mult = 1.2 if tempo_m > 18 else 1.0
            sal_base_plr = (float(sal_x) * mult) if sal_x is not None else None
            vpo = (
                (sal_base_plr / 12.0) * 6 * (float(p_val) / 100.0)
                if sal_base_plr is not None and p_val is not None
                else None
            )
            valor_total = vpo

            out.append(
                {
                    **base,
                    'segmento_ordem': seg_ord,
                    'segmento_inicio': seg_i_ini,
                    'segmento_fim': seg_i_fim,
                    'nome_funcao_planilha': nome_funcao,
                    'tempo_casa_meses': tempo_m,
                    'pcts_meses': pcts_seg,
                    'soma': round(soma_pct, 2) if soma_pct else None,
                    'p': round(p_val, 2) if p_val is not None else None,
                    'salario_atualizado': sal_x,
                    'salario_base_plr': sal_base_plr,
                    'vpo': round(vpo, 2) if vpo is not None else None,
                    'valor_total': round(valor_total, 2) if valor_total is not None else None,
                }
            )

    return out


def _row_planilha_para_json(r):
    """Converte um item de resultado da planilha em dict para JSON (DataTables)."""
    colab = r['colaborador']
    data_fech = r.get('data_fechamento')
    demissao_ou_fech = (
        colab.data_demissao.strftime('%d/%m/%Y')
        if colab.data_demissao
        else (data_fech.strftime('%d/%m/%Y') if data_fech else '-')
    )
    return {
        'cpf': colab.cpf or '-',
        'nome': (colab.nome or '').upper(),
        'admissao': colab.data_admissao.strftime('%d/%m/%Y') if colab.data_admissao else '-',
        'demissao_fechamento': demissao_ou_fech,
        'tempo_casa_meses': r['tempo_casa_meses'],
        'funcao': (r.get('nome_funcao_planilha') or (colab.cargo.nome if colab.cargo else '-')),
        'pcts_meses': r['pcts_meses'],
        'soma': f"{r['soma']:.2f}%" if r['soma'] is not None else '-',
        'p': f"{r['p']:.2f}%" if r['p'] is not None else '-',
        'salario_atualizado': (
            f"R$ {r['salario_atualizado']:.2f}".replace('.', ',')
            if r.get('salario_atualizado') is not None
            else '-'
        ),
        'salario_base_plr': (
            f"R$ {r['salario_base_plr']:.2f}".replace('.', ',')
            if r['salario_base_plr'] is not None else '-'
        ),
        'vpo': f"R$ {r['vpo']:.2f}".replace('.', ',') if r['vpo'] is not None else '-',
        'valor_total': (
            f"R$ {r['valor_total']:.2f}".replace('.', ',')
            if r['valor_total'] is not None else '-'
        ),
    }


def _row_planilha_flat_row_dict(r, meses_colunas):
    """Linha para DataTables server-side: ``pct_0``..``pct_{n-1}`` no lugar de ``pcts_meses``."""
    row = dict(_row_planilha_para_json(r))
    pcts = row.pop('pcts_meses') or []
    for i in range(len(meses_colunas)):
        pct = pcts[i] if i < len(pcts) else None
        row[f'pct_{i}'] = f'{pct:.2f}%' if pct is not None else '-'
    return row


def _planilha_column_keys(n_meses: int):
    keys = [
        'cpf',
        'nome',
        'admissao',
        'demissao_fechamento',
        'tempo_casa_meses',
        'funcao',
    ]
    keys.extend(f'pct_{i}' for i in range(n_meses))
    keys.extend(
        [
            'soma',
            'p',
            'salario_atualizado',
            'salario_base_plr',
            'vpo',
            'valor_total',
        ]
    )
    return tuple(keys)


def _planilha_sort_tuple(r, meses_colunas):
    """Tupla alinhada a ``_planilha_column_keys`` para ordenação server-side."""
    colab = r['colaborador']
    n = len(meses_colunas)
    pcts = r.get('pcts_meses') or []
    data_fech = r.get('data_fechamento')
    dem_ord = (
        colab.data_demissao.toordinal()
        if colab.data_demissao
        else (data_fech.toordinal() if data_fech else 0)
    )
    neg = float('-inf')
    keys = [
        (colab.cpf or '').lower(),
        (colab.nome or '').lower(),
        colab.data_admissao.toordinal() if colab.data_admissao else 0,
        dem_ord,
        int(r['tempo_casa_meses']) if r.get('tempo_casa_meses') is not None else 0,
        (
            (r.get('nome_funcao_planilha') or (colab.cargo.nome if colab.cargo else '') or '')
        ).lower(),
    ]
    for i in range(n):
        p = pcts[i] if i < len(pcts) else None
        keys.append(neg if p is None else float(p))
    keys.append(neg if r.get('soma') is None else float(r['soma']))
    keys.append(neg if r.get('p') is None else float(r['p']))
    keys.append(neg if r.get('salario_atualizado') is None else float(r['salario_atualizado']))
    keys.append(neg if r.get('salario_base_plr') is None else float(r['salario_base_plr']))
    keys.append(neg if r.get('vpo') is None else float(r['vpo']))
    keys.append(neg if r.get('valor_total') is None else float(r['valor_total']))
    seg_ini = r.get('segmento_inicio')
    keys.append(seg_ini.toordinal() if isinstance(seg_ini, date) else 0)
    keys.append(int(r.get('segmento_ordem', 0)))
    return tuple(keys)


def montar_relatorio_planilha_datatables(dt: DataTableParams, payload: dict):
    """Monta JSON server-side DataTables a partir do payload de ``carregar_payload_planilha``."""
    linhas = payload['linhas_exibicao']
    meses_colunas = payload['meses_colunas']
    data_fechamento = payload['data_fechamento']
    n_meses = len(meses_colunas)
    column_keys = _planilha_column_keys(n_meses)

    internas = []
    for r, flat in zip(linhas, payload['rows_datatables'], strict=True):
        sort_t = _planilha_sort_tuple(r, meses_colunas)
        blob = ' '.join(str(flat.get(k, '')) for k in column_keys).lower()
        internas.append({'flat': flat, 'sort': sort_t, 'blob': blob})

    records_total = len(internas)
    if dt.search:
        q = dt.search.lower()
        internas = [x for x in internas if q in x['blob']]
    records_filtered = len(internas)

    if 0 <= dt.order_col < len(column_keys):
        idx = dt.order_col
        rev = dt.order_dir == 'desc'
        tie_a = len(column_keys)
        tie_b = tie_a + 1

        def _sort_key(x):
            s = x['sort']
            return (s[idx], s[tie_a], s[tie_b])

        internas.sort(key=_sort_key, reverse=rev)

    if dt.length == -1:
        slice_rows = internas[dt.start :]
    else:
        per_page = max(1, min(dt.length, 500))
        slice_rows = internas[dt.start : dt.start + per_page]

    data = [x['flat'] for x in slice_rows]
    base = dt.resposta(data, records_total, records_filtered)
    out = base.get_json(silent=True) or {}
    out['meses_colunas'] = [{'mes': m, 'ano': a} for (m, a) in meses_colunas]
    out['data_fechamento'] = data_fechamento.strftime('%d/%m/%Y') if data_fechamento else None
    return jsonify(out)


def _excel_cpf_para_chapa(resultado, data_inicio, data_fechamento):
    """
    Mapa CPF -> chapa a partir do EfetivoPLR no período.
    Usa o último efetivo (por data) que tiver chapa disponível para cada CPF.
    """
    cpf_set = set()
    for r in resultado:
        colab = r.get('colaborador')
        if colab and colab.cpf:
            cpf_set.add(colab.cpf)
    cpf_para_chapa = {}
    if cpf_set:
        efetivos = (
            EfetivoPLR.query
            .filter(EfetivoPLR.cpf.in_(cpf_set))
            .filter(EfetivoPLR.data >= data_inicio, EfetivoPLR.data <= data_fechamento)
            .order_by(EfetivoPLR.cpf.asc(), EfetivoPLR.data.desc())
            .all()
        )
        for ef in efetivos:
            if not ef.cpf:
                continue
            chapa_val = (ef.chapa or '').strip()
            if ef.cpf not in cpf_para_chapa:
                cpf_para_chapa[ef.cpf] = chapa_val
            elif chapa_val and not cpf_para_chapa.get(ef.cpf):
                # Já tinha vazio; pega chapa de registro mais antigo que tenha chapa
                cpf_para_chapa[ef.cpf] = chapa_val
    return cpf_para_chapa


def _excel_criterios_por_colab_mes(resultado, meses_colunas, data_inicio, data_fechamento,
                                   modelo_plr_id, equipe_filtro):
    """Mapa (colaborador_id, (mes, ano)) -> dict de critérios (média por tipo)."""
    criterios_por_colab_mes = {}
    if not resultado or not meses_colunas:
        return criterios_por_colab_mes
    colab_ids = [r['colaborador'].id for r in resultado if r.get('colaborador')]
    if not colab_ids:
        return criterios_por_colab_mes

    q_crit = PLRColaborador.query.filter(
        PLRColaborador.colaborador_id.in_(colab_ids),
        PLRColaborador.data >= data_inicio,
        PLRColaborador.data <= data_fechamento,
    )
    if modelo_plr_id:
        q_crit = q_crit.filter(PLRColaborador.PlrModelo_id == int(modelo_plr_id))
    avaliacoes_crit = q_crit.all()
    if equipe_filtro:
        avaliacoes_crit = [
            av for av in avaliacoes_crit
            if av.equipe_alocada and isinstance(av.equipe_alocada, list)
            and equipe_filtro in [str(e).strip() for e in av.equipe_alocada if e]
        ]

    acumulado = {}
    for av in avaliacoes_crit:
        if not av.data:
            continue
        cid = av.colaborador_id
        mes_key = (av.data.month, av.data.year)
        key = (cid, mes_key)
        if key not in acumulado:
            acumulado[key] = {
                'Assiduidade': [],
                'Zero Acidente': [],
                'Segurança, Limpeza, Organização': [],
                'Prazo': [],
            }
        for tipo in ['Assiduidade', 'Zero Acidente', 'Segurança, Limpeza, Organização', 'Prazo']:
            v = _valor_por_tipo(av.avaliacao, tipo)
            if v is not None:
                acumulado[key][tipo].append(v)

    for (cid, mes_key), valores in acumulado.items():
        if cid not in criterios_por_colab_mes:
            criterios_por_colab_mes[cid] = {}
        criterios_por_colab_mes[cid][mes_key] = {
            tipo: (sum(lst) / len(lst) if lst else None)
            for tipo, lst in valores.items()
        }

    # Sobrescrever Assiduidade com dados de PlrAssiduidade quando existir (faltas -> %)
    meses_set = set(meses_colunas)
    assid_records = PlrAssiduidade.query.filter(
        PlrAssiduidade.colaborador_id.in_(colab_ids),
    ).all()
    for rec in assid_records:
        mes_key = (rec.mes, rec.ano)
        if mes_key not in meses_set:
            continue
        pct = assiduidade_pct_por_faltas(rec.faltas)
        if rec.colaborador_id not in criterios_por_colab_mes:
            criterios_por_colab_mes[rec.colaborador_id] = {}
        if mes_key not in criterios_por_colab_mes[rec.colaborador_id]:
            criterios_por_colab_mes[rec.colaborador_id][mes_key] = {}
        criterios_por_colab_mes[rec.colaborador_id][mes_key]['Assiduidade'] = pct

    return criterios_por_colab_mes
