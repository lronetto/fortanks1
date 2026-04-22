from datetime import datetime
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, flash, Response, send_file, current_app
from sqlalchemy.orm import defer
from models.estoque import Estoque,EstoqueMovimentacoes
from flask_login import login_required, current_user
from models.produto_composto import ProdutoComposto, ProdutoCompostoItem
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.material import Materiais

from models.database import db
import logging
import base64
import json
import os
from sqlalchemy import or_, func, and_
from sqlalchemy.orm import joinedload
from decimal import Decimal
from collections import defaultdict
from utils.utils import parse_dados_json
from utils.datatable_helper import DataTableParams

from controllers.cadastro_operacional.services.produto_composto_componentes_service import (
    expandir_componentes_produto_composto,
)
from controllers.cadastro_operacional.services.produto_composto_excel_service import (
    exportar_produtos_compostos_para_excel,
    importar_produtos_compostos_de_excel,
    salvar_upload_excel_temporario,
)
from controllers.cadastro_operacional.services.produto_composto_imagem_service import comprimir_imagem_base64

logger = logging.getLogger(__name__)

produto_composto_bp = Blueprint('produto_composto', __name__, url_prefix='/produto-composto')


@produto_composto_bp.route('/get_componentes/<int:id>/<int:quantidade>')
@login_required
def get_componentes(id,quantidade):
    """
    Retorna os componentes de um produto composto a partir do ID
    """
    try:
        produto = ProdutoComposto.query.join(ProdutoCompostoItem).join(Estoque).filter(ProdutoComposto.id == id).first()  
        componentes = []
        for componente in produto.componentes:
            estoque = componente.estoque.get_estoque_atual()
            capacidade = 0;
            if componente.quantidade >0 and estoque >0:
                capacidade = estoque / componente.quantidade
            componentes.append({
                'estoque_id': componente.estoque_id,
                'quantidade': format(float(componente.quantidade), '.2f'),
                'quantidade_total': format(float(componente.quantidade * quantidade), '.2f'),
                'nome': componente.estoque.material.nome if componente.estoque.material_id else componente.estoque.produto_composto.nome,
                'estoque': format(float(estoque if estoque else 0), '.2f'),
                'capacidade': format(float(capacidade), '.2f'),
                'valor_unitario': format(float(componente.get_valor_total()), '.2f'),
                'valor_total': format(float(componente.get_valor_total()*quantidade), '.2f')
            })
        quantidade_maxima = min(componente['capacidade'] for componente in componentes)
        return jsonify({
            'success': True,
            'componentes': componentes,
            'quantidade_maxima': quantidade_maxima,
            'valor_unitario': format(float(produto.get_valor_total()), '.2f'),
            'valor_total': format(float(produto.get_valor_total()*quantidade), '.2f')
        })
    except Exception as e:
        logger.error(f"Erro ao obter componentes: {str(e)}")
        return jsonify({'success': False, 'message': f'Erro ao obter componentes: {str(e)}'}), 500


@produto_composto_bp.route('/api/comparacao/componentes', methods=['GET'])
@login_required
def api_comparacao_componentes():
    """
    Retorna os itens (componentes) para comparação lado a lado entre 2+ produtos.
    """
    try:
        produto_ids = request.args.getlist('produto_ids', type=int)
        produto_ids = [pid for pid in produto_ids if pid]
        produto_ids = list(dict.fromkeys(produto_ids))  # unique preservando ordem

        if len(produto_ids) < 2:
            return jsonify({'success': False, 'message': 'Selecione pelo menos 2 produtos para comparar.'}), 400

        produtos = (
            ProdutoComposto.query.options(
                joinedload(ProdutoComposto.componentes).joinedload(ProdutoCompostoItem.estoque).joinedload(Estoque.material),
                joinedload(ProdutoComposto.componentes).joinedload(ProdutoCompostoItem.estoque).joinedload(Estoque.produto_composto),
            )
            .filter(ProdutoComposto.id.in_(produto_ids))
            .all()
        )

        by_id = {p.id: p for p in produtos}
        produtos_out = []
        for pid in produto_ids:
            p = by_id.get(pid)
            if not p:
                continue
            produtos_out.append({'id': p.id, 'nome': p.nome})

        # Union dos estoque_id + nome "humano"
        itens = {}
        for p in produtos_out:
            prod = by_id[p['id']]
            for comp in (prod.componentes or []):
                e = comp.estoque
                if not e:
                    continue
                nome = None
                if e.material_id and e.material:
                    nome = '[M] ' + (e.material.nome or '')
                elif getattr(e, 'ProdComp_id', None) and e.produto_composto:
                    nome = '[P] ' + (e.produto_composto.nome or '')
                else:
                    # fallback
                    nome = '[Item] ' + str(e.id)
                if e.id not in itens:
                    itens[e.id] = {
                        'estoque_id': e.id,
                        'nome': nome.strip(),
                        'por_produto': {}
                    }

        # preencher quantidades por produto
        for p in produtos_out:
            prod = by_id[p['id']]
            for comp in (prod.componentes or []):
                e = comp.estoque
                if not e or e.id not in itens:
                    continue
                itens[e.id]['por_produto'][prod.id] = float(comp.quantidade or 0)

        # Ordenação por nome, depois por estoque_id
        itens_out = list(itens.values())
        itens_out.sort(key=lambda x: (x.get('nome') or '').lower())

        return jsonify({
            'success': True,
            'produtos': produtos_out,
            'itens': itens_out
        })
    except Exception as e:
        logger.exception("Erro na comparação de componentes")
        return jsonify({'success': False, 'message': f'Erro ao carregar comparação: {str(e)}'}), 500


@produto_composto_bp.route('/api/comparacao/salvar', methods=['POST'])
@login_required
def api_comparacao_salvar():
    """
    Salva as quantidades editadas no modal de comparação.
    Recebe:
      { produtos: [ { id: int, componentes: [ { estoque_id: int, quantidade: number } ] } ] }
    Regras:
      - quantidade <= 0 remove o item do produto (se existir)
      - quantidade > 0 adiciona/atualiza o item
    """
    data = request.get_json(silent=True) or {}
    try:
        produtos_data = data.get('produtos') or []
        if not isinstance(produtos_data, list) or len(produtos_data) < 2:
            return jsonify({'success': False, 'message': 'Informe 2 ou mais produtos para salvar.'}), 400

        produto_ids = []
        for p in produtos_data:
            pid = p.get('id')
            if isinstance(pid, int) and pid:
                produto_ids.append(pid)
        produto_ids = list(dict.fromkeys(produto_ids))
        if len(produto_ids) < 2:
            return jsonify({'success': False, 'message': 'Informe 2 ou mais produtos válidos.'}), 400

        produtos = (
            ProdutoComposto.query.options(joinedload(ProdutoComposto.componentes))
            .filter(ProdutoComposto.id.in_(produto_ids))
            .all()
        )
        by_id = {p.id: p for p in produtos}

        # Atualiza produto a produto
        for p_in in produtos_data:
            pid = p_in.get('id')
            if pid not in by_id:
                continue

            produto = by_id[pid]
            comps_in = p_in.get('componentes') or []
            if not isinstance(comps_in, list):
                continue

            # map estoque_id -> ProdutoCompostoItem
            atuais = {int(ci.estoque_id): ci for ci in (produto.componentes or []) if ci.estoque_id}

            for ci in comps_in:
                estoque_id = ci.get('estoque_id')
                qtd = ci.get('quantidade')
                if not isinstance(estoque_id, int) or not estoque_id:
                    continue

                try:
                    qtd_num = float(qtd)
                except Exception:
                    continue

                if qtd_num <= 0:
                    if estoque_id in atuais:
                        produto.remover_item(int(estoque_id))
                    continue

                estoque = Estoque.query.get_or_404(int(estoque_id))
                produto.adicionar_item(estoque=estoque, quantidade=qtd_num)

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro ao salvar comparação")
        return jsonify({'success': False, 'message': f'Erro ao salvar comparação: {str(e)}'}), 500

@produto_composto_bp.route('/get_cadastro_operacional/produto_composto/<int:id>')
@login_required
def get_produto_composto(id):
    """
    Retorna um produto composto a partir do ID
    """
    produtos = []
    if id == 0 or not id:
        produto = ProdutoComposto.query.order_by(ProdutoComposto.nome.asc()).all()
       
        for p in produto:
            estoque = Estoque.query.filter(Estoque.ProdComp_id == p.id).first()
            produtos.append({
                'id': p.id,
                'nome': p.nome,
                'tempo_producao': float(p.tempo_producao) if p.tempo_producao else None,
                'componentes': len(p.componentes),
                'estoque': estoque.quantidade if estoque else 0,
                'status': p.status
            })
    else:
        produto = ProdutoComposto.query.get_or_404(id)
        componentes = []

        for p in produto.componentes:
            estoque = Estoque.query.filter(Estoque.ProdComp_id == p.estoque_id).first()
            nome_material_ou_produto = p.estoque.material.nome if p.estoque.material_id else p.estoque.produto_composto.nome
            componente_data = {
                'estoque_id': p.estoque_id,
                'quantidade': p.quantidade,
                'nome': '('+str(p.estoque.id)+') '+('[M] '+p.estoque.material.nome if p.estoque.material_id else '[P] '+p.estoque.produto_composto.nome),
                'nome_ordenacao': nome_material_ou_produto
            }
            # Adicionar dados_adicionais se existir
            if p.dados_adicionais:
                componente_data['dados_adicionais'] = p.dados_adicionais
            componentes.append(componente_data)
        
        # Ordenar componentes pelo nome do material ou produto composto (case-insensitive)
        componentes.sort(key=lambda x: x['nome_ordenacao'].lower())
        
        # Remover a chave temporária de ordenação
        for componente in componentes:
            componente.pop('nome_ordenacao', None)
        produtos.append({
            'id': produto.id,
            'nome': produto.nome,
            'tempo_producao': float(produto.tempo_producao) if produto.tempo_producao else None,
            'componentes': componentes,
            'estoque': estoque.quantidade if estoque else 0,
            'status': produto.status,
            'descricao': produto.descricao,
            'traco': produto.traco if produto.traco else 0,
            'imagem': produto.imagem,
            'imagem_mime_type': produto.imagem_mime_type
        })

    return jsonify({
        'produtos': produtos
    })


def _map_estoque_por_produto_composto(ids):
    """Quantidade em estoque por ProdutoComposto.id (primeiro registro por id, como no legado)."""
    if not ids:
        return {}
    out = {}
    rows = (
        Estoque.query.filter(
            Estoque.ProdComp_id.in_(ids),
            Estoque.tipo_item == 'produto_composto',
        ).all()
    )
    for e in rows:
        pid = e.ProdComp_id
        if pid not in out:
            out[pid] = float(e.quantidade or 0)
    return out


@produto_composto_bp.route('/api/datatables', methods=['GET'])
@login_required
def api_datatables():
    """JSON para DataTables (server-side): listagem de produtos compostos."""
    dt = DataTableParams()
    try:
        search_value = dt.search
        query = ProdutoComposto.query

        if search_value:
            if search_value.isdigit():
                sid = int(search_value)
                query = query.filter(
                    or_(
                        ProdutoComposto.nome.ilike(f'%{search_value}%'),
                        ProdutoComposto.id == sid,
                    )
                )
            else:
                query = query.filter(ProdutoComposto.nome.ilike(f'%{search_value}%'))

        total_records = ProdutoComposto.query.count()
        records_filtered = query.count()

        # Colunas: 0 checkbox, 1 id, 2 imagem, 3 nome, 4 estoque, 5 ações
        column_map = {
            1: ProdutoComposto.id,
            3: ProdutoComposto.nome,
        }
        if dt.order_col in column_map:
            col = column_map[dt.order_col]
            if dt.order_dir == 'desc':
                query = query.order_by(col.desc())
            else:
                query = query.order_by(col.asc())
        else:
            query = query.order_by(ProdutoComposto.nome.asc())

        if dt.length == -1:
            remaining = max(0, records_filtered - dt.start)
            cap = min(remaining, 5000)
            items = query.offset(dt.start).limit(cap).all() if cap else []
        else:
            lim = max(1, min(dt.length, 500))
            items = query.offset(dt.start).limit(lim).all()

        estoque_por = _map_estoque_por_produto_composto([p.id for p in items])

        data = []
        for p in items:
            data.append({
                'id': p.id,
                'nome': p.nome or '',
                'estoque': estoque_por.get(p.id, 0.0),
            })

        return dt.resposta(data, total_records, records_filtered)
    except Exception as e:
        logger.error(f'Erro api_datatables produto composto: {e}', exc_info=True)
        return jsonify({
            'draw': dt.draw,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e),
        }), 500


@produto_composto_bp.route('/')
@login_required
def index():
    """
    Lista todos os produtos compostos cadastrados
    """
    return render_template('cadastro_operacional/produto_composto/index.html')

@produto_composto_bp.route('/imagem/<int:id>')
def imagem_produto(id):
    """
    Serve a imagem de um produto a partir do banco de dados,
    decodificando-a de Base64.
    """
    produto = ProdutoComposto.query.get_or_404(id)

    if produto.imagem and produto.imagem_mime_type:
        # Decodificar a string Base64 para binário
        dados_imagem = base64.b64decode(produto.imagem)
        return Response(dados_imagem, mimetype=produto.imagem_mime_type)
    else:
        # Servir uma imagem placeholder se não houver imagem
        return send_file('static/img/logo.png', mimetype='image/png')

@produto_composto_bp.route('/<int:id>/form', methods=['GET'])
@produto_composto_bp.route('/form', methods=['GET'])
@login_required
def form(id=None):
    """
    Renderiza o formulário para novo ou edição de produto composto.
    """
    produto = ProdutoComposto.query.get_or_404(id) if id else None
    itens_estoque = Estoque.query.join(Materiais).order_by(Materiais.nome).all()
    return render_template('cadastro_operacional/produto_composto/modais/form.html', produto=produto, itens_estoque=itens_estoque)


@produto_composto_bp.route('/salvar', methods=['POST'])
@login_required
def salvar():
    """
    Salva um novo produto composto ou atualiza um existente.
    """
    data = request.get_json()
    produto_id = data.get('id')
    
    try:
        if produto_id:
            # Edição
            produto = ProdutoComposto.query.get_or_404(produto_id)
            produto.nome = data['nome']
            produto.descricao = data.get('descricao')
            produto.tempo_producao = data.get('tempo_producao') or None
            produto.status = data.get('status', 'Ativo')
            produto.traco = data.get('traco', 0) or 0

            # Lógica para remover imagem
            if data.get('remover_imagem'):
                produto.imagem = None
                produto.imagem_mime_type = None

            if not (produto.imagem == data.get('imagem') and produto.imagem_mime_type == data.get('imagem_mime_type')):
                
                # Lógica para atualizar imagem
                imagem_data = data.get('imagem')
                logger.info(f"Dados de imagem recebidos: {imagem_data is not None}, Tipo: {type(imagem_data)}")
                
                if imagem_data:
                    logger.info(f"Processando imagem - Tamanho: {len(imagem_data)} caracteres")
                    # Comprimir a imagem antes de salvar
                    imagem_comprimida, mime_type = comprimir_imagem_base64(imagem_data)
                    header, encoded = imagem_comprimida.split(',', 1)
                    
                    # Validação simples
                    if not mime_type.startswith('image/'):
                        return jsonify({'success': False, 'message': 'Formato de arquivo inválido. Apenas imagens são permitidas.'}), 400
                    
                    # Validar tamanho (Base64 é ~33% maior que o binário)
                    if len(encoded) * 0.75 > 2 * 1024 * 1024:
                        return jsonify({'success': False, 'message': 'A imagem excede o tamanho máximo de 2MB.'}), 400

                    # Salvar a string Base64 diretamente, como no modelo Upload
                    produto.imagem = encoded
                    produto.imagem_mime_type = mime_type

            # Atualizar componentes
            componentes_data = data.get('componentes', [])
            
            # Mapear componentes atuais para fácil acesso
            componentes_atuais = {str(comp.estoque_id): comp for comp in produto.componentes}
            
            # IDs dos componentes recebidos do formulário
            componentes_recebidos_ids = {item['estoque_id'] for item in componentes_data}
            
            # Remover componentes que não estão mais na lista
            for estoque_id, componente in list(componentes_atuais.items()):
                if estoque_id not in componentes_recebidos_ids:
                    produto.remover_item(int(estoque_id))
            
            # Adicionar ou atualizar componentes
            for item in componentes_data:
                tipo = item.get('tipo')
                if tipo == 'material':
                    estoque=Estoque(
                            material_id=item.get('estoque_id'),
                            quantidade=0,
                            tipo_item='material',
                            localizacao='Estoque Matriz',
                        )
                    estoque.save()
                    estoque.refresh()
                else:
                    estoque_id = item.get('estoque_id')
                    estoque = Estoque.query.get_or_404(estoque_id)
                
                # Log para debug dos valores de quantidade
                logger.info(f"Adicionando componente - Estoque ID: {item['estoque_id']}, Quantidade: {item['quantidade']} (tipo: {type(item['quantidade'])})")
                
                componente = produto.adicionar_item(
                    estoque=estoque,
                    quantidade=item['quantidade']
                )
                
                # Salvar dados adicionais (datas) se existirem
                if item.get('dados_adicionais'):
                    # Converter dicionário para string JSON
                    if isinstance(item['dados_adicionais'], dict):
                        componente.dados_adicionais = json.dumps(item['dados_adicionais'])
                    else:
                        componente.dados_adicionais = item['dados_adicionais']
        else:
            # Criação
            produto = ProdutoComposto(
                nome=data['nome'],
                descricao=data.get('descricao'),
                tempo_producao=data.get('tempo_producao') or None,
                status='Ativo',
                traco=data.get('traco', 0) or 0
            )
            
            # Log para debug - verificar se há dados muito longos
            logger.info(f"Nome do produto: {len(data['nome'])} caracteres")
            logger.info(f"Descrição: {len(data.get('descricao', ''))} caracteres")
            
            db.session.add(produto)

            # Lógica para adicionar imagem na criação
            imagem_data = data.get('imagem')
            logger.info(f"Criação - Dados de imagem recebidos: {imagem_data is not None}, Tipo: {type(imagem_data)}")
            
            if imagem_data:
                logger.info(f"Criação - Processando imagem - Tamanho: {len(imagem_data)} caracteres")
                # Log do tamanho original
                original_size = len(imagem_data.split(',')[1]) if ',' in imagem_data else len(imagem_data)
                logger.info(f"Tamanho original da imagem: {original_size} caracteres")
                
                # Comprimir a imagem antes de salvar
                imagem_comprimida, mime_type = comprimir_imagem_base64(imagem_data)
                header, encoded = imagem_comprimida.split(',', 1)
                
                # Log do tamanho comprimido
                logger.info(f"Tamanho comprimido da imagem: {len(encoded)} caracteres")
                logger.info(f"Redução: {((original_size - len(encoded)) / original_size * 100):.1f}%")
                
                # Verificação adicional: rejeitar se ainda for muito grande
                if len(encoded) > 100000:  # Limite de 100KB em Base64
                    return jsonify({'success': False, 'message': 'A imagem ainda é muito grande após a compressão. Tente uma imagem menor.'}), 400
                
                if not mime_type.startswith('image/'):
                    return jsonify({'success': False, 'message': 'Formato de arquivo inválido.'}), 400
                
                if len(encoded) * 0.75 > 2 * 1024 * 1024:
                     return jsonify({'success': False, 'message': 'A imagem excede o tamanho máximo de 2MB.'}), 400

                # Salvar a string Base64 diretamente, como no modelo Upload
                produto.imagem = encoded
                produto.imagem_mime_type = mime_type

            # Flush para obter o ID do produto antes de adicionar componentes
            db.session.flush()
            estoque = Estoque(
                produto_composto=produto,
                quantidade=0,
                tipo_item='produto_composto',
                localizacao='Estoque Matriz',
                )
            estoque.save()
            # Adicionar componentes
            componentes_data = data.get('componentes', [])
            for item in componentes_data:
                tipo = item.get('tipo')
                if tipo == 'material':
                    estoque=Estoque(
                            material_id=item.get('estoque_id'),
                            quantidade=0,
                            tipo_item='material',
                            localizacao='Estoque Matriz',
                        )
                    estoque.save()
                    estoque.refresh()
                else:
                    estoque_id = item.get('estoque_id')
                    estoque = Estoque.query.get_or_404(estoque_id)
                
                    
                # Log para debug dos valores de quantidade
                logger.info(f"Criando componente - Estoque ID: {item['estoque_id']}, Quantidade: {item['quantidade']} (tipo: {type(item['quantidade'])})")
                
                componente = produto.adicionar_item(
                    estoque=estoque,
                    quantidade=item['quantidade']
                )
                
                # Salvar dados adicionais (datas) se existirem
                if item.get('dados_adicionais'):
                    # Converter dicionário para string JSON
                    if isinstance(item['dados_adicionais'], dict):
                        componente.dados_adicionais = json.dumps(item['dados_adicionais'])
                    else:
                        componente.dados_adicionais = item['dados_adicionais']
        estoque = Estoque.query.filter(Estoque.ProdComp_id == produto.id).first()
        if not estoque:
            estoque = Estoque(produto_composto=produto,
                              quantidade=0,
                              tipo_item='produto_composto',
                              localizacao='Estoque Matriz',
                              )
            db.session.add(estoque)
            db.session.flush()
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Produto composto salvo com sucesso!'})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao salvar produto composto: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao salvar produto composto: {str(e)}'}), 500


@produto_composto_bp.route('/<int:id>/deletar', methods=['POST'])
@login_required
def deletar(id):
    """
    Remove um produto composto do sistema
    """
    produto = ProdutoComposto.query.get_or_404(id)
    
    try:
        produto.delete()
        return jsonify({'success': True, 'message': 'Produto composto removido com sucesso!'})
        
    except Exception as e:
        logger.error(f"Erro ao deletar produto composto: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao deletar produto composto: {str(e)}'}), 500

@produto_composto_bp.route('/<int:id>/duplicar', methods=['POST'])
@login_required
def duplicar(id):
    """
    Duplica um produto composto existente
    """
    print('duplicar produto composto id', id)
    produto_original = ProdutoComposto.query.get_or_404(id)
    
    try:
        # Criar novo produto com dados do original
        novo_produto = ProdutoComposto(
            nome=f"{produto_original.nome} (Cópia)",
            descricao=produto_original.descricao,
            tempo_producao=produto_original.tempo_producao,
            status='Ativo',
            imagem=produto_original.imagem,
            traco=produto_original.traco,
            dados_adicionais=produto_original.dados_adicionais,
            imagem_mime_type=produto_original.imagem_mime_type
        )
        
        db.session.add(novo_produto)
        db.session.flush()  # Para obter o ID do novo produto
        estoque = Estoque(
            produto_composto=novo_produto,
            quantidade=0,
            tipo_item='produto_composto',
            localizacao='Estoque Matriz',
        )
        estoque.save()
        # Duplicar todos os componentes
        for componente in produto_original.componentes:
            novo_componente = ProdutoCompostoItem(
                produto_id=novo_produto.id,
                estoque_id=componente.estoque_id,
                quantidade=componente.quantidade,
                observacao=componente.observacao,
                dados_adicionais=componente.dados_adicionais  # Copiar dados adicionais (datas)
            )
            db.session.add(novo_componente)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Produto composto duplicado com sucesso!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao duplicar produto composto: {e}'}), 500

@produto_composto_bp.route('/produzir', methods=['POST'])
@login_required
def produzir():
    try:
        data = request.form
        produto_id = int(data.get('produto_id'))
        quantidade = int(data.get('quantidade'))

        if not produto_id or not quantidade or quantidade <= 0:
            return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

        produto = ProdutoComposto.query.get(produto_id)
        if not produto:
            return jsonify({'success': False, 'message': 'Produto não encontrado.'}), 404

        # Lógica para baixar o estoque dos componentes
        for componente in produto.componentes:
            material = componente.material
            quantidade_necessaria = componente.quantidade * quantidade
            
            if material.estoque_atual < quantidade_necessaria:
                return jsonify({
                    'success': False, 
                    'message': f'Estoque insuficiente para o material {material.nome}. Necessário: {quantidade_necessaria}, Disponível: {material.estoque_atual}'
                }), 400

            material.estoque_atual -= quantidade_necessaria
            
            # Registrar movimentação de saída
            movimentacao = EstoqueMovimentacoes(
                material_id=material.id,
                quantidade=-quantidade_necessaria,
                tipo='saida_producao',
                observacao=f'Produção do produto {produto.nome} (ID: {produto.id})',
                usuario_id=current_user.id
            )
            db.session.add(movimentacao)

        # Aumentar o estoque do produto acabado
        produto.estoque += quantidade
        db.session.commit()

        return jsonify({
            'success': True, 
            'message': 'Produção registrada com sucesso!',
            'produto_id': produto.id,
            'novo_estoque': produto.estoque
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erro ao registrar produção: {e}")
        return jsonify({'success': False, 'message': 'Erro interno no servidor.'}), 500

@produto_composto_bp.route('/api/componentes/<int:id>')
@login_required
def api_componentes(id):
    """
    API que retorna os componentes de um produto composto
    """
    produto = ProdutoComposto.query.get_or_404(id)
    
    # Montar resposta com componentes
    componentes = []

    for componente in produto.componentes:
        componentes.append({
            'id': componente.id,
            'estoque_id': componente.estoque_id,
            'estoque_nome': componente.estoque.material.nome if componente.estoque.material_id else componente.estoque.produto_composto.nome,
            'quantidade': float(componente.quantidade),
            'unidade': componente.estoque.material.unidade_obj.sigla if (componente.estoque.material and componente.estoque.material.unidade_obj) else '',
            'observacao': componente.observacao
        })
    componentes.sort(key=lambda x: x['estoque_nome'])
    return jsonify({
        'id': produto.id,
        'nome': produto.nome,
        'tempo_producao': float(produto.tempo_producao) if produto.tempo_producao else None,
        'componentes': componentes
    })

@produto_composto_bp.route('/api/verificar-estoque/<int:id>')
@login_required
def api_verificar_estoque(id):
    """
    API que verifica a disponibilidade de estoque para um produto composto
    """
    produto = ProdutoComposto.query.get_or_404(id)
    quantidade = request.args.get('quantidade', 1, type=int)
    
    disponibilidade = produto.verificar_disponibilidade_estoque(quantidade)
    
    # Preparar resposta
    resultado = []
    for item in disponibilidade:
        resultado.append({
            'estoque': item['estoque'].material.nome if item['estoque'].material_id else item['estoque'].produto_composto.nome,
            'quantidade_necessaria': float(item['quantidade_necessaria']),
            'quantidade_estoque': float(item['quantidade_estoque']),
            'disponivel': item['disponivel']
        })
        
    return jsonify({
        'produto': produto.nome,
        'quantidade': quantidade,
        'disponibilidade': resultado,
        'disponivel_total': all(item['disponivel'] for item in disponibilidade)
    })


@produto_composto_bp.route('/api/itens-estoque', methods=['GET'])
@login_required
def api_itens_estoque():
    """
    API para Select2: lista itens de estoque que podem ser componentes de Produto Composto.
    Retorna Materiais (Estoque.material_id) e Produtos Compostos (Estoque.ProdComp_id).
    """
    search_term = (request.args.get('q') or '').strip()

    query = (
        Estoque.query.options(
            joinedload(Estoque.material).joinedload(Materiais.unidade_obj),
            joinedload(Estoque.produto_composto),
        )
        .filter(or_(Estoque.material_id.isnot(None), Estoque.ProdComp_id.isnot(None)))
        .outerjoin(Materiais, Estoque.material_id == Materiais.id)
        .outerjoin(ProdutoComposto, Estoque.ProdComp_id == ProdutoComposto.id)
    )

    if search_term:
        like = f'%{search_term}%'
        query = query.filter(
            or_(
                Materiais.nome.ilike(like),
                Materiais.dados_adicionais.ilike(like),
                ProdutoComposto.nome.ilike(like),
            )
        )

    itens = query.order_by(func.coalesce(Materiais.nome, ProdutoComposto.nome).asc()).limit(200).all()

    results = []
    for item in itens:
        if item.material:
            sigla = item.material.unidade_obj.sigla if (item.material.unidade_obj and hasattr(item.material.unidade_obj, "sigla")) else None
            unidade_txt = f" ({sigla})" if sigla else ""
            codigo_sox = parse_dados_json(item.material.dados_adicionais).get("codigo_sox")
            codigo_txt = f"{codigo_sox} - " if codigo_sox else ""
            # [E] = material contido em estoque.py (ou seja, existe registro em Estoque)
            text = f"[E] {codigo_txt}{item.material.nome}{unidade_txt}"
            results.append({'id': item.id, 'text_sort': item.material.nome.lower(), 'text': text,'tipo': 'estoque'})
        elif item.produto_composto:
            text = f"[P] {item.produto_composto.nome}"
            results.append({'id': item.id, 'text_sort': item.produto_composto.nome.lower(), 'text': text,'tipo': 'produto_composto'})

    # [M] = material em material.py que não está em estoque.py (sem registro em Estoque)
    materiais_query = (
        Materiais.query.options(joinedload(Materiais.unidade_obj))
        .filter(Materiais.ativo.is_(True))
        .outerjoin(
            Estoque,
            and_(
                Estoque.material_id == Materiais.id,
                Estoque.tipo_item == 'material',
            ),
        )
        .filter(Estoque.id.is_(None))
    )
    if search_term:
        like = f'%{search_term}%'
        materiais_query = materiais_query.filter(or_(Materiais.nome.ilike(like), Materiais.dados_adicionais.ilike(like)))

    materiais_sem_estoque = materiais_query.order_by(Materiais.nome.asc()).limit(200).all()
    for material in materiais_sem_estoque:
        sigla = material.unidade_obj.nome if (material.unidade_obj and hasattr(material.unidade_obj, "sigla")) else None
        unidade_txt = f" ({sigla})" if sigla else ""
        codigo_sox = parse_dados_json(material.dados_adicionais).get("codigo_sox")
        codigo_txt = f"{codigo_sox} - " if codigo_sox else ""
        results.append({'id': f"material:{material.id}", 'text_sort': material.nome.lower(), 'text': f"[M] {codigo_txt}{material.nome}{unidade_txt}",'tipo': 'material'})

    results.sort(key=lambda x: x['text_sort'])
    return jsonify({'results': results})

@produto_composto_bp.route('/api/historico-custo/<int:id>')
@login_required
def api_historico_custo(id):
    """
    API que retorna o histórico de custo de um produto composto
    considerando o preço médio dos materiais vinculados às notas fiscais ao longo do tempo
    Inclui produtos compostos aninhados recursivamente
    """
    try:
        produto = ProdutoComposto.query.get_or_404(id)
        data_inicio = request.args.get('data_inicio', type=str)
        data_fim = request.args.get('data_fim', type=str)
        
        # Expandir todos os componentes recursivamente (incluindo produtos compostos aninhados)
        componentes_materiais_raw = expandir_componentes_produto_composto(produto.id)
        
        # Agrupar materiais por material_id e somar quantidades
        componentes_agrupados = {}
        for comp in componentes_materiais_raw:
            material_id = comp['material_id']
            if material_id in componentes_agrupados:
                componentes_agrupados[material_id]['quantidade'] += comp['quantidade']
            else:
                componentes_agrupados[material_id] = comp.copy()
        
        componentes_materiais = list(componentes_agrupados.values())
        
        if not componentes_materiais:
            return jsonify({
                'success': True,
                'produto_nome': produto.nome,
                'historico': [],
                'mensagem': 'Este produto composto não possui componentes de material para calcular o histórico de custo.'
            })
        
        # Buscar histórico de preços para cada material
        historico_por_material = {}
        for comp in componentes_materiais:
            material_id = comp['material_id']
            query = (
                db.session.query(
                    NotaFiscalItem.quantidade,
                    NotaFiscalItem.valor_unitario,
                    NotaFiscalItem.valor_total,
                    NotaFiscalItem.unidade.label("unidade_item_nf"),
                    NotaFiscalItem.fator_conversao_aplicado,
                    NotaFiscal.data_emissao,
                    NotaFiscal.numero_nf,
                    NotaFiscal.nome_emitente,
                    NotaFiscal.id.label("nota_id"),
                    NotaFiscal.chave_acesso,
                )
                .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
                .filter(NotaFiscal.status_processamento != "cancelada")
                .filter(NotaFiscalItem.material_id == material_id)
            )
            
            if data_inicio:
                try:
                    dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
                    query = query.filter(NotaFiscal.data_emissao >= dt_inicio)
                except ValueError:
                    pass
            
            if data_fim:
                try:
                    dt_fim = datetime.strptime(data_fim, "%Y-%m-%d").date()
                    query = query.filter(NotaFiscal.data_emissao <= dt_fim)
                except ValueError:
                    pass
            
            historico_cru = query.order_by(NotaFiscal.data_emissao.desc()).all()
            
            historico_formatado = []
            for item in historico_cru:
                quantidade_final = item.quantidade
                valor_unitario_final = item.valor_unitario
                unidade_final = item.unidade_item_nf
                fator_aplicado = None
                
                # SEMPRE aplicar fator de conversão se existir
                # O fator converte a unidade da NF para a unidade padrão do material
                if item.fator_conversao_aplicado is not None:
                    try:
                        fator = Decimal(str(item.fator_conversao_aplicado))
                        if fator > 0 and item.quantidade is not None and item.valor_total is not None:
                            # Quantidade convertida para a unidade padrão do material
                            quantidade_conv = Decimal(str(item.quantidade)) * fator
                            if quantidade_conv > 0:
                                # Valor unitário na unidade padrão do material
                                valor_unitario_conv = Decimal(str(item.valor_total)) / quantidade_conv
                                quantidade_final = quantidade_conv
                                valor_unitario_final = valor_unitario_conv
                                fator_aplicado = float(fator)
                    except Exception as e:
                        logger.warning(f"Erro ao aplicar fator de conversão para material {material_id}: {str(e)}")
                        # Se falhar, usar valores originais
                        pass
                else:
                    # Se não há fator de conversão, usar valores originais
                    # Mas garantir que valor_unitario está correto
                    if item.valor_total is not None and item.quantidade is not None and item.quantidade > 0:
                        try:
                            valor_unitario_calculado = Decimal(str(item.valor_total)) / Decimal(str(item.quantidade))
                            valor_unitario_final = valor_unitario_calculado
                        except Exception:
                            pass
                
                # Calcular valor_total do item (já convertido se houver fator)
                valor_total_item = None
                if item.valor_total is not None:
                    if fator_aplicado:
                        # Se houve conversão, o valor_total já está na unidade convertida
                        # Mas precisamos manter o valor_total original do item para calcular com frete
                        valor_total_item = float(item.valor_total)
                    else:
                        valor_total_item = float(item.valor_total)
                
                historico_formatado.append({
                    "quantidade": float(quantidade_final) if quantidade_final is not None else 0.0,
                    "valor_unitario": float(valor_unitario_final) if valor_unitario_final is not None else 0.0,
                    "valor_total_item": valor_total_item,  # Valor total do item na nota (sem conversão de unidade)
                    "data_emissao": item.data_emissao.strftime("%Y-%m-%d") if item.data_emissao else None,
                    "numero_nf": item.numero_nf,
                    "nome_emitente": item.nome_emitente,
                    "nota_id": item.nota_id,
                    "chave_acesso": item.chave_acesso,
                    "fator_conversao_aplicado": fator_aplicado,
                    "unidade_original": unidade_final
                })
            
            historico_por_material[material_id] = historico_formatado
        
        print(f'historico_por_material: {len(historico_por_material)}')
        # Agrupar por data e calcular custo total do produto composto
        # Usar um dicionário para agrupar por data
        custo_por_data = defaultdict(lambda: {
            'data': None,
            'custo_total': 0.0,
            'componentes': [],
            'preco_medio_ponderado': 0.0
        })
        
        # Para cada data, calcular o preço médio de cada material e o custo total
        todas_datas = set()
        for material_id, historico in historico_por_material.items():
            for item in historico:
                if item['data_emissao']:
                    todas_datas.add(item['data_emissao'])
        
        # Ordenar datas
        todas_datas = sorted(todas_datas, reverse=True)
        
        # Para cada data, calcular o custo usando o preço mais recente disponível até aquela data
        # IMPORTANTE: Para cada data, precisamos recalcular os componentes ativos considerando
        # as datas de início e término de cada componente
        historico_custo = []
        precos_anteriores = {}  # material_id -> último preço conhecido
        
        for data in todas_datas:
            # Converter data string para date object
            try:
                data_obj = datetime.strptime(data, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            
            # Expandir componentes considerando a data atual (filtra por data_inicio e data_termino)
            componentes_materiais_data = expandir_componentes_produto_composto(
                produto.id, 
                quantidade_base=1.0, 
                caminho_atual=None, 
                data_movimento=data_obj
            )
            
            # Agrupar materiais por material_id e somar quantidades para esta data
            componentes_agrupados_data = {}
            for comp in componentes_materiais_data:
                material_id = comp['material_id']
                if material_id in componentes_agrupados_data:
                    componentes_agrupados_data[material_id]['quantidade'] += comp['quantidade']
                else:
                    componentes_agrupados_data[material_id] = comp.copy()
            
            componentes_materiais_ativos = list(componentes_agrupados_data.values())
            
            custo_total = 0.0
            componentes_data = []
            
            for comp in componentes_materiais_ativos:
                material_id = comp['material_id']
                quantidade_necessaria = comp['quantidade']
                
                # Buscar o preço mais recente até esta data
                # O valor_unitario já está calculado considerando o fator de conversão aplicado
                preco_atual = precos_anteriores.get(material_id)
                historico_material = historico_por_material.get(material_id, [])
                chave_acesso_nf_usada = None
                quantidade_item_nf = None
                valor_total_item_nf = None
                
                # Encontrar o preço mais recente até esta data
                # O valor_unitario retornado já está na unidade padrão do material (após aplicar fator de conversão)
                for item in historico_material:
                    if item['data_emissao'] and item['data_emissao'] <= data:
                        # valor_unitario já considera fator_conversao_aplicado se existir
                        preco_atual = item['valor_unitario']
                        chave_acesso_nf_usada = item.get('chave_acesso')
                        quantidade_item_nf = item.get('quantidade')  # Quantidade já convertida (se houver fator)
                        valor_total_item_nf = item.get('valor_total_item')  # Valor total do item na nota
                        precos_anteriores[material_id] = preco_atual
                        break
                
                if preco_atual is not None and preco_atual > 0:
                    # Buscar CTE (frete) relacionado à nota fiscal
                    valor_frete = 0.0
                    tem_frete = False
                    if chave_acesso_nf_usada:
                        try:
                            # Buscar CTEs (tipo 2) que possam ter chave_nf correspondente nos dados_adicionais
                            # Primeiro tenta busca direta por json_extract (mais eficiente)
                            cte = (
                                db.session.query(NotaFiscal).options(
                                    defer(NotaFiscal.dados_adicionais),
                                    defer(NotaFiscal.xml_data))
                                .filter(NotaFiscal.tipo == 2)
                                .filter(NotaFiscal.status_processamento != "cancelada")
                                .filter(NotaFiscal.chave_nf is not None)
                                .filter(NotaFiscal.chave_nf == chave_acesso_nf_usada)
                                .first()
                            )
                            print(f'cte: {cte}')
                            if cte and cte.valor_total:
                                valor_frete = float(cte.valor_total)
                                tem_frete = True
                            
                        except Exception as e:
                            logger.warning(f"Erro ao buscar frete para chave_acesso {chave_acesso_nf_usada}: {str(e)}")
                    
                    # Recalcular preço unitário se houver frete
                    # O custo unitário correto é: (valor_total_item + valor_frete) / quantidade_convertida
                    if tem_frete and valor_total_item_nf is not None and quantidade_item_nf is not None and quantidade_item_nf > 0:
                        preco_atual = (valor_total_item_nf + valor_frete) / quantidade_item_nf
                    
                    # Cálculo do custo: quantidade_necessaria (já na unidade padrão) × preco_unitario (já convertido, com frete se houver)
                    custo_componente = quantidade_necessaria * preco_atual
                    custo_total += custo_componente
                    
                    # Montar nome do material com "+ frete" se houver
                    nome_material = comp['material_nome']
                    if tem_frete:
                        nome_material += " + frete"
                    
                    componentes_data.append({
                        'material_nome': nome_material,
                        'quantidade': quantidade_necessaria,
                        'preco_unitario': preco_atual,  # Já considera fator de conversão e frete se houver
                        'custo_componente': custo_componente,
                        'unidade': comp['unidade'],  # Unidade padrão do material
                        'tem_frete': tem_frete,
                        'valor_frete': valor_frete
                    })
            
            if custo_total > 0:
                # Calcular peso percentual de cada componente e ordenar por custo
                for comp in componentes_data:
                    comp['peso_percentual'] = round((comp['custo_componente'] / custo_total) * 100, 2) if custo_total > 0 else 0
                
                # Ordenar componentes por custo_componente (maior primeiro)
                componentes_data.sort(key=lambda x: x['custo_componente'], reverse=True)
                
                historico_custo.append({
                    'data': data,
                    'custo_total': round(custo_total, 2),
                    'componentes': componentes_data
                })
        
        print(f'historico_custo: {len(historico_custo)}')
        return jsonify({
            'success': True,
            'produto_nome': produto.nome,
            'produto_id': produto.id,
            'historico': historico_custo,
            'componentes': componentes_materiais
        })
        
    except Exception as e:
        logger.error(f"Erro ao buscar histórico de custo: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Erro ao buscar histórico de custo: {str(e)}'
        }), 500

@produto_composto_bp.route('/exportar-excel', methods=['POST'])
@login_required
def exportar_excel():
    """
    Exporta produtos compostos selecionados para Excel
    Cada produto terá sua própria aba com seus materiais/componentes
    """
    try:
        produto_ids = request.form.getlist("produto_ids")
        if not produto_ids:
            flash("Nenhum produto selecionado para exportar.", "warning")
            return redirect(url_for("produto_composto.index"))

        produto_ids = [int(pid) for pid in produto_ids if str(pid).isdigit()]
        if not produto_ids:
            flash("IDs de produtos inválidos.", "danger")
            return redirect(url_for("produto_composto.index"))

        produtos = ProdutoComposto.query.filter(ProdutoComposto.id.in_(produto_ids)).all()
        if not produtos:
            flash("Nenhum produto encontrado.", "warning")
            return redirect(url_for("produto_composto.index"))

        output, filename = exportar_produtos_compostos_para_excel(produtos)
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        logger.error(f"Erro ao exportar produtos compostos: {str(e)}", exc_info=True)
        flash(f'Erro ao exportar: {str(e)}', 'danger')
        return redirect(url_for('produto_composto.index'))

@produto_composto_bp.route('/importar-excel', methods=['POST'])
@login_required
def importar_excel():
    """
    Importa produtos compostos de um arquivo Excel
    Cada aba do Excel representa um produto composto
    """
    try:
        if "arquivo_excel" not in request.files:
            return jsonify({"success": False, "message": "Nenhum arquivo enviado"}), 400

        arquivo = request.files["arquivo_excel"]
        if not getattr(arquivo, "filename", ""):
            return jsonify({"success": False, "message": "Nenhum arquivo selecionado"}), 400

        if not arquivo.filename.endswith((".xlsx", ".xls")):
            return jsonify({"success": False, "message": "Apenas arquivos Excel (.xlsx ou .xls) são permitidos"}), 400

        sobrescrever = request.form.get("sobrescrever") == "1"
        temp_path = salvar_upload_excel_temporario(arquivo)
        try:
            result = importar_produtos_compostos_de_excel(temp_path, sobrescrever=sobrescrever)
            return jsonify(result)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Erro ao importar produtos compostos: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erro ao importar: {str(e)}'
        }), 500
