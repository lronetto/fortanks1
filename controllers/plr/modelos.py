"""
Rotas de Modelos de PLR e Cargos/Salários (mês/ano + salário).
"""
import json

from flask import request, redirect, url_for, flash, render_template

from models.database import db
from models.plr import ModeloPLR
from models.cargo_salario import CargoSalario
from models.cargo import Cargo
from models.departamento import Departamento

from . import plr_bp


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
