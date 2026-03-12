"""
Pacote PLR: avaliações do colaborador, modelos de PLR, efetivo e relatórios.

O blueprint `plr_bp` é definido aqui; as rotas são distribuídas em:
- efetivo: importação/listagem/edição de efetivo PLR
- avaliacao: avaliações PLR (listagem, nova/editar/excluir, importar, por-mês)
- modelos: modelos de PLR e cargos-salários
- Este módulo: relatórios (avaliação, planilha) e rota index.
"""
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required

from models.database import db
from models.plr import ModeloPLR, PLRColaborador
from models.colaborador import Colaborador

plr_bp = Blueprint('plr', __name__, url_prefix='/plr')


@plr_bp.before_request
@login_required
def _login_required():
    pass


# Registrar rotas dos submódulos (decoradores vinculam ao plr_bp)
from . import efetivo  # noqa: E402
from . import avaliacao  # noqa: E402
from . import modelos  # noqa: E402

from .avaliacao import _equipes_distintas_plr  # noqa: E402


# ---------- Relatório de Avaliação ----------

@plr_bp.route('/relatorio-avaliacao/', methods=['GET', 'POST'])
def relatorio_avaliacao():
    """Relatório de avaliação: filtro por modelo PLR e período; média quando mais de uma avaliação por colaborador."""
    modelos_list = ModeloPLR.query.filter_by(ativo=True).order_by(ModeloPLR.nome).all()
    resultado = None
    ano_sugerido = datetime.now().year
    if request.method == 'POST':
        modelo_plr_id = request.form.get('modelo_plr_id')
        mes_inicio = request.form.get('mes_inicio')
        mes_fim = request.form.get('mes_fim')
        ano = request.form.get('ano')
        if not ano:
            flash('Informe o ano.', 'danger')
            return render_template('plr/relatorio_avaliacao.html', modelos=modelos_list)
        ano = int(ano)
        mes_i = int(mes_inicio or 1)
        mes_f = int(mes_fim or 12)
        data_inicio = date(ano, mes_i, 1)
        if mes_f == 12:
            data_fim = date(ano, 12, 31)
        else:
            data_fim = date(ano, mes_f + 1, 1) - timedelta(days=1)
        q = PLRColaborador.query.filter(
            PLRColaborador.data >= data_inicio,
            PLRColaborador.data <= data_fim,
        )
        if modelo_plr_id:
            q = q.filter(PLRColaborador.PlrModelo_id == int(modelo_plr_id))
        avaliacoes = q.order_by(PLRColaborador.colaborador_id, PLRColaborador.data).all()
        por_colaborador = {}
        for av in avaliacoes:
            cid = av.colaborador_id
            if cid not in por_colaborador:
                por_colaborador[cid] = {'colaborador': av.colaborador, 'notas': [], 'avaliacoes': []}
            media = av.nota_media_avaliacao()
            if media is not None:
                por_colaborador[cid]['notas'].append(media)
            por_colaborador[cid]['avaliacoes'].append(av)
        resultado = []
        for cid, dados in por_colaborador.items():
            media_final = sum(dados['notas']) / len(dados['notas']) if dados['notas'] else None
            resultado.append({
                'colaborador': dados['colaborador'],
                'quantidade_avaliacoes': len(dados['avaliacoes']),
                'media': round(media_final, 2) if media_final is not None else None,
                'avaliacoes': dados['avaliacoes'],
            })
        resultado.sort(key=lambda x: (x['colaborador'].nome if x['colaborador'] else ''))
    return render_template('plr/relatorio_avaliacao.html', modelos=modelos_list, resultado=resultado, ano_sugerido=ano_sugerido)


# ---------- Relatório Planilha (Cálculo PLR - formato Excel) ----------

def _relatorio_planilha_calcular(ano_inicio, mes_inicio, ano_fim, mes_fim, modelo_plr_id, equipe_filtro=None):
    """
    Retorna (resultado, meses_colunas, data_fechamento) para o relatório planilha.
    Suporta períodos que abrangem anos diferentes.
    """
    from utils.plr_calculo import tempo_de_casa_meses, salario_base_plr

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

    q_av = (
        PLRColaborador.query.filter(
            PLRColaborador.data >= data_inicio,
            PLRColaborador.data <= data_fechamento,
        )
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

    av_por_colab_mes = {}
    for av in avaliacoes_periodo:
        cid = av.colaborador_id
        if cid not in av_por_colab_mes:
            av_por_colab_mes[cid] = {}
        mes_key = (av.data.month, av.data.year) if av.data else None
        if mes_key:
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
        data_ref = (colab.data_demissao if colab.data_demissao and colab.data_demissao <= data_fechamento else data_fechamento)
        tempo_meses = tempo_de_casa_meses(colab.data_admissao, data_ref)
        if tempo_meses < 2:
            continue
        tempo_meses = tempo_de_casa_meses(colab.data_admissao, data_fechamento)
        ref_mes, ref_ano = meses_colunas[-1] if meses_colunas else (mes_f, ano_f)
        dados_sal = salario_base_plr(colab, ref_mes, ref_ano, data_fechamento, db.session)
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
        vpo = salario_base_plr_val * (p_val / 100.0) if (salario_base_plr_val is not None and p_val is not None) else None
        valor_total = vpo

        resultado.append({
            'colaborador': colab,
            'tempo_casa_meses': tempo_meses,
            'data_fechamento': data_fechamento,
            'salario_base_plr': salario_base_plr_val,
            'meses_colunas': meses_colunas,
            'pcts_meses': pcts_meses,
            'soma': round(soma_pct, 2) if soma_pct else None,
            'p': round(p_val, 2) if p_val is not None else None,
            'vpo': round(vpo, 2) if vpo is not None else None,
            'valor_total': round(valor_total, 2) if valor_total is not None else None,
        })

    resultado.sort(key=lambda x: (x['colaborador'].nome if x['colaborador'] else ''))
    return resultado, meses_colunas, data_fechamento


@plr_bp.route('/relatorio-planilha/dados')
def relatorio_planilha_dados():
    """Retorna JSON com os dados da planilha para DataTables (AJAX)."""
    ano_inicio = request.args.get('ano_inicio') or request.args.get('ano')
    ano_fim = request.args.get('ano_fim') or ano_inicio
    mes_inicio = request.args.get('mes_inicio', '1')
    mes_fim = request.args.get('mes_fim', '12')
    modelo_plr_id = request.args.get('modelo_plr_id', '')
    equipe_filtro = request.args.get('equipe', '').strip() or None
    if not ano_inicio:
        return jsonify({'error': 'Informe o período.', 'data': [], 'meses_colunas': [], 'data_fechamento': None}), 400
    try:
        ano_inicio = int(ano_inicio)
        ano_fim = int(ano_fim)
    except (ValueError, TypeError):
        return jsonify({'error': 'Ano inválido.', 'data': [], 'meses_colunas': [], 'data_fechamento': None}), 400
    try:
        resultado, meses_colunas, data_fechamento = _relatorio_planilha_calcular(
            ano_inicio, mes_inicio, ano_fim, mes_fim, modelo_plr_id, equipe_filtro
        )
    except Exception as e:
        return jsonify({'error': str(e), 'data': [], 'meses_colunas': [], 'data_fechamento': None}), 500

    data = []
    for r in resultado:
        colab = r['colaborador']
        data_fech = r.get('data_fechamento')
        demissao_ou_fech = colab.data_demissao.strftime('%d/%m/%Y') if colab.data_demissao else (data_fech.strftime('%d/%m/%Y') if data_fech else '-')
        row = {
            'cpf': colab.cpf or '-',
            'nome': colab.nome,
            'admissao': colab.data_admissao.strftime('%d/%m/%Y') if colab.data_admissao else '-',
            'demissao_fechamento': demissao_ou_fech,
            'tempo_casa_meses': r['tempo_casa_meses'],
            'funcao': colab.cargo.nome if colab.cargo else '-',
            'pcts_meses': r['pcts_meses'],
            'soma': f"{r['soma']:.2f}%" if r['soma'] is not None else '-',
            'p': f"{r['p']:.2f}%" if r['p'] is not None else '-',
            'salario_base_plr': f"R$ {r['salario_base_plr']:.2f}".replace('.', ',') if r['salario_base_plr'] is not None else '-',
            'vpo': f"R$ {r['vpo']:.2f}".replace('.', ',') if r['vpo'] is not None else '-',
            'valor_total': f"R$ {r['valor_total']:.2f}".replace('.', ',') if r['valor_total'] is not None else '-',
        }
        data.append(row)

    return jsonify({
        'data': data,
        'meses_colunas': [{'mes': m, 'ano': a} for (m, a) in meses_colunas],
        'data_fechamento': data_fechamento.strftime('%d/%m/%Y') if data_fechamento else None,
    })


@plr_bp.route('/relatorio-planilha/', methods=['GET', 'POST'])
def relatorio_planilha():
    """
    Relatório em formato planilha: CPF, Nome, Admissão, Demissão/Fechamento, Tempo de casa (meses),
    Função, colunas mensais (%), SOMA, P, Salário base PLR, VPO, Valor total a pagar.
    """
    modelos_list = ModeloPLR.query.filter_by(ativo=True).order_by(ModeloPLR.nome).all()
    equipes = _equipes_distintas_plr()
    ano_sugerido = datetime.now().year

    if request.method == 'POST':
        modelo_plr_id = request.form.get('modelo_plr_id', '')
        equipe_filtro = request.form.get('equipe', '').strip() or None
        periodo_inicio = request.form.get('periodo_inicio')
        periodo_fim = request.form.get('periodo_fim')
        if periodo_inicio and periodo_fim:
            parts_i = periodo_inicio.split('-')
            parts_f = periodo_fim.split('-')
            ano_inicio = int(parts_i[0])
            mes_inicio = parts_i[1].lstrip('0') or '1'
            ano_fim = int(parts_f[0])
            mes_fim = parts_f[1].lstrip('0') or '12'
            if ano_inicio > ano_fim or (ano_inicio == ano_fim and int(mes_inicio) > int(mes_fim)):
                flash('A data de início deve ser anterior ou igual à data de fim.', 'danger')
                return render_template('plr/relatorio_planilha.html', modelos=modelos_list, equipes=equipes, ano_sugerido=ano_sugerido)
        else:
            ano_inicio = request.form.get('ano_inicio') or request.form.get('ano')
            ano_fim = request.form.get('ano_fim') or ano_inicio
            mes_inicio = request.form.get('mes_inicio', '1')
            mes_fim = request.form.get('mes_fim', '12')
            if not ano_inicio:
                flash('Informe o período.', 'danger')
                return render_template('plr/relatorio_planilha.html', modelos=modelos_list, equipes=equipes, ano_sugerido=ano_sugerido)
            ano_inicio = int(ano_inicio)
            ano_fim = int(ano_fim)
        try:
            resultado, meses_colunas, data_fechamento = _relatorio_planilha_calcular(
                ano_inicio, mes_inicio, ano_fim, mes_fim, modelo_plr_id, equipe_filtro
            )
        except Exception as e:
            flash(f'Erro ao gerar relatório: {e}', 'danger')
            return render_template('plr/relatorio_planilha.html', modelos=modelos_list, equipes=equipes, ano_sugerido=ano_sugerido)
        planilha_json = {
            'data': [],
            'meses_colunas': [{'mes': m, 'ano': a} for (m, a) in meses_colunas],
            'data_fechamento': data_fechamento.strftime('%d/%m/%Y') if data_fechamento else None,
        }
        for r in resultado:
            colab = r['colaborador']
            data_fech = r.get('data_fechamento')
            demissao_ou_fech = colab.data_demissao.strftime('%d/%m/%Y') if colab.data_demissao else (data_fech.strftime('%d/%m/%Y') if data_fech else '-')
            planilha_json['data'].append({
                'cpf': colab.cpf or '-',
                'nome': colab.nome,
                'admissao': colab.data_admissao.strftime('%d/%m/%Y') if colab.data_admissao else '-',
                'demissao_fechamento': demissao_ou_fech,
                'tempo_casa_meses': r['tempo_casa_meses'],
                'funcao': colab.cargo.nome if colab.cargo else '-',
                'pcts_meses': r['pcts_meses'],
                'soma': f"{r['soma']:.2f}%" if r['soma'] is not None else '-',
                'p': f"{r['p']:.2f}%" if r['p'] is not None else '-',
                'salario_base_plr': f"R$ {r['salario_base_plr']:.2f}".replace('.', ',') if r['salario_base_plr'] is not None else '-',
                'vpo': f"R$ {r['vpo']:.2f}".replace('.', ',') if r['vpo'] is not None else '-',
                'valor_total': f"R$ {r['valor_total']:.2f}".replace('.', ',') if r['valor_total'] is not None else '-',
            })
        return render_template(
            'plr/relatorio_planilha.html',
            modelos=modelos_list,
            equipes=equipes,
            ano_sugerido=ano_sugerido,
            planilha_json=planilha_json,
        )

    return render_template(
        'plr/relatorio_planilha.html',
        modelos=modelos_list,
        equipes=equipes,
        ano_sugerido=ano_sugerido,
        planilha_json=None,
    )


@plr_bp.route('/')
def index():
    """Redireciona para avaliações."""
    return redirect(url_for('plr.avaliacoes_index'))
