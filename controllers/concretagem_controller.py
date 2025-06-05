import logging
from flask import Blueprint, render_template, redirect, request, url_for, flash, jsonify
from models import Concretagem, Tanque, Peca, ConcretagemPeca, ConcretagemTanque, UsinagemConcreto, db, CentroCusto, Contrato
from flask_login import login_required
#from flask_wtf.csrf import csrf_exempt
import json
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import text
# Definir o blueprint
concretagem = Blueprint('concretagem', __name__, url_prefix='/concretagens')

@concretagem.route('/')
@login_required
def index():
    """Lista todas as concretagens cadastradas"""
    concretagens = Concretagem.query.order_by(Concretagem.data_concretagem.desc()).all()
    
    # Buscar dados para o modal de nova concretagem
    tanques = Tanque.query.join(Contrato).join(CentroCusto).order_by(CentroCusto.nome).all()
    usinagens = UsinagemConcreto.query.order_by(UsinagemConcreto.data_usinagem.desc(),UsinagemConcreto.nbt.desc(),UsinagemConcreto.nota.desc()).all()
    
    return render_template('concretagens/index.html', 
                           concretagens=concretagens,
                           tanques=tanques,
                           usinagens=usinagens)

@concretagem.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """Cria uma nova concretagem"""
    tanques = Tanque.query.order_by(Tanque.nome).all()
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            tanque_ids = request.form.getlist('tanque_ids')
            data_concretagem = request.form.get('data_concretagem')
            pista = request.form.get('pista')
            observacoes = request.form.get('observacoes', '')
            peca_ids = request.form.getlist('peca_ids')
            formas = request.form.getlist('formas')
            
            # Validar dados
            if not tanque_ids or not data_concretagem or not pista or not peca_ids:
                flash('Todos os campos obrigatórios devem ser preenchidos', 'danger')
                return render_template('concretagens/novo.html', tanques=tanques)
            
            # Converter data
            try:
                data_concretagem = datetime.strptime(data_concretagem, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de data inválido', 'danger')
                return render_template('concretagens/novo.html', tanques=tanques)
            
            # Criar nova concretagem
            concretagem = Concretagem(
                data_concretagem=data_concretagem,
                pista=pista,
                observacoes=observacoes
            )
            
            # Adicionar os tanques selecionados
            for tanque_id in tanque_ids:
                tanque = Tanque.query.get(tanque_id)
                if tanque:
                    concretagem.adicionar_tanque(tanque)
            
            # Adicionar peças com suas formas
            for i, peca_id in enumerate(peca_ids):
                peca = Peca.query.get(peca_id)
                if peca and str(peca.tanque_id) in tanque_ids:
                    # Obter a forma correspondente, se existir
                    forma = formas[i] if i < len(formas) else None
                    concretagem.adicionar_peca(peca, forma)
            
            # Salvar no banco de dados
            concretagem.save()
            
            flash('Concretagem cadastrada com sucesso!', 'success')
            return redirect(url_for('concretagem.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao cadastrar concretagem: {str(e)}', 'danger')
    
    return render_template('concretagens/novo.html', tanques=tanques)

@concretagem.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Edita uma concretagem existente"""
    concretagem = Concretagem.query.get_or_404(id)
    tanques = Tanque.query.order_by(Tanque.nome).all()
    usinagens = UsinagemConcreto.query.order_by(UsinagemConcreto.data_usinagem.desc()).all()
    
    if request.method == 'POST':
        try:
            # Obter dados do formulário
            tanque_ids = request.form.getlist('tanque_ids')
            data_concretagem = request.form.get('data_concretagem')
            pista = request.form.get('pista')
            observacoes = request.form.get('observacoes', '')
            peca_ids = request.form.getlist('peca_ids')
            formas = request.form.getlist('formas')
            usinagem_ids = request.form.getlist('usinagem_ids')
            
            # Validar dados
            if not tanque_ids or not data_concretagem or not pista or not peca_ids:
                flash('Todos os campos obrigatórios devem ser preenchidos', 'danger')
                return render_template('concretagens/editar.html', 
                                      concretagem=concretagem, 
                                      tanques=tanques,
                                      usinagens=usinagens)
            
            # Converter data
            try:
                data_concretagem = datetime.strptime(data_concretagem, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de data inválido', 'danger')
                return render_template('concretagens/editar.html', 
                                      concretagem=concretagem, 
                                      tanques=tanques,
                                      usinagens=usinagens)
            
            # Atualizar concretagem
            concretagem.data_concretagem = data_concretagem
            concretagem.pista = pista
            concretagem.observacoes = observacoes
            
            # Atualizar tanques
            # Primeiro removemos todas as associações existentes
            for ct in list(concretagem.tanques_associados):
                db.session.delete(ct)
            
            # Depois adicionamos as novas associações
            for tanque_id in tanque_ids:
                tanque = Tanque.query.get(tanque_id)
                if tanque:
                    concretagem.adicionar_tanque(tanque)
            
            # Atualizar peças
            # Primeiro removemos todas as associações existentes
            for cp in list(concretagem.pecas_associadas):
                db.session.delete(cp)
            
            # Depois adicionamos as novas associações
            for i, peca_id in enumerate(peca_ids):
                peca = Peca.query.get(peca_id)
                if peca and str(peca.tanque_id) in tanque_ids:
                    # Obter a forma correspondente, se existir
                    forma = formas[i] if i < len(formas) else None
                    
                    # Obter a usinagem correspondente, se existir
                    usinagem_id = usinagem_ids[i] if i < len(usinagem_ids) and usinagem_ids[i] else None
                    usinagem = UsinagemConcreto.query.get(usinagem_id) if usinagem_id else None
                    
                    cp = ConcretagemPeca(
                        concretagem=concretagem, 
                        peca=peca, 
                        forma=forma,
                        usinagem_id=usinagem.id if usinagem else None
                    )
                    db.session.add(cp)
            
            # Salvar no banco de dados
            concretagem.save()
            
            flash('Concretagem atualizada com sucesso!', 'success')
            return redirect(url_for('concretagem.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar concretagem: {str(e)}', 'danger')
    
    # Obter IDs dos tanques da concretagem para pré-selecionar no formulário
    tanque_ids = [ct.tanque_id for ct in concretagem.tanques_associados]
    
    return render_template('concretagens/editar.html', 
                          concretagem=concretagem, 
                          tanques=tanques,
                          usinagens=usinagens,
                          tanque_ids=tanque_ids)

@concretagem.route('/<int:id>/visualizar')
@login_required
def visualizar(id):
    """Visualiza detalhes de uma concretagem"""
    concretagem = Concretagem.query.get_or_404(id)
    # Obtemos as associações para ter acesso às formas de cada peça e usinagens
    pecas_com_dados = [(cp.peca, cp.forma, cp.usinagem) for cp in concretagem.pecas_associadas]
    # Obtemos os tanques associados
    tanques = concretagem.tanques
    return render_template('concretagens/visualizar.html', 
                          concretagem=concretagem,
                          pecas_com_dados=pecas_com_dados,
                          tanques=tanques)

@concretagem.route('/<int:id>/excluir', methods=['POST'])
@login_required
def excluir(id):
    """Exclui uma concretagem"""
    try:
        print(f"Iniciando exclusão da concretagem {id}")
        concretagem = Concretagem.query.get_or_404(id)
        print(f"Concretagem encontrada: {concretagem}")
        
        # Obter nomes dos tanques para mensagem de confirmação
        tanques_nomes = [tanque.nome for tanque in concretagem.tanques]
        data_formatada = concretagem.data_concretagem.strftime('%d/%m/%Y')
        
        print(f"Removendo associações de peças...")
        # Remover manualmente as associações de peças primeiro
        for cp in list(concretagem.pecas_associadas):
            print(f"Removendo associação com peça {cp.peca_id}")
            db.session.delete(cp)
        
        print(f"Removendo associações de tanques...")
        # Remover manualmente as associações de tanques
        for ct in list(concretagem.tanques_associados):
            print(f"Removendo associação com tanque {ct.tanque_id}")
            db.session.delete(ct)
        
        print("Removendo concretagem...")
        # Depois remover a concretagem
        db.session.delete(concretagem)
        db.session.commit()
        
        print("Exclusão concluída com sucesso")
        flash(f'Concretagem #{id} - {", ".join(tanques_nomes)} ({data_formatada}) excluída com sucesso!', 'success')
        
    except Exception as e:
        print(f"Erro ao excluir concretagem {id}: {str(e)}")
        import traceback
        print(traceback.format_exc())
        db.session.rollback()
        flash(f'Erro ao excluir concretagem: {str(e)}', 'danger')
    
    # Usando URL absoluta em vez de url_for
    return redirect('/concretagens/')

@concretagem.route('/api/tanque/<int:tanque_id>/pecas')
@login_required
def get_pecas_por_tanque(tanque_id):
    """Retorna as peças de um tanque em formato JSON para ser usado em seleção dinâmica"""
    try:
        print(f"[API] Função get_pecas_por_tanque chamada com tanque_id: {tanque_id}")
        logging.info(f"[API] Buscando peças para o tanque ID: {tanque_id}")
        
        # Verificar se o tanque existe
        tanque = Tanque.query.get(tanque_id)
        if not tanque:
            print(f"[API] Tanque ID {tanque_id} não encontrado")
            logging.warning(f"[API] Tanque ID {tanque_id} não encontrado")
            return jsonify({'erro': f'Tanque ID {tanque_id} não encontrado', 'status': 'error'}), 404
            
        # Verificar se deve filtrar apenas peças não concretadas
        mostrar_nao_concretadas = request.args.get('nao_concretadas', 'false').lower() == 'true'
        print(f"[API] Filtro mostrar_nao_concretadas: {mostrar_nao_concretadas}")
        
        # Obter todas as peças do tanque
        pecas = Peca.query.filter_by(tanque_id=tanque_id).order_by(Peca.numero_sequencial).all()
        print(f"[API] Quantidade de peças encontradas: {len(pecas)}")
        
        # Obter IDs de peças já concretadas
        pecas_concretadas_ids = db.session.query(ConcretagemPeca.peca_id).distinct().all()
        pecas_concretadas_ids = [p[0] for p in pecas_concretadas_ids]
        print(f"[API] Peças já concretadas: {len(pecas_concretadas_ids)}")
        
        # Preparar resultados
        result = []
        for peca in pecas:
            concretada = peca.id in pecas_concretadas_ids
            
            # Se só quer não concretadas e a peça está concretada, pular
            if mostrar_nao_concretadas and concretada:
                continue
                
            # Garantir que todos os campos necessários estejam presentes e com nomes consistentes
            peca_dict = {
                'id': peca.id,
                'nome': peca.nome,
                'tipo': peca.tipo,
                'numero_sequencial': peca.numero_sequencial,
                'concretada': concretada
            }
            result.append(peca_dict)
        
        print(f"[API] Retornando {len(result)} peças no resultado final")
        # Adicionar um cabeçalho para evitar caching
        response = jsonify(result)
        response.headers.add('Cache-Control', 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0')
        return response
        
    except Exception as e:
        print(f"[API] Erro ao buscar peças do tanque: {str(e)}")
        logging.error(f"[API] Erro ao buscar peças do tanque {tanque_id}: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar peças: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/api/concretagem/<int:concretagem_id>', methods=['GET'])
@login_required
##@csrf_exempt
def get_concretagem_por_id(concretagem_id):
    """Retorna detalhes de uma concretagem em formato JSON para ser usado em edição dinâmica"""
    try:
        # Esta rota não precisa de CSRF pois é uma requisição de leitura apenas (GET)
        
        print(f"[API] Buscando dados da concretagem ID: {concretagem_id}")
        
        # Buscar a concretagem
        concretagem = Concretagem.query.get_or_404(concretagem_id)
        
        # Buscar os tanques associados
        tanques = []
        for ct in concretagem.tanques_associados:
            tanques.append({
                'id': ct.tanque.id,
                'nome': ct.tanque.nome,
                'sistema': ct.tanque.sistema
            })
        
        # Buscar as peças associadas
        pecas = []
        for cp in concretagem.pecas_associadas:
            pecas.append({
                'id': cp.peca.id,
                'nome': cp.peca.nome,
                'tipo': cp.peca.tipo,
                'numero_sequencial': cp.peca.numero_sequencial,
                'tanque_id': cp.peca.tanque_id,
                'tanque_nome': cp.peca.tanque.nome,
                'forma': cp.forma,
                'usinagem_id': cp.usinagem_id
            })
        
        # Formatar os dados para retorno em JSON
        result = {
            'id': concretagem.id,
            'tanques': tanques,
            'data_concretagem': concretagem.data_concretagem.strftime('%Y-%m-%d'),
            'pista': concretagem.pista,
            'observacoes': concretagem.observacoes or '',
            'pecas': pecas,
            'data_cadastro': concretagem.data_cadastro.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Adicionar cabeçalho para evitar caching
        response = jsonify(result)
        response.headers.add('Cache-Control', 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0')
        return response
        
    except Exception as e:
        print(f"[API] Erro ao buscar dados da concretagem: {str(e)}")
        logging.error(f"[API] Erro ao buscar dados da concretagem {concretagem_id}: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar dados da concretagem: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/api/concretagem/<int:concretagem_id>/pecas', methods=['GET'])
@login_required
##@csrf_exempt
def get_pecas_concretagem(concretagem_id):
    """Retorna peças de uma concretagem em formato JSON"""
    try:
        print(f"[API] Buscando peças da concretagem ID: {concretagem_id}")
        
        # Buscar a concretagem
        concretagem = Concretagem.query.get_or_404(concretagem_id)
        
        # Buscar as peças associadas
        pecas = []
        for cp in concretagem.pecas_associadas:
            pecas.append({
                'id': cp.peca.id,
                'tanque': cp.peca.tanque.nome,
                'nome': cp.peca.nome,
                'tipo': cp.peca.tipo,
                'numero_sequencial': cp.peca.numero_sequencial,
                'forma': cp.forma,
                'usinagem_id': cp.usinagem_id
            })
        
        return jsonify(pecas)
        
    except Exception as e:
        print(f"[API] Erro ao buscar peças da concretagem: {str(e)}")
        logging.error(f"[API] Erro ao buscar peças da concretagem {concretagem_id}: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar peças da concretagem: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/referenciar-usinagem/<int:concretagem_id>', methods=['POST'])
@login_required
def referenciar_usinagem(concretagem_id):
    """Referencia uma usinagem às peças selecionadas de uma concretagem"""
    try:
        # Buscar a concretagem
        concretagem = Concretagem.query.get_or_404(concretagem_id)
        
        # Obter dados do formulário
        usinagem_id = request.form.get('usinagem_id')
        peca_ids = request.form.getlist('peca_ids')
        
        # Validar dados
        if not usinagem_id or not peca_ids:
            flash('Selecione uma usinagem e pelo menos uma peça', 'danger')
            return redirect(url_for('concretagem.index'))
        
        # Buscar a usinagem
        usinagem = UsinagemConcreto.query.get_or_404(usinagem_id)
        
        # Atualizar as peças selecionadas
        for associacao in concretagem.pecas_associadas:
            if str(associacao.peca_id) in peca_ids:
                associacao.usinagem_id = usinagem.id
        
        # Salvar no banco de dados
        db.session.commit()
        
        flash(f'Usinagem referenciada com sucesso para {len(peca_ids)} peças!', 'success')
        return redirect(url_for('concretagem.index'))
        
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao referenciar usinagem: {str(e)}")
        flash(f'Erro ao referenciar usinagem: {str(e)}', 'danger')
        return redirect(url_for('concretagem.index'))

@concretagem.route('/pecas-tanque/<int:tanque_id>')
@login_required
def pecas_tanque(tanque_id):
    """Rota alternativa para buscar peças de um tanque"""
    try:
        print(f"[ALTERNATIVA] Rota pecas_tanque chamada com tanque_id: {tanque_id}")
        logging.info(f"[ALTERNATIVA] Buscando peças para o tanque ID: {tanque_id}")
        
        # Verificar se o tanque existe
        tanque = Tanque.query.get(tanque_id)
        if not tanque:
            print(f"[ALTERNATIVA] Tanque ID {tanque_id} não encontrado")
            logging.warning(f"[ALTERNATIVA] Tanque ID {tanque_id} não encontrado")
            return jsonify({'erro': f'Tanque ID {tanque_id} não encontrado', 'status': 'error'}), 404
        
        # Verificar se deve filtrar apenas peças não concretadas
        mostrar_nao_concretadas = request.args.get('nao_concretadas', 'false').lower() == 'true'
        
        # Obter todas as peças do tanque
        pecas = Peca.query.filter_by(tanque_id=tanque_id).order_by(Peca.numero_sequencial).all()
        print(f"[ALTERNATIVA] Quantidade de peças encontradas: {len(pecas)}")
        
        # Obter IDs de peças já concretadas
        pecas_concretadas_ids = db.session.query(ConcretagemPeca.peca_id).distinct().all()
        pecas_concretadas_ids = [p[0] for p in pecas_concretadas_ids]
        print(f"[ALTERNATIVA] Total de peças concretadas no sistema: {len(pecas_concretadas_ids)}")
        
        # Preparar resultados
        result = []
        for peca in pecas:
            concretada = peca.id in pecas_concretadas_ids
            
            # Se só quer não concretadas e a peça está concretada, pular
            if mostrar_nao_concretadas and concretada:
                continue
                
            result.append({
                'id': peca.id,
                'nome': peca.nome,
                'tipo': peca.tipo,
                'numero_sequencial': peca.numero_sequencial,
                'concretada': concretada
            })
            
        print(f"[ALTERNATIVA] Retornando {len(result)} peças")
        response = jsonify(result)
        response.headers.add('Cache-Control', 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0')
        return response
        
    except Exception as e:
        print(f"[ALTERNATIVA] Erro ao buscar peças do tanque: {str(e)}")
        logging.error(f"[ALTERNATIVA] Erro ao buscar peças do tanque {tanque_id}: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar peças: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/api/diagnostico')
@login_required
##@csrf_exempt
def diagnostico_api():
    """Endpoint para diagnóstico da API de concretagens"""
    try:
        # Obter estatísticas básicas
        total_tanques = Tanque.query.count()
        total_pecas = Peca.query.count()
        total_concretagens = Concretagem.query.count()
        total_usinagens = UsinagemConcreto.query.count()
        
        # Verificar conexão com o banco de dados
        db_ok = True
        db_message = "Conexão com banco de dados ativa"
        try:
            # Testar consulta simples
            db.session.execute("SELECT 1")
        except Exception as e:
            db_ok = False
            db_message = f"Erro na conexão com banco de dados: {str(e)}"
        
        # Obter as últimas concretagens (limitadas a 5)
        ultimas_concretagens = []
        try:
            recentes = Concretagem.query.order_by(Concretagem.data_concretagem.desc()).limit(5).all()
            for conc in recentes:
                ultimas_concretagens.append({
                    'id': conc.id,
                    'data': conc.data_concretagem.strftime('%d/%m/%Y') if conc.data_concretagem else 'N/A',
                    'tanque': conc.tanque.id if conc.tanque else 'N/A',
                    'num_pecas': len(conc.pecas)
                })
        except Exception as e:
            ultimas_concretagens = [{'erro': str(e)}]
        
        # Obter informações sobre todos os tanques
        tanques_info = []
        try:
            tanques = Tanque.query.all()
            for tanque in tanques:
                num_pecas = Peca.query.filter_by(tanque_id=tanque.id).count()
                tanques_info.append({
                    'id': tanque.id,
                    'nome': tanque.nome,
                    'sistema': tanque.sistema,
                    'num_pecas': num_pecas
                })
        except Exception as e:
            tanques_info = [{'erro': str(e)}]
        
        diagnostico = {
            'status': 'ok',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mensagem': 'API de concretagens funcionando normalmente',
            'database': {
                'status': 'conectado' if db_ok else 'erro',
                'mensagem': db_message
            },
            'estatisticas': {
                'total_tanques': total_tanques,
                'total_pecas': total_pecas,
                'total_concretagens': total_concretagens,
                'total_usinagens': total_usinagens
            },
            'tanques': tanques_info,
            'ultimas_concretagens': ultimas_concretagens,
            'rotas_disponiveis': [
                '/concretagens/',
                '/concretagens/novo',
                '/concretagens/pecas-tanque/<tanque_id>',
                '/concretagens/api/tanque/<tanque_id>/pecas',
                '/concretagens/api/diagnostico'
            ]
        }
        
        return jsonify(diagnostico)
    except Exception as e:
        logging.error(f"Erro no diagnóstico da API: {str(e)}")
        return jsonify({
            'status': 'erro',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mensagem': f'Erro ao gerar diagnóstico: {str(e)}'
        }), 500

@concretagem.route('/api/tanques/pecas', methods=['POST'])
@login_required
def get_pecas_por_tanques():
    """Retorna as peças de múltiplos tanques em formato JSON para ser usado em seleção dinâmica"""
    try:
        # Obter lista de IDs de tanques do corpo da requisição
        data = request.get_json()
        if not data or 'tanque_ids' not in data:
            return jsonify({'erro': 'IDs de tanques não fornecidos', 'status': 'error'}), 400
            
        tanque_ids = data['tanque_ids']
        print(f"[API] Função get_pecas_por_tanques chamada com tanque_ids: {tanque_ids}")
        
        # Verificar se deve filtrar apenas peças não concretadas
        mostrar_nao_concretadas = data.get('nao_concretadas', False)
        print(f"[API] Filtro mostrar_nao_concretadas: {mostrar_nao_concretadas}")
        
        # Obter todas as peças dos tanques selecionados
        pecas = Peca.query.filter(Peca.tanque_id.in_(tanque_ids)).order_by(Peca.id).all()
        print(f"[API] Quantidade de peças encontradas: {len(pecas)}")
        
        # Obter IDs de peças já concretadas
        pecas_concretadas_ids = db.session.query(ConcretagemPeca.peca_id).distinct().all()
        pecas_concretadas_ids = [p[0] for p in pecas_concretadas_ids]
        print(f"[API] Peças já concretadas: {len(pecas_concretadas_ids)}")
        
        # Preparar resultados
        result = []
        for peca in pecas:
            concretada = peca.id in pecas_concretadas_ids
            
            # Se só quer não concretadas e a peça está concretada, pular
            if mostrar_nao_concretadas and concretada:
                continue
                
            # Garantir que todos os campos necessários estejam presentes
            peca_dict = {
                'id': peca.id,
                'nome': peca.nome,
                'tipo': peca.tipo,
                'numero_sequencial': peca.numero_sequencial,
                'tanque_nome': peca.tanque.nome,
                'tanque_id': peca.tanque_id,
                'concretada': concretada
            }
            result.append(peca_dict)
        
        print(f"[API] Retornando {len(result)} peças no resultado final")
        # Adicionar um cabeçalho para evitar caching
        response = jsonify(result)
        response.headers.add('Cache-Control', 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0')
        return response
        
    except Exception as e:
        print(f"[API] Erro ao buscar peças dos tanques: {str(e)}")
        logging.error(f"[API] Erro ao buscar peças dos tanques {tanque_ids}: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar peças: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/api/<int:id>/visualizar')
@login_required
def api_visualizar(id):
    concretagem = Concretagem.query.get_or_404(id)
    pecas = []
    for cp in concretagem.pecas_associadas:
        pecas.append({
            'tipo': cp.peca.tipo,
            'nome': cp.peca.nome,
            'numero_sequencial': cp.peca.numero_sequencial,
            'forma': cp.forma,
            'usinagem': {
                'data_usinagem': cp.usinagem.data_usinagem.strftime('%d/%m/%Y') if cp.usinagem else None,
                'traco_nome': cp.usinagem.traco.nome if cp.usinagem and cp.usinagem.traco else None
            } if cp.usinagem else None
        })
    tanques = [{'id': t.id, 'nome': t.nome, 'sistema': t.sistema} for t in concretagem.tanques]
    return jsonify({
        'id': concretagem.id,
        'pista': concretagem.pista,
        'data_concretagem': concretagem.data_concretagem.strftime('%d/%m/%Y'),
        'observacoes': concretagem.observacoes,
        'data_cadastro': concretagem.data_cadastro.strftime('%d/%m/%Y %H:%M'),
        'ultima_atualizacao': concretagem.ultima_atualizacao.strftime('%d/%m/%Y %H:%M'),
        'tanques': tanques,
        'pecas': pecas
    })

@concretagem.route('/<int:id>/alongamentos', methods=['POST'])
@login_required
def salvar_alongamentos(id):
    concretagem = Concretagem.query.get_or_404(id)
    
    try:
        alongamentos = request.form.get('alongamentos')
        if alongamentos:
            concretagem.alongamentos = alongamentos
            concretagem.save()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Dados de alongamentos inválidos'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@concretagem.route('/api/tanques/<int:id>/detalhes')
@login_required
def detalhes_tanques(id):
    concretagem = Concretagem.query.get_or_404(id)
    tanques = []
    
    for tanque in concretagem.tanques:
        tanques.append({
            'id': tanque.id,
            'nome': tanque.nome,
            'ncabospn': tanque.ncabospn,
            'ncabospf': tanque.ncabospf
        })
    if tanques:
        return jsonify({'success': True, 'tanques': tanques, 'alongamentos': concretagem.alongamentos})
    else:
        return jsonify({'success': False, 'message': 'Nenhum tanque encontrado'})

@concretagem.route('/api/teste_planilha')
@login_required
def teste_planilha():
   
    df = pd.read_excel("pecas.xlsx", sheet_name="CADASTRO")
    df=df.sort_values(by='SEQ')
    seq=0
    for index, row in df.iterrows():
        if row['DATA'] not in [None, np.nan]:
            if 'PRIMARIO' in row['TANQUE']:
                tq_id=4
            if 'REATOR' in row['TANQUE']:
                tq_id=1
            pc = Peca.query.filter(Peca.nome.like(f'%{row['NOME']}%'),Peca.tanque_id==tq_id).first()
            if row['SEQ']!=seq and seq not in [None, np.nan]:
                seq=row['SEQ']
                partes = row['PISTA'].split('-')
                pista = None
                if len(partes)==2:
                    pista = int(partes[-1].lstrip('0'))

                concretagem = Concretagem(
                    data_concretagem=row['DATA'],
                    pista=pista
                )
                db.session.add(concretagem)
                db.session.flush()
            conPeca = ConcretagemPeca(
                concretagem_id=concretagem.id,
                peca_id=pc.id
            )
            db.session.add(conPeca)
            db.session.flush()
            pc.data_concretagem=row['DATA'].strftime('%Y-%m-%d') if pd.notna(row['DATA']) else None
            acabamento=None
            if row['ACABAMENTO'] not in [None, np.nan]:
                acabamento=row['ACABAMENTO']
            chapa=None
            if row['CHAPA'] not in [None, np.nan,'A DEFINIR','SEM CHAPA','NÃO TEM CHAPA']:
                chapa=row['CHAPA']
            transporte=None
            if row['DATA TRANS.'] not in [None, np.nan]:
                transporte={
                    'data_transporte': row['DATA TRANS.'].strftime('%Y-%m-%d') if pd.notna(row['DATA TRANS.']) else None,
                    'placa': row['PLACA'] if pd.notna(row['PLACA']) else None,
                    'nota': row['NF'] if pd.notna(row['NF']) else None
                }
                pc.data_entrega=row['DATA TRANS.'].strftime('%Y-%m-%d') if pd.notna(row['DATA TRANS.']) else None
            pc.qualidade={
                'acabamento':acabamento,
                'chapa':chapa,
                'transporte':transporte
            }
            db.session.commit()

        return jsonify({'success': True, 'message': 'Planilha teste'})