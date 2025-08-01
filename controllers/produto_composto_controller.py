from datetime import datetime
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, flash, Response, send_file
from io import BytesIO
from werkzeug.exceptions import abort
from models import db, ProdutoComposto, Estoque, Material, ProdutoCompostoItem
from flask_login import login_required, current_user
import logging
import base64
from PIL import Image
import io

logger = logging.getLogger(__name__)

produto_composto_bp = Blueprint('produto_composto', __name__, url_prefix='/produto-composto')

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

@produto_composto_bp.route('/get_componentes/<int:id>')
@login_required
def get_componentes(id):
    """
    Retorna os componentes de um produto composto a partir do ID
    """
    produto = ProdutoComposto.query.get_or_404(id)  
    componentes = []
    for componente in produto.componentes:
        componentes.append({
            'estoque_id': componente.estoque_id,
            'quantidade': componente.quantidade,
            'nome': componente.estoque.material.nome if componente.estoque.material_id else componente.estoque.produto_composto.nome
        })
    return jsonify({
        'componentes': componentes
    })

@produto_composto_bp.route('/get_produto_composto/<int:id>')
@login_required
def get_produto_composto(id):
    """
    Retorna um produto composto a partir do ID
    """
    produtos = []
    if id == 0 or not id:
        produto = ProdutoComposto.query.all()
       
        for p in produto:
            produtos.append({
                'id': p.id,
                'nome': p.nome,
                'tempo_producao': float(p.tempo_producao) if p.tempo_producao else None,
                'componentes': len(p.componentes),
                'status': p.status
            })
    else:
        produto = ProdutoComposto.query.get_or_404(id)
        componentes = []
        for p in produto.componentes:
            componentes.append({
                'estoque_id': p.estoque_id,
                'quantidade': p.quantidade,
                'nome': '[M] '+p.estoque.material.nome if p.estoque.material_id else '[P] '+p.estoque.produto_composto.nome
            })
        produtos.append({
            'id': produto.id,
            'nome': produto.nome,
            'tempo_producao': float(produto.tempo_producao) if produto.tempo_producao else None,
            'componentes': componentes,
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
    itens_estoque = Estoque.query.join(Material).order_by(Material.nome).all()
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
                estoque = Estoque.query.get_or_404(item['estoque_id'])
                
                # Log para debug dos valores de quantidade
                logger.info(f"Adicionando componente - Estoque ID: {item['estoque_id']}, Quantidade: {item['quantidade']} (tipo: {type(item['quantidade'])})")
                
                produto.adicionar_item(
                    estoque=estoque,
                    quantidade=item['quantidade']
                )
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

            # Adicionar componentes
            componentes_data = data.get('componentes', [])
            for item in componentes_data:
                estoque = Estoque.query.get_or_404(item['estoque_id'])
                
                    
                # Log para debug dos valores de quantidade
                logger.info(f"Criando componente - Estoque ID: {item['estoque_id']}, Quantidade: {item['quantidade']} (tipo: {type(item['quantidade'])})")
                
                produto.adicionar_item(
                    estoque=estoque,
                    quantidade=item['quantidade']
                )
        estoque = Estoque.query.filter(Estoque.ProdComp_id == produto.id).first()
        if not estoque:
            estoque = Estoque(produto_composto=produto,
                              quantidade=0,
                              tipo_item='produto_composto')
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
        
        # Duplicar todos os componentes
        for componente in produto_original.componentes:
            novo_componente = ProdutoCompostoItem(
                produto_id=novo_produto.id,
                estoque_id=componente.estoque_id,
                quantidade=componente.quantidade,
                observacao=componente.observacao
            )
            db.session.add(novo_componente)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Produto composto duplicado com sucesso!'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao duplicar produto composto: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro ao duplicar produto composto: {str(e)}'}), 500

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
