import logging
from flask import Blueprint, render_template, redirect, request, url_for, flash, jsonify
from models.concreto import ConcretoConcretagens, ConcretoConcretagensTanques,ConcretoUsinagens
from models.tanque import Tanques, TanquesPecas, TanquesProdutoComposto
from models.contrato import Contrato
from models.centro_custo import CentroCusto
from models.database import db
from flask_login import login_required
#from flask_wtf.csrf import csrf_exempt
import json
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import joinedload
# Definir o blueprint
concretagem = Blueprint('concretagem', __name__, url_prefix='/concretagens')


@concretagem.route('/')
@login_required
def index():
    """Lista todas as concretagens cadastradas"""
    return render_template('concretagens/index.html')



@concretagem.route('/api/tanque/<int:tanque_id>/pecas')
@login_required
def get_pecas_por_tanque(tanque_id):
    """Retorna as peças de um tanque em formato JSON para ser usado em seleção dinâmica"""
    try:
        print(f"[API] Função get_pecas_por_tanque chamada com tanque_id: {tanque_id}")
        logging.info(f"[API] Buscando peças para o tanque ID: {tanque_id}")
        
        # Verificar se o tanque existe
        tanque = Tanques.query.get(tanque_id)
        if not tanque:
            print(f"[API] Tanque ID {tanque_id} não encontrado")
            logging.warning(f"[API] Tanque ID {tanque_id} não encontrado")
            return jsonify({'erro': f'Tanque ID {tanque_id} não encontrado', 'status': 'error'}), 404
            
        # Verificar se deve filtrar apenas peças não concretadas
        mostrar_nao_concretadas = request.args.get('nao_concretadas', 'false').lower() == 'true'
        print(f"[API] Filtro mostrar_nao_concretadas: {mostrar_nao_concretadas}")
        
        # Obter todas as peças do tanque
        pecas = TanquesPecas.query.filter_by(tanque_id=tanque_id).order_by(TanquesPecas.numero_sequencial).all()
        print(f"[API] Quantidade de peças encontradas: {len(pecas)}")
        
        # Obter IDs de peças já concretadas (verificar no campo pecas JSON)
        pecas_concretadas_ids = set()
        concretagens = ConcretoConcretagens.query.filter(ConcretoConcretagens.pecas.isnot(None)).all()
        for conc in concretagens:
            try:
                pecas_json = json.loads(conc.pecas) if isinstance(conc.pecas, str) else conc.pecas
                if isinstance(pecas_json, list):
                    for p in pecas_json:
                        if p.get('placa'):
                            pecas_concretadas_ids.add(str(p['placa']))
            except:
                pass
        
        print(f"[API] Peças já concretadas: {len(pecas_concretadas_ids)}")
        
        # Preparar resultados
        result = []
        for peca in pecas:
            concretada = str(peca.id) in pecas_concretadas_ids
            
            # Se só quer não concretadas e a peça está concretada, pular
            if mostrar_nao_concretadas and concretada:
                continue
                
            # Garantir que todos os campos necessários estejam presentes e com nomes consistentes
            peca_dict = {
                'id': peca.id,
                'nome': peca.nome,
                'tipo': peca.tipo,
                'numero_sequencial': peca.numero_sequencial,
                'tanque_nome': peca.tanque.nome if peca.tanque else '',
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
        print(f"[API] Erro ao buscar peças do tanque: {str(e)}")
        logging.error(f"[API] Erro ao buscar peças do tanque {tanque_id}: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar peças: {str(e)}', 'status': 'error'}), 500



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
        pecas = TanquesPecas.query.filter(TanquesPecas.tanque_id.in_(tanque_ids)).order_by(TanquesPecas.id).all()
        print(f"[API] Quantidade de peças encontradas: {len(pecas)}")
        
        # Obter IDs de peças já concretadas (verificar no campo pecas JSON)
        pecas_concretadas_ids = set()
        concretagens = ConcretoConcretagens.query.filter(ConcretoConcretagens.pecas.isnot(None)).all()
        for conc in concretagens:
            try:
                pecas_json = json.loads(conc.pecas) if isinstance(conc.pecas, str) else conc.pecas
                if isinstance(pecas_json, list):
                    for p in pecas_json:
                        if p.get('placa'):
                            pecas_concretadas_ids.add(p['placa'])
            except:
                pass
        
        print(f"[API] Peças já concretadas: {len(pecas_concretadas_ids)}")
        
        # Preparar resultados
        result = []
        for peca in pecas:
            concretada = str(peca.id) in pecas_concretadas_ids
            
            # Se só quer não concretadas e a peça está concretada, pular
            if mostrar_nao_concretadas and concretada:
                continue
                
            # Garantir que todos os campos necessários estejam presentes
            peca_dict = {
                'id': peca.id,
                'nome': peca.nome,
                'tipo': peca.tipo,
                'numero_sequencial': peca.numero_sequencial,
                'tanque_nome': peca.tanque.nome if peca.tanque else '',
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
        logging.error(f"[API] Erro ao buscar peças dos tanques: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar peças: {str(e)}', 'status': 'error'}), 500

# Novas rotas AJAX simplificadas

@concretagem.route('/api/listar')
@login_required
def api_listar():
    """Retorna lista de concretagens para DataTables"""
    try:
        concretagens = ConcretoConcretagens.query.order_by(ConcretoConcretagens.data_concretagem.desc()).all()
        
        data = []
        for conc in concretagens:
            pecas_count = 0
            if conc.pecas:
                try:
                    pecas_json = json.loads(conc.pecas) if isinstance(conc.pecas, str) else conc.pecas
                    if isinstance(pecas_json, list):
                        pecas_count = len(pecas_json)
                except:
                    pass
            
            data.append({
                'id': conc.id,
                'data_concretagem': conc.data_concretagem.isoformat() if conc.data_concretagem else None,
                'pista': conc.pista,
                'quantidade_pecas': pecas_count,
                'data_cadastro': conc.data_cadastro.isoformat() if conc.data_cadastro else None
            })
        
        return jsonify({'data': data})
    except Exception as e:
        logging.error(f"Erro ao listar concretagens: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao listar concretagens: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/api/novo', methods=['POST'])
@login_required
def api_novo():
    """Cria uma nova concretagem via AJAX"""
    try:
        data = request.get_json()
        
        if not data.get('data_concretagem') or not data.get('pista'):
            return jsonify({'success': False, 'message': 'Data e pista são obrigatórios'}), 400
        
        data_concretagem = datetime.strptime(data['data_concretagem'], '%Y-%m-%d').date()
        
        concretagem = ConcretoConcretagens(
            data_concretagem=data_concretagem,
            pista=data['pista']
        )
        
        concretagem.save()
        
        return jsonify({'success': True, 'id': concretagem.id, 'message': 'Concretagem cadastrada com sucesso!'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao criar concretagem: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao cadastrar concretagem: {str(e)}'}), 500

@concretagem.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    """Retorna dados de uma concretagem"""
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)
        
        return jsonify({
            'id': concretagem.id,
            'data_concretagem': concretagem.data_concretagem.strftime('%Y-%m-%d') if concretagem.data_concretagem else None,
            'pista': concretagem.pista,
            'cordoalhas': concretagem.cordoalhas,
            'pecas': concretagem.pecas
        })
    except Exception as e:
        logging.error(f"Erro ao buscar concretagem: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar concretagem: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/api/<int:id>/editar', methods=['POST'])
@login_required
def api_editar(id):
    """Edita uma concretagem via AJAX"""
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)
        data = request.get_json()
        
        if data.get('data_concretagem'):
            concretagem.data_concretagem = datetime.strptime(data['data_concretagem'], '%Y-%m-%d').date()
        
        if data.get('pista'):
            concretagem.pista = data['pista']
        
        concretagem.save()
        
        return jsonify({'success': True, 'message': 'Concretagem atualizada com sucesso!'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao editar concretagem: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao atualizar concretagem: {str(e)}'}), 500

@concretagem.route('/api/<int:id>/excluir', methods=['POST'])
@login_required
def api_excluir(id):
    """Exclui uma concretagem via AJAX"""
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)
        
        # Remover associações de tanques
        for ct in list(concretagem.tanques_associados):
            db.session.delete(ct)
        
        db.session.delete(concretagem)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Concretagem excluída com sucesso!'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao excluir concretagem: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao excluir concretagem: {str(e)}'}), 500

@concretagem.route('/api/<int:id>/alongamentos', methods=['POST'])
@login_required
def api_salvar_alongamentos(id):
    """Salva alongamentos de uma concretagem via AJAX"""
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)
        data = request.get_json()
        
        if data.get('cordoalhas'):
            concretagem.cordoalhas = data['cordoalhas']
            concretagem.save()
            return jsonify({'success': True, 'message': 'Alongamentos salvos com sucesso!'})
        
        return jsonify({'success': False, 'message': 'Dados de alongamentos inválidos'}), 400
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao salvar alongamentos: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao salvar alongamentos: {str(e)}'}), 500

@concretagem.route('/api/<int:id>/pecas', methods=['POST', 'GET'])
@login_required
def api_pecas(id):
    """Salva ou retorna peças de uma concretagem via AJAX"""
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)
        
        if request.method == 'POST':
            data = request.get_json()
            
            if data.get('pecas'):
                concretagem.pecas = data['pecas']
                concretagem.save()
                return jsonify({'success': True, 'message': 'Peças salvas com sucesso!'})
            
            return jsonify({'success': False, 'message': 'Dados de peças inválidos'}), 400
        else:
            # GET - retornar peças com objetos completos
            pecas_data = []
            if concretagem.pecas:
                try:
                    pecas_json = json.loads(concretagem.pecas) if isinstance(concretagem.pecas, str) else concretagem.pecas
                    if isinstance(pecas_json, list):
                        for peca_item in pecas_json:
                            peca_obj = {
                                'placa': peca_item.get('nome'),  # Nome da peça
                                'tanque': peca_item.get('tanque_id'),  # ID do tanque
                                'forma': peca_item.get('forma')
                            }
                            
                            # Buscar dados completos do tanque primeiro
                            tanque_obj = None
                            if peca_item.get('tanque'):
                                tanque_id = peca_item.get('tanque')
                                try:
                                    tanque_id_int = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
                                    tanque = Tanques.query.get(tanque_id_int)
                                    if tanque:
                                        tanque_obj = {
                                            'id': tanque.id,
                                            'nome': tanque.nome,
                                            'sistema': tanque.sistema
                                        }
                                        peca_obj['tanque_obj'] = tanque_obj
                                except (ValueError, TypeError) as e:
                                    print(f"[API] Erro ao converter ID do tanque {tanque_id}: {str(e)}")
                            
                            # Buscar dados completos da peça pelo nome e tanque_id
                            if peca_item.get('nome') and peca_item.get('tanque_id'):
                                peca_nome = peca_item.get('nome')  # Nome da peça
                                tanque_id = peca_item.get('tanque_id')
                                try:
                                    tanque_id_int = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
                                    # Buscar peça pelo nome e tanque_id (pode haver peças com mesmo nome em tanques diferentes)
                                    peca = TanquesPecas.query.filter_by(
                                        nome=peca_nome,
                                        tanque_id=tanque_id_int
                                    ).first()
                                    
                                    if peca:
                                        # Carregar qualidade para obter séries
                                        qualidade = {}
                                        if peca.qualidade:
                                            try:
                                                qualidade = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else peca.qualidade
                                            except:
                                                qualidade = {}
                                        
                                        peca_obj['peca'] = {
                                            'id': peca.id,
                                            'nome': peca.nome,
                                            'tipo': peca.tipo,
                                            'numero_sequencial': peca.numero_sequencial,
                                            'tanque_id': peca.tanque_id,
                                            'tanque_nome': peca.tanque.nome if peca.tanque else None,
                                            'qualidade': qualidade
                                        }
                                        
                                        # Se não tinha tanque_obj, buscar usando o tanque_id da peça
                                        if not peca_obj.get('tanque_obj') and peca.tanque:
                                            peca_obj['tanque_obj'] = {
                                                'id': peca.tanque.id,
                                                'nome': peca.tanque.nome,
                                                'sistema': peca.tanque.sistema
                                            }
                                    else:
                                        print(f"[API] Peça não encontrada: nome='{peca_nome}', tanque_id={tanque_id_int}")
                                except (ValueError, TypeError) as e:
                                    print(f"[API] Erro ao processar peça: {str(e)}")
                            
                            pecas_data.append(peca_obj)
                        
                        print(f"[API] Retornando {len(pecas_data)} peças com objetos completos para concretagem {id}")
                except Exception as e:
                    print(f"[API] Erro ao parsear peças: {str(e)}")
                    logging.error(f"Erro ao parsear peças da concretagem {id}: {str(e)}")
            
            return jsonify({'pecas': pecas_data})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao processar peças: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao processar peças: {str(e)}'}), 500

@concretagem.route('/api/tanques', methods=['GET'])
@login_required
def api_tanques():
    """Retorna lista de tanques"""
    try:
        tanques = Tanques.query.order_by(Tanques.nome).all()
        tanques_data = [{'id': t.id, 'nome': t.nome, 'sistema': t.sistema} for t in tanques]
        return jsonify({'tanques': tanques_data})
    except Exception as e:
        logging.error(f"Erro ao listar tanques: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao listar tanques: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/api/usinagens/por-data', methods=['GET'])
@login_required
def api_usinagens_por_data():
    """Retorna usinagens (séries) filtradas por data"""
    try:
        data_str = request.args.get('data')
        if not data_str:
            return jsonify({'series': []})
        
        # Converter data para datetime
        data_filtro = datetime.strptime(data_str, '%Y-%m-%d')
        data_fim = datetime.combine(data_filtro.date(), datetime.max.time())
        
        # Buscar usinagens da data
        usinagens = ConcretoUsinagens.query.filter(
            ConcretoUsinagens.data_usinagem >= data_filtro,
            ConcretoUsinagens.data_usinagem <= data_fim
        ).order_by(ConcretoUsinagens.data_usinagem.desc()).all()
        print(f"Usinagens encontradas: {len(usinagens)}")
        series_data = []
        for usinagem in usinagens:
            series_data.append({
                'serie': usinagem.serie,
                'data_usinagem': usinagem.data_usinagem.isoformat() if usinagem.data_usinagem else None,
                'volume': float(usinagem.volume) if usinagem.volume else 0,
                'nota': usinagem.nota,
                'flow': usinagem.flow
            })
        
        return jsonify({'series': series_data})
    except Exception as e:
        logging.error(f"Erro ao buscar usinagens por data: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar usinagens: {str(e)}', 'status': 'error'}), 500

@concretagem.route('/api/<int:id>/usinagens', methods=['POST'])
@login_required
def api_salvar_usinagens(id):
    """Salva referências de séries (usinagens) nas peças da concretagem - por peça individual"""
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)
        data = request.get_json()
        
        if not data.get('pecas'):
            return jsonify({'success': False, 'message': 'Nenhuma peça com séries fornecida'}), 400
        
        pecas_com_series = data.get('pecas', [])
        if not isinstance(pecas_com_series, list):
            return jsonify({'success': False, 'message': 'Formato de dados inválido'}), 400
        
        pecas_atualizadas = 0
        
        for peca_data in pecas_com_series:
            peca_id = peca_data.get('peca_id')
            peca_nome = peca_data.get('peca_nome')
            tanque_id = peca_data.get('tanque_id')
            series = peca_data.get('series', [])
            
            if not series or len(series) == 0:
                continue
            
            if not isinstance(series, list):
                series = [series]
            
            # Buscar a peça no banco
            peca = None
            if peca_id:
                try:
                    peca = TanquesPecas.query.get(int(peca_id))
                except (ValueError, TypeError):
                    pass
            
            # Se não encontrou por ID, tentar por nome e tanque
            if not peca and peca_nome and tanque_id:
                try:
                    tanque_id_int = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
                    peca = TanquesPecas.query.filter_by(
                        nome=peca_nome,
                        tanque_id=tanque_id_int
                    ).first()
                except (ValueError, TypeError) as e:
                    logging.warning(f"Erro ao buscar peça {peca_nome}: {str(e)}")
                    continue
            
            if not peca:
                logging.warning(f"Peça não encontrada: ID={peca_id}, Nome={peca_nome}, Tanque={tanque_id}")
                continue
            
            # Carregar qualidade atual
            qualidade = {}
            if peca.qualidade:
                try:
                    qualidade = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else peca.qualidade
                except:
                    qualidade = {}
            
            # Garantir que existe o array de séries
            if 'series' not in qualidade:
                qualidade['series'] = []
            
            # Substituir séries existentes pelas selecionadas
            # Primeiro, remover séries antigas que não estão mais selecionadas
            series_selecionadas_str = [str(s) for s in series]
            qualidade['series'] = [s for s in qualidade['series'] if str(s) in series_selecionadas_str]
            
            # Adicionar novas séries (evitando duplicatas)
            for serie in series:
                serie_str = str(serie)
                if serie_str not in [str(s) for s in qualidade['series']]:
                    qualidade['series'].append(serie_str)
            
            # Salvar qualidade atualizada
            peca.qualidade = json.dumps(qualidade, ensure_ascii=False)
            peca.save()
            pecas_atualizadas += 1
        
        if pecas_atualizadas > 0:
            return jsonify({
                'success': True, 
                'message': f'Séries referenciadas com sucesso em {pecas_atualizadas} peça(s)!'
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Nenhuma peça foi atualizada. Verifique se as peças existem e se há séries selecionadas.'
            }), 400
            
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao salvar referências de usinagens: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao salvar referências: {str(e)}'}), 500
