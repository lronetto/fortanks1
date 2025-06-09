from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from models import Peca, Tanque
from models import db
from flask_wtf.csrf import generate_csrf
from datetime import datetime
import json

# Criação do blueprint
peca = Blueprint('peca', __name__, url_prefix='/pecas')

@peca.route('/')
def index():
    """Lista todas as peças do sistema agrupadas por tanque"""
    # Busca todos os tanques que possuem peças associadas
    tanques_com_pecas = db.session.query(Tanque)\
        .join(Peca, Tanque.id == Peca.tanque_id)\
        .distinct()\
        .order_by(Tanque.id)\
        .all()
    
    # Dicionário para armazenar peças por tanque
    tanques_pecas = {}
    
    # Para cada tanque, busca suas peças
    for tanque in tanques_com_pecas:
        pecas = Peca.query.filter_by(tanque_id=tanque.id)\
            .order_by(Peca.numero_sequencial)\
            .all()
        tanques_pecas[tanque] = pecas
    
    return render_template('pecas/index.html', tanques_pecas=tanques_pecas)

@peca.route('/tanque/<int:tanque_id>')
def listar_por_tanque(tanque_id):
    """Lista todas as peças de um tanque específico"""
    tanque = Tanque.query.get_or_404(tanque_id)
    pecas = Peca.query.filter_by(tanque_id=tanque_id).order_by(Peca.numero_sequencial).all()
    
    return render_template('pecas/listar.html', pecas=pecas, tanque=tanque)

@peca.route('/novo/<int:tanque_id>', methods=['GET', 'POST'])
def novo(tanque_id):
    """Adiciona uma nova peça a um tanque"""
    tanque = Tanque.query.get_or_404(tanque_id)
    
    # Obtém o próximo número sequencial
    proximo_sequencial = db.session.query(db.func.max(Peca.numero_sequencial))\
        .filter(Peca.tanque_id == tanque_id).scalar() or 0
    proximo_sequencial += 1
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            tipo = request.form.get('tipo')
            nome = request.form.get('nome')
            numero_tanque = request.form.get('numero_tanque')
            
            # Converter numero_tanque para inteiro se não estiver vazio
            if numero_tanque and numero_tanque.strip():
                try:
                    numero_tanque = int(numero_tanque)
                except ValueError:
                    numero_tanque = None
            else:
                numero_tanque = None
            
            # Criar nova peça
            nova_peca = Peca(
                tipo=tipo,
                nome=nome,
                numero_tanque=numero_tanque,
                tanque_id=tanque_id,
                numero_sequencial=proximo_sequencial
            )
            
            # Salvar no banco de dados
            nova_peca.save()
            
            flash('Peça adicionada com sucesso!', 'success')
            return redirect(url_for('peca.listar_por_tanque', tanque_id=tanque_id))
            
        except Exception as e:
            flash(f'Erro ao adicionar peça: {str(e)}', 'danger')
    
    return render_template('pecas/novo.html', tanque=tanque, proximo_sequencial=proximo_sequencial)

@peca.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """Edita uma peça existente"""
    peca = Peca.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            peca.tipo = request.form.get('tipo')
            peca.nome = request.form.get('nome')
            
            numero_tanque = request.form.get('numero_tanque')
            # Converter numero_tanque para inteiro se não estiver vazio
            if numero_tanque and numero_tanque.strip():
                try:
                    peca.numero_tanque = int(numero_tanque)
                except ValueError:
                    peca.numero_tanque = None
            else:
                peca.numero_tanque = None
            
            # Salvar alterações
            peca.save()
            
            flash('Peça atualizada com sucesso!', 'success')
            return redirect(url_for('peca.visualizar', id=peca.id))
            
        except Exception as e:
            flash(f'Erro ao atualizar peça: {str(e)}', 'danger')
    
    return render_template('pecas/editar.html', peca=peca)

@peca.route('/visualizar/<int:id>')
def visualizar(id):
    """Visualiza detalhes de uma peça"""
    peca = Peca.query.get_or_404(id)
    return render_template('pecas/visualizar.html', peca=peca)

@peca.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """Exclui uma peça"""
    peca = Peca.query.get_or_404(id)
    tanque_id = peca.tanque_id
    numero_sequencial = peca.numero_sequencial
    
    try:
        # Excluir a peça
        peca.delete()
        
        # Reordenar as peças restantes
        pecas_posteriores = Peca.query.filter(
            Peca.tanque_id == tanque_id,
            Peca.numero_sequencial > numero_sequencial
        ).order_by(Peca.numero_sequencial).all()
        
        # Atualizar os números sequenciais
        for p in pecas_posteriores:
            p.numero_sequencial -= 1
            p.save()
            
        flash('Peça excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir peça: {str(e)}', 'danger')
    
    return redirect(url_for('peca.listar_por_tanque', tanque_id=tanque_id))

@peca.route('/acabamento', methods=['GET', 'POST'])
def acabamento():
    """Registra acabamento de uma peça"""
    if request.method == 'POST':
        tanque_id = request.form.get('tanque_id')
        peca_nome = request.form.get('peca_nome')
        placa = request.form.get('placa')
        data_acabamento = request.form.get('data_acabamento')
        if not data_acabamento:
            data_acabamento = datetime.now().strftime('%Y-%m-%d')
        try:
            peca = Peca.query.filter_by(tanque_id=tanque_id, nome=peca_nome).first()
            if not peca:
                return jsonify({'success': False, 'message': 'Peça não encontrada'}), 404
            qualidade = peca.qualidade or '{}'
            qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
            qualidade_dict['acabamento'] = {
                'placa': placa,
                'data': data_acabamento
            }
            peca.qualidade = json.dumps(qualidade_dict)
            peca.save()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    # GET: retorna o modal
    tanques = Tanque.query.order_by(Tanque.nome).all()
    csrf_token = generate_csrf()
    return render_template('pecas/modais/acabamento.html', tanques=tanques, csrf_token=csrf_token)

@peca.route('/transporte', methods=['GET', 'POST'])
def transporte():
    """Registra transporte de peças"""
    if request.method == 'POST':
        tanque_ids = request.form.getlist('tanque_ids')
        peca_nomes = request.form.getlist('peca_nomes')
        placas = request.form.getlist('placas')
        nota_fiscal = request.form.get('nota_fiscal')
        placa_carreta = request.form.get('placa_carreta')
        data_transporte = request.form.get('data_transporte')
        transportadora = request.form.get('transportadora')
        if not data_transporte:
            data_transporte = datetime.now().strftime('%Y-%m-%d')
        try:
            pecas = Peca.query.filter(Peca.tanque_id.in_(tanque_ids), Peca.nome.in_(peca_nomes)).all()
            for peca in pecas:
                qualidade = peca.qualidade or '{}'
                qualidade_dict = json.loads(qualidade) if isinstance(qualidade, str) else qualidade
                qualidade_dict['transporte'] = {
                    'data_transporte': data_transporte,
                    'placas': placas,
                    'nota': nota_fiscal,
                    'placa_carreta': placa_carreta,
                    'transportadora': transportadora
                }
                peca.qualidade = json.dumps(qualidade_dict)
                peca.data_entrega = data_transporte
                peca.save()
            return jsonify({'success': True, 'pecas_afetadas': [p.id for p in pecas]})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    # GET: retorna o modal
    tanques = Tanque.query.order_by(Tanque.nome).all()
    csrf_token = generate_csrf()
    return render_template('pecas/modais/transporte.html', tanques=tanques, csrf_token=csrf_token) 