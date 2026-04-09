"""
Assiduidade PLR: visualização, importação, edição e inclusão de faltas por colaborador/mês.
"""
from datetime import date
from flask import request, redirect, url_for, flash, jsonify, render_template
from flask_wtf.csrf import generate_csrf

from models.database import db
from models.plr import PlrAssiduidade
from models.colaborador import Colaborador
from models.departamento import Departamento

from . import plr_bp


@plr_bp.route('/assiduidade/')
def assiduidade_index():
    """Página de listagem de assiduidade (faltas) com filtros e DataTables AJAX."""
    from datetime import datetime
    ano_atual = datetime.now().year
    anos = list(range(ano_atual, ano_atual - 6, -1))
    colaboradores = Colaborador.query.order_by(Colaborador.nome).all()
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    return render_template(
        'plr/assiduidade_index.html',
        anos=anos,
        ano_atual=ano_atual,
        colaboradores=colaboradores,
        departamentos=departamentos,
        url_dados=url_for('plr.assiduidade_dados'),
        url_template=url_for('plr.relatorio_planilha_assiduidade_template'),
        url_import=url_for('plr.relatorio_planilha_assiduidade_import'),
        url_preview_meses=url_for('plr.relatorio_planilha_assiduidade_preview_meses'),
        url_next=url_for('plr.assiduidade_index'),
    )


@plr_bp.route('/assiduidade/dados')
def assiduidade_dados():
    """Retorna JSON para DataTables: filtros ano, mes, colaborador_id, departamento_id."""
    ano = request.args.get('ano', type=int)
    mes = request.args.get('mes', type=int)
    colaborador_id = request.args.get('colaborador_id', type=int)
    departamento_id = request.args.get('departamento_id', type=int)

    query = PlrAssiduidade.query.join(Colaborador)
    if ano is not None:
        query = query.filter(PlrAssiduidade.ano == ano)
    if mes is not None and 1 <= mes <= 12:
        query = query.filter(PlrAssiduidade.mes == mes)
    if colaborador_id is not None:
        query = query.filter(PlrAssiduidade.colaborador_id == colaborador_id)
    if departamento_id is not None:
        query = query.filter(Colaborador.departamento_id == departamento_id)

    lista = query.order_by(PlrAssiduidade.ano.desc(), PlrAssiduidade.mes.desc(), Colaborador.nome).all()
    csrf = generate_csrf()
    data = []
    for reg in lista:
        excluir_url = url_for('plr.assiduidade_excluir', id=reg.id)
        acoes = (
            f'<button type="button" class="btn btn-sm btn-primary btn-editar-assiduidade" data-id="{reg.id}" '
            f'title="Editar"><i class="fas fa-edit"></i></button> '
            f'<form method="POST" action="{excluir_url}" class="d-inline" onsubmit="return confirm(\'Excluir este registro?\');">'
            f'<input type="hidden" name="csrf_token" value="{csrf}">'
            f'<button type="submit" class="btn btn-sm btn-danger" title="Excluir"><i class="fas fa-trash"></i></button></form>'
        )
        data.append({
            'id': reg.id,
            'colaborador_id': reg.colaborador_id,
            'colaborador_nome': reg.colaborador.nome if reg.colaborador else '-',
            'colaborador_cpf': reg.colaborador.cpf or '-' if reg.colaborador else '-',
            'mes': reg.mes,
            'ano': reg.ano,
            'mes_ano': f'{reg.mes:02d}/{reg.ano}',
            'faltas': reg.faltas,
            'acoes': acoes,
        })
    return jsonify({'data': data})


@plr_bp.route('/assiduidade/<int:id>/json')
def assiduidade_json(id):
    """Retorna um registro de assiduidade em JSON para o modal de edição."""
    reg = PlrAssiduidade.query.get_or_404(id)
    return jsonify(reg.to_dict())


@plr_bp.route('/assiduidade/nova', methods=['POST'])
def assiduidade_nova():
    """Cria um novo registro de assiduidade."""
    colaborador_id = request.form.get('colaborador_id', type=int)
    mes = request.form.get('mes', type=int)
    ano = request.form.get('ano', type=int)
    faltas = request.form.get('faltas', type=int)
    if not colaborador_id or not mes or not ano or mes < 1 or mes > 12 or ano < 2000 or ano > 2100:
        flash('Colaborador, mês (1-12) e ano são obrigatórios.', 'danger')
        return redirect(url_for('plr.assiduidade_index'))
    faltas = max(0, faltas) if faltas is not None else 0
    existente = PlrAssiduidade.query.filter_by(
        colaborador_id=colaborador_id, mes=mes, ano=ano
    ).first()
    if existente:
        flash(f'Já existe registro de assiduidade para este colaborador em {mes:02d}/{ano}. Edite o existente.', 'warning')
        return redirect(url_for('plr.assiduidade_index'))
    reg = PlrAssiduidade(colaborador_id=colaborador_id, mes=mes, ano=ano, faltas=faltas)
    db.session.add(reg)
    db.session.commit()
    flash('Assiduidade cadastrada com sucesso.', 'success')
    return redirect(url_for('plr.assiduidade_index'))


@plr_bp.route('/assiduidade/<int:id>/editar', methods=['POST'])
def assiduidade_editar(id):
    """Atualiza um registro de assiduidade."""
    reg = PlrAssiduidade.query.get_or_404(id)
    faltas = request.form.get('faltas', type=int)
    reg.faltas = max(0, faltas) if faltas is not None else 0
    db.session.commit()
    flash('Assiduidade atualizada com sucesso.', 'success')
    return redirect(url_for('plr.assiduidade_index'))


@plr_bp.route('/assiduidade/<int:id>/excluir', methods=['POST'])
def assiduidade_excluir(id):
    """Exclui um registro de assiduidade."""
    reg = PlrAssiduidade.query.get_or_404(id)
    db.session.delete(reg)
    db.session.commit()
    flash('Registro de assiduidade excluído.', 'success')
    return redirect(url_for('plr.assiduidade_index'))
