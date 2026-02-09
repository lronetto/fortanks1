import logging
from flask import Blueprint, render_template, redirect, request, url_for, flash, jsonify, send_file
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
import os
import io
import shutil
from controllers.relatorios.commun import _converter_excel_para_pdf_libreoffice, _criar_arquivo_temp_projeto, _limpar_arquivo_temp

# Tentar importar odfpy para suporte a ODS
try:
    from odf.opendocument import load
    from odf.table import Table, TableRow, TableCell
    from odf.text import P
    from odf.style import PageLayout
    from odf.namespaces import STYLENS
    ODFPY_AVAILABLE = True
except ImportError:
    ODFPY_AVAILABLE = False
    print('odfpy não está instalado. Para processar ODS diretamente, instale: pip install odfpy')
# Definir o blueprint
concretagem = Blueprint('concretagem', __name__, url_prefix='/concretagens')


@concretagem.route('/')
@login_required
def index():
    """Lista todas as concretagens cadastradas"""
    return render_template('concretagens/index.html')



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
        
        # Filtrar apenas peças não concretadas se solicitado
        if mostrar_nao_concretadas:
            pecas = pecas.filter(TanquesPecas.data_concretagem.is_(None))
        
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




# Novas rotas AJAX simplificadas

def _concretagem_tem_alongamentos(conc):
    """Retorna True se a concretagem tem alongamentos (cordoalhas) associados."""
    if not conc.cordoalhas or not conc.cordoalhas.strip():
        return False
    try:
        cord = json.loads(conc.cordoalhas) if isinstance(conc.cordoalhas, str) else conc.cordoalhas
        if isinstance(cord, list):
            return len(cord) > 0
        return bool(cord)
    except (TypeError, json.JSONDecodeError):
        return False


def _concretagem_tem_usinagens(conc):
    """Retorna True se pelo menos uma peça da concretagem tem séries (usinagens) referenciadas."""
    pecas = conc.get_pecas()
    if not pecas:
        return False
    for peca_item in pecas:
        nome = peca_item.get('nome') or peca_item.get('placa')
        tanque_id = peca_item.get('tanque_id') or peca_item.get('tanque')
        if not nome or tanque_id is None:
            continue
        try:
            tid = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
            peca = TanquesPecas.query.filter_by(nome=nome, tanque_id=tid).first()
            if peca and peca.get_series_de_pecas():
                return True
        except (ValueError, TypeError):
            continue
    return False


@concretagem.route('/api/listar')
@login_required
def api_listar():
    """Retorna lista de concretagens para DataTables"""
    try:
        concretagens = ConcretoConcretagens.query.order_by(ConcretoConcretagens.data_concretagem.desc()).all()
        
        data = []
        for conc in concretagens:
            data.append({
                'concretagem': conc.conc,
                'id': conc.id,
                'data_concretagem': conc.data_concretagem.isoformat() if conc.data_concretagem else None,
                'pista': conc.pista,
                'quantidade_pecas': len(conc.get_pecas()),
                'tem_alongamentos': _concretagem_tem_alongamentos(conc),
                'tem_usinagens': _concretagem_tem_usinagens(conc),
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
                json_pecas = json.loads(data.get('pecas')) if isinstance(data.get('pecas'), str) else data.get('pecas')
                for peca in json_pecas:
                    peca=json.loads(peca) if isinstance(peca, str) else peca
                    peca_obj = TanquesPecas.query.filter_by(nome=peca['nome'], tanque_id=peca['tanque_id']).first()
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
            
            # Salvar qualidade atualizada
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

def _aplicar_layout_pagina_horizontal_ods(doc):
    """
    Ajusta todos os page layouts do documento ODS para orientação paisagem (horizontal)
    e escala para caber em uma página.
    """
    if not ODFPY_AVAILABLE:
        return
    try:
        layouts = doc.getElementsByType(PageLayout)
        for layout in layouts:
            for child in (layout.childNodes or []):
                if getattr(child, 'qname', None) == (STYLENS, 'page-layout-properties'):
                    # odfpy setAttribute usa nome normalizado: sem hífen, minúsculo
                    child.setAttribute('printorientation', 'landscape')
                    child.setAttribute('scaletopages', '1')
                    break
    except Exception as e:
        logging.warning(f"Não foi possível aplicar layout horizontal ao ODS: {e}")


def _processar_ods_template_inspecao_pista(ods_path, concretagem_id, concretagem):
    """
    Processa o template INSPECAO_PISTA.ods substituindo placeholders pelos dados das peças.
    
    Args:
        ods_path: Caminho do arquivo ODS
        concretagem_id: ID da concretagem
        concretagem: Objeto concretagem
    """
    if not ODFPY_AVAILABLE:
        raise ImportError('odfpy não está disponível. Instale com: pip install odfpy')
    
    try:
        # Carregar o documento ODS
        doc = load(ods_path)
        
        # Obter todas as tabelas (planilhas)
        tables = doc.getElementsByType(Table)
        
        # Preparar dados das peças
        pecas_data = concretagem.get_pecas() if concretagem else []
        pecas_concretadas = []
        
        for peca_item in pecas_data:
            peca_nome = peca_item.get('nome') or peca_item.get('placa')
            tanque_id = peca_item.get('tanque_id') or peca_item.get('tanque')
            forma = peca_item.get('forma', 0)
            
            if peca_nome and tanque_id:
                try:
                    tanque_id_int = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
                    peca_obj = TanquesPecas.query.filter_by(
                        nome=peca_nome,
                        tanque_id=tanque_id_int
                    ).first()
                    
                    if peca_obj:
                        pecas_concretadas.append({
                            'nome': peca_nome,
                            'tipo': peca_obj.tipo,
                            'forma': forma,
                            'tanque_id': tanque_id_int,
                            'tanque_nome': peca_obj.tanque.nome if peca_obj.tanque else ''
                        })
                except (ValueError, TypeError) as e:
                    logging.warning(f"Erro ao processar peça {peca_nome}: {str(e)}")
                    continue
        
        # Processar todas as tabelas
        for table in tables:
            rows = table.getElementsByType(TableRow)
            for row_idx, row in enumerate(rows):
                cells = row.getElementsByType(TableCell)
                for cell_idx, cell in enumerate(cells):
                    # Obter o texto da célula
                    original_text = ''
                    paragraphs = cell.getElementsByType(P)
                    
                    if paragraphs:
                        for para in paragraphs:
                            para_text = ''
                            for node in para.childNodes:
                                if hasattr(node, 'data'):
                                    para_text += str(node.data)
                                elif hasattr(node, 'nodeValue'):
                                    para_text += str(node.nodeValue)
                            if para_text:
                                original_text += para_text
                    
                    if not original_text:
                        for node in cell.childNodes:
                            if hasattr(node, 'data'):
                                original_text += str(node.data)
                            elif hasattr(node, 'nodeValue'):
                                original_text += str(node.nodeValue)
                    
                    # Processar apenas células com texto no formato de placeholder (1 a 5 caracteres)
                    if original_text and len(original_text.strip()) > 0 and 1 < len(original_text) <= 5:
                        new_value = original_text
                        
                        # Substituir placeholders básicos
                        new_value = new_value.replace('{1}', str(concretagem_id))
                        new_value = new_value.replace('{4}', concretagem.data_concretagem.strftime('%d/%m/%Y') if concretagem.data_concretagem else '')
                        new_value = new_value.replace('{7}', concretagem.pista if concretagem.pista else '')
                        
                        # Processar formas (0 a 12)
                        formas = list(range(13))  # 0 a 12
                        for forma in formas:
                            count = 0
                            for peca in pecas_concretadas:
                                if peca.get('forma') == forma:
                                    new_value = new_value.replace(f'{{{7+forma}}}', str(forma))
                                    new_value = new_value.replace(f'{{{19+forma}}}', str(peca['nome']))
                                    new_value = new_value.replace(f'{{{31+forma}}}', str(peca['tipo']))
                                    
                                    tipo_painel = 'FECHO' if peca['tipo'] == 'PF' else ('NORMAL' if peca['tipo'] in ['PN', 'P'] else 'ESPECIAL')
                                    new_value = new_value.replace(f'{{{43+forma}}}', str(tipo_painel))
                                    count += 1
                            
                            if count == 0:
                                new_value = new_value.replace(f'{{{7+forma}}}', '')
                                new_value = new_value.replace(f'{{{19+forma}}}', '')
                                new_value = new_value.replace(f'{{{31+forma}}}', '')
                                new_value = new_value.replace(f'{{{43+forma}}}', '')
                        
                        # Atualizar o texto da célula
                        if new_value != original_text:
                            # Limpar todos os parágrafos existentes
                            paragraphs_to_remove = cell.getElementsByType(P)
                            for para in paragraphs_to_remove:
                                cell.removeChild(para)
                            
                            # Criar novo parágrafo com o texto atualizado
                            new_para = P()
                            new_para.addText(new_value)
                            cell.addElement(new_para)
        
        # Ajustar página para orientação horizontal e caber em uma página
        _aplicar_layout_pagina_horizontal_ods(doc)
        
        # Salvar documento modificado
        doc.save(ods_path)
        
    except Exception as e:
        logging.error(f"Erro ao processar template ODS: {str(e)}", exc_info=True)
        raise

@concretagem.route('/api/<int:id>/pecas/exportar-pdf', methods=['GET'])
@login_required
def api_exportar_pecas_pdf(id):
    """Exporta peças de uma concretagem para PDF usando o template INSPECAO_PISTA.ods"""
    excel_path = None
    pdf_temp_path = None
    
    try:
        concretagem = ConcretoConcretagens.query.get_or_404(id)
        
        # Caminho do template
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'controllers','templates_excel'
        )
        template_ods = os.path.join(templates_dir, 'INSPECAO_PISTA.ods')
        print(f'[_api_exportar_pecas_pdf] Template ODS: {template_ods}')
        if not os.path.exists(template_ods):
            return jsonify({'error': 'Template INSPECAO_PISTA.ods não encontrado'}), 404
        
        if not ODFPY_AVAILABLE:
            return jsonify({'error': 'odfpy não está instalado. Instale com: pip install odfpy'}), 500
        
        # Criar cópia temporária do template
        excel_path = _criar_arquivo_temp_projeto(suffix='.ods', prefix='inspecao_pista_')
        shutil.copy2(template_ods, excel_path)
        
        # Processar template com dados das peças
        _processar_ods_template_inspecao_pista(excel_path, id, concretagem)
        
        # Converter ODS para PDF usando LibreOffice
        generated_pdf_path = _converter_excel_para_pdf_libreoffice(excel_path)
        
        if not generated_pdf_path or not os.path.exists(generated_pdf_path):
            return jsonify({
                'error': 'Erro ao converter ODS para PDF. Verifique se o LibreOffice está instalado e configurado corretamente.'
            }), 500
        
        # Verificar se o PDF foi gerado corretamente
        pdf_size = os.path.getsize(generated_pdf_path)
        if pdf_size == 0:
            return jsonify({'error': 'PDF gerado está vazio'}), 500
        
        # Ler o PDF gerado para buffer de memória
        output = io.BytesIO()
        with open(generated_pdf_path, 'rb') as f:
            output.write(f.read())
        output.seek(0)
        
        # Nome do arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'inspecao_pista_{id}_{timestamp}.pdf'
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logging.error(f"Erro ao exportar PDF de peças: {str(e)}", exc_info=True)
        return jsonify({'error': f'Erro ao exportar PDF: {str(e)}'}), 500
    finally:
        # Limpar arquivos temporários
        if excel_path and os.path.exists(excel_path):
            _limpar_arquivo_temp(excel_path)
        if 'generated_pdf_path' in locals() and generated_pdf_path and os.path.exists(generated_pdf_path):
            _limpar_arquivo_temp(generated_pdf_path)
