"""
Rotas e lógica de Avaliações PLR: listagem, nova/editar/excluir, importar planilha, por-mês.
"""
import json
import os
import re
import tempfile
from datetime import datetime

from flask import request, redirect, url_for, flash, jsonify, render_template


def _is_ajax():
    """Indica se a requisição é AJAX (ex.: submit do modal sem fechar)."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'
from flask_wtf.csrf import generate_csrf
from sqlalchemy import func

from models.database import db
from models.plr import PLRColaborador, EfetivoPLR, PlrAssiduidade
from models.colaborador import Colaborador
from models.centro_custo import CentroCusto
from models.plr import ModeloPLR
from models.departamento import Departamento
from utils.plr_import_planilha import ler_avaliacoes_planilha
from utils.plr_calculo import assiduidade_pct_por_faltas, nota_media_com_assiduidade

from . import plr_bp
from .constantes import CRITERIOS_PADRAO_PLR
from .efetivo import CAMPOS_EFETIVO_PLR


def _avaliacao_list_for_form(avaliacao_field):
    """Converte campo avaliacao (JSON) em lista de dicts para o formulário."""
    if not avaliacao_field:
        return list(CRITERIOS_PADRAO_PLR)
    if isinstance(avaliacao_field, list):
        return [x if isinstance(x, dict) else {'tipo': '', 'valor': x} for x in avaliacao_field]
    if isinstance(avaliacao_field, dict):
        return [avaliacao_field]
    return list(CRITERIOS_PADRAO_PLR)


def _valor_por_tipo(avaliacao, tipo):
    """Retorna o valor do critério pelo tipo na lista avaliacao, ou None."""
    if not avaliacao or not isinstance(avaliacao, list):
        return None
    for item in avaliacao:
        if isinstance(item, dict) and item.get('tipo') == tipo:
            v = item.get('valor')
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
    return None


def _equipes_distintas_plr():
    """Retorna lista de nomes de equipe distintos em PLRColaborador.equipe_alocada."""
    registros = PLRColaborador.query.filter(PLRColaborador.equipe_alocada.isnot(None)).all()
    seen = set()
    result = []
    for av in registros:
        if not isinstance(av.equipe_alocada, list):
            continue
        for nome in av.equipe_alocada:
            if not nome or not isinstance(nome, str):
                continue
            s = nome.strip()
            if s and s not in seen:
                seen.add(s)
                result.append(s)
    return sorted(result)


def _cpf_apenas_digitos(cpf):
    """Retorna CPF apenas com dígitos para comparação."""
    if cpf is None:
        return ''
    return re.sub(r'\D', '', str(cpf))


@plr_bp.route('/avaliacoes/')
def avaliacoes_index():
    """Lista avaliações PLR dos colaboradores."""
    lista = (
        PLRColaborador.query
        .order_by(PLRColaborador.data.desc(), PLRColaborador.id.desc())
        .all()
    )
    ano_atual = datetime.now().year
    anos_db = db.session.query(func.extract('year', PLRColaborador.data)).distinct().all()
    anos_set = {int(r[0]) for r in anos_db if r[0] is not None}
    for a in range(ano_atual, ano_atual - 5, -1):
        anos_set.add(a)
    anos = sorted(anos_set, reverse=True)
    centros = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.nome).all()
    colaboradores = Colaborador.query.filter(Colaborador.status == 'Ativo').order_by(Colaborador.nome).all()
    modelos = ModeloPLR.query.filter_by(ativo=True).order_by(ModeloPLR.nome).all()
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    equipes = _equipes_distintas_plr()
    avaliacoes_com_lista = [
        {'av': av, 'avaliacao_list_editar': _avaliacao_list_for_form(av.avaliacao)}
        for av in lista
    ]
    return render_template(
        'plr/avaliacoes_index.html',
        avaliacoes=lista,
        avaliacoes_com_lista=avaliacoes_com_lista,
        centros=centros,
        colaboradores=colaboradores,
        modelos=modelos,
        departamentos=departamentos,
        equipes=equipes,
        criterios_padrao=CRITERIOS_PADRAO_PLR,
        campos_efetivo=CAMPOS_EFETIVO_PLR,
        anos=anos,
    )


@plr_bp.route('/avaliacoes/dados')
def avaliacoes_dados():
    """Retorna JSON com as avaliações para DataTables (AJAX). Params: ano, mes, departamento_id (opcionais)."""
    ano = request.args.get('ano', type=int)
    mes = request.args.get('mes', type=int)
    # Suporta departamento_id[] (jQuery) ou múltiplos departamento_id
    dept_ids = request.args.getlist('departamento_id[]') or request.args.getlist('departamento_id')
    departamento_ids = []
    for vid in dept_ids:
        try:
            departamento_ids.append(int(vid))
        except (TypeError, ValueError):
            continue
    query = PLRColaborador.query
    if ano is not None:
        query = query.filter(func.extract('year', PLRColaborador.data) == ano)
    if mes is not None and 1 <= mes <= 12:
        query = query.filter(func.extract('month', PLRColaborador.data) == mes)
    if departamento_ids:
        query = query.join(Colaborador, PLRColaborador.colaborador_id == Colaborador.id).filter(
            Colaborador.departamento_id.in_(departamento_ids)
        )
    lista = query.order_by(PLRColaborador.data.desc(), PLRColaborador.id.desc()).all()

    colab_ids = list({av.colaborador_id for av in lista})
    assid_map = {}
    if colab_ids:
        for rec in PlrAssiduidade.query.filter(PlrAssiduidade.colaborador_id.in_(colab_ids)).all():
            assid_map[(rec.colaborador_id, rec.mes, rec.ano)] = rec.faltas

    csrf = generate_csrf()
    data = []
    for av in lista:
        av_mes = av.data.month if av.data else None
        av_ano = av.data.year if av.data else None
        faltas_rec = assid_map.get((av.colaborador_id, av_mes, av_ano))
        assid_pct = assiduidade_pct_por_faltas(faltas_rec) if faltas_rec is not None else None

        if assid_pct is not None:
            nota = nota_media_com_assiduidade(av.avaliacao, assid_pct)
            assid_val = assid_pct / 10.0
            assid_label = f'{assid_val:.2f} ({int(faltas_rec)}f)'
        else:
            nota = av.nota_media_avaliacao()
            raw = _valor_por_tipo(av.avaliacao, 'Assiduidade')
            assid_label = f'{raw:.2f}' if raw is not None else '-'

        total_pct = f'{(nota / 10.0) * 100:.1f}%' if nota is not None else '-'
        excluir_url = url_for('plr.avaliacao_excluir', id=av.id)
        acoes = (
            f'<button type="button" class="btn btn-sm btn-primary" data-bs-toggle="modal" '
            f'data-bs-target="#modalEditarAvaliacao{av.id}" title="Editar"><i class="fas fa-edit"></i></button> '
            f'<form method="POST" action="{excluir_url}" class="d-inline" onsubmit="return confirm(\'Excluir esta avaliação?\');">'
            f'<input type="hidden" name="csrf_token" value="{csrf}">'
            f'<button type="submit" class="btn btn-sm btn-danger" title="Excluir"><i class="fas fa-trash"></i></button></form>'
        )
        data.append({
            'id': av.id,
            'data': av.data.strftime('%d/%m/%Y') if av.data else '-',
            'colaborador_nome': av.colaborador.nome if av.colaborador else '-',
            'obra_codigo': av.centro_custo.codigo if av.centro_custo else '-',
            'equipe_alocada': ', '.join(av.equipe_alocada) if av.equipe_alocada else '-',
            'assiduidade': assid_label,
            'zero_acidente': f'{_valor_por_tipo(av.avaliacao, "Zero Acidente"):.1f}' if _valor_por_tipo(av.avaliacao, "Zero Acidente") is not None else '-',
            'seguranca': f'{_valor_por_tipo(av.avaliacao, "Segurança, Limpeza, Organização"):.1f}' if _valor_por_tipo(av.avaliacao, "Segurança, Limpeza, Organização") is not None else '-',
            'prazo': f'{_valor_por_tipo(av.avaliacao, "Prazo"):.1f}' if _valor_por_tipo(av.avaliacao, "Prazo") is not None else '-',
            'total_pct': total_pct,
            'acoes': acoes,
        })
    return jsonify({'data': data})


@plr_bp.route('/avaliacoes/por-mes')
def avaliacoes_por_mes():
    """
    Retorna colaboradores ativos (não demitidos até o fim do mês) no mes/ano
    e a avaliação PLR existente para aquele mês (primeiro dia do mês), se houver.
    Params: ano, mes, departamento_id (opcional), equipe (opcional).
    """
    from datetime import date, timedelta
    ano = request.args.get('ano')
    mes = request.args.get('mes')
    departamento_id = request.args.get('departamento_id', '').strip()
    equipe_filtro = request.args.get('equipe', '').strip()
    if not ano or not mes:
        return jsonify({'error': 'Informe ano e mês.', 'data': []}), 400
    try:
        ano = int(ano)
        mes = int(mes)
        if mes < 1 or mes > 12:
            raise ValueError('Mês inválido')
    except ValueError:
        return jsonify({'error': 'Ano ou mês inválido.', 'data': []}), 400
    ultimo_dia = date(ano, mes, 1) + timedelta(days=32)
    ultimo_dia = ultimo_dia.replace(day=1) - timedelta(days=1)
    primeiro_dia = date(ano, mes, 1)
    q = (
        Colaborador.query.filter(Colaborador.data_admissao <= date(ano,mes,15))
        .filter(
            (Colaborador.data_demissao.is_(None)) | (Colaborador.data_demissao > ultimo_dia)
        )
    )
    if departamento_id:
        try:
            q = q.filter(Colaborador.departamento_id == int(departamento_id))
        except ValueError:
            pass
    colaboradores = q.order_by(Colaborador.nome).all()
    avaliacoes_mes = {
        av.colaborador_id: av
        for av in PLRColaborador.query.filter(
            PLRColaborador.data == primeiro_dia
        ).all()
    }
    # Fallback: se não houver avaliação no mês, carregar Obra/Equipe do mês anterior (sem salvar)
    colab_ids = [c.id for c in colaboradores]
    prev_por_colab = {}
    if colab_ids:
        prev_q = (
            PLRColaborador.query
            .filter(PLRColaborador.colaborador_id.in_(colab_ids))
            .filter(PLRColaborador.data < primeiro_dia)
            .order_by(PLRColaborador.colaborador_id.asc(), PLRColaborador.data.desc(), PLRColaborador.id.desc())
            .all()
        )
        for pav in prev_q:
            if pav.colaborador_id not in prev_por_colab:
                prev_por_colab[pav.colaborador_id] = pav
    efetivos_mes = EfetivoPLR.query.filter_by(data=primeiro_dia).all()
    cpf_to_secao = {}
    for ef in efetivos_mes:
        if ef.cpf:
            dig = re.sub(r'\D', '', str(ef.cpf))
            if len(dig) == 11:
                cpf_to_secao[dig] = ef.secao or ''
    assid_mes_map = {}
    colab_ids_all = [c.id for c in colaboradores]
    if colab_ids_all:
        for rec in PlrAssiduidade.query.filter(
            PlrAssiduidade.colaborador_id.in_(colab_ids_all),
            PlrAssiduidade.mes == mes,
            PlrAssiduidade.ano == ano,
        ).all():
            assid_mes_map[rec.colaborador_id] = rec.faltas

    data = []
    for c in colaboradores:
        av = avaliacoes_mes.get(c.id)
        av_ref = av or prev_por_colab.get(c.id)
        if equipe_filtro:
            if not av_ref or not av_ref.equipe_alocada or not isinstance(av_ref.equipe_alocada, list):
                continue
            equipes_str = [str(e).strip() for e in av_ref.equipe_alocada if e]
            if equipe_filtro not in equipes_str:
                continue

        faltas_rec = assid_mes_map.get(c.id)
        assid_pct = assiduidade_pct_por_faltas(faltas_rec) if faltas_rec is not None else None

        if av and assid_pct is not None:
            v_assid = assid_pct / 10.0
            nota = nota_media_com_assiduidade(av.avaliacao, assid_pct)
        elif av:
            v_assid = _valor_por_tipo(av.avaliacao, 'Assiduidade')
            nota = av.nota_media_avaliacao()
        else:
            v_assid = None
            nota = None

        v_zero = _valor_por_tipo(av.avaliacao, 'Zero Acidente') if av else None
        v_seg = _valor_por_tipo(av.avaliacao, 'Segurança, Limpeza, Organização') if av else None
        v_prazo = _valor_por_tipo(av.avaliacao, 'Prazo') if av else None
        total_pct = f'{(nota / 10.0) * 100:.1f}%' if nota is not None else None
        cpf_dig = re.sub(r'\D', '', str(c.cpf or '')) if c.cpf else ''
        secao_efetivo = cpf_to_secao.get(cpf_dig, '') if len(cpf_dig) == 11 else ''
        centro_custo_id = av.centro_custo_id if av else (av_ref.centro_custo_id if av_ref else None)
        centro_custo_nome = ''
        if av and av.centro_custo:
            centro_custo_nome = (av.centro_custo.codigo or av.centro_custo.nome) or ''
        elif av_ref and av_ref.centro_custo:
            centro_custo_nome = (av_ref.centro_custo.codigo or av_ref.centro_custo.nome) or ''
        equipe_str = ''
        if av_ref and av_ref.equipe_alocada:
            equipe_str = ', '.join(av_ref.equipe_alocada) if isinstance(av_ref.equipe_alocada, list) else str(av_ref.equipe_alocada)
        data.append({
            'colaborador_id': c.id,
            'nome': c.nome,
            'cpf': c.cpf or '',
            'secao': secao_efetivo,
            'cargo': c.cargo.nome if c.cargo else '',
            'data_admissao': c.data_admissao.strftime('%d/%m/%Y') if c.data_admissao else '',
            'data_demissao': c.data_demissao.strftime('%d/%m/%Y') if c.data_demissao else '',
            'avaliacao_id': av.id if av else None,
            'centro_custo_id': centro_custo_id,
            'centro_custo_nome': centro_custo_nome,
            'modelo_plr_id': av.PlrModelo_id if av else (av_ref.PlrModelo_id if av_ref else None),
            'equipe_alocada': (', '.join(av.equipe_alocada) if av and av.equipe_alocada else equipe_str) if (av or equipe_str) else '',
            'assiduidade': v_assid,
            'assiduidade_faltas': int(faltas_rec) if faltas_rec is not None else None,
            'zero_acidente': v_zero,
            'seguranca': v_seg,
            'prazo': v_prazo,
            'total_pct': total_pct,
        })
    return jsonify({'data': data, 'data_ref': primeiro_dia.isoformat()})


@plr_bp.route('/avaliacoes/nova', methods=['GET', 'POST'])
def avaliacao_nova():
    """Nova avaliação PLR do colaborador."""
    centros = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.nome).all()
    colaboradores = Colaborador.query.filter(Colaborador.status == 'Ativo').order_by(Colaborador.nome).all()
    modelos = ModeloPLR.query.filter_by(ativo=True).order_by(ModeloPLR.nome).all()

    if request.method == 'POST':
        colaborador_id = request.form.get('colaborador_id')
        centro_custo_id = request.form.get('centro_custo_id') or None
        modelo_plr_id = request.form.get('modelo_plr_id') or None
        data_str = request.form.get('data')
        equipe_raw = request.form.get('equipe_alocada', '')
        observacoes = request.form.get('observacoes', '') or None

        try:
            avaliacao_json = request.form.get('avaliacao')
            if not avaliacao_json:
                msg = 'Informe ao menos um critério de avaliação.'
                if _is_ajax():
                    return jsonify({'success': False, 'message': msg}), 400
                flash(msg, 'danger')
                return render_template('plr/avaliacao_form.html', centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)
            avaliacao = json.loads(avaliacao_json)
        except json.JSONDecodeError:
            msg = 'Formato de avaliação inválido.'
            if _is_ajax():
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'danger')
            return render_template('plr/avaliacao_form.html', centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)

        if not colaborador_id or not data_str:
            msg = 'Colaborador e data são obrigatórios.'
            if _is_ajax():
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'danger')
            return render_template('plr/avaliacao_form.html', centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)

        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            msg = 'Data inválida.'
            if _is_ajax():
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'danger')
            return render_template('plr/avaliacao_form.html', centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)

        equipe_alocada = None
        if equipe_raw.strip():
            equipe_alocada = [x.strip() for x in equipe_raw.replace('\r', '').split('\n') if x.strip()]

        if centro_custo_id:
            centro_custo_id = int(centro_custo_id)
        if modelo_plr_id:
            modelo_plr_id = int(modelo_plr_id)

        reg = PLRColaborador(
            colaborador_id=int(colaborador_id),
            centro_custo_id=centro_custo_id,
            PlrModelo_id=modelo_plr_id,
            equipe_alocada=equipe_alocada,
            avaliacao=avaliacao,
            data=data,
            observacoes=observacoes,
        )
        db.session.add(reg)
        db.session.commit()
        if _is_ajax():
            return jsonify({'success': True, 'message': 'Avaliação registrada com sucesso.'})
        flash('Avaliação registrada com sucesso.', 'success')
        return redirect(url_for('plr.avaliacoes_index'))

    avaliacao_list = list(CRITERIOS_PADRAO_PLR)
    return render_template('plr/avaliacao_form.html', centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=avaliacao_list, criterios_padrao=CRITERIOS_PADRAO_PLR)


@plr_bp.route('/avaliacoes/editar/<int:id>', methods=['GET', 'POST'])
def avaliacao_editar(id):
    """Editar avaliação PLR."""
    reg = PLRColaborador.query.get_or_404(id)
    centros = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.nome).all()
    colaboradores = Colaborador.query.order_by(Colaborador.nome).all()
    modelos = ModeloPLR.query.filter_by(ativo=True).order_by(ModeloPLR.nome).all()

    if request.method == 'POST':
        reg.colaborador_id = int(request.form.get('colaborador_id'))
        centro_custo_id = request.form.get('centro_custo_id')
        reg.centro_custo_id = int(centro_custo_id) if centro_custo_id else None
        modelo_plr_id = request.form.get('modelo_plr_id')
        reg.PlrModelo_id = int(modelo_plr_id) if modelo_plr_id else None
        reg.data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
        equipe_raw = request.form.get('equipe_alocada', '')
        reg.equipe_alocada = [x.strip() for x in equipe_raw.replace('\r', '').split('\n') if x.strip()] if equipe_raw.strip() else None
        reg.observacoes = request.form.get('observacoes') or None
        try:
            reg.avaliacao = json.loads(request.form.get('avaliacao', '[]'))
        except json.JSONDecodeError:
            msg = 'Formato de avaliação inválido.'
            if _is_ajax():
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'danger')
            return render_template('plr/avaliacao_form.html', reg=reg, centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)
        db.session.commit()
        if _is_ajax():
            return jsonify({'success': True, 'message': 'Avaliação atualizada.'})
        flash('Avaliação atualizada.', 'success')
        return redirect(url_for('plr.avaliacoes_index'))

    avaliacao_list = []
    if reg.avaliacao:
        if isinstance(reg.avaliacao, list):
            avaliacao_list = [x if isinstance(x, dict) else {'tipo': '', 'valor': x} for x in reg.avaliacao]
        elif isinstance(reg.avaliacao, dict):
            avaliacao_list = [reg.avaliacao]
    return render_template('plr/avaliacao_form.html', reg=reg, centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=avaliacao_list, criterios_padrao=CRITERIOS_PADRAO_PLR)


@plr_bp.route('/avaliacoes/excluir/<int:id>', methods=['POST'])
def avaliacao_excluir(id):
    """Excluir avaliação PLR."""
    reg = PLRColaborador.query.get_or_404(id)
    db.session.delete(reg)
    db.session.commit()
    flash('Avaliação excluída.', 'success')
    return redirect(url_for('plr.avaliacoes_index'))


@plr_bp.route('/avaliacoes/importar', methods=['POST'])
def avaliacoes_importar():
    """Importa avaliações a partir da planilha Acompanhamento Mensal - MOD (.xls ou .xlsx)."""
    arquivo = request.files.get('arquivo')
    if not arquivo or arquivo.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))

    fn = arquivo.filename.lower()
    if not fn.endswith(('.xls', '.xlsx')):
        flash('Use um arquivo Excel no formato .xls ou .xlsx (Acompanhamento Mensal - MOD).', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))

    modelo_plr_id = request.form.get('modelo_plr_id') or None
    if modelo_plr_id:
        modelo_plr_id = int(modelo_plr_id)

    suffix = '.xlsx' if fn.endswith('.xlsx') else '.xls'
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        arquivo.save(temp_path)
        linhas = ler_avaliacoes_planilha(temp_path)
    except Exception as e:
        flash(f'Erro ao ler a planilha: {e}', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    if not linhas:
        flash('Nenhuma avaliação encontrada nas abas no formato MES ANO (ex.: AGO 2025).', 'warning')
        return redirect(url_for('plr.avaliacoes_index'))

    colaboradores = Colaborador.query.filter(Colaborador.cpf.isnot(None)).all()
    cpf_to_colab = {_cpf_apenas_digitos(c.cpf): c for c in colaboradores}
    centros = CentroCusto.query.filter_by(ativo=True).all()
    codigo_to_centro = {str(cc.codigo).strip(): cc for cc in centros}

    inseridos = 0
    ignorados_duplicado = 0
    erros_cpf = set()
    erros_obra = set()
    erro_descricao = set()

    for item in linhas:
        cpf_dig = item['cpf']
        colab = cpf_to_colab.get(cpf_dig)
        if not colab:
            if cpf_dig not in erros_cpf:
                erros_cpf.add(cpf_dig)
                erro_descricao.add(item['data'].strftime('%d/%m/%Y') + ' - ' + cpf_dig)
            continue

        centro = None
        if item.get('obra'):
            centro = codigo_to_centro.get(item['obra'].strip())
            if not centro:
                erros_obra.add(item['obra'].strip())

        existe = PLRColaborador.query.filter(
            PLRColaborador.colaborador_id == colab.id,
            PLRColaborador.data == item['data'],
            (PLRColaborador.centro_custo_id == centro.id if centro else PLRColaborador.centro_custo_id.is_(None)),
        ).first()
        if existe:
            ignorados_duplicado += 1
            continue

        equipe_alocada = None
        if item.get('equipe'):
            equipe_alocada = [str(item['equipe']).strip()]

        reg = PLRColaborador(
            colaborador_id=colab.id,
            centro_custo_id=centro.id if centro else None,
            PlrModelo_id=modelo_plr_id,
            equipe_alocada=equipe_alocada,
            avaliacao=item['avaliacao'],
            data=item['data'],
            observacoes=None,
        )
        db.session.add(reg)
        inseridos += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao salvar: {e}', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))

    msg = f'Importação concluída: {inseridos} avaliação(ões) importada(s).'
    if ignorados_duplicado:
        msg += f' {ignorados_duplicado} linha(s) ignorada(s) (já existente).'
    if erros_cpf:
        for erro in erro_descricao:
            print(erro)
        ex = next(iter(erros_cpf), '')[:3]
        msg += f' CPF não encontrado: {len(erros_cpf)} (ex.: {ex}***).'
    if erros_obra:
        ex = next(iter(erros_obra), '')
        msg += f' Obra não encontrada: {len(erros_obra)} (ex.: {ex}).'
    flash(msg, 'success' if inseridos else 'warning')
    return redirect(url_for('plr.avaliacoes_index'))
