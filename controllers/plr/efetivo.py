"""
Rotas e lógica de Efetivo PLR: importação Excel, listagem, edição e exclusão.
"""
import json
import os
import re
import tempfile
from datetime import datetime

import pandas as pd
from flask import request, redirect, url_for, flash, jsonify, render_template
from flask_wtf.csrf import generate_csrf

from models.database import db
from models.plr import EfetivoPLR
from utils.utils import valor_para_str

from . import plr_bp


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
                kwargs = {'ano': ano, 'mes': mes}
                for key in campos_keys:
                    raw = get_val(key)
                    kwargs[key] = _parse_valor_efetivo(key, raw)

                cpf = kwargs.get('cpf')
                existente = None
                if cpf:
                    existente = EfetivoPLR.query.filter_by(ano=ano, mes=mes, cpf=cpf).first()

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
    anos_db = db.session.query(EfetivoPLR.ano).distinct().order_by(EfetivoPLR.ano.desc()).limit(15).all()
    anos_set = {r[0] for r in anos_db}
    for a in range(ano_atual, ano_atual - 5, -1):
        anos_set.add(a)
    anos = sorted(anos_set, reverse=True)
    return render_template(
        'plr/efetivos_index.html',
        ano_sugerido=ano_atual,
        mes_sugerido=mes_atual,
        anos=anos,
        campos_efetivo=CAMPOS_EFETIVO_PLR,
        redirect_after_import=url_for('plr.efetivos_index'),
    )


@plr_bp.route('/efetivos/dados')
def efetivos_dados():
    """Retorna JSON com os efetivos para DataTables (AJAX). Params: ano, mes (opcionais)."""
    ano = request.args.get('ano', type=int)
    mes = request.args.get('mes', type=int)
    query = EfetivoPLR.query
    if ano is not None:
        query = query.filter(EfetivoPLR.ano == ano)
    if mes is not None and 1 <= mes <= 12:
        query = query.filter(EfetivoPLR.mes == mes)
    lista = query.order_by(EfetivoPLR.ano.desc(), EfetivoPLR.mes.desc(), EfetivoPLR.nome.asc()).all()
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
            'ano': reg.ano,
            'mes': reg.mes,
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
    reg.ano = request.form.get('ano', type=int) or reg.ano
    reg.mes = request.form.get('mes', type=int) or reg.mes
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
