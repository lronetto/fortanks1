"""
Rotas de Modelos de PLR e Cargos/Salários (período mês/ano + salário).
"""
from datetime import date
import json

from flask import jsonify, request, redirect, url_for, flash, render_template
from flask_wtf.csrf import generate_csrf

from models.database import db
from models.plr import ModeloPLR
from models.cargo_salario import CargoSalario
from models.cargo import Cargo
from models.departamento import Departamento

from utils.datatable_helper import DataTableParams

from . import plr_bp
from .services.cargos_salarios_datatables import montar_payload_cargos_salarios_datatables


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
    """Lista vínculos cargo x mês/ano x salário (tabela via DataTables server-side)."""
    cargos = Cargo.query.filter_by(status='Ativo').order_by(Cargo.nome).all()
    return render_template('plr/cargos_salarios_index.html', cargos=cargos)


@plr_bp.route('/cargos-salarios/api/datatables', methods=['GET'])
def cargos_salarios_datatables():
    """JSON DataTables server-side para cargos x salário."""
    dt = DataTableParams()
    try:
        return montar_payload_cargos_salarios_datatables(dt, generate_csrf())
    except Exception as e:
        return (
            jsonify(
                {
                    'draw': dt.draw,
                    'recordsTotal': 0,
                    'recordsFiltered': 0,
                    'data': [],
                    'error': str(e),
                }
            ),
            500,
        )


@plr_bp.route('/cargos-salarios/<int:id>/json')
def cargo_salario_json(id):
    """Dados de um registro para preencher o modal de edição."""
    reg = CargoSalario.query.get_or_404(id)
    return jsonify(
        {
            'id': reg.id,
            'cargo_id': reg.cargo_id,
            'cargo_nome': reg.cargo.nome if reg.cargo else '',
            'mes': reg.mes,
            'ano': reg.ano,
            'salario': float(reg.salario) if reg.salario is not None else None,
        }
    )


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
            mes_i, ano_i = int(mes), int(ano)
            if mes_i < 1 or mes_i > 12:
                raise ValueError('Mês inválido')
            salario_val = float(salario.replace(',', '.'))
        except (ValueError, TypeError):
            flash('Mês, ano ou salário inválidos.', 'danger')
            return render_template('plr/cargo_salario_form.html', reg=None, cargos=cargos)
        data_ref = date(ano_i, mes_i, 1)
        existente = CargoSalario.query.filter_by(cargo_id=int(cargo_id), data=data_ref).first()
        if existente:
            flash('Já existe registro para este cargo no mês/ano informado.', 'danger')
            return render_template('plr/cargo_salario_form.html', reg=None, cargos=cargos)
        reg = CargoSalario(cargo_id=int(cargo_id), data=data_ref, salario=salario_val)
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
        mes = request.form.get('mes')
        ano = request.form.get('ano')
        try:
            mes_i, ano_i = int(mes), int(ano)
            if 1 <= mes_i <= 12:
                reg.data = date(ano_i, mes_i, 1)
        except (ValueError, TypeError):
            pass
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
