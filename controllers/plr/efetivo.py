"""
Rotas e lógica de Efetivo PLR: importação Excel, listagem, edição e exclusão.
"""
import json
import os
import re
import tempfile
from datetime import datetime, date

import pandas as pd
from flask import request, redirect, url_for, flash, jsonify, render_template
from flask_wtf.csrf import generate_csrf

from sqlalchemy import func

from models.database import db
from models.plr import EfetivoPLR
from models.colaborador import Colaborador
from models.cargo_salario import CargoSalario
from models.cargo import Cargo
from models.departamento import Departamento
from utils.utils import valor_para_str

from . import plr_bp


# Campos do efetivo que podem ser gravados no cadastro de colaboradores (vínculo por CPF).
CAMPOS_SINC_EFETIVO_COLAB = [
    ('nome', 'Nome'),
    ('funcao', 'Cargo (nome da função no efetivo → cargo)'),
    ('salario', 'Salário (tabela cargo × mês do período)'),
    ('data_nascimento', 'Data de nascimento'),
    ('data_demissao', 'Data de demissão'),
    ('secao', 'Departamento (nome da seção no efetivo)'),
    ('data_admissao', 'Data de admissão'),
    ('chapa', 'Chapa / matrícula (dados adicionais)'),
]

_CAMPOS_SINC_PERMITIDOS = frozenset(k for k, _ in CAMPOS_SINC_EFETIVO_COLAB)


def _cpf_normalizado_efetivo(val):
    """Somente dígitos, até 11, preenchido com zeros à esquerda (igual importação Excel)."""
    if val is None:
        return None
    dig = re.sub(r'\D', '', str(val).strip() or '')
    if not dig or len(dig) > 11:
        return None
    return dig.zfill(11)


def _mesclar_matricula_em_dados_adicionais(dados_adicionais_existentes, matricula_raw):
    """Igual ao cadastro de colaboradores: atualiza `matricula` no JSON preservando outras chaves."""
    base = {}
    if dados_adicionais_existentes:
        try:
            parsed = (
                json.loads(dados_adicionais_existentes)
                if isinstance(dados_adicionais_existentes, str)
                else dados_adicionais_existentes
            )
            if isinstance(parsed, dict):
                base = dict(parsed)
        except (json.JSONDecodeError, TypeError):
            base = {}
    matricula = (matricula_raw or '').strip()
    if matricula:
        base['matricula'] = matricula
        base.pop('chapa', None)
    else:
        base.pop('matricula', None)
        base.pop('chapa', None)
    if not base:
        return None
    return json.dumps(base, ensure_ascii=False)


def _cargo_id_por_nome_funcao(nome_funcao):
    nome = (nome_funcao or '').strip()
    if not nome:
        return None
    ln = nome.lower()
    rows = Cargo.query.filter(func.lower(Cargo.nome) == ln).all()
    if not rows:
        return None
    ativos = [r for r in rows if (r.status or '').strip().lower() == 'ativo']
    escolhido = ativos[0] if ativos else rows[0]
    return escolhido.id


def _departamento_id_por_secao(nome_secao):
    nome = (nome_secao or '').strip()
    if not nome:
        return None
    ln = nome.lower()
    rows = Departamento.query.filter(func.lower(Departamento.nome) == ln).all()
    if not rows:
        return None
    ativos = [r for r in rows if (r.status or '').strip().lower() == 'ativo']
    escolhido = ativos[0] if ativos else rows[0]
    return escolhido.id


# Ano e mês vêm do formulário (digitados); os demais campos podem ser mapeados do Excel.
# Cada item: (chave, rótulo) ou (chave, rótulo, padrão) — padrão = nome sugerido da coluna no Excel.
CAMPOS_EFETIVO_PLR = [
    ('cpf', 'CPF'),
    ('nome', 'Nome'),
    ('funcao', 'Função', 'Nome Função', 'Nome Funcão', 'Nome Funcão'),
    ('salario', 'Salário', 'Salário Mensal'),
    ('data_nascimento', 'Data Nascimento', 'Data de Nascimento'),
    ('data_demissao', 'Data Demissão', 'Data de Demissão'),
    ('secao', 'Seção', 'Descrição Seção'),
    ('data_admissao', 'Data Admissão', 'Data de Admissão'),
    ('chapa', 'Chapa'),
]

_CAMPOS_DATA_EFETIVO = {'data_nascimento', 'data_demissao', 'data_admissao'}
_CAMPOS_DECIMAL_EFETIVO = {'salario'}


def _parse_data_efetivo(val):
    """Converte valor para date; aceita datetime, string, NaN ou NaT."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    if hasattr(val, "date"):
        try:
            return val.date()
        except Exception:
            return None
    try:
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


def _parse_valor_efetivo(key: str, val):
    """Converte valor da planilha para o tipo do campo (cpf, data, decimal ou string)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if key == 'cpf':
        dig = re.sub(r'\D', '', valor_para_str(val, '') or '')
        if not dig or len(dig) > 11:
            return None
        return dig.zfill(11)
    if key in _CAMPOS_DATA_EFETIVO:
        return _parse_data_efetivo(val)
    if key in _CAMPOS_DECIMAL_EFETIVO:
        return _parse_decimal_efetivo(val)
    return valor_para_str(val, None)


@plr_bp.route('/efetivo/preview-excel', methods=['POST'])
def efetivo_preview_excel():
    """Retorna as colunas da primeira aba do arquivo Excel para mapeamento."""
    arquivo = request.files.get('arquivo')
    if not arquivo or arquivo.filename == '':
        return jsonify({'success': False, 'message': 'Nenhum arquivo selecionado.'}), 400
    fn = arquivo.filename.lower()
    if not fn.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'message': 'Use um arquivo Excel (.xlsx ou .xls).'}), 400
    suffix = '.xlsx' if fn.endswith('.xlsx') else '.xls'
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        arquivo.save(temp_path)
        engine = 'openpyxl' if suffix == '.xlsx' else 'xlrd'
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


@plr_bp.route('/efetivo/importar', methods=['POST'])
def efetivo_importar():
    """Importa efetivo a partir de Excel com mapeamento de colunas."""
    arquivo = request.files.get('arquivo')
    if not arquivo or arquivo.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))
    fn = arquivo.filename.lower()
    if not fn.endswith(('.xlsx', '.xls')):
        flash('Use um arquivo Excel (.xlsx ou .xls).', 'danger')
        return redirect(url_for('plr.avaliacoes_index'))
    suffix = '.xlsx' if fn.endswith('.xlsx') else '.xls'

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

    data_ref = date(ano, mes, 1)

    mapping_raw = request.form.get('mapping')
    mapping = {}
    if mapping_raw:
        try:
            mapping = json.loads(mapping_raw)
        except json.JSONDecodeError:
            pass

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        arquivo.save(temp_path)
        engine = 'openpyxl' if suffix == '.xlsx' else 'xlrd'
        df = pd.read_excel(temp_path, sheet_name=0, engine=engine)

        inseridos = 0
        atualizados = 0
        erros = []

        campos_keys = [item[0] for item in CAMPOS_EFETIVO_PLR]

        for idx, row in df.iterrows():
            try:
                get_val = lambda col: row.get(mapping[col], None) if mapping.get(col) else None
                kwargs = {'data': data_ref}
                for key in campos_keys:
                    raw = get_val(key)
                    kwargs[key] = _parse_valor_efetivo(key, raw)

                cpf = kwargs.get('cpf')
                existente = None
                if cpf:
                    existente = EfetivoPLR.query.filter_by(data=data_ref, cpf=cpf).first()

                if existente:
                    for key in campos_keys:
                        setattr(existente, key, kwargs.get(key))
                    atualizados += 1
                else:
                    reg = EfetivoPLR(**kwargs)
                    db.session.add(reg)
                    inseridos += 1
            except Exception as e:
                erros.append(f'Linha {idx + 2}: {str(e)}')

        db.session.commit()
        msg = f'Importação do efetivo concluída: {inseridos} registro(s) inserido(s), {atualizados} atualizado(s).'
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
    next_url = (request.form.get('next') or '').strip()
    if next_url:
        return redirect(next_url)
    return redirect(url_for('plr.avaliacoes_index'))


@plr_bp.route('/efetivos/')
def efetivos_index():
    """Lista efetivos PLR com filtros de ano/mês e DataTables (AJAX)."""
    ano_atual = datetime.now().year
    mes_atual = datetime.now().month
    anos_db = db.session.query(func.extract('year', EfetivoPLR.data).label('ano')).distinct().order_by(func.extract('year', EfetivoPLR.data).desc()).limit(15).all()
    anos_set = {int(r[0]) for r in anos_db if r[0] is not None}
    for a in range(ano_atual, ano_atual - 5, -1):
        anos_set.add(a)
    anos = sorted(anos_set, reverse=True)
    return render_template(
        'plr/efetivos_index.html',
        ano_sugerido=ano_atual,
        mes_sugerido=mes_atual,
        anos=anos,
        campos_efetivo=CAMPOS_EFETIVO_PLR,
        campos_sinc_colaborador=CAMPOS_SINC_EFETIVO_COLAB,
        redirect_after_import=url_for('plr.efetivos_index'),
    )


@plr_bp.route('/efetivos/sincronizar-colaboradores', methods=['POST'])
def efetivos_sincronizar_colaboradores():
    """
    Atualiza colaboradores com dados do efetivo do período (ano/mês), vínculo pelo CPF normalizado.
    Função no efetivo → `cargo_id` (cargo com mesmo nome). Seção → `departamento_id`.
    Salário → registro em CargoSalario (cargo do colaborador após aplicar função, se também selecionada).
    """
    try:
        ano = int(request.form.get('ano') or 0)
        mes = int(request.form.get('mes') or 0)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Ano e mês inválidos.'}), 400
    if not (1 <= mes <= 12) or ano < 2000 or ano > 2100:
        return jsonify({'success': False, 'message': 'Informe ano e mês válidos (mês 1–12).'}), 400

    campos_raw = request.form.getlist('campos')
    campos = [c for c in campos_raw if c in _CAMPOS_SINC_PERMITIDOS]
    if not campos:
        return jsonify({'success': False, 'message': 'Selecione ao menos um campo para sincronizar.'}), 400

    data_ref = date(ano, mes, 1)
    efetivos = EfetivoPLR.query.filter(EfetivoPLR.data == data_ref).all()
    if not efetivos:
        return jsonify({
            'success': True,
            'message': 'Não há registros de efetivo neste período. Nada a atualizar.',
            'atualizados': 0,
            'sem_colaborador': 0,
            'sem_alteracao': 0,
        })

    por_cpf = {}
    for col in Colaborador.query.all():
        k = _cpf_normalizado_efetivo(col.cpf)
        if k:
            por_cpf[k] = col

    atualizados = 0
    sem_colaborador = 0
    sem_alteracao = 0
    salario_sem_cargo = 0
    campos_set = set(campos)

    for reg in efetivos:
        cpf_key = _cpf_normalizado_efetivo(reg.cpf)
        if not cpf_key:
            sem_colaborador += 1
            continue
        col = por_cpf.get(cpf_key)
        if not col:
            sem_colaborador += 1
            continue

        mudou = False

        if 'nome' in campos_set:
            v = (reg.nome or '').strip()
            if v and col.nome != v:
                col.nome = v
                mudou = True

        if 'data_nascimento' in campos_set:
            v = reg.data_nascimento
            if col.data_nascimento != v:
                col.data_nascimento = v
                mudou = True

        if 'data_demissao' in campos_set:
            v = reg.data_demissao
            if col.data_demissao != v:
                col.data_demissao = v
                mudou = True

        if 'data_admissao' in campos_set:
            v = reg.data_admissao
            if v is not None and col.data_admissao != v:
                col.data_admissao = v
                mudou = True

        if 'secao' in campos_set:
            did = _departamento_id_por_secao(reg.secao)
            if did is not None and col.departamento_id != did:
                col.departamento_id = did
                mudou = True

        if 'funcao' in campos_set:
            cid = _cargo_id_por_nome_funcao(reg.funcao)
            if cid is not None and col.cargo_id != cid:
                col.cargo_id = cid
                mudou = True

        if 'chapa' in campos_set:
            ch = (reg.chapa or '').strip()
            novo_json = _mesclar_matricula_em_dados_adicionais(col.dados_adicionais, ch)
            atual = col.dados_adicionais
            if atual != novo_json:
                col.dados_adicionais = novo_json
                mudou = True

        if 'salario' in campos_set and reg.salario is not None:
            cargo_id = col.cargo_id
            if not cargo_id:
                salario_sem_cargo += 1
            else:
                sal_f = float(reg.salario)
                cs = CargoSalario.query.filter_by(cargo_id=cargo_id, data=data_ref).first()
                if cs:
                    if float(cs.salario) != sal_f:
                        cs.salario = sal_f
                        mudou = True
                else:
                    db.session.add(
                        CargoSalario(cargo_id=cargo_id, data=data_ref, salario=sal_f)
                    )
                    mudou = True

        if mudou:
            atualizados += 1
        else:
            sem_alteracao += 1

    db.session.commit()
    extra = f' Salário ignorado (colaborador sem cargo): {salario_sem_cargo}.' if salario_sem_cargo else ''
    msg = (
        f'Sincronização concluída: {atualizados} colaborador(es) atualizado(s). '
        f'Efetivo com CPF sem colaborador correspondente: {sem_colaborador}. '
        f'Sem alteração (já iguais, nome vazio no efetivo ou cargo/departamento não encontrado pelo nome): {sem_alteracao}.'
        f'{extra}'
    )
    return jsonify({
        'success': True,
        'message': msg.replace('  ', ' ').strip(),
        'atualizados': atualizados,
        'sem_colaborador': sem_colaborador,
        'sem_alteracao': sem_alteracao,
        'salario_sem_cargo': salario_sem_cargo,
    })


@plr_bp.route('/efetivos/dados')
def efetivos_dados():
    """Retorna JSON com os efetivos para DataTables (AJAX). Params: ano, mes (opcionais)."""
    ano = request.args.get('ano', type=int)
    mes = request.args.get('mes', type=int)
    query = EfetivoPLR.query
    if ano is not None and mes is not None and 1 <= mes <= 12:
        data_filtro = date(ano, mes, 1)
        query = query.filter(EfetivoPLR.data == data_filtro)
    elif ano is not None:
        query = query.filter(func.extract('year', EfetivoPLR.data) == ano)
    lista = query.order_by(EfetivoPLR.data.desc(), EfetivoPLR.nome.asc()).all()
    csrf = generate_csrf()
    data = []
    for reg in lista:
        excluir_url = url_for('plr.efetivo_excluir', id=reg.id)
        acoes = (
            f'<button type="button" class="btn btn-sm btn-primary btn-editar-efetivo" data-id="{reg.id}" '
            f'title="Editar"><i class="fas fa-edit"></i></button> '
            f'<form method="POST" action="{excluir_url}" class="d-inline" onsubmit="return confirm(\'Excluir este efetivo?\');">'
            f'<input type="hidden" name="csrf_token" value="{csrf}">'
            f'<button type="submit" class="btn btn-sm btn-danger" title="Excluir"><i class="fas fa-trash"></i></button></form>'
        )
        data.append({
            'id': reg.id,
            'data': reg.data.isoformat() if reg.data else None,
            'ano': reg.data.year if reg.data else None,
            'mes': reg.data.month if reg.data else None,
            'cpf': reg.cpf or '-',
            'nome': reg.nome or '-',
            'funcao': reg.funcao or '-',
            'salario': f'{float(reg.salario):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') if reg.salario is not None else '-',
            'data_nascimento': reg.data_nascimento.strftime('%d/%m/%Y') if reg.data_nascimento else '-',
            'data_demissao': reg.data_demissao.strftime('%d/%m/%Y') if reg.data_demissao else '-',
            'secao': reg.secao or '-',
            'data_admissao': reg.data_admissao.strftime('%d/%m/%Y') if reg.data_admissao else '-',
            'chapa': reg.chapa or '-',
            'acoes': acoes,
        })
    return jsonify({'data': data})


@plr_bp.route('/efetivos/<int:id>/json')
def efetivo_json(id):
    """Retorna um efetivo em JSON para preencher o modal de edição."""
    reg = EfetivoPLR.query.get_or_404(id)
    d = reg.to_dict()
    return jsonify(d)


@plr_bp.route('/efetivos/<int:id>/editar', methods=['POST'])
def efetivo_editar(id):
    """Atualiza um registro de efetivo PLR."""
    reg = EfetivoPLR.query.get_or_404(id)
    data_val = request.form.get('data')
    if data_val:
        try:
            from datetime import datetime as dt
            parsed = dt.strptime(data_val.strip()[:10], '%Y-%m-%d').date()
            reg.data = date(parsed.year, parsed.month, 1)
        except (ValueError, TypeError):
            pass
    else:
        ano_f, mes_f = request.form.get('ano'), request.form.get('mes')
        if ano_f and mes_f:
            try:
                a, m = int(ano_f), int(mes_f)
                if 1 <= m <= 12:
                    reg.data = date(a, m, 1)
            except (ValueError, TypeError):
                pass
    reg.cpf = (request.form.get('cpf') or '').strip() or None
    reg.nome = (request.form.get('nome') or '').strip() or None
    reg.funcao = (request.form.get('funcao') or '').strip() or None
    sal = request.form.get('salario')
    reg.salario = _parse_decimal_efetivo(sal) if sal else reg.salario
    reg.data_nascimento = _parse_data_efetivo(request.form.get('data_nascimento') or None)
    reg.data_demissao = _parse_data_efetivo(request.form.get('data_demissao') or None)
    reg.secao = (request.form.get('secao') or '').strip() or None
    reg.data_admissao = _parse_data_efetivo(request.form.get('data_admissao') or None)
    reg.chapa = (request.form.get('chapa') or '').strip() or None
    db.session.commit()
    flash('Efetivo atualizado com sucesso.', 'success')
    return redirect(url_for('plr.efetivos_index'))


@plr_bp.route('/efetivos/<int:id>/excluir', methods=['POST'])
def efetivo_excluir(id):
    """Exclui um registro de efetivo PLR."""
    reg = EfetivoPLR.query.get_or_404(id)
    db.session.delete(reg)
    db.session.commit()
    flash('Efetivo excluído com sucesso.', 'success')
    return redirect(url_for('plr.efetivos_index'))
