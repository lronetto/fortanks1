import logging
from flask import request, jsonify
from models.concreto import (
    ConcretoConcretagens,
    ConcretoUsinagens,
    peca_obj_ja_produzida,
    limpar_data_producao_em_qualidade_str,
    qualidade_peca_remover_data_producao_de_dados_adicionais,
)
from models.tanque import Tanques, TanquesPecas
from models.database import db
from flask_login import login_required, current_user
import json
from datetime import datetime
from .. import concretagem
from ..services.estado import concretagem_tem_alongamentos
from ..services.listagens import montar_dados_api_listar, montar_resumo_pecas_nao_produzidas
from ..services.producao import remover_movimentacoes_producao_peca_escopo_concretagens


@concretagem.route('/api/tanque/pecas', methods=['GET'])
@login_required
def get_pecas_por_tanque():
    """Retorna as peças de um tanque em formato JSON para ser usado em seleção dinâmica"""
    try:
        tanque_id = request.args.get('tanque_id', type=int)
        pista = request.args.get('pista', None)
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
        pecas = TanquesPecas.query.filter(TanquesPecas.tanque_id == tanque_id)
        pecas_ids = tanque.get_pecas_id_concretadas()
        # Filtrar apenas peças não concretadas se solicitado
        if mostrar_nao_concretadas:
            pecas = pecas.filter(TanquesPecas.id.notin_(pecas_ids))
        
        print(f"[API] Pista: {pista}")
        if pista:
            if 'PF' in pista:
                pecas = pecas.filter(TanquesPecas.tipo == 'PF')
            else:
                pecas = pecas.filter(TanquesPecas.tipo != 'PF')

        pecas = pecas.order_by(TanquesPecas.numero_sequencial).all()
        print(f"[API] Quantidade de peças encontradas: {len(pecas)}")
        
        # Preparar resultados
        result = []
        for peca in pecas:
            result.append(peca.to_dict())
        
        print(f"[API] Retornando {len(result)} peças no resultado final")
        # Adicionar um cabeçalho para evitar caching
        response = jsonify(result)
        response.headers.add('Cache-Control', 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0')
        return response
        
    except Exception as e:
        print(f"[API] Erro ao buscar peças do tanque: {str(e)}")
        logging.error(f"[API] Erro ao buscar peças do tanque {tanque_id}: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao buscar peças: {str(e)}', 'status': 'error'}), 500




@concretagem.route('/api/listar')
@login_required
def api_listar():
    """Retorna lista de concretagens para DataTables. Aceita ?status=concluido|em_andamento para filtrar."""
    try:
        filtro_status = request.args.get('status', '').strip().lower()
        data = montar_dados_api_listar(filtro_status)
        return jsonify({'data': data})
    except Exception as e:
        logging.error(f"Erro ao listar concretagens: {str(e)}", exc_info=True)
        return jsonify({'erro': f'Erro ao listar concretagens: {str(e)}', 'status': 'error'}), 500


@concretagem.route('/api/resumo-pecas-nao-produzidas', methods=['GET'])
@login_required
def api_resumo_pecas_nao_produzidas():
    """
    Agrega quantidade de peças referenciadas em concretagens que ainda não têm produção
    (sem data_producao na qualidade), agrupado por tanque e tipo da peça.
    """
    try:
        linhas, total = montar_resumo_pecas_nao_produzidas()
        return jsonify({'data': linhas, 'total_geral': total})
    except Exception as e:
        logging.error(f"Erro no resumo de peças não produzidas: {str(e)}", exc_info=True)
        return jsonify({'erro': str(e), 'data': [], 'total_geral': 0}), 500


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
            'concretagem': concretagem.conc,
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

@concretagem.route('/api/<int:id>/processar-producao', methods=['POST'])
@login_required
def api_processar_producao(id):
    """Processa a produção das peças desta concretagem (consumo de estoque e marca data_producao)."""
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)
        resultado = concretagem.produzir()
        if resultado is None:
            return jsonify({
                'success': False,
                'message': 'Todas as peças desta concretagem já possuem produção registrada.',
            }), 409
        if not resultado:
            return jsonify({'success': False, 'message': 'Erro ao processar produção.'}), 500
        return jsonify({'success': True, 'message': 'Produção da concretagem processada com sucesso!'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao processar produção da concretagem: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao processar produção: {str(e)}'}), 500


@concretagem.route('/api/desfazer-todas-producoes', methods=['POST'])
@login_required
def api_desfazer_todas_producoes():
    """Admin: zera data_producao nas TanquesPecas ligadas às concretagens informadas (ex.: listagem filtrada)."""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Acesso negado.'}), 403
    try:
        data = request.get_json(silent=True) or {}
        remover_movimentacoes = bool(data.get('remover_movimentacoes'))
        raw_ids = data.get('concretagem_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return jsonify({
                'success': False,
                'message': 'Informe os IDs das concretagens (nenhuma linha visível ou lista vazia).',
            }), 400

        vistos = set()
        concretagem_ids = []
        for x in raw_ids:
            try:
                cid = int(x)
            except (TypeError, ValueError):
                continue
            if cid not in vistos:
                vistos.add(cid)
                concretagem_ids.append(cid)
        if not concretagem_ids:
            return jsonify({
                'success': False,
                'message': 'Nenhum ID de concretagem válido.',
            }), 400

        peca_ids_processadas = set()
        desfeitas = 0

        for cid in concretagem_ids:
            concretagem = ConcretoConcretagens.query.get(cid)
            if not concretagem:
                continue
            for peca_ref in concretagem.get_pecas():
                try:
                    nome = peca_ref.get('nome')
                    tanque_id = int(peca_ref['tanque_id'])
                except (KeyError, TypeError, ValueError):
                    continue
                if not nome:
                    continue
                peca_obj = TanquesPecas.query.filter_by(nome=nome, tanque_id=tanque_id).first()
                if not peca_obj or peca_obj.id in peca_ids_processadas:
                    continue
                peca_ids_processadas.add(peca_obj.id)
                if not (peca_obj.qualidade or '').strip():
                    continue
                tinha_producao = peca_obj_ja_produzida(peca_obj)
                nova = limpar_data_producao_em_qualidade_str(peca_obj.qualidade)
                if nova is None:
                    continue
                peca_obj.qualidade = nova
                if tinha_producao:
                    desfeitas += 1

        db.session.commit()
        movs_removidas = 0
        if remover_movimentacoes:
            movs_removidas = remover_movimentacoes_producao_peca_escopo_concretagens(concretagem_ids)
        msg_parte_mov = (
            f' Movimentações de produção de peças removidas (estoque revertido): {movs_removidas}.'
            if remover_movimentacoes
            else ' Movimentações de estoque não foram alteradas.'
        )
        return jsonify({
            'success': True,
            'message': (
                f'Escopo: {len(concretagem_ids)} concretagem(ns) enviada(s). '
                f'Peças (TanquesPecas) com data de produção limpa (tinham registro): {desfeitas}.'
                + msg_parte_mov
            ),
            'pecas_com_producao_desfeita': desfeitas,
            'concretagens_escopo': len(concretagem_ids),
            'movimentacoes_removidas': movs_removidas,
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao desfazer produções (escopo filtrado): {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao desfazer produções: {str(e)}'}), 500


@concretagem.route('/api/<int:id>/excluir', methods=['POST'])
@login_required
def api_excluir(id):
    """Exclui uma concretagem via AJAX"""
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)

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
            if data is not None and 'pecas' in data:
                def _norm_key(item):
                    if not isinstance(item, dict):
                        return None
                    nome = item.get('nome') or item.get('placa')
                    tanque_id_val = item.get('tanque_id') or item.get('tanque')
                    if not nome or tanque_id_val is None:
                        return None
                    try:
                        tid = int(tanque_id_val) if isinstance(tanque_id_val, str) else int(tanque_id_val)
                    except (ValueError, TypeError):
                        return None
                    return (tid, str(nome))

                # Snapshot do que estava antes (para detectar remoções)
                pecas_antes_raw = []
                if concretagem.pecas:
                    try:
                        pecas_antes_raw = json.loads(concretagem.pecas) if isinstance(concretagem.pecas, str) else concretagem.pecas
                    except Exception:
                        pecas_antes_raw = []
                if not isinstance(pecas_antes_raw, list):
                    pecas_antes_raw = []
                keys_antes = set(filter(None, (_norm_key(p) for p in pecas_antes_raw)))

                # Peças recebidas no POST (pode vir como JSON string ou lista; itens podem ser dict ou JSON string)
                pecas_recebidas_raw = data.get('pecas')
                json_pecas = json.loads(pecas_recebidas_raw) if isinstance(pecas_recebidas_raw, str) else pecas_recebidas_raw
                if json_pecas is None:
                    json_pecas = []
                if not isinstance(json_pecas, list):
                    return jsonify({'success': False, 'message': 'Dados de peças inválidos'}), 400

                pecas_dicts = []
                for p in json_pecas:
                    p_dict = json.loads(p) if isinstance(p, str) else p
                    if isinstance(p_dict, dict):
                        pecas_dicts.append(p_dict)

                keys_depois = set(filter(None, (_norm_key(p) for p in pecas_dicts)))
                removidas = keys_antes - keys_depois

                # Se removeu peça da concretagem, precisa apagar a data_concretagem dela
                for (tanque_id_int, nome) in removidas:
                    peca_removida = TanquesPecas.query.filter_by(nome=nome, tanque_id=tanque_id_int).first()
                    if peca_removida:
                        peca_removida.data_concretagem = None
                        peca_removida.save()

                # Persistir a lista atual e marcar data_concretagem nas peças presentes
                concretagem.pecas = data.get('pecas')
                for peca in pecas_dicts:
                    nome = peca.get('nome') or peca.get('placa')
                    tanque_id_val = peca.get('tanque_id') or peca.get('tanque')
                    if not nome or tanque_id_val is None:
                        continue
                    try:
                        tanque_id_int = int(tanque_id_val) if isinstance(tanque_id_val, str) else int(tanque_id_val)
                    except (ValueError, TypeError):
                        continue

                    peca_obj = TanquesPecas.query.filter_by(nome=nome, tanque_id=tanque_id_int).first()
                    if peca_obj:
                        peca_obj.data_concretagem = concretagem.data_concretagem
                        peca_obj.save()

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
                            # Suporta tanto formato antigo ("placa", "tanque") quanto novo ("nome", "tanque_id")
                            peca_nome = peca_item.get('nome') or peca_item.get('placa')
                            tanque_id_val = peca_item.get('tanque_id') or peca_item.get('tanque')
                            
                            peca_obj = {
                                'nome': peca_nome,  # Nome da peça
                                'tanque': tanque_id_val,  # ID do tanque (formato antigo)
                                'tanque_id': tanque_id_val,  # ID do tanque (formato novo)
                                'forma': peca_item.get('forma', 0)
                            }
                            
                            # Buscar dados completos do tanque primeiro
                            tanque_obj = None
                            if tanque_id_val:
                                tanque_id = tanque_id_val
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
                            # Suporta tanto formato antigo quanto novo
                            peca_nome_busca = peca_item.get('nome') or peca_item.get('placa')
                            tanque_id_busca = peca_item.get('tanque_id') or peca_item.get('tanque')
                            
                            if peca_nome_busca and tanque_id_busca:
                                peca_nome = peca_nome_busca  # Nome da peça
                                tanque_id = tanque_id_busca
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
                                            'perca': qualidade.get('perca', False),
                                            'numero_sequencial': peca.numero_sequencial,
                                            'tanque_id': peca.tanque_id,
                                            'tanque_nome': peca.tanque.nome if peca.tanque else None,
                                            'qualidade': qualidade
                                        }
                                        peca_obj['tem_usinagem'] = bool(peca.get_series_de_pecas())
                                        
                                        # Se não tinha tanque_obj, buscar usando o tanque_id da peça
                                        if not peca_obj.get('tanque_obj') and peca.tanque:
                                            peca_obj['tanque_obj'] = {
                                                'id': peca.tanque.id,
                                                'nome': peca.tanque.nome,
                                                'sistema': peca.tanque.sistema
                                            }
                                    else:
                                        peca_obj['tem_usinagem'] = False
                                        print(f"[API] Peça não encontrada: nome='{peca_nome}', tanque_id={tanque_id_int}")
                                except (ValueError, TypeError) as e:
                                    print(f"[API] Erro ao processar peça: {str(e)}")
                            
                            if 'tem_usinagem' not in peca_obj:
                                peca_obj['tem_usinagem'] = False
                            pecas_data.append(peca_obj)
                        
                        print(f"[API] Retornando {len(pecas_data)} peças com objetos completos para concretagem {id}")
                except Exception as e:
                    print(f"[API] Erro ao parsear peças: {str(e)}")
                    logging.error(f"Erro ao parsear peças da concretagem {id}: {str(e)}")
            
            tem_alongamentos = concretagem_tem_alongamentos(concretagem)
            return jsonify({'pecas': pecas_data, 'tem_alongamentos': tem_alongamentos})
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
        ).order_by(ConcretoUsinagens.data_usinagem.asc()).all()
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
        print(f'[_api_salvar_usinagens] Data: {data}')
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
            
            # Garantir que existe o array de séries (lista de strings: ['1', '2', '-C3', ...])
            if 'series' not in qualidade:
                qualidade['series'] = []
            
            # Normalizar séries recebidas: gerar lista de strings
            # Se for segunda concretagem: prefixo '-C' na frente da série; caso contrário, série normal
            series_list = []
            for s in series:
                if isinstance(s, dict):
                    serie_val = str(s.get('serie', s))
                    if s.get('segunda_concretagem') is True:
                        series_list.append(f'{serie_val}-C')
                    else:
                        series_list.append(serie_val)
                else:
                    # Formato antigo: string simples
                    series_list.append(str(s))
            
            # Atualizar qualidade com série como lista: [1, 2, '-C3', ...]
            qualidade['series'] = series_list
            qualidade_peca_remover_data_producao_de_dados_adicionais(qualidade)
            peca.qualidade = json.dumps(qualidade, ensure_ascii=False)
            peca.data_concretagem = concretagem.data_concretagem
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
