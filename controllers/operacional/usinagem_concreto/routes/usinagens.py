"""
Rotas relacionadas a usinagens de concreto
"""
import logging
from flask import render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_login import login_required, current_user
from models.material import Materiais
from models.unidade import Unidades, UnidadesConversao, get_conversao_unidade
from utils.utils import parse_dados_json
from models.colaborador import Colaborador
from models.concreto import (
    ConcretoUsinagensRompimentos,
    ConcretoUsinagens,
    ConcretoUsinagensMateriais,
    limpar_data_producao_dados_adicionais_usinagem_str,
)
from models.produto_composto import ProdutoComposto
from models.database import db
from models.estoque import EstoqueMovimentacoes
from datetime import datetime
from decimal import Decimal
import json
import pandas as pd
import io
from .. import usinagem_concreto
from ..services.listagem_usinagens import obter_linhas_datatable_usinagens


# Rotas para API
@usinagem_concreto.route('/api/materiais-para-traco')
@login_required
def api_materiais_para_traco():
    """API para obter materiais que podem ser usados em traços de concreto"""
    try:
        # Busca todos os materiais ordenados por nome
        materiais = Materiais.query.order_by(Materiais.nome).all()
        
        # Transforma em JSON
        result = []
        for m in materiais:
            result.append({
                'id': m.id,
                'codigo': m.codigo,
                'nome': m.nome,
                'unidade_id': m.unidade_id
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@usinagem_concreto.route('/api/conversoes-unidade', methods=['GET'])
@login_required
def api_conversoes_unidade():
    """Retorna todas as conversões de unidade cadastradas"""
    try:
        conversoes = UnidadesConversao.query.all()
        resultado = []
        
        for conversao in conversoes:
            resultado.append({
                'id': conversao.id,
                'descricao': conversao.nome,
                'unidade_origem': conversao.unidade_entrada,
                'unidade_destino': conversao.unidade_saida,
                'fator': float(conversao.fator)
            })
        
        return jsonify(resultado)
    except Exception as e:
        print(f"Erro ao buscar conversões: {str(e)}")
        return jsonify([])


@usinagem_concreto.route('/api/materiais-traco/<int:produto_composto_id>')
@login_required
def api_materiais_traco(produto_composto_id):
    """API para obter materiais de um traço (produto_composto) com suas quantidades.
    Se fornecido usinagem_id, aplica a redosagem dos dados_adicionais."""
    try:
        produto_composto = ProdutoComposto.query.get_or_404(produto_composto_id)
        
        if not produto_composto.traco:
            return jsonify({'error': 'Produto composto não é um traço válido.'}), 400
        
        # Verificar se foi fornecido usinagem_id para aplicar redosagem
        usinagem_id = request.args.get('usinagem_id', type=int)
        redosagem_map = {}
        
        if usinagem_id:
            # Buscar usinagem e verificar se há redosagem nos dados_adicionais
            usinagem = ConcretoUsinagens.query.get(usinagem_id)
            if usinagem and usinagem.dados_adicionais:
                try:
                    dados_adicionais = usinagem.dados_adicionais
                    if isinstance(dados_adicionais, str):
                        dados_adicionais = json.loads(dados_adicionais)
                    
                    if dados_adicionais.get('redosagem') and dados_adicionais['redosagem'].get('materiais'):
                        # Criar mapa de material_id -> quantidade_redosada
                        for item in dados_adicionais['redosagem']['materiais']:
                            material_id = item.get('material_id')
                            quantidade_redosada = item.get('quantidade_redosada')
                            if material_id and quantidade_redosada is not None:
                                redosagem_map[material_id] = float(quantidade_redosada)
                        print(f"DEBUG api_materiais_traco - Redosagem encontrada para {len(redosagem_map)} materiais")
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    print(f"DEBUG api_materiais_traco - Erro ao processar redosagem: {str(e)}")
        
        # Obter volume da usinagem se fornecido
        volume_usinagem = None
        if usinagem_id:
            usinagem = ConcretoUsinagens.query.get(usinagem_id)
            if usinagem:
                volume_usinagem = float(usinagem.volume) if usinagem.volume else None
        
        materiais = []
        for componente in produto_composto.componentes:
            if componente.estoque and componente.estoque.tipo_item == 'material' and componente.estoque.material:
                material = componente.estoque.material
                unidade_nome = material.unidade_obj.nome if material.unidade_obj else 'N/A'
                conversao = get_conversao_unidade(material_id=material.id, unidade_saida='KG')
                
                # Calcular quantidade base (por m³) - sempre por m³
                quantidade_base = float(componente.quantidade) * conversao
                
                # Se houver redosagem para este material
                # quantidade_redosada já vem com o volume aplicado (total), não por m³
                quantidade_redosada_total = None
                if material.id in redosagem_map:
                    quantidade_redosada_total = redosagem_map[material.id]
                    print(f"DEBUG api_materiais_traco - Material {material.nome} (ID {material.id}): quantidade_redosada_total = {quantidade_redosada_total}")
                
                materiais.append({
                    'material_id': material.id,
                    'material_nome': material.nome,
                    'material_codigo': parse_dados_json(material.dados_adicionais).get("codigo_sox") or '',
                    'quantidade_base': quantidade_base,  # Quantidade por m³ (sempre)
                    'quantidade_redosada_total': quantidade_redosada_total,  # Quantidade total redosada (se houver)
                    'unidade_id': material.unidade_id,
                    'unidade_nome': unidade_nome,
                    'estoque_id': componente.estoque_id
                })
        
        return jsonify({
            'success': True,
            'materiais': materiais,
            'traco_nome': produto_composto.nome
        })
    except Exception as e:
        print(f"Erro ao buscar materiais do traço: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@usinagem_concreto.route('/api/listar-usinagens', methods=['GET'])
@login_required
def api_listar_usinagens_datatables():
    """
    Retorna usinagens no formato esperado pelo DataTables (ajax + client-side).
    Aceita filtros:
    - ?data_inicial=AAAA-MM-DD&data_final=AAAA-MM-DD
    - ?produzido=sim|nao
    """
    try:
        data_inicial_str = (request.args.get('data_inicial') or '').strip()
        data_final_str = (request.args.get('data_final') or '').strip()
        filtro_produzido = (request.args.get('produzido') or '').strip().lower()
        if filtro_produzido not in {'sim', 'nao'}:
            filtro_produzido = ''

        data = obter_linhas_datatable_usinagens(data_inicial_str, data_final_str, filtro_produzido)
        return jsonify({'data': data})
    except Exception as e:
        return jsonify({'erro': f'Erro ao listar usinagens: {str(e)}'}), 500


@usinagem_concreto.route('/api/<int:id>/processar-producao', methods=['POST'])
@login_required
def api_processar_producao_usinagem(id):
    """
    Processa a produção (consome estoque e marca `data_producao` em dados_adicionais).
    """
    try:
        usinagem = ConcretoUsinagens.query.get_or_404(id)

        # Se já tem data_producao (produzida), não reprocessa
        if usinagem.dados_adicionais:
            try:
                dados_obj = json.loads(usinagem.dados_adicionais) if isinstance(usinagem.dados_adicionais, str) else usinagem.dados_adicionais
            except Exception:
                dados_obj = None
            if isinstance(dados_obj, dict) and dados_obj.get('data_producao'):
                return jsonify({'success': False, 'message': 'Usinagem já produzida.'}), 400

        ok = usinagem.produzir(usuario_id=current_user.id if current_user and hasattr(current_user, 'id') else 1)
        if not ok:
            return jsonify({'success': False, 'message': 'Erro ao processar produção (verifique estoque e dados).'}), 400

        return jsonify({'success': True, 'message': 'Produção da usinagem processada com sucesso!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao processar produção: {str(e)}'}), 500


@usinagem_concreto.route('/api/desfazer-todas-producoes', methods=['POST'])
@login_required
def api_desfazer_todas_producoes_usinagens():
    """
    Admin: zera data_producao no JSON da coluna dados_adicionais das usinagens informadas
    (escopo = linhas visíveis na tabela, como em concretagens). Não reverte estoque.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Acesso negado.'}), 403
    try:
        payload = request.get_json(silent=True) or {}
        remover_movimentacoes = bool(payload.get('remover_movimentacoes'))
        raw_ids = payload.get('usinagem_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return jsonify({
                'success': False,
                'message': 'Informe os IDs das usinagens (nenhuma linha visível ou lista vazia).',
            }), 400

        vistos = set()
        usinagem_ids = []
        for x in raw_ids:
            try:
                uid = int(x)
            except (TypeError, ValueError):
                continue
            if uid not in vistos:
                vistos.add(uid)
                usinagem_ids.append(uid)
        if not usinagem_ids:
            return jsonify({'success': False, 'message': 'Nenhum ID de usinagem válido.'}), 400

        desfeitas = 0
        for uid in usinagem_ids:
            u = ConcretoUsinagens.query.get(uid)
            if not u:
                continue
            tinha = False
            if u.dados_adicionais:
                try:
                    d = json.loads(u.dados_adicionais) if isinstance(u.dados_adicionais, str) else u.dados_adicionais
                    if isinstance(d, dict) and d.get('data_producao'):
                        tinha = True
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            nova = limpar_data_producao_dados_adicionais_usinagem_str(u.dados_adicionais)
            if nova is None:
                continue
            u.dados_adicionais = nova
            if tinha:
                desfeitas += 1

        db.session.commit()

        movs_removidas = 0
        if remover_movimentacoes:
            movs = EstoqueMovimentacoes.query.filter(
                EstoqueMovimentacoes.origem_id.in_(usinagem_ids),
                EstoqueMovimentacoes.origem_tipo == 'usinagem_concreto',
            ).all()
            mov_ids = [m.id for m in movs]
            if mov_ids:
                ConcretoUsinagensMateriais.query.filter(
                    ConcretoUsinagensMateriais.movimentacao_estoque_id.in_(mov_ids)
                ).update({ConcretoUsinagensMateriais.movimentacao_estoque_id: None}, synchronize_session=False)
                db.session.commit()
            for mid in mov_ids:
                m = EstoqueMovimentacoes.query.get(mid)
                if m:
                    m.delete()
                    movs_removidas += 1

        msg_mov = (
            f' Movimentações destas usinagens removidas (estoque revertido): {movs_removidas}.'
            if remover_movimentacoes
            else ' Movimentações de estoque não foram alteradas.'
        )
        return jsonify({
            'success': True,
            'message': (
                f'Escopo: {len(usinagem_ids)} usinagem(ns) enviada(s). '
                f'Com data de produção limpa em dados_adicionais (tinham registro): {desfeitas}.'
                + msg_mov
            ),
            'usinagens_com_producao_desfeita': desfeitas,
            'usinagens_escopo': len(usinagem_ids),
            'movimentacoes_removidas': movs_removidas,
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao desfazer produções (usinagens): {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao desfazer produções: {str(e)}'}), 500


@usinagem_concreto.route('/api/<int:id>/resumo-materiais', methods=['GET'])
@login_required
def api_resumo_materiais_usinagem(id):
    """
    Retorna resumo de materiais consumidos da usinagem.
    Prioriza materiais executados; se não houver, usa cálculo do traço.
    """
    try:
        usinagem = ConcretoUsinagens.query.get_or_404(id)

        materiais = []

        # 1) Materiais executados (consumo efetivo lançado na usinagem)
        for item in usinagem.materiais or []:
            if item.quantidade_executada is None:
                continue
            materiais.append({
                'material': item.material.nome if item.material else f'Material #{item.material_id}',
                'quantidade': float(item.quantidade_executada),
                'unidade': item.unidade or (item.material.unidade_obj.nome if item.material and item.material.unidade_obj else ''),
                'origem': 'executado'
            })

        # 2) Fallback: materiais calculados do traço x volume
        if not materiais:
            for calc in usinagem.calcular_materiais():
                material_obj = calc.get('material')
                materiais.append({
                    'material': material_obj.nome if material_obj else '-',
                    'quantidade': float(calc.get('quantidade') or 0),
                    'unidade': calc.get('unidade') or '',
                    'origem': 'calculado'
                })

        return jsonify({
            'success': True,
            'usinagem': {
                'id': usinagem.id,
                'serie': usinagem.serie,
                'data_usinagem': usinagem.data_usinagem.strftime('%d/%m/%Y %H:%M') if usinagem.data_usinagem else '-',
                'traco_nome': usinagem.produto_composto.nome if usinagem.produto_composto else '-',
                'volume': float(usinagem.volume) if usinagem.volume is not None else 0
            },
            'materiais': materiais,
            'total_materiais': len(materiais)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao buscar resumo de materiais: {str(e)}'}), 500


@usinagem_concreto.route('/api/processar-producao-pendentes', methods=['POST'])
@login_required
def api_processar_producao_pendentes_usinagem():
    """
    Processa produção em lote para usinagens pendentes.
    Pode receber filtros opcionais via JSON:
    - data_inicial (AAAA-MM-DD)
    - data_final (AAAA-MM-DD)
    """
    try:
        payload = request.get_json(silent=True) or {}
        data_inicial_str = (payload.get('data_inicial') or '').strip()
        data_final_str = (payload.get('data_final') or '').strip()

        query = ConcretoUsinagens.query

        if data_inicial_str:
            try:
                data_inicial = datetime.strptime(data_inicial_str, '%Y-%m-%d')
                query = query.filter(ConcretoUsinagens.data_usinagem >= data_inicial)
            except ValueError:
                return jsonify({'success': False, 'message': 'Data inicial inválida. Use AAAA-MM-DD.'}), 400

        if data_final_str:
            try:
                data_final_dt = datetime.strptime(data_final_str, '%Y-%m-%d')
                data_final_query = datetime.combine(data_final_dt.date(), datetime.max.time())
                query = query.filter(ConcretoUsinagens.data_usinagem <= data_final_query)
            except ValueError:
                return jsonify({'success': False, 'message': 'Data final inválida. Use AAAA-MM-DD.'}), 400

        usinagens = query.order_by(ConcretoUsinagens.data_usinagem.desc()).all()

        total_analisadas = 0
        total_pendentes = 0
        total_processadas = 0
        total_falhas = 0
        falhas = []

        for usinagem in usinagens:
            total_analisadas += 1

            dados = usinagem.dados_adicionais
            try:
                dados_obj = json.loads(dados) if isinstance(dados, str) else (dados or {})
            except Exception:
                dados_obj = {}

            ja_produzida = isinstance(dados_obj, dict) and bool(dados_obj.get('data_producao'))
            if ja_produzida:
                continue

            total_pendentes += 1

            try:
                ok = usinagem.produzir(usuario_id=current_user.id if current_user and hasattr(current_user, 'id') else 1)
                if ok:
                    total_processadas += 1
                else:
                    total_falhas += 1
                    falhas.append(f"Série {usinagem.serie}: erro ao processar produção.")
            except Exception as exc:
                db.session.rollback()
                total_falhas += 1
                falhas.append(f"Série {usinagem.serie}: {str(exc)}")

        return jsonify({
            'success': True,
            'message': (
                f'Produção em lote concluída. '
                f'Pendentes: {total_pendentes}, Processadas: {total_processadas}, Falhas: {total_falhas}.'
            ),
            'resumo': {
                'analisadas': total_analisadas,
                'pendentes': total_pendentes,
                'processadas': total_processadas,
                'falhas': total_falhas
            },
            'falhas': falhas[:20]
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao processar pendentes: {str(e)}'}), 500


# Rotas para Usinagens
@usinagem_concreto.route('/usinagens')
@login_required
def listar_usinagens():
    """Lista todas as usinagens de concreto cadastradas com filtros opcionais de data."""
    
    # Obter parâmetros de filtro da URL
    data_inicial_str = request.args.get('data_inicial')
    data_final_str = request.args.get('data_final')
    
    data_inicial = None
    data_final = None
    filtro_produzido = (request.args.get('produzido') or '').strip().lower()
    if filtro_produzido not in {'sim', 'nao'}:
        filtro_produzido = ''

    if data_inicial_str:
        try:
            data_inicial = datetime.strptime(data_inicial_str, '%Y-%m-%d')
        except ValueError:
            flash('Formato de Data Inicial inválido. Use AAAA-MM-DD.', 'warning')
            data_inicial = None

    if data_final_str:
        try:
            data_final_dt_obj = datetime.strptime(data_final_str, '%Y-%m-%d')
            data_final = data_final_dt_obj
        except ValueError:
            flash('Formato de Data Final inválido. Use AAAA-MM-DD.', 'warning')
            data_final = None

    # Buscar produtos compostos que são traços (traco=True)
    tracos = ProdutoComposto.query.filter_by(traco=True, status='Ativo').order_by(ProdutoComposto.nome).all()
    tracos_data = [{'id': t.id, 'nome': t.nome} for t in tracos]

    return render_template(
        'operacional/usinagem_concreto/usinagens/index.html', 
        now=datetime.now().strftime('%Y-%m-%dT%H:%M'),
        tracos=tracos, 
        tracos_json=tracos_data,
        filtro_data_inicial=data_inicial_str if data_inicial else '',
        filtro_data_final=data_final_str if data_final else '',
        filtro_produzido=filtro_produzido
    )


@usinagem_concreto.route('/usinagens/nova', methods=['GET', 'POST'])
@login_required
def nova_usinagem():
    """Nova usinagem de concreto - suporta AJAX e formulário tradicional"""
    # Buscar produtos compostos que são traços
    tracos = ProdutoComposto.query.filter_by(traco=True, status='Ativo').order_by(ProdutoComposto.nome).all()
    
    if request.method == 'POST':
        try:
            # Verificar se é requisição AJAX
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            
            # Extrair dados do formulário
            serie = request.form.get('serie', '').strip()
            data_usinagem_str = request.form.get('data_usinagem', '').strip()
            produto_composto_id_str = request.form.get('produto_composto_id', '').strip()
            flow = request.form.get('flow', '').strip()
            volume_str = request.form.get('volume', '').strip()
            nf = request.form.get('nf', '').strip()
            dados_adicionais_str = request.form.get('dados_adicionais', '').strip()

            # Validar campos obrigatórios
            campos_faltando = []
            if not serie:
                campos_faltando.append('Série')
            if not data_usinagem_str:
                campos_faltando.append('Data/Hora')
            if not produto_composto_id_str:
                campos_faltando.append('Traço')
            if not volume_str:
                campos_faltando.append('Volume')
            
            if campos_faltando:
                error_msg = f'Campos obrigatórios não preenchidos: {", ".join(campos_faltando)}'
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': error_msg
                    }), 400
                flash(error_msg, 'error')
                return render_template('operacional/usinagem_concreto/usinagens/nova.html', 
                                     tracos=tracos,
                                     now=datetime.now().strftime('%Y-%m-%dT%H:%M'))

            # Verificar se série já existe
            if ConcretoUsinagens.query.filter_by(serie=serie).first():
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Já existe uma usinagem com esta série.'
                    }), 400
                flash('Já existe uma usinagem com esta série.', 'error')
                return render_template('operacional/usinagem_concreto/usinagens/nova.html', tracos=tracos)

            # Converter e validar dados
            try:
                data_usinagem = datetime.fromisoformat(data_usinagem_str)
            except ValueError:
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Formato de data/hora inválido. Use o formato: AAAA-MM-DDTHH:MM'
                    }), 400
                flash('Formato de data/hora inválido.', 'error')
                return render_template('operacional/usinagem_concreto/usinagens/nova.html', 
                                     tracos=tracos,
                                     now=datetime.now().strftime('%Y-%m-%dT%H:%M'))
            
            try:
                volume = Decimal(volume_str.replace(',', '.'))
                if volume <= 0:
                    raise ValueError("Volume deve ser maior que zero")
            except (ValueError, TypeError):
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Volume inválido. Deve ser um número maior que zero.'
                    }), 400
                flash('Volume inválido.', 'error')
                return render_template('operacional/usinagem_concreto/usinagens/nova.html', 
                                     tracos=tracos,
                                     now=datetime.now().strftime('%Y-%m-%dT%H:%M'))
            
            try:
                produto_composto_id = int(produto_composto_id_str)
            except (ValueError, TypeError):
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Traço inválido.'
                    }), 400
                flash('Traço inválido.', 'error')
                return render_template('operacional/usinagem_concreto/usinagens/nova.html', 
                                     tracos=tracos,
                                     now=datetime.now().strftime('%Y-%m-%dT%H:%M'))
            
            # Validar produto composto
            produto_composto = ProdutoComposto.query.get_or_404(produto_composto_id)
            if not produto_composto or not produto_composto.traco:
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Produto composto selecionado não é um traço válido.'
                    }), 400
                flash('Produto composto selecionado não é um traço válido.', 'error')
                return render_template('operacional/usinagem_concreto/usinagens/nova.html', tracos=tracos)

            # Processar dados_adicionais (JSON)
            dados_adicionais = None
            print(f"DEBUG nova_usinagem - dados_adicionais_str recebido: {dados_adicionais_str}")
            if dados_adicionais_str:
                try:
                    print(f"DEBUG nova_usinagem - dados_adicionais_str: {dados_adicionais_str}")
                    dados_adicionais = json.loads(dados_adicionais_str)
                    print(f"DEBUG nova_usinagem - dados_adicionais parseado com sucesso: {dados_adicionais}")
                except json.JSONDecodeError as e:
                    print(f"DEBUG nova_usinagem - Erro ao parsear JSON: {str(e)}")
                    if is_ajax:
                        return jsonify({
                            'success': False,
                            'error': 'Dados adicionais inválidos (deve ser JSON válido).'
                        }), 400
                    flash('Dados adicionais inválidos (deve ser JSON válido).', 'warning')
            else:
                print("DEBUG nova_usinagem - dados_adicionais_str está vazio")

            # Criar nova usinagem
            print(f"DEBUG nova_usinagem - Criando usinagem com dados_adicionais: {dados_adicionais}")
            usinagem = ConcretoUsinagens(
                serie=serie,
                data_usinagem=data_usinagem,
                produtoCompostoId=produto_composto_id,
                flow=flow,
                volume=volume,
                nota=nf,
                dados_adicionais=dados_adicionais
            )
            db.session.add(usinagem)
            db.session.flush()  # Flush para obter o ID antes do commit
            print(f"DEBUG nova_usinagem - Usinagem criada com ID: {usinagem.id}, dados_adicionais: {usinagem.dados_adicionais}")
            db.session.commit()
            print(f"DEBUG nova_usinagem - Commit realizado. dados_adicionais após commit: {usinagem.dados_adicionais}")
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Usinagem cadastrada com sucesso!',
                    'usinagem_id': usinagem.id
                })
            
            flash('Usinagem cadastrada com sucesso!', 'success')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro geral ao cadastrar usinagem: {e}")
            import traceback
            traceback.print_exc()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': f'Erro ao cadastrar usinagem: {str(e)}'
                }), 500
            
            flash(f'Erro ao cadastrar usinagem: {str(e)}', 'danger')
            return render_template('operacional/usinagem_concreto/usinagens/nova.html', 
                                   tracos=tracos, 
                                 now=datetime.now().strftime('%Y-%m-%dT%H:%M'))
    
    return render_template('operacional/usinagem_concreto/usinagens/nova.html', 
                           tracos=tracos, 
                         now=datetime.now().strftime('%Y-%m-%dT%H:%M'))


@usinagem_concreto.route('/usinagens/<int:id>/visualizar')
@login_required
def visualizar_usinagem(id):
    """Visualiza detalhes de uma usinagem de concreto"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
    materiais_calculados = usinagem.calcular_materiais()
    
    # Se for uma requisição AJAX, retorna apenas o conteúdo do modal
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        idade = (datetime.now() - usinagem.data_usinagem)
        usinagem.idade = idade
        usinagem.idade_hours = idade.total_seconds() / 3600
        usinagem.idade_str = f"{usinagem.idade_hours} horas" if usinagem.idade.days == 0 else f"{usinagem.idade.days} dias"

        usinagem.rompimentos = []
        # Buscar rompimentos pela série (conforme mudança feita pelo usuário)
        rompimentos = ConcretoUsinagensRompimentos.query.filter_by(numero_serie=usinagem.serie).all()
        for rompimento in rompimentos:
            if rompimento.data_rompimento and usinagem.data_usinagem:
                rompimento.idade = rompimento.data_rompimento - usinagem.data_usinagem
                rompimento.idade_hours = rompimento.idade.total_seconds() / 3600
                rompimento.idade_str = f"{rompimento.idade_hours} horas" if rompimento.idade.days == 0 else f"{rompimento.idade.days} dias"
            usinagem.rompimentos.append(rompimento)
        return render_template('operacional/usinagem_concreto/usinagens/partials/visualizar_usinagem_content.html',
                             usinagem=usinagem,
                             materiais_calculados=materiais_calculados)
    
    # Se não for AJAX, retorna a página completa
    return render_template('operacional/usinagem_concreto/usinagens/visualizar.html',
                          usinagem=usinagem,
                          materiais_calculados=materiais_calculados)


@usinagem_concreto.route('/usinagens/<int:id>/rompimentos')
@login_required
def visualizar_rompimentos_usinagem(id):
    """API para visualizar rompimentos de uma usinagem - retorna JSON"""
    try:
        usinagem = ConcretoUsinagens.query.get_or_404(id)
        
        # Buscar rompimentos pela série
        rompimentos = ConcretoUsinagensRompimentos.query.filter_by(numero_serie=usinagem.serie).order_by(
            ConcretoUsinagensRompimentos.data_rompimento.desc()
        ).all()
        
        rompimentos_data = []
        for rompimento in rompimentos:
            # Calcular idade do rompimento
            idade_str = '-'
            idade_dias = None
            if rompimento.data_rompimento and usinagem.data_usinagem:
                idade = rompimento.data_rompimento - usinagem.data_usinagem
                idade_hours = idade.total_seconds() / 3600
                idade_dias = idade.days
                idade_str = f"{idade_hours:.1f} horas" if idade.days == 0 else f"{idade.days} dias"
            
            rompimentos_data.append({
                'id': rompimento.id,
                'data_rompimento': rompimento.data_rompimento.strftime('%d/%m/%Y %H:%M') if rompimento.data_rompimento else '-',
                'data_moldagem': rompimento.data_moldagem.strftime('%d/%m/%Y %H:%M') if rompimento.data_moldagem else '-',
                'numero_cp': str(rompimento.numero_serie) if rompimento.numero_serie else '-',
                'resultado': float(rompimento.resultado) if rompimento.resultado else None,
                'idade_str': idade_str,
                'idade_dias': idade_dias,
                'tipo_rompimento': rompimento.tipo_rompimento or '-',
                'observacoes': rompimento.observacoes or '-'
            })
        
        return jsonify({
            'success': True,
            'usinagem': {
                'id': usinagem.id,
                'serie': usinagem.serie,
                'data_usinagem': usinagem.data_usinagem.strftime('%d/%m/%Y %H:%M') if usinagem.data_usinagem else '-',
                'traco_nome': usinagem.produto_composto.nome if usinagem.produto_composto else '-',
                'volume': float(usinagem.volume) if usinagem.volume else 0
            },
            'rompimentos': rompimentos_data,
            'total_rompimentos': len(rompimentos_data)
        })
    except Exception as e:
        print(f"Erro ao buscar rompimentos da usinagem: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@usinagem_concreto.route('/usinagens/<int:id>/editar', methods=['POST'])
@login_required
def editar_usinagem(id):
    """Edita uma usinagem de concreto - suporta AJAX e formulário tradicional"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
    
    try:
        # Verificar se é requisição AJAX
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Extrair dados do formulário
        serie = request.form.get('serie', '').strip()
        data_usinagem_str = request.form.get('data_usinagem', '').strip()
        produto_composto_id_str = request.form.get('produto_composto_id', '').strip()
        flow = request.form.get('flow', '').strip()
        volume_str = request.form.get('volume', '').strip()
        nf = request.form.get('nf', '').strip()
        dados_adicionais_str = request.form.get('dados_adicionais', '').strip()

        # Validar campos obrigatórios
        campos_faltando = []
        if not serie:
            campos_faltando.append('Série')
        if not data_usinagem_str:
            campos_faltando.append('Data/Hora')
        if not produto_composto_id_str:
            campos_faltando.append('Traço')
        if not volume_str:
            campos_faltando.append('Volume')
        
        if campos_faltando:
            error_msg = f'Campos obrigatórios não preenchidos: {", ".join(campos_faltando)}'
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
            flash(error_msg, 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))

        # Verificar se série já existe (exceto para a própria usinagem)
        # Só verifica se a série foi alterada
        if serie != usinagem.serie:
            # Verificar se existe outra usinagem com a mesma série (excluindo a atual que está sendo editada)
            usinagem_existente = ConcretoUsinagens.query.filter(
                ConcretoUsinagens.serie == serie,
                ConcretoUsinagens.id != usinagem.id  # Excluir a própria usinagem que está sendo editada
            ).first()
            
            if usinagem_existente:
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Já existe uma usinagem com esta série.'
                    }), 400
                flash('Já existe uma usinagem com esta série.', 'error')
                return redirect(url_for('usinagem_concreto.listar_usinagens'))

        # Converter e validar dados
        try:
            data_usinagem = datetime.fromisoformat(data_usinagem_str)
        except ValueError:
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': 'Formato de data/hora inválido. Use o formato: AAAA-MM-DDTHH:MM'
                }), 400
            flash('Formato de data/hora inválido.', 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))
        
        try:
            volume = Decimal(volume_str.replace(',', '.'))
            if volume <= 0:
                raise ValueError("Volume deve ser maior que zero")
        except (ValueError, TypeError):
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': 'Volume inválido. Deve ser um número maior que zero.'
                }), 400
            flash('Volume inválido.', 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))
        
        try:
            produto_composto_id = int(produto_composto_id_str)
        except (ValueError, TypeError):
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': 'Traço inválido.'
                }), 400
            flash('Traço inválido.', 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))
        
        # Validar produto composto
        produto_composto = ProdutoComposto.query.get_or_404(produto_composto_id)
        if not produto_composto or not produto_composto.traco:
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': 'Produto composto selecionado não é um traço válido.'
                }), 400
            flash('Produto composto selecionado não é um traço válido.', 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))

        # Processar dados_adicionais (JSON)
        dados_adicionais = None
        print(f"DEBUG editar_usinagem - dados_adicionais_str recebido: '{dados_adicionais_str}'")
        print(f"DEBUG editar_usinagem - Tipo: {type(dados_adicionais_str)}")
        print(f"DEBUG editar_usinagem - Tamanho da string: {len(dados_adicionais_str) if dados_adicionais_str else 0}")
        
        # Sempre processar se foi enviado
        if dados_adicionais_str is not None:
            dados_adicionais_str = dados_adicionais_str.strip()
            
            # Remover aspas duplas extras se houver (caso venha como '"{"')
            if dados_adicionais_str.startswith('"') and dados_adicionais_str.endswith('"'):
                try:
                    # Tentar fazer unescape da string JSON
                    dados_adicionais_str = json.loads(dados_adicionais_str)
                    print(f"DEBUG editar_usinagem - Removidas aspas extras, nova string: '{dados_adicionais_str}'")
                except:
                    # Se não conseguir, remover aspas manualmente
                    dados_adicionais_str = dados_adicionais_str[1:-1]
                    print(f"DEBUG editar_usinagem - Removidas aspas manualmente, nova string: '{dados_adicionais_str}'")
            
            # Se for string vazia ou None, manter dados existentes
            if not dados_adicionais_str or dados_adicionais_str == '{}' or dados_adicionais_str == '{':
                print("DEBUG editar_usinagem - String vazia, objeto vazio ou incompleto recebido, mantendo dados existentes")
                if usinagem.dados_adicionais:
                    dados_adicionais = usinagem.dados_adicionais
                    print(f"DEBUG editar_usinagem - Mantendo dados_adicionais existentes: {dados_adicionais}")
                else:
                    dados_adicionais = None
            else:
                # Verificar se a string parece estar incompleta (começa com "{" mas não termina)
                if dados_adicionais_str.startswith('{') and not dados_adicionais_str.endswith('}'):
                    print(f"DEBUG editar_usinagem - ATENÇÃO: JSON parece estar incompleto: '{dados_adicionais_str}'")
                    # Tentar manter dados existentes se houver
                    if usinagem.dados_adicionais:
                        dados_adicionais = usinagem.dados_adicionais
                        print(f"DEBUG editar_usinagem - Mantendo dados_adicionais existentes devido a JSON incompleto")
                    else:
                        dados_adicionais = None
                else:
                    try:
                        dados_adicionais = json.loads(dados_adicionais_str)
                        print(f"DEBUG editar_usinagem - dados_adicionais parseado: {dados_adicionais}")
                        print(f"DEBUG editar_usinagem - Tipo do objeto: {type(dados_adicionais)}")
                        
                        # Verificar se o resultado é uma string (não deveria ser, mas pode acontecer com '"{"')
                        if isinstance(dados_adicionais, str):
                            print(f"DEBUG editar_usinagem - ATENÇÃO: Parse retornou string em vez de objeto: '{dados_adicionais}'")
                            # Se for uma string que parece JSON incompleto, manter dados existentes
                            if dados_adicionais == '{' or (dados_adicionais.startswith('{') and not dados_adicionais.endswith('}')):
                                print("DEBUG editar_usinagem - String parece JSON incompleto, mantendo dados existentes")
                                if usinagem.dados_adicionais:
                                    dados_adicionais = usinagem.dados_adicionais
                                    print(f"DEBUG editar_usinagem - Mantendo dados_adicionais existentes")
                                else:
                                    dados_adicionais = None
                            else:
                                # Tentar parsear novamente a string
                                try:
                                    dados_adicionais = json.loads(dados_adicionais)
                                    print(f"DEBUG editar_usinagem - Re-parse bem-sucedido: {dados_adicionais}")
                                except:
                                    # Se falhar, manter dados existentes
                                    if usinagem.dados_adicionais:
                                        dados_adicionais = usinagem.dados_adicionais
                                        print(f"DEBUG editar_usinagem - Mantendo dados_adicionais existentes devido a re-parse falhou")
                                    else:
                                        dados_adicionais = None
                        
                        # Se for objeto vazio {}, manter dados existentes
                        if isinstance(dados_adicionais, dict) and dados_adicionais == {}:
                            print("DEBUG editar_usinagem - Objeto vazio {} recebido, mantendo dados existentes")
                            if usinagem.dados_adicionais:
                                dados_adicionais = usinagem.dados_adicionais
                                print(f"DEBUG editar_usinagem - Mantendo dados_adicionais existentes")
                            else:
                                dados_adicionais = None
                        # Se tiver conteúdo e for um dict válido, usar os novos dados
                        elif isinstance(dados_adicionais, dict):
                            print(f"DEBUG editar_usinagem - Usando novos dados_adicionais: {dados_adicionais}")
                        else:
                            # Se não for dict, manter dados existentes
                            print(f"DEBUG editar_usinagem - dados_adicionais não é um dict válido (tipo: {type(dados_adicionais)}), mantendo existentes")
                            if usinagem.dados_adicionais:
                                dados_adicionais = usinagem.dados_adicionais
                            else:
                                dados_adicionais = None
                            
                    except json.JSONDecodeError as e:
                        print(f"DEBUG editar_usinagem - Erro ao parsear JSON: {str(e)}")
                        print(f"DEBUG editar_usinagem - String recebida (primeiros 200 chars): {dados_adicionais_str[:200]}")
                        # Se o JSON for inválido, manter os dados existentes
                        if usinagem.dados_adicionais:
                            dados_adicionais = usinagem.dados_adicionais
                            print(f"DEBUG editar_usinagem - Mantendo dados_adicionais existentes devido a JSON inválido")
                        else:
                            dados_adicionais = None
        else:
            # Se não foi enviado, manter os dados existentes
            print("DEBUG editar_usinagem - dados_adicionais_str não foi enviado, mantendo dados existentes")
            if usinagem.dados_adicionais:
                dados_adicionais = usinagem.dados_adicionais
                print(f"DEBUG editar_usinagem - Mantendo dados_adicionais existentes: {dados_adicionais}")
            else:
                dados_adicionais = None
                print("DEBUG editar_usinagem - Não há dados_adicionais existentes, definindo como None")

        # Atualizar usinagem
        print(f"DEBUG editar_usinagem - Atualizando usinagem ID {id} com dados_adicionais: {dados_adicionais}")
        usinagem.serie = serie
        usinagem.data_usinagem = data_usinagem
        usinagem.produtoCompostoId = produto_composto_id
        usinagem.flow = flow if flow else None
        usinagem.volume = volume
        usinagem.nota = nf if nf else None
        usinagem.dados_adicionais = dados_adicionais
        
        db.session.flush()
        print(f"DEBUG editar_usinagem - Após flush, dados_adicionais: {usinagem.dados_adicionais}")
        db.session.commit()
        print(f"DEBUG editar_usinagem - Commit realizado. dados_adicionais após commit: {usinagem.dados_adicionais}")
        
        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Usinagem atualizada com sucesso!',
                'usinagem_id': usinagem.id
            })
        
        flash('Usinagem atualizada com sucesso!', 'success')
        return redirect(url_for('usinagem_concreto.listar_usinagens'))
        
    except Exception as e:
        db.session.rollback()
        print(f"Erro geral ao atualizar usinagem: {e}")
        import traceback
        traceback.print_exc()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': f'Erro ao atualizar usinagem: {str(e)}'
            }), 500
        
        flash(f'Erro ao atualizar usinagem: {str(e)}', 'danger')
        return redirect(url_for('usinagem_concreto.listar_usinagens'))


@usinagem_concreto.route('/usinagens/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_usinagem(id):
    """Exclui uma usinagem de concreto"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
    
    try:
        usinagem.delete()
        flash('Usinagem de concreto excluída com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir usinagem de concreto: {str(e)}', 'danger')
    
    return redirect(url_for('usinagem_concreto.listar_usinagens'))


@usinagem_concreto.route('/usinagens/<int:id>/rompimentos')
@login_required
def listar_rompimentos_usinagem(id):
    """Lista todos os rompimentos de corpo de prova de uma usinagem específica"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)

    return render_template('operacional/usinagem_concreto/rompimentos/por_usinagem.html',
                          usinagem=usinagem)


@usinagem_concreto.route('/usinagens/<int:id>/data-usinagem')
@login_required
def get_data_usinagem(id):
    """Retorna a data de usinagem de uma usinagem específica"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
    return jsonify({
        'data_usinagem': usinagem.data_usinagem.isoformat()
    })


@usinagem_concreto.route('/usinagens/numeros-betoneira')
@login_required
def get_numeros_betoneira():
    """Retorna todos os números de betoneira únicos já cadastrados"""
    try:
        # Busca todos os números de betoneira únicos, ordenados
        numeros = db.session.query(ConcretoUsinagens.nbt).distinct().filter(ConcretoUsinagens.nbt.isnot(None)).order_by(ConcretoUsinagens.nbt).all()
        
        # Transforma em lista simples
        resultado = [numero[0] for numero in numeros if numero[0]]
        
        return jsonify(resultado)
    except Exception as e:
        print(f"Erro ao buscar números de betoneira: {str(e)}")
        return jsonify([])


@usinagem_concreto.route('/usinagens/ultima-nota')
@login_required
def get_ultima_nota():
    """Retorna a última nota de usinagem"""
    try:
        # Busca a última nota de usinagem
        nota = db.session.query(ConcretoUsinagens.nota).order_by(ConcretoUsinagens.nota.desc()).first()
        
        # Transforma em lista simples
        resultado = nota[0] if nota else None
        
        return jsonify(resultado)
    except Exception as e:
        print(f"Erro ao buscar última nota: {str(e)}")
        return jsonify(None)
@usinagem_concreto.route('/usinagens/download-excel-modelo-usinagem')
@login_required
def download_excel_modelo_usinagem():
    """Retorna o modelo de excel para importação de usinagens"""
    return send_file('templates/usinagem_concreto/usinagens/modelos/modelo_importacao_usinagem.xlsx', as_attachment=True)


@usinagem_concreto.route('/usinagens/importar-excel', methods=['POST'])
@login_required
def importar_usinagens_excel():
    """Importa usinagens de concreto a partir de um arquivo Excel"""
    if 'arquivo_excel' not in request.files:
        return jsonify({'success': False, 'errors': ['Nenhum arquivo enviado.']}), 400
    
    arquivo = request.files['arquivo_excel']
    produto_composto_id_str = request.form.get('produto_composto_id')  # Usando produto_composto_id em vez de traco_id
    responsavel_id_str = request.form.get('responsavel_id')

    if not arquivo or arquivo.filename == '':
        return jsonify({'success': False, 'errors': ['Nome de arquivo inválido.']}), 400
    
    if not produto_composto_id_str:
        return jsonify({'success': False, 'errors': ['Traço (Produto Composto) é obrigatório.']}), 400

    try:
        produto_composto_id = int(produto_composto_id_str)
    except ValueError:
        return jsonify({'success': False, 'errors': ['ID de Traço inválido.']}), 400

    # Buscar produto composto (traço)
    produto_composto = ProdutoComposto.query.get(produto_composto_id)
    if not produto_composto:
        return jsonify({'success': False, 'errors': [f'Traço com ID {produto_composto_id} não encontrado.']}), 404
    
    if not produto_composto.traco:
        return jsonify({'success': False, 'errors': [f'Produto composto com ID {produto_composto_id} não é um traço.']}), 400

    # Buscar responsável se informado
    responsavel_id = None
    if responsavel_id_str:
        try:
            responsavel_id = int(responsavel_id_str)
            responsavel = Colaborador.query.get(responsavel_id)
            if not responsavel:
                return jsonify({'success': False, 'errors': [f'Responsável com ID {responsavel_id} não encontrado.']}), 404
        except ValueError:
            pass

    map_coluna_material_info = {}
    try:
        # Ler a aba de referência primeiro para saber quais colunas de material esperar
        df_referencia_materiais = pd.read_excel(arquivo, sheet_name='_Referencia_Materiais')
        for _, row_ref in df_referencia_materiais.iterrows():
            map_coluna_material_info[row_ref['Nome Coluna Excel']] = {
                'material_id': row_ref['ID Material'],
                'unidade_id': row_ref['ID Unidade'],
                'item_produto_composto_id': row_ref.get('ID ItemProdutoComposto', row_ref.get('ID ItemTracoConcreto'))  # Compatibilidade
            }
        
        df = pd.read_excel(arquivo, sheet_name='Modelo_Importacao_Usinagens')

    except Exception as e:
        # Captura erros como aba não encontrada ou problema de parsing geral do Excel
        try:
            excel_file = pd.ExcelFile(arquivo)
            if '_Referencia_Materiais' not in excel_file.sheet_names:
                return jsonify({'success': False, 'errors': ['Aba de referência "_Referencia_Materiais" não encontrada no arquivo. Por favor, use o modelo gerado pelo sistema.']}), 400
            if 'Modelo_Importacao_Usinagens' not in excel_file.sheet_names:
                return jsonify({'success': False, 'errors': ['Aba principal "Modelo_Importacao_Usinagens" não encontrada no arquivo.']}), 400
        except:
            pass
        return jsonify({'success': False, 'errors': [f'Erro ao ler o arquivo Excel: {str(e)}.']}), 400

    feedback_erros = []
    usinagens_importadas_count = 0
    
    colunas_fixas_rename_map = {
        'Data Usinagem (AAAA-MM-DD HH:MM)': 'data_usinagem_raw',
        'Volume Produzido (m³)': 'volume_produzido_raw',
        'Umidade (%)': 'umidade_raw',
        'Nota': 'nota_raw',
        'Quantidade de CPs': 'quantidade_cps_raw',
    }
    # Renomeia apenas as colunas que existem no DF para evitar erros se o usuário remover alguma
    df.rename(columns={k: v for k, v in colunas_fixas_rename_map.items() if k in df.columns}, inplace=True)

    for index, row in df.iterrows():
        linha_excel = index + 2  # Para feedback ao usuário (1-indexed + cabeçalho)
        try:
            data_usinagem_str = row.get('data_usinagem_raw')
            volume_produzido_str = row.get('volume_produzido_raw')
            umidade_str = row.get('umidade_raw')
            quantidade_cps_str = row.get('quantidade_cps_raw')
            nota_str = row.get('nota_raw')
            serie_str = row.get('Série', '').strip() if 'Série' in row else None

            # Validações
            if pd.isna(data_usinagem_str):
                feedback_erros.append(f"Linha {linha_excel}: Data de Usinagem não informada.")
                continue
            try:
                if isinstance(data_usinagem_str, datetime):  # Pandas já converteu
                    data_usinagem = data_usinagem_str
                else:  # Tenta converter de string
                    data_usinagem = datetime.strptime(str(data_usinagem_str).split('.')[0].split(' ')[0], '%Y-%m-%d')  # Pega só a data
                    # Adicionar hora se vier na string:
                    if ' ' in str(data_usinagem_str):
                        time_part_str = str(data_usinagem_str).split(' ')[1].split('.')[0]
                        time_part = datetime.strptime(time_part_str, '%H:%M:%S' if ':' in time_part_str and time_part_str.count(':') == 2 else '%H:%M').time()
                        data_usinagem = datetime.combine(data_usinagem.date(), time_part)
            except ValueError:
                feedback_erros.append(f"Linha {linha_excel}: Data de Usinagem ('{data_usinagem_str}') em formato inválido. Use AAAA-MM-DD ou AAAA-MM-DD HH:MM.")
                continue
            
            if pd.isna(volume_produzido_str):
                feedback_erros.append(f"Linha {linha_excel}: Volume Produzido não informado.")
                continue
            try:
                volume_produzido = Decimal(str(volume_produzido_str).replace(',', '.'))
                if volume_produzido <= 0:
                    raise ValueError("Volume deve ser positivo")
            except:
                feedback_erros.append(f"Linha {linha_excel}: Volume Produzido ('{volume_produzido_str}') inválido.")
                continue

            # Gerar série se não informada
            if not serie_str or pd.isna(serie_str):
                # Gerar série automática baseada na data e volume
                serie_str = f"IMP-{data_usinagem.strftime('%Y%m%d%H%M')}-{index+1}"
            
            # Verificar se série já existe
            if ConcretoUsinagens.query.filter_by(serie=serie_str).first():
                feedback_erros.append(f"Linha {linha_excel}: Série '{serie_str}' já existe. Pulando esta linha.")
                continue

            # Criar nova usinagem
            nova_usinagem = ConcretoUsinagens(
                serie=serie_str,
                data_usinagem=data_usinagem,
                produtoCompostoId=produto_composto_id,
                volume=volume_produzido,
                nota=nota_str if not pd.isna(nota_str) and str(nota_str).strip() else None
            )
            db.session.add(nova_usinagem)
            db.session.flush()

            # Processar materiais se houver informações no Excel
            materiais_para_salvar = []
            algum_material_informado = False
            if map_coluna_material_info:
                from models.concreto import ConcretoUsinagensMateriais
                for nome_coluna_excel, info_material in map_coluna_material_info.items():
                    if nome_coluna_excel in df.columns:  # Verifica se a coluna do material existe no arquivo do usuário
                        quantidade_executada_str = row.get(nome_coluna_excel)
                        if not pd.isna(quantidade_executada_str) and str(quantidade_executada_str).strip() != '':
                            algum_material_informado = True
                            try:
                                quantidade_executada = Decimal(str(quantidade_executada_str).replace(',', '.'))
                                if quantidade_executada < 0:
                                    raise ValueError("Quantidade não pode ser negativa.")
                                
                                # Buscar unidade
                                unidade = Unidades.query.get(info_material['unidade_id'])
                                if not unidade:
                                    feedback_erros.append(f"Linha {linha_excel}, Material '{nome_coluna_excel}': Unidade não encontrada.")
                                    continue
                                
                                # Criar registro de material da usinagem
                                usinagem_material = ConcretoUsinagensMateriais(
                                    usinagem_id=nova_usinagem.id,
                                    material_id=info_material['material_id'],
                                    quantidade_executada=quantidade_executada,
                                    unidade_id=info_material['unidade_id']
                                )
                                materiais_para_salvar.append(usinagem_material)
                            except Exception as e:
                                feedback_erros.append(f"Linha {linha_excel}, Material '{nome_coluna_excel}': Quantidade ('{quantidade_executada_str}') inválida. {str(e)}")
                                continue
            
            if materiais_para_salvar:
                db.session.add_all(materiais_para_salvar)
                db.session.flush()
            
            db.session.commit()
            usinagens_importadas_count += 1

        except Exception as e_row:
            db.session.rollback()
            feedback_erros.append(f"Linha {linha_excel}: Erro inesperado ao processar - {str(e_row)}")
            import traceback
            traceback.print_exc()

    if usinagens_importadas_count > 0 and not feedback_erros:
        flash(f'{usinagens_importadas_count} usinagem(ns) importada(s) com sucesso!', 'success')
        return jsonify({'success': True, 'message': f'{usinagens_importadas_count} usinagem(ns) importada(s) com sucesso!', 'errors': []})
    elif usinagens_importadas_count > 0 and feedback_erros:
        flash(f'{usinagens_importadas_count} usinagem(ns) importada(s). Alguns erros ocorreram (ver detalhes abaixo).', 'warning')
        return jsonify({'success': True, 'message': f'{usinagens_importadas_count} usinagem(ns) importada(s). Erros em {len(feedback_erros)} linha(s).', 'errors': feedback_erros})
    else:
        flash('Nenhuma usinagem foi importada. Verifique os erros.', 'danger')
        return jsonify({'success': False, 'message': 'Nenhuma usinagem importada.', 'errors': feedback_erros if feedback_erros else ['Nenhuma usinagem válida encontrada no arquivo ou nenhum dado fornecido.']})