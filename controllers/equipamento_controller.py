from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models.database import db
from models.equipamento import (
    Equipamento, Manutencao, ChecklistModelo,
    ChecklistItem, ChecklistEquipamento, ChecklistResposta
)

equipamento_bp = Blueprint('equipamento', __name__, url_prefix='/equipamentos')


@equipamento_bp.route('/')
@login_required
def index():
    equipamentos = Equipamento.query.all()
    return render_template('equipamentos/index.html', equipamentos=equipamentos)


@equipamento_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if request.method == 'POST':
        try:
            equipamento = Equipamento(
                nome=request.form['nome'],
                tipo=request.form['tipo'],
                propriedade=request.form['propriedade'],
                modelo=request.form['modelo'],
                numero_serie=request.form['numero_serie'],
                nota_fiscal=request.form.get('nota_fiscal', ''),
                data_aquisicao=datetime.strptime(
                    request.form['data_aquisicao'], '%Y-%m-%d').date(),
                status=request.form['status'],
                observacoes=request.form['observacoes']
            )
            db.session.add(equipamento)
            db.session.commit()
            flash('Equipamento cadastrado com sucesso!', 'success')
            return redirect(url_for('equipamento.index'))
        except Exception as e:
            flash(f'Erro ao cadastrar equipamento: {str(e)}', 'danger')
            db.session.rollback()
    return redirect(url_for('equipamento.index'))


@equipamento_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    equipamento = Equipamento.query.get_or_404(id)
    if request.method == 'POST':
        try:
            equipamento.nome = request.form['nome']
            equipamento.modelo = request.form['modelo']
            equipamento.numero_serie = request.form['numero_serie']
            equipamento.data_aquisicao = datetime.strptime(
                request.form['data_aquisicao'], '%Y-%m-%d').date()
            equipamento.status = request.form['status']
            equipamento.observacoes = request.form['observacoes']
            db.session.commit()
            flash('Equipamento atualizado com sucesso!', 'success')
            return redirect(url_for('equipamento.index'))
        except Exception as e:
            flash('Erro ao atualizar equipamento!', 'danger')
            db.session.rollback()
    return render_template('equipamentos/editar.html', equipamento=equipamento)


@equipamento_bp.route('/<int:id>/visualizar')
@login_required
def visualizar(id):
    equipamento = Equipamento.query.get_or_404(id)
    return render_template('equipamentos/visualizar.html', equipamento=equipamento)

# Rotas para Manutenção


@equipamento_bp.route('/<int:id>/manutencoes')
@login_required
def manutencoes(id):
    equipamento = Equipamento.query.get_or_404(id)
    return render_template('equipamentos/manutencoes/index.html', equipamento=equipamento)


@equipamento_bp.route('/<int:id>/manutencoes/nova', methods=['GET', 'POST'])
@login_required
def nova_manutencao(id):
    equipamento = Equipamento.query.get_or_404(id)
    if request.method == 'POST':
        try:
            manutencao = Manutencao(
                equipamento_id=id,
                tipo=request.form['tipo'],
                descricao=request.form['descricao'],
                data_inicio=datetime.strptime(
                    request.form['data_inicio'], '%Y-%m-%dT%H:%M'),
                responsavel=request.form['responsavel'],
                status=request.form['status'],
                observacoes=request.form['observacoes']
            )
            if request.form.get('data_fim'):
                manutencao.data_fim = datetime.strptime(
                    request.form['data_fim'], '%Y-%m-%dT%H:%M')
            if request.form.get('custo'):
                manutencao.custo = float(request.form['custo'])

            db.session.add(manutencao)
            db.session.commit()
            flash('Manutenção registrada com sucesso!', 'success')
            return redirect(url_for('equipamento.manutencoes', id=id))
        except Exception as e:
            flash('Erro ao registrar manutenção!', 'danger')
            db.session.rollback()
    return render_template('equipamentos/manutencoes/nova.html', equipamento=equipamento)

# Rotas para Checklist


@equipamento_bp.route('/checklists')
@login_required
def checklists():
    modelos = ChecklistModelo.query.all()
    return render_template('equipamentos/checklists/index.html', modelos=modelos)


@equipamento_bp.route('/checklists/novo', methods=['GET', 'POST'])
@login_required
def novo_checklist():
    if request.method == 'POST':
        try:
            print("Dados do formulário:", request.form)
            print("Itens:", request.form.getlist('item_descricao[]'))
            print("Tipos:", request.form.getlist('item_tipo[]'))
            print("Obrigatórios:", request.form.getlist('item_obrigatorio[]'))
            
            modelo = ChecklistModelo(
                nome=request.form['nome'],
                descricao=request.form['descricao']
            )
            db.session.add(modelo)
            db.session.commit()

            # Adicionar itens do checklist
            itens = request.form.getlist('item_descricao[]')
            tipos = request.form.getlist('item_tipo[]')
            obrigatorios = request.form.getlist('item_obrigatorio[]')

            print(f"Total de itens: {len(itens)}")
            
            for i, descricao in enumerate(itens):
                if descricao.strip():
                    # Garantir que temos um valor para obrigatorio
                    obrigatorio = False
                    if i < len(obrigatorios):
                        obrigatorio = True if obrigatorios[i] == '1' else False
                    
                    print(f"Adicionando item {i+1}: {descricao}, tipo: {tipos[i]}, obrigatório: {obrigatorio}")
                    
                    item = ChecklistItem(
                        modelo_id=modelo.id,
                        descricao=descricao,
                        tipo=tipos[i],
                        obrigatorio=obrigatorio,
                        ordem=i+1
                    )
                    db.session.add(item)

            db.session.commit()
            flash('Modelo de checklist criado com sucesso!', 'success')
            return redirect(url_for('equipamento.checklists'))
        except Exception as e:
            print(f"Erro ao criar checklist: {str(e)}")
            flash('Erro ao criar modelo de checklist!', 'danger')
            db.session.rollback()
            return redirect(url_for('equipamento.checklists'))
    # Se for GET, redireciona para a listagem (já que agora usamos modal)
    return redirect(url_for('equipamento.checklists'))


@equipamento_bp.route('/<int:id>/checklist/novo', methods=['GET', 'POST'])
@login_required
def novo_checklist_equipamento(id):
    # Se o ID for 0 e vier do formulário, usamos o ID do formulário
    if id == 0 and request.method == 'POST' and 'equipamento_id' in request.form:
        id = int(request.form['equipamento_id'])
        
    equipamento = Equipamento.query.get_or_404(id)
    modelos = ChecklistModelo.query.all()

    if request.method == 'POST':
        try:
            checklist = ChecklistEquipamento(
                equipamento_id=id,
                modelo_id=request.form['modelo_id'],
                data_checklist=datetime.strptime(
                    request.form['data_checklist'], '%Y-%m-%dT%H:%M'),
                responsavel=current_user.nome,
                status='Em Andamento',
                observacoes=request.form['observacoes']
            )
            db.session.add(checklist)
            db.session.commit()

            # Criar respostas vazias para cada item do modelo
            modelo = ChecklistModelo.query.get(request.form['modelo_id'])
            for item in modelo.itens:
                resposta = ChecklistResposta(
                    checklist_id=checklist.id,
                    item_id=item.id
                )
                db.session.add(resposta)

            db.session.commit()
            flash('Checklist iniciado com sucesso!', 'success')
            return redirect(url_for('equipamento.preencher_checklist', id=id, checklist_id=checklist.id))
        except Exception as e:
            flash('Erro ao iniciar checklist!', 'danger')
            db.session.rollback()

    return render_template('equipamentos/checklists/novo_equipamento.html',
                           equipamento=equipamento, modelos=modelos, now1=datetime.now())


@equipamento_bp.route('/<int:id>/checklist/<int:checklist_id>/preencher', methods=['GET', 'POST'])
@login_required
def preencher_checklist(id, checklist_id):
    checklist = ChecklistEquipamento.query.get_or_404(checklist_id)
    if request.method == 'POST':
        try:
            for resposta in checklist.respostas:
                resposta_valor = request.form.get(f'resposta_{resposta.id}')
                observacao = request.form.get(f'observacao_{resposta.id}')

                resposta.resposta = resposta_valor
                resposta.observacao = observacao
                resposta.data_resposta = datetime.utcnow()

            checklist.status = 'Concluído'
            db.session.commit()
            flash('Checklist preenchido com sucesso!', 'success')
            return redirect(url_for('equipamento.visualizar', id=id))
        except Exception as e:
            flash('Erro ao salvar respostas do checklist!', 'danger')
            db.session.rollback()

    return render_template('equipamentos/checklists/preencher.html',
                           equipamento=checklist.equipamento, checklist=checklist)


@equipamento_bp.route('/checklists/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_checklist(id):
    modelo = ChecklistModelo.query.get_or_404(id)
    if request.method == 'POST':
        try:
            modelo.nome = request.form['nome']
            modelo.descricao = request.form['descricao']
            
            # Remover itens antigos
            for item in modelo.itens:
                db.session.delete(item)
            
            # Adicionar novos itens
            itens = request.form.getlist('item_descricao[]')
            tipos = request.form.getlist('item_tipo[]')
            obrigatorios = request.form.getlist('item_obrigatorio[]')
            
            for i, descricao in enumerate(itens):
                if descricao.strip():
                    # Garantir que temos um valor para obrigatorio
                    obrigatorio = False
                    if i < len(obrigatorios):
                        obrigatorio = True if obrigatorios[i] == '1' else False
                    
                    item = ChecklistItem(
                        modelo_id=modelo.id,
                        descricao=descricao,
                        tipo=tipos[i],
                        obrigatorio=obrigatorio,
                        ordem=i+1
                    )
                    db.session.add(item)
            
            db.session.commit()
            flash('Modelo de checklist atualizado com sucesso!', 'success')
            return redirect(url_for('equipamento.checklists'))
        except Exception as e:
            flash('Erro ao atualizar modelo de checklist!', 'danger')
            db.session.rollback()
    return render_template('equipamentos/checklists/editar.html', modelo=modelo)


@equipamento_bp.route('/checklists/pendentes', methods=['GET'])
@login_required
def checklists_pendentes():
    # Buscar todos os checklists com status "Em Andamento" ou "Pendente"
    checklists = ChecklistEquipamento.query.filter(
        ChecklistEquipamento.status.in_(['Pendente', 'Em Andamento'])
    ).order_by(ChecklistEquipamento.data_checklist.desc()).all()
    
    return render_template('equipamentos/checklists/pendentes.html', checklists=checklists)


@equipamento_bp.route('/checklists/realizar', methods=['GET'])
@login_required
def realizar_checklist():
    # Buscar todos os equipamentos ativos
    equipamentos = Equipamento.query.filter_by(status='Ativo').order_by(Equipamento.nome).all()
    modelos = ChecklistModelo.query.order_by(ChecklistModelo.nome).all()
    
    return render_template('equipamentos/checklists/realizar.html', 
                           equipamentos=equipamentos, 
                           modelos=modelos,
                           now1=datetime.now())


@equipamento_bp.route('/<int:id>/excluir')
@login_required
def excluir(id):
    if not current_user.is_gerente_ou_superior:
        flash('Você não tem permissão para excluir equipamentos!', 'danger')
        return redirect(url_for('equipamento.index'))
    
    try:
        equipamento = Equipamento.query.get_or_404(id)
        
        # Verificar se existem manutenções ou checklists associados
        if equipamento.manutencoes or equipamento.checklists:
            flash('Não é possível excluir este equipamento pois existem registros associados a ele!', 'warning')
            return redirect(url_for('equipamento.index'))
        
        nome_equipamento = equipamento.nome
        db.session.delete(equipamento)
        db.session.commit()
        flash(f'Equipamento "{nome_equipamento}" excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir equipamento: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('equipamento.index'))
