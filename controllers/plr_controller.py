"""
Controller do módulo PLR: avaliações do colaborador, modelos de PLR e cargo/salário.
"""
import json
import os
import re
import tempfile
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from flask_wtf.csrf import generate_csrf
from datetime import datetime
from sqlalchemy import func, and_, or_
import pandas as pd
from models.database import db
from models.plr import ModeloPLR, PLRColaborador, EfetivoPLR
from models.cargo_salario import CargoSalario
from models.colaborador import Colaborador
from models.centro_custo import CentroCusto
from models.cargo import Cargo
from models.departamento import Departamento
from utils.plr_import_planilha import ler_avaliacoes_planilha_xls

plr_bp = Blueprint('plr', __name__, url_prefix='/plr')

# Critérios padrão de avaliação PLR (tipo e peso em %)
CRITERIOS_PADRAO_PLR = [
    {'tipo': 'Assiduidade', 'valor': '', 'peso': 0.30},
    {'tipo': 'Zero Acidente', 'valor': '', 'peso': 0.15},
    {'tipo': 'Segurança, Limpeza, Organização', 'valor': '', 'peso': 0.25},
    {'tipo': 'Prazo', 'valor': '', 'peso': 0.30},
]


@plr_bp.before_request
@login_required
def _login_required():
    pass


# ---------- Avaliações PLR ----------

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


@plr_bp.route('/avaliacoes/')
def avaliacoes_index():
    """Lista avaliações PLR dos colaboradores."""
    lista = (
        PLRColaborador.query
        .order_by(PLRColaborador.data.desc(), PLRColaborador.id.desc())
        .all()
    )
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
    )


@plr_bp.route('/avaliacoes/dados')
def avaliacoes_dados():
    """Retorna JSON com as avaliações para DataTables (AJAX)."""
    lista = (
        PLRColaborador.query
        .order_by(PLRColaborador.data.desc(), PLRColaborador.id.desc())
        .all()
    )
    csrf = generate_csrf()
    data = []
    for av in lista:
        nota = av.nota_media_avaliacao()
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
            'assiduidade': f'{_valor_por_tipo(av.avaliacao, "Assiduidade"):.1f}' if _valor_por_tipo(av.avaliacao, "Assiduidade") is not None else '-',
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
        Colaborador.query.filter(Colaborador.data_admissao <= ultimo_dia)
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
    data = []
    for c in colaboradores:
        av = avaliacoes_mes.get(c.id)
        if equipe_filtro:
            if not av or not av.equipe_alocada or not isinstance(av.equipe_alocada, list):
                continue
            equipes_str = [str(e).strip() for e in av.equipe_alocada if e]
            if equipe_filtro not in equipes_str:
                continue
        v_assid = _valor_por_tipo(av.avaliacao, 'Assiduidade') if av else None
        v_zero = _valor_por_tipo(av.avaliacao, 'Zero Acidente') if av else None
        v_seg = _valor_por_tipo(av.avaliacao, 'Segurança, Limpeza, Organização') if av else None
        v_prazo = _valor_por_tipo(av.avaliacao, 'Prazo') if av else None
        nota = av.nota_media_avaliacao() if av else None
        total_pct = f'{(nota / 10.0) * 100:.1f}%' if nota is not None else None
        data.append({
            'colaborador_id': c.id,
            'nome': c.nome,
            'cpf': c.cpf or '',
            'cargo': c.cargo.nome if c.cargo else '',
            'data_admissao': c.data_admissao.strftime('%d/%m/%Y') if c.data_admissao else '',
            'data_demissao': c.data_demissao.strftime('%d/%m/%Y') if c.data_demissao else '',
            'avaliacao_id': av.id if av else None,
            'centro_custo_id': av.centro_custo_id if av else None,
            'centro_custo_nome': (av.centro_custo.codigo or av.centro_custo.nome) if av and av.centro_custo else '',
            'modelo_plr_id': av.PlrModelo_id if av else None,
            'equipe_alocada': (', '.join(av.equipe_alocada) if av.equipe_alocada else '') if av else '',
            'assiduidade': v_assid,
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
                flash('Informe ao menos um critério de avaliação.', 'danger')
                return render_template('plr/avaliacao_form.html', centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)
            avaliacao = json.loads(avaliacao_json)
        except json.JSONDecodeError:
            flash('Formato de avaliação inválido.', 'danger')
            return render_template('plr/avaliacao_form.html', centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)

        if not colaborador_id or not data_str:
            flash('Colaborador e data são obrigatórios.', 'danger')
            return render_template('plr/avaliacao_form.html', centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)

        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Data inválida.', 'danger')
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
            flash('Formato de avaliação inválido.', 'danger')
            return render_template('plr/avaliacao_form.html', reg=reg, centros=centros, colaboradores=colaboradores, modelos=modelos, avaliacao_list=[], criterios_padrao=CRITERIOS_PADRAO_PLR)
        db.session.commit()
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


def _cpf_apenas_digitos(cpf):
    """Retorna CPF apenas com dígitos para comparação."""
    if cpf is None:
        return ''
    return re.sub(r'\D', '', str(cpf))


@plr_bp.route('/avaliacoes/importar', methods=['POST'])
def avaliacoes_importar():
    """Importa avaliações a partir da planilha Acompanhamento Mensal - MOD (.xls)."""
    arquivo = request.files.get('arquivo')
    if not arquivo or arquivo.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))

    if not arquivo.filename.lower().endswith('.xls'):
        flash('Use um arquivo Excel no formato .xls (Acompanhamento Mensal - MOD).', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))

    modelo_plr_id = request.form.get('modelo_plr_id') or None
    if modelo_plr_id:
        modelo_plr_id = int(modelo_plr_id)

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix='.xls')
        os.close(fd)
        arquivo.save(temp_path)
        linhas = ler_avaliacoes_planilha_xls(temp_path)
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

    # Mapas CPF (só dígitos) -> Colaborador e código obra -> CentroCusto
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

        # Evitar duplicata: mesmo colaborador, mesmo centro, mesma data
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


# ---------- Efetivo PLR (importação Excel com mapeamento) ----------

# Ano e mês vêm do formulário (digitados); os demais campos podem ser mapeados do Excel
CAMPOS_EFETIVO_PLR = [
    ('cpf', 'CPF'),
    ('nome', 'Nome'),
    ('funcao', 'Função'),
    ('salario', 'Salário'),
    ('data_nascimento', 'Data Nascimento'),
    ('data_demissao', 'Data Demissão'),
    ('secao', 'Seção'),
    ('data_admissao', 'Data Admissão'),
    ('chapa', 'Chapa'),
]


@plr_bp.route('/efetivo/preview-excel', methods=['POST'])
def efetivo_preview_excel():
    """Retorna as colunas da primeira aba do arquivo Excel para mapeamento."""
    arquivo = request.files.get('arquivo')
    if not arquivo or arquivo.filename == '':
        return jsonify({'success': False, 'message': 'Nenhum arquivo selecionado.'}), 400
    if not arquivo.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'message': 'Use um arquivo Excel (.xlsx ou .xls).'}), 400
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(arquivo.filename)[1])
        os.close(fd)
        arquivo.save(temp_path)
        engine = 'openpyxl' if temp_path.lower().endswith('.xlsx') else 'xlrd'
        df = pd.read_excel(temp_path, sheet_name=0, engine=engine, nrows=0)
        colunas = [str(c).strip() for c in df.columns.tolist()]
        return jsonify({'success': True, 'colunas': colunas})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _parse_data_efetivo(val):
    """Converte valor para date; aceita datetime, string, NaN ou NaT."""
    # Pandas usa NaT para datas vazias; pd.isna cobre NaN/NaT em qualquer tipo
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        # Se pd.isna não aceitar o tipo de val, seguimos com as demais verificações
        pass
    if hasattr(val, "date"):
        # datetime.date ou datetime.datetime
        try:
            return val.date()
        except Exception:
            return None
    try:
        # Tenta converter strings, inteiros, etc.
        return pd.to_datetime(val).date()
    except Exception:
        return None


def _parse_num_efetivo(val):
    """Converte para int ou None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if isinstance(val, float) and val == int(val):
            return int(val)
        return int(float(str(val).replace(',', '.')))
    except (ValueError, TypeError):
        return None


def _parse_decimal_efetivo(val):
    """Converte para float para salário."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        s = str(val).replace(',', '.').strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


@plr_bp.route('/efetivo/importar', methods=['POST'])
def efetivo_importar():
    """Importa efetivo a partir de Excel com mapeamento de colunas."""
    arquivo = request.files.get('arquivo')
    if not arquivo or arquivo.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))
    if not arquivo.filename.lower().endswith(('.xlsx', '.xls')):
        flash('Use um arquivo Excel (.xlsx ou .xls).', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))

    # Ano e mês vêm do formulário (digitados); não do Excel
    ano_raw = request.form.get('ano') or request.form.get('ano_ref')
    mes_raw = request.form.get('mes') or request.form.get('mes_ref')
    try:
        ano = int(ano_raw) if ano_raw and str(ano_raw).strip() else None
        mes = int(mes_raw) if mes_raw and str(mes_raw).strip() else None
    except (ValueError, TypeError):
        ano = mes = None
    if ano is None or mes is None or not (1 <= mes <= 12):
        flash('Informe o ano e o mês de referência (mês de 1 a 12).', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))

    mapping_raw = request.form.get('mapping')
    mapping = {}
    if mapping_raw:
        try:
            mapping = json.loads(mapping_raw)
        except json.JSONDecodeError:
            pass

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(arquivo.filename)[1])
        os.close(fd)
        arquivo.save(temp_path)
        engine = 'openpyxl' if temp_path.lower().endswith('.xlsx') else 'xlrd'
        df = pd.read_excel(temp_path, sheet_name=0, engine=engine)

        inseridos = 0
        erros = []

        for idx, row in df.iterrows():
            try:
                # Montar valores a partir do mapeamento (chave = campo do sistema, valor = nome da coluna no Excel)
                get_val = lambda col: row.get(mapping[col], None) if mapping.get(col) else None

                cpf = get_val('cpf')
                if cpf is not None:
                    cpf = re.sub(r'\D', '', str(cpf))
                nome = get_val('nome')
                if nome is not None:
                    nome = str(nome).strip() or None
                funcao = get_val('funcao')
                if funcao is not None:
                    funcao = str(funcao).strip() or None
                salario = _parse_decimal_efetivo(get_val('salario'))
                data_nascimento = _parse_data_efetivo(get_val('data_nascimento'))
                data_demissao = _parse_data_efetivo(get_val('data_demissao'))
                secao = get_val('secao')
                if secao is not None:
                    secao = str(secao).strip() or None
                data_admissao = _parse_data_efetivo(get_val('data_admissao'))
                chapa = get_val('chapa')
                if chapa is not None:
                    chapa = str(chapa).strip() or None

                reg = EfetivoPLR(
                    ano=ano,
                    mes=mes,
                    cpf=cpf or None,
                    nome=nome,
                    funcao=funcao,
                    salario=salario,
                    data_nascimento=data_nascimento,
                    data_demissao=data_demissao,
                    secao=secao,
                    data_admissao=data_admissao,
                    chapa=chapa,
                )
                db.session.add(reg)
                inseridos += 1
            except Exception as e:
                erros.append(f'Linha {idx + 2}: {str(e)}')

        db.session.commit()
        msg = f'Importação do efetivo concluída: {inseridos} registro(s) importado(s).'
        if erros:
            msg += f' Erros: {len(erros)} (primeiros: {"; ".join(erros[:3])}).'
        flash(msg, 'success' if inseridos else 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao importar efetivo: {e}', 'danger')
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    return redirect(url_for('plr.avaliacoes_index'))


# ---------- Relatório de Avaliação ----------

@plr_bp.route('/relatorio-avaliacao/', methods=['GET', 'POST'])
def relatorio_avaliacao():
    """Relatório de avaliação: filtro por modelo PLR e período; média quando mais de uma avaliação por colaborador."""
    modelos = ModeloPLR.query.filter_by(ativo=True).order_by(ModeloPLR.nome).all()
    resultado = None
    ano_sugerido = datetime.now().year
    if request.method == 'POST':
        modelo_plr_id = request.form.get('modelo_plr_id')
        mes_inicio = request.form.get('mes_inicio')
        mes_fim = request.form.get('mes_fim')
        ano = request.form.get('ano')
        if not ano:
            flash('Informe o ano.', 'danger')
            return render_template('plr/relatorio_avaliacao.html', modelos=modelos)

        ano = int(ano)
        mes_i = int(mes_inicio or 1)
        mes_f = int(mes_fim or 12)
        from datetime import date
        data_inicio = date(ano, mes_i, 1)
        if mes_f == 12:
            data_fim = date(ano, 12, 31)
        else:
            data_fim = date(ano, mes_f + 1, 1)
            from datetime import timedelta
            data_fim = data_fim - timedelta(days=1)

        q = PLRColaborador.query.filter(
            PLRColaborador.data >= data_inicio,
            PLRColaborador.data <= data_fim,
        )
        if modelo_plr_id:
            q = q.filter(PLRColaborador.PlrModelo_id == int(modelo_plr_id))
        avaliacoes = q.order_by(PLRColaborador.colaborador_id, PLRColaborador.data).all()

        # Agrupar por colaborador e calcular média
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

    return render_template('plr/relatorio_avaliacao.html', modelos=modelos, resultado=resultado, ano_sugerido=ano_sugerido)


# ---------- Relatório Planilha (Cálculo PLR - formato Excel) ----------

def _relatorio_planilha_calcular(ano_inicio, mes_inicio, ano_fim, mes_fim, modelo_plr_id, equipe_filtro=None):
    """
    Retorna (resultado, meses_colunas, data_fechamento) para o relatório planilha.
    Suporta períodos que abrangem anos diferentes.
    """
    from datetime import date, timedelta
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
    """Retorna JSON com os dados da planilha para DataTables (AJAX). Params: ano_inicio, mes_inicio, ano_fim, mes_fim, modelo_plr_id."""
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
        resultado, meses_colunas, data_fechamento = _relatorio_planilha_calcular(ano_inicio, mes_inicio, ano_fim, mes_fim, modelo_plr_id, equipe_filtro)
    except Exception as e:
        return jsonify({'error': str(e), 'data': [], 'meses_colunas': [], 'data_fechamento': None}), 500

    MESES_ABREV = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ']
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
    Dados da tabela são carregados via AJAX (DataTables) ao clicar em Gerar.
    """
    modelos = ModeloPLR.query.filter_by(ativo=True).order_by(ModeloPLR.nome).all()
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
                return render_template('plr/relatorio_planilha.html', modelos=modelos, equipes=equipes, ano_sugerido=ano_sugerido)
        else:
            ano_inicio = request.form.get('ano_inicio') or request.form.get('ano')
            ano_fim = request.form.get('ano_fim') or ano_inicio
            mes_inicio = request.form.get('mes_inicio', '1')
            mes_fim = request.form.get('mes_fim', '12')
            if not ano_inicio:
                flash('Informe o período.', 'danger')
                return render_template('plr/relatorio_planilha.html', modelos=modelos, equipes=equipes, ano_sugerido=ano_sugerido)
            ano_inicio = int(ano_inicio)
            ano_fim = int(ano_fim)
        try:
            resultado, meses_colunas, data_fechamento = _relatorio_planilha_calcular(
                ano_inicio, mes_inicio, ano_fim, mes_fim, modelo_plr_id, equipe_filtro
            )
        except Exception as e:
            flash(f'Erro ao gerar relatório: {e}', 'danger')
            return render_template('plr/relatorio_planilha.html', modelos=modelos, equipes=equipes, ano_sugerido=ano_sugerido)
        # Serializar para o template (fallback quando formulário é enviado por POST sem AJAX)
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
            modelos=modelos,
            equipes=equipes,
            ano_sugerido=ano_sugerido,
            planilha_json=planilha_json,
        )

    return render_template(
        'plr/relatorio_planilha.html',
        modelos=modelos,
        equipes=equipes,
        ano_sugerido=ano_sugerido,
        planilha_json=None,
    )


# ---------- Modelos de PLR ----------

@plr_bp.route('/modelos/')
def modelos_index():
    """Lista modelos de PLR."""
    lista = ModeloPLR.query.order_by(ModeloPLR.nome).all()
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    return render_template('plr/modelos_index.html', modelos=lista, departamentos=departamentos)


@plr_bp.route('/modelos/novo', methods=['GET', 'POST'])
def modelo_novo():
    """Novo modelo de PLR."""
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    if request.method == 'POST':
        nome = request.form.get('nome')
        if not nome:
            flash('Nome é obrigatório.', 'danger')
            return render_template('plr/modelo_form.html', departamentos=departamentos)
        m = ModeloPLR(
            nome=nome.strip(),
            descricao=request.form.get('descricao') or None,
            ativo=request.form.get('ativo') == '1',
            forma_calculo_colaborador=request.form.get('forma_calculo_colaborador') or None,
            forma_calculo_final=request.form.get('forma_calculo_final') or None,
        )
        pesos_raw = request.form.get('pesos_colaboradores')
        if pesos_raw:
            try:
                m.pesos_colaboradores = json.loads(pesos_raw)
            except json.JSONDecodeError:
                pass
        config_raw = request.form.get('config_calculo_final')
        if config_raw:
            try:
                m.config_calculo_final = json.loads(config_raw)
            except json.JSONDecodeError:
                pass
        db.session.add(m)
        db.session.flush()
        for dep_id in request.form.getlist('departamento_ids'):
            try:
                dep = Departamento.query.get(int(dep_id))
                if dep:
                    m.departamentos.append(dep)
            except (ValueError, TypeError):
                pass
        db.session.commit()
        flash('Modelo de PLR criado.', 'success')
        return redirect(url_for('plr.modelos_index'))
    return render_template('plr/modelo_form.html', modelo=None, departamentos=departamentos)


@plr_bp.route('/modelos/editar/<int:id>', methods=['GET', 'POST'])
def modelo_editar(id):
    """Editar modelo de PLR."""
    m = ModeloPLR.query.get_or_404(id)
    departamentos = Departamento.query.filter_by(status='Ativo').order_by(Departamento.nome).all()
    if request.method == 'POST':
        m.nome = request.form.get('nome', m.nome).strip()
        m.descricao = request.form.get('descricao') or None
        m.ativo = request.form.get('ativo') == '1'
        m.forma_calculo_colaborador = request.form.get('forma_calculo_colaborador') or None
        m.forma_calculo_final = request.form.get('forma_calculo_final') or None
        pesos_raw = request.form.get('pesos_colaboradores')
        if pesos_raw:
            try:
                m.pesos_colaboradores = json.loads(pesos_raw)
            except json.JSONDecodeError:
                pass
        config_raw = request.form.get('config_calculo_final')
        if config_raw:
            try:
                m.config_calculo_final = json.loads(config_raw)
            except json.JSONDecodeError:
                pass
        m.departamentos = []
        for dep_id in request.form.getlist('departamento_ids'):
            try:
                dep = Departamento.query.get(int(dep_id))
                if dep:
                    m.departamentos.append(dep)
            except (ValueError, TypeError):
                pass
        db.session.commit()
        flash('Modelo de PLR atualizado.', 'success')
        return redirect(url_for('plr.modelos_index'))
    return render_template('plr/modelo_form.html', modelo=m, departamentos=departamentos)


@plr_bp.route('/modelos/excluir/<int:id>', methods=['POST'])
def modelo_excluir(id):
    """Excluir modelo de PLR."""
    m = ModeloPLR.query.get_or_404(id)
    if m.avaliacoes.count() > 0:
        flash('Não é possível excluir: existem avaliações vinculadas a este modelo.', 'danger')
        return redirect(url_for('plr.modelos_index'))
    db.session.delete(m)
    db.session.commit()
    flash('Modelo de PLR excluído.', 'success')
    return redirect(url_for('plr.modelos_index'))


# ---------- Cargo Salário (mês/ano + salário) ----------

@plr_bp.route('/cargos-salarios/')
def cargos_salarios_index():
    """Lista vínculos cargo x mês/ano x salário."""
    lista = CargoSalario.query.order_by(CargoSalario.ano.desc(), CargoSalario.mes.desc()).all()
    cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
    return render_template('plr/cargos_salarios_index.html', itens=lista, cargos=cargos)


@plr_bp.route('/cargos-salarios/novo', methods=['GET', 'POST'])
def cargo_salario_novo():
    """Novo vínculo cargo / mês / ano / salário."""
    cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
    if request.method == 'POST':
        cargo_id = request.form.get('cargo_id')
        mes = request.form.get('mes')
        ano = request.form.get('ano')
        salario = request.form.get('salario')
        if not all([cargo_id, mes, ano, salario]):
            flash('Preencha cargo, mês, ano e salário.', 'danger')
            return render_template('plr/cargo_salario_form.html', reg=None, cargos=cargos)
        try:
            mes, ano = int(mes), int(ano)
            salario = float(salario.replace(',', '.'))
        except (ValueError, TypeError):
            flash('Mês, ano ou salário inválidos.', 'danger')
            return render_template('plr/cargo_salario_form.html', reg=None, cargos=cargos)
        existente = CargoSalario.query.filter_by(cargo_id=int(cargo_id), mes=mes, ano=ano).first()
        if existente:
            flash('Já existe registro para este cargo no mês/ano informado.', 'danger')
            return render_template('plr/cargo_salario_form.html', reg=None, cargos=cargos)
        reg = CargoSalario(cargo_id=int(cargo_id), mes=mes, ano=ano, salario=salario)
        db.session.add(reg)
        db.session.commit()
        flash('Salário do cargo registrado.', 'success')
        return redirect(url_for('plr.cargos_salarios_index'))
    return render_template('plr/cargo_salario_form.html', reg=None, cargos=cargos)


@plr_bp.route('/cargos-salarios/editar/<int:id>', methods=['GET', 'POST'])
def cargo_salario_editar(id):
    """Editar cargo salário."""
    reg = CargoSalario.query.get_or_404(id)
    cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
    if request.method == 'POST':
        reg.mes = int(request.form.get('mes'))
        reg.ano = int(request.form.get('ano'))
        reg.salario = float(request.form.get('salario').replace(',', '.'))
        db.session.commit()
        flash('Salário do cargo atualizado.', 'success')
        return redirect(url_for('plr.cargos_salarios_index'))
    return render_template('plr/cargo_salario_form.html', reg=reg, cargos=cargos)


@plr_bp.route('/cargos-salarios/excluir/<int:id>', methods=['POST'])
def cargo_salario_excluir(id):
    """Excluir cargo salário."""
    reg = CargoSalario.query.get_or_404(id)
    db.session.delete(reg)
    db.session.commit()
    flash('Registro excluído.', 'success')
    return redirect(url_for('plr.cargos_salarios_index'))


@plr_bp.route('/')
def index():
    """Redireciona para avaliações."""
    return redirect(url_for('plr.avaliacoes_index'))
