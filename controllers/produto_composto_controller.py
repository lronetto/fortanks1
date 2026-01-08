from datetime import datetime
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, flash, Response, send_file, current_app
from io import BytesIO
from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename
from models.estoque import Estoque,EstoqueMovimentacoes
from flask_login import login_required, current_user
from models.produto_composto import ProdutoComposto, ProdutoCompostoItem
from models.nota_fiscal import NotaFiscal, NotaFiscalItem
from models.material import Materiais

from models.database import db
import logging
import base64
import re
import json
from PIL import Image
import io
import os
import tempfile
import pandas as pd
from sqlalchemy import or_, func, and_
from sqlalchemy.orm import joinedload
from decimal import Decimal
from collections import defaultdict

logger = logging.getLogger(__name__)

produto_composto_bp = Blueprint('produto_composto', __name__, url_prefix='/produto-composto')


def _resolver_estoque_id_para_componente(estoque_id_raw):
    """
    Resolve o identificador vindo do Select2:
    - "123" / 123  -> estoque_id (int) existente
    - "material:45" -> cria/busca Estoque(tipo_item='material') e retorna estoque_id (int)
    """
    if estoque_id_raw is None:
        raise ValueError("estoque_id não informado")

    # Pode vir como string (ex: "material:123") ou número
    estoque_id_txt = str(estoque_id_raw).strip()
    if estoque_id_txt.startswith("material:"):
        material_id_txt = estoque_id_txt.split("material:", 1)[1].strip()
        if not material_id_txt.isdigit():
            raise ValueError("material_id inválido no estoque_id")
        material_id = int(material_id_txt)

        material = Materiais.query.get_or_404(material_id)
        estoque = Estoque.query.filter_by(material_id=material.id, tipo_item='material').first()
        if not estoque:
            estoque = Estoque(
                material_id=material.id,
                tipo_item='material',
                quantidade=0,
                localizacao='Estoque Matriz',
                usuario_id=getattr(current_user, "id", None),
            )
            db.session.add(estoque)
            db.session.flush()
        return estoque.id

    # fallback: id numérico de Estoque
    if not estoque_id_txt.isdigit():
        raise ValueError("estoque_id inválido")
    return int(estoque_id_txt)

def comprimir_imagem_base64(imagem_base64, max_size=(400, 300), quality=70):
    """
    Comprime uma imagem em Base64, reduzindo seu tamanho de forma mais agressiva
    """
    try:
        # Verificar se a string contém o formato data:image/...
        if not imagem_base64 or not imagem_base64.startswith('data:image/'):
            logger.error("Formato de imagem inválido")
            return imagem_base64, "image/jpeg"
        
        # Decodificar Base64 para bytes
        header, encoded = imagem_base64.split(',', 1)
        mime_type = header.split(';')[0].split(':')[1]
        
        logger.info(f"Tipo MIME original: {mime_type}")
        
        # Decodificar para imagem
        dados_imagem = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(dados_imagem))
        
        logger.info(f"Dimensões originais: {img.size}")
        logger.info(f"Modo da imagem: {img.mode}")
        
        # Converter para RGB se necessário (PNG com transparência)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
            logger.info("Imagem convertida para RGB")
        
        # Redimensionar se necessário (tamanho menor)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        logger.info(f"Dimensões após redimensionamento: {img.size}")
        
        # Comprimir e converter para Base64 (qualidade menor)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        buffer.seek(0)
        
        # Converter de volta para Base64
        dados_comprimidos = buffer.getvalue()
        base64_comprimido = base64.b64encode(dados_comprimidos).decode('utf-8')
        
        logger.info(f"Tamanho dos dados comprimidos: {len(dados_comprimidos)} bytes")
        
        return f"data:image/jpeg;base64,{base64_comprimido}", "image/jpeg"
        
    except Exception as e:
        logger.error(f"Erro ao comprimir imagem: {str(e)}")
        # Se falhar, retorna a imagem original e um mime_type padrão
        return imagem_base64, "image/jpeg"

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

@produto_composto_bp.route('/get_produto_composto/<int:id>')
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
            'imagem': produto.imagem,
            'imagem_mime_type': produto.imagem_mime_type
        })

    return jsonify({
        'produtos': produtos
    })

@produto_composto_bp.route('/')
@login_required
def index():
    """
    Lista todos os produtos compostos cadastrados
    """
    produtos = ProdutoComposto.query.order_by(ProdutoComposto.id.desc()).all()
    return render_template('produto_composto/index.html', produtos=produtos)

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
    return render_template('produto_composto/modais/form.html', produto=produto, itens_estoque=itens_estoque)


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
                    componente.dados_adicionais = item['dados_adicionais']
        else:
            # Criação
            produto = ProdutoComposto(
                nome=data['nome'],
                descricao=data.get('descricao'),
                tempo_producao=data.get('tempo_producao') or None,
                status='Ativo'
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
                Materiais.codigo.ilike(like),
                ProdutoComposto.nome.ilike(like),
            )
        )

    itens = query.order_by(func.coalesce(Materiais.nome, ProdutoComposto.nome).asc()).limit(200).all()

    results = []
    for item in itens:
        if item.material:
            sigla = item.material.unidade_obj.sigla if (item.material.unidade_obj and hasattr(item.material.unidade_obj, "sigla")) else None
            unidade_txt = f" ({sigla})" if sigla else ""
            codigo_txt = f"{item.material.codigo} - " if item.material.codigo else ""
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
        materiais_query = materiais_query.filter(or_(Materiais.nome.ilike(like), Materiais.codigo.ilike(like)))

    materiais_sem_estoque = materiais_query.order_by(Materiais.nome.asc()).limit(200).all()
    for material in materiais_sem_estoque:
        sigla = material.unidade_obj.nome if (material.unidade_obj and hasattr(material.unidade_obj, "sigla")) else None
        unidade_txt = f" ({sigla})" if sigla else ""
        codigo_txt = f"{material.codigo} - " if material.codigo else ""
        results.append({'id': f"material:{material.id}", 'text_sort': material.nome.lower(), 'text': f"[M] {codigo_txt}{material.nome}{unidade_txt}",'tipo': 'material'})

    results.sort(key=lambda x: x['text_sort'])
    return jsonify({'results': results})

def _sanitizar_nome_aba(nome):
    """
    Sanitiza o nome para ser usado como nome de aba no Excel.
    Remove caracteres inválidos e limita o tamanho.
    """
    # Remover apóstrofos no início e fim
    nome = nome.strip().strip("'").strip('"')
    
    # Remover caracteres inválidos para nomes de abas do Excel: [ ] * ? : / \
    nome = re.sub(r'[\[\]:*?/\\]', '', nome)
    
    # Limitar a 31 caracteres (limite do Excel)
    if len(nome) > 31:
        nome = nome[:28] + '...'
    
    # Se ficou vazio após sanitização, usar nome padrão
    if not nome or nome.strip() == '':
        nome = 'Produto'
    
    return nome

def _expandir_componentes_produto_composto(produto_id, quantidade_base=1.0, caminho_atual=None):
    """
    Função recursiva para expandir todos os componentes de um produto composto
    até chegar apenas em materiais, considerando produtos compostos aninhados.
    Usa caminho_atual para evitar loops infinitos (mesmo produto na mesma cadeia).
    """
    if caminho_atual is None:
        caminho_atual = []
    
    # Evitar loops infinitos - se o produto já está no caminho atual, há um ciclo
    if produto_id in caminho_atual:
        logger.warning(f"Loop detectado no produto composto {produto_id}. Caminho: {caminho_atual}")
        return []
    
    # Adicionar ao caminho atual
    novo_caminho = caminho_atual + [produto_id]
    
    produto = ProdutoComposto.query.get(produto_id)
    if not produto:
        return []
    
    componentes_materiais = []
    
    for componente in produto.componentes:
        if not componente.estoque:
            continue
            
        quantidade_componente = float(componente.quantidade) * quantidade_base
        
        if componente.estoque.tipo_item == 'material' and componente.estoque.material:
            # É um material direto
            componentes_materiais.append({
                'material_id': componente.estoque.material.id,
                'material_nome': componente.estoque.material.nome,
                'quantidade': quantidade_componente,
                'unidade': componente.estoque.material.unidade_obj.sigla if (componente.estoque.material.unidade_obj and hasattr(componente.estoque.material.unidade_obj, 'sigla')) else ''
            })
        elif componente.estoque.tipo_item == 'produto_composto' and componente.estoque.ProdComp_id:
            # É um produto composto aninhado - processar recursivamente
            produto_composto_id = componente.estoque.ProdComp_id
            componentes_aninhados = _expandir_componentes_produto_composto(
                produto_composto_id, 
                quantidade_componente,
                novo_caminho  # Passar o caminho atual para detectar loops
            )
            componentes_materiais.extend(componentes_aninhados)
    
    return componentes_materiais

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
        componentes_materiais_raw = _expandir_componentes_produto_composto(produto.id)
        
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
                
                historico_formatado.append({
                    "quantidade": float(quantidade_final) if quantidade_final is not None else 0.0,
                    "valor_unitario": float(valor_unitario_final) if valor_unitario_final is not None else 0.0,
                    "data_emissao": item.data_emissao.strftime("%Y-%m-%d") if item.data_emissao else None,
                    "numero_nf": item.numero_nf,
                    "nome_emitente": item.nome_emitente,
                    "nota_id": item.nota_id,
                    "fator_conversao_aplicado": fator_aplicado,
                    "unidade_original": unidade_final
                })
            
            historico_por_material[material_id] = historico_formatado
        
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
        historico_custo = []
        precos_anteriores = {}  # material_id -> último preço conhecido
        
        for data in todas_datas:
            custo_total = 0.0
            componentes_data = []
            
            for comp in componentes_materiais:
                material_id = comp['material_id']
                quantidade_necessaria = comp['quantidade']
                
                # Buscar o preço mais recente até esta data
                # O valor_unitario já está calculado considerando o fator de conversão aplicado
                preco_atual = precos_anteriores.get(material_id)
                historico_material = historico_por_material.get(material_id, [])
                
                # Encontrar o preço mais recente até esta data
                # O valor_unitario retornado já está na unidade padrão do material (após aplicar fator de conversão)
                for item in historico_material:
                    if item['data_emissao'] and item['data_emissao'] <= data:
                        # valor_unitario já considera fator_conversao_aplicado se existir
                        preco_atual = item['valor_unitario']
                        precos_anteriores[material_id] = preco_atual
                        break
                
                if preco_atual is not None and preco_atual > 0:
                    # Cálculo do custo: quantidade_necessaria (já na unidade padrão) × preco_unitario (já convertido)
                    custo_componente = quantidade_necessaria * preco_atual
                    custo_total += custo_componente
                    componentes_data.append({
                        'material_nome': comp['material_nome'],
                        'quantidade': quantidade_necessaria,
                        'preco_unitario': preco_atual,  # Já considera fator de conversão
                        'custo_componente': custo_componente,
                        'unidade': comp['unidade']  # Unidade padrão do material
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
        produto_ids = request.form.getlist('produto_ids')
        
        if not produto_ids:
            flash('Nenhum produto selecionado para exportar.', 'warning')
            return redirect(url_for('produto_composto.index'))
        
        # Converter IDs para inteiros
        produto_ids = [int(id) for id in produto_ids if id.isdigit()]
        
        if not produto_ids:
            flash('IDs de produtos inválidos.', 'danger')
            return redirect(url_for('produto_composto.index'))
        
        # Buscar produtos
        produtos = ProdutoComposto.query.filter(ProdutoComposto.id.in_(produto_ids)).all()
        
        if not produtos:
            flash('Nenhum produto encontrado.', 'warning')
            return redirect(url_for('produto_composto.index'))
        
        # Criar arquivo Excel em memória
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for produto in produtos:
                # Preparar dados dos componentes
                dados_componentes = []
                
                for componente in produto.componentes:
                    estoque = componente.estoque
                    if estoque:
                        if estoque.material:
                            nome_item = estoque.material.nome
                            codigo_item = estoque.material.codigo or ''
                            unidade = estoque.material.unidade_obj.sigla if (estoque.material.unidade_obj and hasattr(estoque.material.unidade_obj, 'sigla')) else ''
                            tipo = 'Material'
                        elif estoque.produto_composto:
                            nome_item = estoque.produto_composto.nome
                            codigo_item = ''
                            unidade = ''
                            tipo = 'Produto Composto'
                        else:
                            nome_item = 'Desconhecido'
                            codigo_item = ''
                            unidade = ''
                            tipo = 'Desconhecido'
                        
                        dados_componentes.append({
                            'ID Estoque': estoque.id,
                            'Tipo': tipo,
                            'Nome': nome_item,
                            'Código': codigo_item,
                            'Quantidade': float(componente.quantidade),
                            'Unidade': unidade,
                            'Observação': componente.observacao or ''
                        })
                
                # Ordenar componentes pelo nome do material/produto
                dados_componentes.sort(key=lambda x: x['Nome'].lower() if x['Nome'] else '')
                
                # Criar DataFrame
                if dados_componentes:
                    df = pd.DataFrame(dados_componentes)
                else:
                    # Se não houver componentes, criar DataFrame vazio com colunas
                    df = pd.DataFrame(columns=['ID Estoque', 'Tipo', 'Nome', 'Código', 'Quantidade', 'Unidade', 'Observação'])
                
                # Sanitizar nome da aba (remover caracteres inválidos)
                nome_aba = _sanitizar_nome_aba(produto.nome)
                
                # Escrever na aba
                df.to_excel(writer, sheet_name=nome_aba, index=False)
                
                # Ajustar largura das colunas
                worksheet = writer.sheets[nome_aba]
                worksheet.set_column('A:A', 12)  # ID Estoque
                worksheet.set_column('B:B', 15)  # Tipo
                worksheet.set_column('C:C', 30)  # Nome
                worksheet.set_column('D:D', 15)  # Código
                worksheet.set_column('E:E', 12)  # Quantidade
                worksheet.set_column('F:F', 10)  # Unidade
                worksheet.set_column('G:G', 30)  # Observação
        
        output.seek(0)
        
        # Nome do arquivo com data
        data_export = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'produtos_compostos_{data_export}.xlsx'
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
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
        if 'arquivo_excel' not in request.files:
            return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'}), 400
        
        arquivo = request.files['arquivo_excel']
        
        if arquivo.filename == '':
            return jsonify({'success': False, 'message': 'Nenhum arquivo selecionado'}), 400
        
        if not arquivo.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'message': 'Apenas arquivos Excel (.xlsx ou .xls) são permitidos'}), 400
        
        sobrescrever = request.form.get('sobrescrever') == '1'
        
        # Salvar arquivo temporariamente
        temp_dir = tempfile.gettempdir()
        filename = secure_filename(arquivo.filename)
        temp_path = os.path.join(temp_dir, f'import_produtos_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{filename}')
        arquivo.save(temp_path)
        
        try:
            # Ler todas as abas do Excel
            excel_file = pd.ExcelFile(temp_path)
            
            contador_criados = 0
            contador_atualizados = 0
            contador_erros = 0
            erros_detalhes = []
            
            for nome_aba in excel_file.sheet_names:
                try:
                    # Ler dados da aba
                    df = pd.read_excel(excel_file, sheet_name=nome_aba)
                    
                    # Verificar colunas necessárias
                    colunas_necessarias = ['Nome', 'Quantidade']
                    colunas_opcionais = ['ID Estoque', 'Material/Produto', 'Código', 'Unidade', 'Observação']
                    
                    # Tentar mapear colunas (case-insensitive)
                    colunas_df = [col.lower() for col in df.columns]
                    
                    # Mapear colunas
                    col_nome = None
                    col_quantidade = None
                    col_id_estoque = None
                    col_material_produto = None
                    
                    for col in df.columns:
                        col_lower = col.lower()
                        if 'nome' in col_lower and not col_nome:
                            col_nome = col
                        elif 'quantidade' in col_lower and not col_quantidade:
                            col_quantidade = col
                        elif 'id' in col_lower and 'estoque' in col_lower and not col_id_estoque:
                            col_id_estoque = col
                        elif ('material' in col_lower or 'produto' in col_lower) and not col_material_produto:
                            col_material_produto = col
                    
                    # Se não encontrou coluna de nome, usar o nome da aba
                    nome_produto = nome_aba.strip()
                    if col_nome and not df[col_nome].empty:
                        # Pegar o primeiro nome não vazio
                        nomes_validos = df[col_nome].dropna()
                        if not nomes_validos.empty:
                            nome_produto = str(nomes_validos.iloc[0]).strip()
                    
                    if not nome_produto:
                        erros_detalhes.append(f"Aba '{nome_aba}': Nome do produto não encontrado")
                        contador_erros += 1
                        continue
                    
                    # Buscar ou criar produto
                    produto = ProdutoComposto.query.filter_by(nome=nome_produto).first()
                    
                    if produto and sobrescrever:
                        # Remover componentes existentes
                        for componente in produto.componentes:
                            db.session.delete(componente)
                        db.session.flush()
                    elif not produto:
                        # Criar novo produto
                        produto = ProdutoComposto(
                            nome=nome_produto,
                            status='Ativo'
                        )
                        db.session.add(produto)
                        db.session.flush()
                        
                        # Criar estoque para o produto
                        estoque_produto = Estoque(
                            produto_composto=produto,
                            quantidade=0,
                            tipo_item='produto_composto',
                            localizacao='Estoque Matriz',
                        )
                        db.session.add(estoque_produto)
                        db.session.flush()
                        contador_criados += 1
                    else:
                        contador_atualizados += 1
                    
                    # Processar componentes
                    if col_quantidade:
                        for index, row in df.iterrows():
                            try:
                                quantidade = float(row[col_quantidade]) if pd.notna(row[col_quantidade]) else None
                                
                                if quantidade is None or quantidade <= 0:
                                    continue
                                
                                estoque_id = None
                                
                                # Tentar obter estoque_id
                                if col_id_estoque and col_id_estoque in df.columns:
                                    estoque_id_val = row[col_id_estoque]
                                    if pd.notna(estoque_id_val):
                                        try:
                                            estoque_id = int(estoque_id_val)
                                        except:
                                            pass
                                
                                # Se não tem estoque_id, tentar buscar por nome
                                if not estoque_id and col_material_produto and col_material_produto in df.columns:
                                    nome_item = str(row[col_material_produto]).strip() if pd.notna(row[col_material_produto]) else None
                                    
                                    if nome_item:
                                        # Buscar por material
                                        material = Materiais.query.filter_by(nome=nome_item).first()
                                        if material:
                                            estoque = Estoque.query.filter_by(material_id=material.id, tipo_item='material').first()
                                            if estoque:
                                                estoque_id = estoque.id
                                        
                                        # Se não encontrou, buscar por produto composto
                                        if not estoque_id:
                                            produto_comp = ProdutoComposto.query.filter_by(nome=nome_item).first()
                                            if produto_comp:
                                                estoque = Estoque.query.filter_by(ProdComp_id=produto_comp.id, tipo_item='produto_composto').first()
                                                if estoque:
                                                    estoque_id = estoque.id
                                
                                if not estoque_id:
                                    erros_detalhes.append(f"Aba '{nome_aba}', linha {index+2}: Não foi possível identificar o estoque/material")
                                    continue
                                
                                estoque = Estoque.query.get(estoque_id)
                                if not estoque:
                                    erros_detalhes.append(f"Aba '{nome_aba}', linha {index+2}: Estoque ID {estoque_id} não encontrado")
                                    continue
                                
                                # Adicionar componente
                                observacao = None
                                if 'Observação' in df.columns or 'observacao' in df.columns:
                                    col_obs = 'Observação' if 'Observação' in df.columns else 'observacao'
                                    if pd.notna(row[col_obs]):
                                        observacao = str(row[col_obs]).strip()
                                
                                produto.adicionar_item(estoque, quantidade)
                                
                                if observacao:
                                    # Atualizar observação do componente
                                    componente = ProdutoCompostoItem.query.filter_by(
                                        produto_id=produto.id,
                                        estoque_id=estoque_id
                                    ).first()
                                    if componente:
                                        componente.observacao = observacao
                                
                            except Exception as e:
                                erros_detalhes.append(f"Aba '{nome_aba}', linha {index+2}: {str(e)}")
                                contador_erros += 1
                                continue
                    
                    db.session.commit()
                    
                except Exception as e:
                    logger.error(f"Erro ao processar aba '{nome_aba}': {str(e)}", exc_info=True)
                    erros_detalhes.append(f"Aba '{nome_aba}': {str(e)}")
                    contador_erros += 1
                    db.session.rollback()
                    continue
            
            return jsonify({
                'success': True,
                'criados': contador_criados,
                'atualizados': contador_atualizados,
                'erros': contador_erros,
                'erros_detalhes': erros_detalhes[:10]  # Limitar a 10 erros
            })
            
        finally:
            # Remover arquivo temporário
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
        
    except Exception as e:
        logger.error(f"Erro ao importar produtos compostos: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erro ao importar: {str(e)}'
        }), 500
