from flask import Blueprint, request, jsonify, send_file
from models.database import db
from models.tanque import TanquesPecas, Tanques 
import pandas as pd
import io
import os
import tempfile
from datetime import datetime
from models.solicitacao import Solicitacoes, SolicitacoesItens
from models.unidade import Unidades
from models.centro_custo import CentroCusto
from models.material import Materiais

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Registrar APIs por modelo (centralizadas em controllers/api/*)
try:
    from controllers.api.nota_fiscal_api import register_api as register_nota_fiscal_api  # noqa: E402
    register_nota_fiscal_api(api_bp)
except Exception:
    # Evitar quebrar import do app caso dependências opcionais não estejam instaladas
    pass

try:
    from controllers.api.material_api import register as register_material_api  # noqa: E402
    # material_api.register espera um blueprint; aqui registramos as rotas sob /api/materiais/...
    register_material_api(api_bp)
except Exception:
    pass

@api_bp.route('/tanques/<int:tanque_id>/proximo-sequencial', methods=['GET'])
def proximo_sequencial(tanque_id):
    """Retorna o próximo número sequencial para uma peça em um tanque"""
    try:
        # Verifica se o tanque existe
        tanque = Tanques.query.get_or_404(tanque_id)
        
        # Busca o maior número sequencial para o tanque
        maior_sequencial = db.session.query(db.func.max(TanquesPecas.numero_sequencial))\
            .filter(TanquesPecas.tanque_id == tanque_id).scalar() or 0
            
        # Retorna o próximo número sequencial
        return jsonify({
            'success': True,
            'proximo_sequencial': maior_sequencial + 1
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@api_bp.route('/tanques/<int:tanque_id>/pecas/adicionar', methods=['POST'])
def adicionar_peca(tanque_id):
    """Adiciona uma nova peça a um tanque"""
    try:
        # Verifica se o tanque existe
        tanque = Tanques.query.get_or_404(tanque_id)
        
        # Obtém os dados do formulário
        tipo = request.form.get('tipo')
        nome = request.form.get('nome')
        quantidade = int(request.form.get('quantidade', 1))
        numero_sequencial = int(request.form.get('numero_sequencial', 1))
        numero_tanque = request.form.get('numero_tanque')
        
        # Converter numero_tanque para inteiro se não estiver vazio
        if numero_tanque and numero_tanque.strip():
            try:
                numero_tanque = int(numero_tanque)
            except ValueError:
                numero_tanque = None
        else:
            numero_tanque = None
        
        # Validação básica
        if not tipo or not nome:
            return jsonify({
                'success': False,
                'message': 'Todos os campos são obrigatórios'
            }), 400
            
        if quantidade < 1:
            return jsonify({
                'success': False,
                'message': 'A quantidade deve ser maior ou igual a 1'
            }), 400
        if TanquesPecas.query.filter_by(nome=nome, tanque_id=tanque_id).count() > 0:
            return jsonify({
                'success': False,
                'message': 'Já existe uma peça com este nome no tanque'
            }), 400
        # Criar as peças
        pecas_criadas = 0
        for i in range(quantidade):
            # Criar nova peça
            peca = TanquesPecas(
                tipo=tipo,
                nome=f"{nome}{' #' + str(i+1) if quantidade > 1 else ''}",
                tanque_id=tanque_id,
                numero_sequencial=numero_sequencial + i,
                numero_tanque=numero_tanque
            )
            
            # Salvar no banco de dados
            peca.save()
            pecas_criadas += 1
            
        return jsonify({
            'success': True,
            'message': f'{pecas_criadas} peça(s) adicionada(s) com sucesso!',
            'total': pecas_criadas
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@api_bp.route('/tanques/<int:tanque_id>/pecas/importar', methods=['POST'])
def importar_pecas(tanque_id):
    """Importa peças de um arquivo Excel para um tanque"""
    try:
        # Verifica se o tanque existe
        tanque = Tanques.query.get_or_404(tanque_id)
        
        # Verifica se um arquivo foi enviado
        if 'arquivo' not in request.files:
            return jsonify({
                'success': False,
                'message': 'Nenhum arquivo enviado'
            }), 400
            
        arquivo = request.files['arquivo']
        if arquivo.filename == '':
            return jsonify({
                'success': False,
                'message': 'Nenhum arquivo selecionado'
            }), 400
            
        # Verifica a extensão do arquivo
        if not arquivo.filename.endswith(('.xlsx', '.xls')):
            return jsonify({
                'success': False,
                'message': 'Formato de arquivo inválido. Use .xlsx ou .xls'
            }), 400
            
        # Lê o arquivo Excel
        try:
            df = pd.read_excel(arquivo)
            
            # Valida as colunas obrigatórias
            colunas_obrigatorias = ['TIPO', 'NOME']
            for coluna in colunas_obrigatorias:
                if coluna not in df.columns:
                    return jsonify({
                        'success': False,
                        'message': f'A coluna {coluna} é obrigatória'
                    }), 400
            
            # Obtém o próximo número sequencial
            maior_sequencial = db.session.query(db.func.max(TanquesPecas.numero_sequencial))\
                .filter(TanquesPecas.tanque_id == tanque_id).scalar() or 0
            proximo_sequencial = maior_sequencial + 1
            
            # Processa os dados do Excel
            pecas_criadas = 0
            for index, row in df.iterrows():
                tipo = str(row['TIPO']).strip()
                nome = str(row['NOME']).strip()
                
                # Processa o número do tanque
                numero_tanque = None
                if 'NUMERO_TANQUE' in df.columns and not pd.isna(row['NUMERO_TANQUE']):
                    numero_tanque_valor = str(row['NUMERO_TANQUE']).strip()
                    if numero_tanque_valor:
                        try:
                            numero_tanque = int(numero_tanque_valor)
                        except ValueError:
                            # Se não for possível converter para inteiro, deixa como None
                            pass
                
                # Verifica se é para criar múltiplas peças
                if 'QUANTIDADE' in df.columns and not pd.isna(row['QUANTIDADE']):
                    quantidade = int(row['QUANTIDADE'])
                else:
                    quantidade = 1
                    
                if quantidade < 1:
                    quantidade = 1
                
                # Cria as peças
                for i in range(quantidade):
                    # Nome da peça com sufixo se necessário
                    nome_peca = f"{nome}{' #' + str(i+1) if quantidade > 1 else ''}"
                    
                    # Cria a peça
                    peca = TanquesPecas(
                        tipo=tipo,
                        nome=nome_peca,
                        tanque_id=tanque_id,
                        numero_sequencial=proximo_sequencial,
                        numero_tanque=numero_tanque
                    )
                    proximo_sequencial += 1
                    
                    # Salva no banco de dados
                    peca.save()
                    pecas_criadas += 1
            
            return jsonify({
                'success': True,
                'message': f'{pecas_criadas} peça(s) importada(s) com sucesso!',
                'total': pecas_criadas
            })
                
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Erro ao processar o arquivo: {str(e)}'
            }), 500
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@api_bp.route('/pecas/modelo-planilha', methods=['GET'])
def modelo_planilha():
    """Gera um modelo de planilha para importação de peças"""
    try:
        # Cria um DataFrame com as colunas necessárias
        df = pd.DataFrame(columns=['TIPO', 'NOME', 'QUANTIDADE', 'NUMERO_TANQUE'])
        
        # Adiciona alguns exemplos
        df.loc[0] = ['VIGA', 'V1', 1, 1]
        df.loc[1] = ['PILAR', 'P1', 4, 2]
        df.loc[2] = ['PLACA', 'PL01', 10, None]
        
        # Cria o arquivo Excel na memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Peças', index=False)
            
            # Ajusta a largura das colunas
            worksheet = writer.sheets['Peças']
            worksheet.set_column('A:A', 15)  # TIPO
            worksheet.set_column('B:B', 20)  # NOME
            worksheet.set_column('C:C', 15)  # QUANTIDADE
            worksheet.set_column('D:D', 15)  # NUMERO_TANQUE
        
        output.seek(0)
        
        # Gera o nome do arquivo com a data atual
        hoje = datetime.now().strftime('%Y%m%d')
        
        # Retorna o arquivo para download
        return send_file(
            output,
            download_name=f'modelo_pecas_{hoje}.xlsx',
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@api_bp.route('/tanques/<int:tanque_id>/pecas/adicionar-lote', methods=['POST'])
def adicionar_lote_pecas(tanque_id):
    """Adiciona um lote de peças a um tanque"""
    try:
        # Verifica se o tanque existe
        tanque = Tanques.query.get_or_404(tanque_id)
        
        # Obtém os dados do JSON
        dados = request.json
        if not dados or 'pecas' not in dados or not isinstance(dados['pecas'], list):
            return jsonify({
                'success': False,
                'error': 'Formato de dados inválido. É necessário fornecer uma lista de peças.'
            }), 400
            
        pecas_lista = dados['pecas']
        
        # Obtém o próximo número sequencial
        maior_sequencial = db.session.query(db.func.max(TanquesPecas.numero_sequencial))\
            .filter(TanquesPecas.tanque_id == tanque_id).scalar() or 0
        proximo_sequencial = maior_sequencial + 1
        
        # Processa as peças
        pecas_criadas = 0
        for peca_dados in pecas_lista:
            tipo = peca_dados.get('tipo')
            nome = peca_dados.get('nome')
            quantidade = int(peca_dados.get('quantidade', 1))
            numero_tanque = peca_dados.get('numero_tanque')
            
            # Validação básica
            if not tipo or not nome:
                continue
                
            if quantidade < 1:
                quantidade = 1
                
            # Criar as peças
            for i in range(quantidade):
                # Nome da peça com sufixo se necessário
                nome_peca = f"{nome}{' #' + str(i+1) if quantidade > 1 else ''}"
                
                # Cria a peça
                peca = TanquesPecas(
                    tipo=tipo,
                    nome=nome_peca,
                    tanque_id=tanque_id,
                    numero_sequencial=proximo_sequencial,
                    numero_tanque=numero_tanque
                )
                proximo_sequencial += 1
                
                # Salva no banco de dados
                peca.save()
                pecas_criadas += 1
        
        return jsonify({
            'success': True,
            'message': f'{pecas_criadas} peça(s) adicionada(s) com sucesso!',
            'total': pecas_criadas
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api_bp.route('/tanques/grupo/<int:grupo_id>', methods=['GET'])
def obter_tanques_grupo(grupo_id):
    """Retorna os tanques de um grupo"""
    try:
        tanques = Tanques.query.filter_by(grupo_id=grupo_id).all()
        return jsonify({
            'success': True,
            'tanques': [tanque.to_dict() for tanque in tanques]
        })   
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api_bp.route('/tanques/<int:tanque_id>', methods=['GET'])
def obter_tanque(tanque_id):
    """Retorna os detalhes de um tanque"""
    try:
        # Verifica se o tanque existe
        tanque = Tanques.query.get_or_404(tanque_id)
        
        # Retorna os dados do tanque
        return jsonify({
            'success': True,
            'tanque': {
                'id': tanque.id,
                'nome': tanque.nome,
                'un': tanque.un,
                'sistema': tanque.sistema,
                'dimensoes': tanque.dimensoes,
                'altura_total': tanque.altura_total,
                'altura_util': tanque.altura_util,
                'quantidade': tanque.quantidade,
                'cobertura': tanque.cobertura,
                'quantidade_bainhas': tanque.quantidade_bainhas or 0,
                'placas_normais': tanque.placas_normais,
                'placas_fecho': tanque.placas_fecho,
                'item_nf': tanque.item_nf,
                'contrato_id': tanque.contrato_id,
                'area_base': tanque.area_base,
                'volume_util': tanque.volume_util,
                'volume_total': tanque.volume_total,
                'data_cadastro': tanque.data_cadastro.strftime('%d/%m/%Y %H:%M') if tanque.data_cadastro else None,
                'ultima_atualizacao': tanque.ultima_atualizacao.strftime('%d/%m/%Y %H:%M') if tanque.ultima_atualizacao else None
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 
@api_bp.route('/solicitacoes/<int:solicitacao_id>/itens', methods=['GET'])
def listar_itens(solicitacao_id):
    """Retorna todos os itens de uma solicitação"""
    try:
        # Verifica se a solicitação existe
        solicitacao = Solicitacoes.query.get_or_404(solicitacao_id)
        unidades = Unidades.query.all()
        centros_custo = CentroCusto.query.all()
        materiais = Materiais.query.all()
        itensSolicitacao = SolicitacoesItens.query.filter_by(solicitacao_id=solicitacao_id).all()
        
        # Retorna os itens da solicitação
        return jsonify({
            'success': True,
            'solicitacao': solicitacao.to_dict(),
            'itens': [item.to_dict() for item in itensSolicitacao],  
            'unidades': [unidade.to_dict() for unidade in unidades],
            'centros_custo': [centro.to_dict() for centro in centros_custo],
            'materiais': [material.to_dict() for material in materiais]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
