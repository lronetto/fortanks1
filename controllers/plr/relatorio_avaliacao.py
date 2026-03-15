"""
Relatório de Avaliação PLR: filtro por modelo e período; média por colaborador.
"""
from datetime import datetime, date, timedelta

from flask import request, render_template, flash
from models.plr import ModeloPLR, PLRColaborador

from . import plr_bp


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

    return render_template(
        'plr/relatorio_avaliacao.html',
        modelos=modelos_list,
        resultado=resultado,
        ano_sugerido=ano_sugerido,
    )
