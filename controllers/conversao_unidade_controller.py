from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, distinct
from flask_login import login_required, current_user
from models import db, ConversaoUnidade, Unidade
from utils.decorators import role_required
from datetime import datetime

conversao_unidade_bp = Blueprint('conversao_unidade', __name__)

def inserir_conversoes_padrao():
    """Insere conversões padrão no banco de dados se não existirem."""
    # Verificar se já existem conversões
    if ConversaoUnidade.query.count() > 0:
        return
    
    # Lista de conversões padrão
    conversoes_padrao = [
        ('Quilograma para Grama', 'kg', 'g', 1000.0),
        ('Grama para Quilograma', 'g', 'kg', 0.001),
        ('Tonelada para Quilograma', 't', 'kg', 1000.0),
        ('Quilograma para Tonelada', 'kg', 't', 0.001),
        ('Metro cúbico para Litro', 'm³', 'l', 1000.0),
        ('Litro para Metro cúbico', 'l', 'm³', 0.001),
        ('Litro para Mililitro', 'l', 'ml', 1000.0),
        ('Mililitro para Litro', 'ml', 'l', 0.001)
    ]
    
    # Criar e inserir as conversões
    for nome, entrada, saida, fator in conversoes_padrao:
        conversao = ConversaoUnidade(
            nome=nome,
            unidade_entrada=entrada,
            unidade_saida=saida,
            fator=fator,
            criado_em=datetime.now(),
            atualizado_em=datetime.now()
        )
        db.session.add(conversao)
    
    # Commit das alterações
    db.session.commit()
    print(f"DEBUG: {len(conversoes_padrao)} conversões padrão inseridas com sucesso")

def obter_unidades_unicas():
    """Retorna todas as unidades únicas registradas no sistema."""
    unidades = db.session.query(Unidade.nome).distinct().all()
    # Busca unidades de entrada únicas
    unidades_entrada = db.session.query(ConversaoUnidade.unidade_entrada.distinct()).all()
    # Busca unidades de saída únicas
    unidades_saida = db.session.query(ConversaoUnidade.unidade_saida.distinct()).all()
    
    # Combina e remove duplicatas
    unidades = set(u[0] for u in unidades)
    
    # Conjunto de unidades comuns para pré-popular se o banco estiver vazio
    unidades_comuns = ConversaoUnidade.unidades_padrao
    
    # Se não houver unidades no banco, retorna as unidades comuns
    if not unidades:
        return sorted(list(unidades_comuns))
    
    # Adiciona as unidades comuns que não existem no banco
    #unidades.update(unidades_comuns)
    
    # Retorna a lista ordenada
    return sorted(list(unidades))

@conversao_unidade_bp.route('/')
@login_required
@role_required(['admin', 'gerente'])
def index():
    """Lista todas as conversões de unidades."""
    conversoes = ConversaoUnidade.query.all()
    unidades = obter_unidades_unicas()
    return render_template('conversao_unidades/index.html', conversoes=conversoes, unidades=unidades)

@conversao_unidade_bp.route('/novo', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'gerente'])
def novo():
    """Cria uma nova conversão de unidade."""
    if request.method == 'POST':
        nome = request.form.get('nome')
        unidade_entrada = request.form.get('unidade_entrada')
        unidade_saida = request.form.get('unidade_saida')
        fator = request.form.get('fator')
        
        if not nome or not unidade_entrada or not unidade_saida or not fator:
            flash('Todos os campos são obrigatórios!', 'danger')
            return redirect(url_for('conversao_unidade.index'))
        
        try:
            fator = float(fator)
            nova_conversao = ConversaoUnidade(
                nome=nome,
                unidade_entrada=unidade_entrada,
                unidade_saida=unidade_saida,
                fator=fator
            )
            db.session.add(nova_conversao)
            db.session.commit()
            flash('Conversão de unidade cadastrada com sucesso!', 'success')
            return redirect(url_for('conversao_unidade.index'))
        except ValueError:
            flash('O fator de conversão deve ser um número válido!', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'Erro ao cadastrar conversão: {str(e)}', 'danger')
    
    return redirect(url_for('conversao_unidade.index'))

@conversao_unidade_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'gerente'])
def editar(id):
    """Edita uma conversão de unidade existente."""
    conversao = ConversaoUnidade.query.get_or_404(id)
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        unidade_entrada = request.form.get('unidade_entrada')
        unidade_saida = request.form.get('unidade_saida')
        fator = request.form.get('fator')
        
        if not nome or not unidade_entrada or not unidade_saida or not fator:
            flash('Todos os campos são obrigatórios!', 'danger')
            return redirect(url_for('conversao_unidade.index'))
        
        try:
            fator = float(fator)
            conversao.nome = nome
            conversao.unidade_entrada = unidade_entrada
            conversao.unidade_saida = unidade_saida
            conversao.fator = fator
            
            db.session.commit()
            flash('Conversão de unidade atualizada com sucesso!', 'success')
            return redirect(url_for('conversao_unidade.index'))
        except ValueError:
            flash('O fator de conversão deve ser um número válido!', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'Erro ao atualizar conversão: {str(e)}', 'danger')
    
    return redirect(url_for('conversao_unidade.index'))

@conversao_unidade_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
@role_required(['admin', 'gerente'])
def excluir(id):
    """Exclui uma conversão de unidade."""
    conversao = ConversaoUnidade.query.get_or_404(id)
    
    try:
        db.session.delete(conversao)
        db.session.commit()
        flash('Conversão de unidade excluída com sucesso!', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'Erro ao excluir conversão: {str(e)}', 'danger')
    
    return redirect(url_for('conversao_unidade.index'))

@conversao_unidade_bp.route('/api/unidades', methods=['GET'])
@login_required
def obter_unidades():
    """API para obter todas as unidades únicas."""
    print("DEBUG: Solicitação para obter unidades recebida")
    unidades = obter_unidades_unicas()
    print(f"DEBUG: Retornando {len(unidades)} unidades: {unidades}")
    return jsonify(unidades)

@conversao_unidade_bp.route('/api/conversoes', methods=['GET'])
@login_required
def obter_conversoes():
    """API para obter conversões disponíveis entre duas unidades."""
    unidade_origem = request.args.get('origem')
    unidade_destino = request.args.get('destino')
    
    print(f"DEBUG: Buscando conversões: {unidade_origem} -> {unidade_destino}")
    print(f"DEBUG: Todos os parâmetros da requisição: {request.args}")
    
    # Verificar existência de conversões no banco de dados
    total_conversoes = ConversaoUnidade.query.count()
    print(f"DEBUG: Total de conversões no banco de dados: {total_conversoes}")
    
    if total_conversoes == 0:
        print("DEBUG: ALERTA! Não há conversões cadastradas no banco de dados.")
        # Se não há conversões, podemos criar algumas básicas
        try:
            inserir_conversoes_padrao()
            print("DEBUG: Conversões padrão inseridas com sucesso")
        except Exception as e:
            print(f"DEBUG: Erro ao inserir conversões padrão: {e}")
    
    if not unidade_origem or not unidade_destino:
        print("DEBUG: Unidades não fornecidas corretamente")
        return jsonify([])
    
    # Buscar conversões diretas (origem -> destino)
    conversoes_diretas = ConversaoUnidade.query.filter_by(
        unidade_entrada=unidade_origem,
        unidade_saida=unidade_destino
    ).all()
    
    print(f"DEBUG: Conversões diretas encontradas: {len(conversoes_diretas)}")
    for conv in conversoes_diretas:
        print(f"DEBUG: Conversão direta: ID={conv.id}, Nome={conv.nome}, {conv.unidade_entrada} -> {conv.unidade_saida}, Fator={conv.fator}")
    
    # Buscar conversões inversas (destino -> origem) para exibir também
    conversoes_inversas = ConversaoUnidade.query.filter_by(
        unidade_entrada=unidade_destino,
        unidade_saida=unidade_origem
    ).all()
    
    print(f"DEBUG: Conversões inversas encontradas: {len(conversoes_inversas)}")
    for conv in conversoes_inversas:
        print(f"DEBUG: Conversão inversa: ID={conv.id}, Nome={conv.nome}, {conv.unidade_entrada} -> {conv.unidade_saida}, Fator={conv.fator}")
    
    # Formatar para retornar como JSON
    resultado = []
    
    for conversao in conversoes_diretas:
        resultado.append({
            'id': conversao.id,
            'nome': conversao.nome,
            'unidade_entrada': conversao.unidade_entrada,
            'unidade_saida': conversao.unidade_saida,
            'fator': conversao.fator,
            'tipo': 'direta'
        })
    
    for conversao in conversoes_inversas:
        resultado.append({
            'id': conversao.id,
            'nome': conversao.nome + ' (inversa)',
            'unidade_entrada': conversao.unidade_entrada,
            'unidade_saida': conversao.unidade_saida,
            'fator': 1 / conversao.fator if conversao.fator != 0 else 0,
            'tipo': 'inversa'
        })
    
    print(f"DEBUG: Total de conversões retornadas: {len(resultado)}")
    return jsonify(resultado)

@conversao_unidade_bp.route('/api/converter', methods=['POST'])
@login_required
def converter():
    """API para converter valores entre unidades."""
    data = request.get_json()
    
    if not data or 'valor' not in data or 'de' not in data or 'para' not in data:
        return jsonify({'erro': 'Dados incompletos'}), 400
    
    try:
        valor = float(data['valor'])
        unidade_entrada = data['de']
        unidade_saida = data['para']
        
        # Procura a conversão direta
        conversao = ConversaoUnidade.query.filter_by(
            unidade_entrada=unidade_entrada,
            unidade_saida=unidade_saida
        ).first()
        
        if conversao:
            resultado = valor * conversao.fator
            return jsonify({
                'resultado': resultado,
                'de': unidade_entrada,
                'para': unidade_saida,
                'fator': conversao.fator
            })
        
        # Verifica se existe a conversão inversa
        conversao_inversa = ConversaoUnidade.query.filter_by(
            unidade_entrada=unidade_saida,
            unidade_saida=unidade_entrada
        ).first()
        
        if conversao_inversa:
            resultado = valor / conversao_inversa.fator
            return jsonify({
                'resultado': resultado,
                'de': unidade_entrada,
                'para': unidade_saida,
                'fator': 1/conversao_inversa.fator
            })
        
        return jsonify({'erro': 'Conversão não encontrada'}), 404
        
    except ValueError:
        return jsonify({'erro': 'Valor inválido'}), 400
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@conversao_unidade_bp.route('/api/obter/<int:id>', methods=['GET'])
@login_required
@role_required(['admin', 'gerente'])
def obter_conversao(id):
    """Retorna os dados de uma conversão específica."""
    conversao = ConversaoUnidade.query.get_or_404(id)
    return jsonify({
        'id': conversao.id,
        'nome': conversao.nome,
        'unidade_entrada': conversao.unidade_entrada,
        'unidade_saida': conversao.unidade_saida,
        'fator': conversao.fator
    }) 