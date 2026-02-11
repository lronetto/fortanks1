import logging
import os
import tempfile
from datetime import datetime
from decimal import Decimal

import pandas as pd
from flask import Blueprint, current_app, flash, jsonify, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_, text
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from models.database import db
from models.estoque import Estoque
from models.estoque_terceiro import EstoqueTerceiro
from models.material import Materiais
from models.unidade import get_conversao_unidade, normalizar_unidade, comparar_unidades
from models.tanque import TanquesPecas, TanquesProdutoComposto, Tanques
from models.produto_composto import ProdutoComposto

logger = logging.getLogger(__name__)

# Criar blueprint
estoque_terceiro_bp = Blueprint('estoque_terceiro', __name__, url_prefix='/estoque-terceiro')


@estoque_terceiro_bp.route('/')
@login_required
def index():
    """
    Página principal com tabela comparativa de estoques
    """
    return render_template('estoque_terceiro/index.html')


@estoque_terceiro_bp.route('/importar', methods=['POST'])
@login_required
def importar():
    """
    Importa planilha de estoque de terceiros
    """
    try:
        logger.info(f'Iniciando importação de estoque terceiro. Form keys: {list(request.form.keys())}, Files keys: {list(request.files.keys())}')
        
        # Verificar arquivo
        if 'arquivo' not in request.files:
            logger.warning('Nenhum arquivo enviado na requisição')
            return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'}), 400
        
        arquivo = request.files['arquivo']
        if arquivo.filename == '':
            logger.warning('Arquivo vazio na requisição')
            return jsonify({'success': False, 'message': 'Nenhum arquivo selecionado'}), 400
        
        logger.info(f'Arquivo recebido: {arquivo.filename}')
        
        # Verificar extensão
        if not arquivo.filename.endswith(('.xlsx', '.xls')):
            logger.warning(f'Extensão inválida: {arquivo.filename}')
            return jsonify({'success': False, 'message': 'Apenas arquivos Excel (.xlsx ou .xls) são permitidos'}), 400
        
        # Obter data
        data_str = request.form.get('data')
        logger.info(f'Data recebida: {data_str}')
        if not data_str:
            logger.warning('Data não fornecida na requisição')
            return jsonify({'success': False, 'message': 'Data é obrigatória'}), 400
        
        try:
            data_importacao = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': 'Formato de data inválido. Use YYYY-MM-DD'}), 400
        
        # Salvar arquivo temporariamente
        temp_dir = tempfile.gettempdir()
        filename = secure_filename(arquivo.filename)
        temp_path = os.path.join(temp_dir, f'estoque_terceiro_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{filename}')
        arquivo.save(temp_path)
        
        try:
            # Ler planilha - tentar primeiro com cabeçalhos
            logger.info(f'Lendo planilha: {temp_path}')
            df = pd.read_excel(temp_path)
            logger.info(f'Planilha lida com sucesso. Colunas encontradas: {list(df.columns)}')
            
            # Verificar se a planilha tem cabeçalhos nomeados ou apenas "Unnamed"
            tem_cabecalhos = not all(str(col).startswith('Unnamed') for col in df.columns)
            
            # Se não tem cabeçalhos, ler novamente sem header e usar posições fixas
            if not tem_cabecalhos:
                logger.info('Planilha sem cabeçalhos detectada. Lendo novamente sem header.')
                df = pd.read_excel(temp_path, header=None)
                logger.info(f'Planilha relida sem cabeçalhos. Total de colunas: {len(df.columns)}')
                
                # Verificar se tem pelo menos 7 colunas
                if len(df.columns) < 7:
                    return jsonify({
                        'success': False,
                        'message': f'A planilha deve ter pelo menos 7 colunas. Encontradas: {len(df.columns)}'
                    }), 400
                
                # Mapear por posição (índice): 0=codigo alterdata, 1=tipo item, 2=nome, 3=unidade, 4=quantidade, 5=valor unitario, 6=valor total
                mapeamento = {
                    'codigo alterdata': 0,
                    'tipo item': 1,
                    'nome': 2,
                    'unidade': 3,
                    'quantidade': 4,
                    'valor unitario': 5,
                    'valor total': 6
                }
                logger.info(f'Mapeamento por posição: {mapeamento}')
            else:
                # Verificar colunas esperadas
                colunas_esperadas = ['codigo alterdata', 'tipo item', 'nome', 'unidade', 'quantidade', 'valor unitario', 'valor total']
                colunas_arquivo = [str(col).lower().strip() for col in df.columns]
                logger.info(f'Colunas normalizadas: {colunas_arquivo}')
                
                # Mapear colunas (case-insensitive)
                mapeamento = {}
                for col_esperada in colunas_esperadas:
                    for idx, col_arquivo in enumerate(colunas_arquivo):
                        if col_esperada in col_arquivo or col_arquivo in col_esperada:
                            mapeamento[col_esperada] = df.columns[idx]
                            logger.info(f'Mapeado: {col_esperada} -> {df.columns[idx]}')
                            break
                
                logger.info(f'Mapeamento completo: {mapeamento}')
                
                # Verificar se todas as colunas foram encontradas
                colunas_faltantes = [col for col in colunas_esperadas if col not in mapeamento]
                if colunas_faltantes:
                    logger.warning(f'Colunas faltantes: {colunas_faltantes}')
                    return jsonify({
                        'success': False,
                        'message': f'Colunas não encontradas na planilha: {", ".join(colunas_faltantes)}. Colunas encontradas: {", ".join([str(c) for c in df.columns.tolist()])}'
                    }), 400
            
            # Processar linhas
            registros_criados = 0
            registros_atualizados = 0
            erros = []
            cods = EstoqueTerceiro.query.filter_by(data=data_importacao).all()
            cods_existentes = [cod.codigo_erp for cod in cods]
            itens = []
            for idx, row in df.iterrows():
                try:
                    # Se mapeamento é por índice (int), usar diretamente; se é por nome de coluna, usar o nome
                    if isinstance(mapeamento.get('codigo alterdata'), int):
                        codigo_erp = str(row.iloc[mapeamento['codigo alterdata']]).strip()
                    else:
                        codigo_erp = str(row[mapeamento['codigo alterdata']]).strip()
                    
                    if pd.isna(codigo_erp) or codigo_erp == '' or codigo_erp == 'nan':
                        continue
                    
                    # Obter valores usando índice ou nome da coluna
                    if isinstance(mapeamento.get('tipo item'), int):
                        tipo_val = row.iloc[mapeamento['tipo item']]
                        unidade_val = row.iloc[mapeamento['unidade']]
                        quantidade_val = row.iloc[mapeamento['quantidade']]
                        valor_unitario_val = row.iloc[mapeamento['valor unitario']]
                        valor_total_val = row.iloc[mapeamento['valor total']]
                    else:
                        tipo_val = row[mapeamento['tipo item']]
                        unidade_val = row[mapeamento['unidade']]
                        quantidade_val = row[mapeamento['quantidade']]
                        valor_unitario_val = row[mapeamento['valor unitario']]
                        valor_total_val = row[mapeamento['valor total']]
                    
                    tipo = str(tipo_val).strip() if pd.notna(tipo_val) else None
                    unidade = str(unidade_val).strip() if pd.notna(unidade_val) else None
                    
                    quantidade = Decimal(str(quantidade_val)) if pd.notna(quantidade_val) else Decimal('0')
                    valor_unitario = Decimal(str(valor_unitario_val)) if pd.notna(valor_unitario_val) else None
                    valor_total = Decimal(str(valor_total_val)) if pd.notna(valor_total_val) else None
                    
                    # Verificar se já existe registro para esta data e código_erp
                   
                    
                    if codigo_erp not in cods_existentes:
                        # Criar novo registro
                        item = EstoqueTerceiro(
                            data=data_importacao,
                            codigo_erp=codigo_erp,
                            tipo=tipo,
                            unidade=unidade,
                            quantidade=quantidade,
                            ValorUnitario=valor_unitario,
                            ValorTotal=valor_total,
                            usuario_id=current_user.id
                        )
                        itens.append(item)
                        registros_criados += 1
                
                    
                except Exception as e:
                    erros.append(f'Linha {idx + 2}: {str(e)}')
                    logger.error(f'Erro ao processar linha {idx + 2}: {str(e)}')
                    continue
            
            db.session.add_all(itens)
            db.session.commit()
            
            mensagem = f'Importação concluída: {registros_criados} registros criados, {registros_atualizados} atualizados'
            if erros:
                mensagem += f'. {len(erros)} erros encontrados.'
            
            return jsonify({
                'success': True,
                'message': mensagem,
                'criados': registros_criados,
                'atualizados': registros_atualizados,
                'erros': len(erros)
            }), 200
            
        finally:
            # Remover arquivo temporário
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f'Erro ao importar estoque terceiro: {str(e)}', exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao importar: {str(e)}'}), 500


@estoque_terceiro_bp.route('/api/comparativo', methods=['GET'])
@login_required
def api_comparativo():
    """
    API para DataTables com dados comparativos entre estoque do sistema e estoque de terceiros
    """
    try:
        # Parâmetros do DataTables
        draw = int(request.args.get('draw', 1))
        start = int(request.args.get('start', 0))
        length = int(request.args.get('length', 25))
        search_value = request.args.get('search[value]', '').strip()
        
        # Parâmetros de ordenação
        order_column_index = int(request.args.get('order[0][column]', 1))
        order_dir = request.args.get('order[0][dir]', 'asc')
        
        # Filtro de data (opcional)
        data_filtro = request.args.get('data_filtro', '')
        data_filtro_date = None
        if data_filtro:
            try:
                data_filtro_date = datetime.strptime(data_filtro, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Query base: buscar materiais que têm codigo_erp e estoque terceiro
        # Usar cast para resolver conflito de collation entre tabelas
        query = db.session.query(
            Materiais.id.label('material_id'),
            Materiais.nome.label('material_nome'),
            Materiais.codigo_erp,
            EstoqueTerceiro.quantidade.label('estoque_terceiro'),
            EstoqueTerceiro.tipo.label('tipo'),
            EstoqueTerceiro.unidade.label('unidade'),
            EstoqueTerceiro.ValorUnitario.label('valor_unitario'),
            EstoqueTerceiro.ValorTotal.label('valor_total'),
            EstoqueTerceiro.data.label('data_estoque_terceiro')
        ).outerjoin(
            EstoqueTerceiro, 
            text("Materiais.codigo_erp COLLATE utf8mb4_unicode_ci = EstoqueTerceiro.codigo_erp COLLATE utf8mb4_unicode_ci")
        ).filter(
            Materiais.codigo_erp.isnot(None),
            Materiais.codigo_erp != '',
            EstoqueTerceiro.tipo == '10.0'
        )
        
        # Aplicar filtro de data se fornecido
        if data_filtro_date:
            query = query.filter(EstoqueTerceiro.data == data_filtro_date)
        
        # Aplicar busca
        if search_value:
            query = query.filter(
                or_(
                    Materiais.nome.ilike(f'%{search_value}%'),
                    Materiais.codigo_erp.ilike(f'%{search_value}%'),
                    EstoqueTerceiro.tipo.ilike(f'%{search_value}%')
                )
            )
        
        # Contar total de registros antes da paginação e ordenação
        total_records = query.count()
        
        # Preparar dados para resposta ANTES da ordenação (precisa calcular diferenças primeiro)
        # Calcular estoque do sistema baseado em movimentações para cada registro
        registros_temp = query.all()
        data_temp = []
        for registro in registros_temp:
            # Buscar o material completo para obter a unidade do sistema
            material = Materiais.query.get(registro.material_id)
            unidade_sistema = None
            if material and material.unidade_obj:
                unidade_sistema = material.unidade_obj.nome
            
            unidade_terceiro = registro.unidade or ''
            
            # Calcular estoque do sistema usando get_saldo_ate_data
            # Buscar todos os estoques do material (pode haver múltiplos por localização)
            estoques_material = Estoque.query.filter_by(material_id=registro.material_id).all()
            
            # Calcular saldo total somando todos os estoques do material
            estoque_sistema_total = Decimal('0.0')
            
            # Determinar data de referência para cálculo do saldo
            data_referencia = None
            if registro.data_estoque_terceiro:
                # Usar a data do estoque terceiro como referência
                data_referencia = datetime.combine(registro.data_estoque_terceiro, datetime.max.time())
            elif data_filtro_date:
                # Se não houver data no registro mas houver filtro, usar o filtro
                data_referencia = datetime.combine(data_filtro_date, datetime.max.time())
            
            # Somar saldos de todos os estoques do material
            for estoque in estoques_material:
                saldo_estoque = estoque.get_saldo_ate_data(data_referencia)
                estoque_sistema_total += saldo_estoque
            
            estoque_sistema_float = float(estoque_sistema_total) if estoque_sistema_total else 0
            estoque_terceiro_original = float(registro.estoque_terceiro) if registro.estoque_terceiro else 0
            
            # Verificar se precisa converter unidades
            fator_conversao = 1.0
            unidade_convertida = False
            fator_conversao = get_conversao_unidade(
                material_id=None,
                unidade_entrada=unidade_terceiro,
                unidade_saida=unidade_sistema
            )
            if fator_conversao:
                fator_conversao = float(fator_conversao)
                unidade_convertida = True
                logger.info(f'Conversão aplicada: Material {registro.material_id}, {unidade_terceiro} -> {unidade_sistema}, fator: {fator_conversao}')
            else:
                logger.warning(f'Não foi possível converter unidades: Material {registro.material_id}, Sistema: {unidade_sistema}, Terceiro: {unidade_terceiro}')
                fator_conversao = 1.0
                unidade_convertida = False
            # Converter estoque terceiro para unidade do sistema se necessário
            estoque_terceiro_convertido = estoque_terceiro_original * fator_conversao
            
            # Calcular diferença usando valores convertidos
            diferenca = estoque_terceiro_convertido - estoque_sistema_float
            
            # Calcular diferença percentual
            if estoque_sistema_float != 0:
                diferenca_percentual = (diferenca / estoque_sistema_float) * 100
            elif estoque_terceiro_convertido != 0:
                diferenca_percentual = 100  # Terceiro tem estoque mas sistema não
            else:
                diferenca_percentual = 0
            
            # Calcular consumo futuro para este material
            consumo_futuro_material = 0.0
            if data_filtro_date:
                try:
                    # Buscar peças não produzidas agrupadas por produto composto
                    pecas_consumo = db.session.query(
                        TanquesPecas,
                        TanquesProdutoComposto
                    ).join(
                        TanquesProdutoComposto,
                        db.and_(
                            TanquesPecas.tanque_id == TanquesProdutoComposto.tanque_id,
                            TanquesPecas.tipo == TanquesProdutoComposto.tipo_peca
                        )
                    ).filter(
                        TanquesPecas.data_concretagem.is_(None),
                        func.date(TanquesPecas.data_cadastro) >= data_filtro_date
                    ).all()
                    
                    # Agrupar peças por produto composto
                    pecas_por_produto = {}
                    for peca_cons, vinculacao_cons in pecas_consumo:
                        produto_id = vinculacao_cons.produto_composto_id
                        if produto_id not in pecas_por_produto:
                            pecas_por_produto[produto_id] = []
                        pecas_por_produto[produto_id].append(peca_cons)
                    
                    # Calcular consumo usando o método produzir do produto composto
                    for produto_id, pecas_list in pecas_por_produto.items():
                        produto_composto_cons = ProdutoComposto.query.get(produto_id)
                        if not produto_composto_cons:
                            continue
                        
                        quantidade_pecas = len(pecas_list)
                        
                        # Calcular materiais necessários usando o método produzir
                        materiais_necessarios = {}
                        produtos_processados = set()
                        
                        try:
                            produto_composto_cons.produzir(
                                quantidade=quantidade_pecas,
                                data_movimento=datetime.now().date(),
                                usuario_id=current_user.id if current_user else 1,
                                log=False,
                                produtos_processados=produtos_processados,
                                materiais_necessarios=materiais_necessarios
                            )
                            
                            # Buscar consumo deste material específico
                            for estoque_id, info in materiais_necessarios.items():
                                estoque = info['estoque']
                                if (estoque and 
                                    estoque.material_id == registro.material_id and
                                    estoque.tipo_item == 'material'):
                                    consumo_futuro_material += float(info['quantidade']) or 0
                        except Exception as e:
                            logger.warning(f'Erro ao calcular consumo para produto composto {produto_id}: {str(e)}')
                            continue
                except Exception as e:
                    logger.warning(f'Erro ao calcular consumo futuro para material {registro.material_id}: {str(e)}')
            
            # Calcular estoque futuro (estoque atual - consumo futuro)
            estoque_futuro = estoque_sistema_float - consumo_futuro_material
            
            # Calcular diferença futura (estoque terceiro - estoque futuro)
            diferenca_futura = estoque_terceiro_convertido - estoque_futuro
            
            data_temp.append({
                'material_id': registro.material_id,
                'material_nome': registro.material_nome or '',
                'codigo_erp': registro.codigo_erp or '',
                'estoque_sistema': estoque_sistema_float,
                'estoque_terceiro': estoque_terceiro_convertido,  # Valor convertido para unidade do sistema
                'estoque_terceiro_original': estoque_terceiro_original,  # Valor original do terceiro
                'diferenca': diferenca,
                'diferenca_percentual': round(diferenca_percentual, 2),
                'consumo_futuro': consumo_futuro_material,
                'estoque_futuro': estoque_futuro,
                'diferenca_futura': diferenca_futura,
                'tipo': registro.tipo or '',
                'unidade_sistema': unidade_sistema or '',
                'unidade_terceiro': unidade_terceiro or '',
                'unidade_convertida': unidade_convertida,
                'fator_conversao': fator_conversao if unidade_convertida else 1.0,
                'valor_unitario': float(registro.valor_unitario) if registro.valor_unitario else 0,
                'valor_total': float(registro.valor_total) if registro.valor_total else 0,
                'data_estoque_terceiro': registro.data_estoque_terceiro.isoformat() if registro.data_estoque_terceiro else ''
            })
        
        # Mapeamento de colunas para ordenação
        # 0: codigo_erp, 1: material_nome, 2: tipo, 3: unidade_sistema, 4: unidade_terceiro,
        # 5: estoque_sistema, 6: estoque_terceiro, 7: diferenca, 8: diferenca_percentual,
        # 9: consumo_futuro, 10: estoque_futuro, 11: diferenca_futura,
        # 12: valor_unitario, 13: valor_total, 14: data_estoque_terceiro
        column_map = {
            0: 'codigo_erp',
            1: 'material_nome',
            2: 'tipo',
            3: 'unidade_sistema',
            4: 'unidade_terceiro',
            5: 'estoque_sistema',
            6: 'estoque_terceiro',
            7: 'diferenca',
            8: 'diferenca_percentual',
            9: 'consumo_futuro',
            10: 'estoque_futuro',
            11: 'diferenca_futura',
            12: 'valor_unitario',
            13: 'valor_total',
            14: 'data_estoque_terceiro'
        }
        
        # Aplicar ordenação
        if order_column_index in column_map:
            sort_key = column_map[order_column_index]
            reverse = order_dir == 'desc'
            
            # Ordenar por chave numérica ou string
            if sort_key == 'diferenca_percentual':
                # Ordenar pelo módulo (valor absoluto) da diferença percentual
                data_temp.sort(key=lambda x: abs(float(x.get(sort_key, 0)) or 0), reverse=reverse)
            elif sort_key in ['estoque_sistema', 'estoque_terceiro', 'diferenca', 'consumo_futuro', 'estoque_futuro', 'diferenca_futura', 'valor_unitario', 'valor_total']:
                data_temp.sort(key=lambda x: float(x.get(sort_key, 0)) or 0, reverse=reverse)
            elif sort_key == 'data_estoque_terceiro':
                data_temp.sort(key=lambda x: x.get(sort_key, '') or '', reverse=reverse)
            else:
                data_temp.sort(key=lambda x: str(x.get(sort_key, '')).lower(), reverse=reverse)
        else:
            # Ordenação padrão por nome do material
            data_temp.sort(key=lambda x: str(x.get('material_nome', '')).lower())
        
        # Aplicar paginação após ordenação
        records_filtered = len(data_temp)
        data = data_temp[start:start + length]
        
        return jsonify({
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': records_filtered,
            'data': data
        }), 200
        
    except Exception as e:
        logger.error(f'Erro ao buscar comparativo: {str(e)}', exc_info=True)
        return jsonify({
            'draw': draw,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e)
        }), 500


@estoque_terceiro_bp.route('/api/datas-disponiveis', methods=['GET'])
@login_required
def api_datas_disponiveis():
    """
    Retorna lista de datas disponíveis para filtro
    """
    try:
        datas = db.session.query(
            EstoqueTerceiro.data
        ).distinct().order_by(EstoqueTerceiro.data.desc()).all()
        
        datas_list = [data[0].isoformat() for data in datas if data[0]]
        
        return jsonify({
            'success': True,
            'datas': datas_list
        }), 200
        
    except Exception as e:
        logger.error(f'Erro ao buscar datas disponíveis: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@estoque_terceiro_bp.route('/api/pecas-nao-produzidas', methods=['GET'])
@login_required
def api_pecas_nao_produzidas():
    """
    Retorna peças não produzidas agrupadas por tanque, filtradas pela data do estoque terceiro até hoje
    """
    try:
        # Parâmetro de data do estoque terceiro
        data_estoque_str = request.args.get('data_estoque', '')
        data_hoje = datetime.now().date()
        
        if not data_estoque_str:
            return jsonify({
                'success': True,
                'pecas': []
            }), 200
        
        try:
            data_estoque = datetime.strptime(data_estoque_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Data inválida'
            }), 400
        
        # Buscar peças não produzidas (sem data_concretagem) que têm vinculação com produto composto
        # e que foram cadastradas entre a data do estoque terceiro e hoje
        pecas_query = db.session.query(
            TanquesPecas,
            TanquesProdutoComposto,
            Tanques
        ).join(
            TanquesProdutoComposto,
            db.and_(
                TanquesPecas.tanque_id == TanquesProdutoComposto.tanque_id,
                TanquesPecas.tipo == TanquesProdutoComposto.tipo_peca
            )
        ).join(
            Tanques,
            TanquesPecas.tanque_id == Tanques.id
        ).filter(
            TanquesPecas.data_concretagem.is_(None),
            func.date(TanquesPecas.data_cadastro) >= data_estoque,
            func.date(TanquesPecas.data_cadastro) <= data_hoje
        ).order_by(
            Tanques.nome,
            TanquesPecas.tipo,
            TanquesPecas.numero_sequencial
        ).all()
        
        # Agrupar por tanque
        pecas_por_tanque = {}
        for peca, vinculacao, tanque in pecas_query:
            tanque_id = tanque.id
            if tanque_id not in pecas_por_tanque:
                pecas_por_tanque[tanque_id] = {
                    'tanque_id': tanque_id,
                    'tanque_nome': tanque.nome,
                    'pecas': []
                }
            
            pecas_por_tanque[tanque_id]['pecas'].append({
                'id': peca.id,
                'nome': peca.nome,
                'tipo': peca.tipo,
                'numero_sequencial': peca.numero_sequencial,
                'produto_composto_id': vinculacao.produto_composto_id,
                'produto_composto_nome': vinculacao.produto_composto.nome if vinculacao.produto_composto else '',
                'data_cadastro': peca.data_cadastro.isoformat() if peca.data_cadastro else None
            })
        
        resultado = list(pecas_por_tanque.values())
        
        return jsonify({
            'success': True,
            'pecas': resultado
        }), 200
        
    except Exception as e:
        logger.error(f'Erro ao buscar peças não produzidas: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@estoque_terceiro_bp.route('/api/calcular-consumo-futuro', methods=['GET'])
@login_required
def api_calcular_consumo_futuro():
    """
    Calcula o consumo futuro de materiais baseado em peças não produzidas
    """
    try:
        # Parâmetros
        data_estoque_str = request.args.get('data_estoque', '')
        material_ids = request.args.getlist('material_ids[]')  # Lista de IDs de materiais
        
        if not data_estoque_str:
            return jsonify({
                'success': True,
                'consumo_futuro': {}
            }), 200
        
        try:
            data_estoque = datetime.strptime(data_estoque_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Data inválida'
            }), 400
        
        data_hoje = datetime.now().date()
        
        # Buscar peças não produzidas com vinculação
        pecas_query = db.session.query(
            TanquesPecas,
            TanquesProdutoComposto
        ).join(
            TanquesProdutoComposto,
            db.and_(
                TanquesPecas.tanque_id == TanquesProdutoComposto.tanque_id,
                TanquesPecas.tipo == TanquesProdutoComposto.tipo_peca
            )
        ).filter(
            TanquesPecas.data_concretagem.is_(None),
            func.date(TanquesPecas.data_cadastro) >= data_estoque,
            func.date(TanquesPecas.data_cadastro) <= data_hoje
        ).all()
        
        # Calcular consumo futuro por material
        consumo_futuro = {}  # material_id -> quantidade total
        
        # Agrupar peças por produto composto para otimizar
        pecas_por_produto = {}
        for peca, vinculacao in pecas_query:
            produto_id = vinculacao.produto_composto_id
            if produto_id not in pecas_por_produto:
                pecas_por_produto[produto_id] = []
            pecas_por_produto[produto_id].append(peca)
        
        # Para cada produto composto, calcular consumo de materiais
        for produto_id, pecas_list in pecas_por_produto.items():
            produto_composto = ProdutoComposto.query.get(produto_id)
            if not produto_composto:
                continue
            
            quantidade_pecas = len(pecas_list)
            
            # Calcular materiais necessários usando o método produzir (sem executar movimentações)
            materiais_necessarios = {}
            produtos_processados = set()
            
            try:
                produto_composto.produzir(
                    quantidade=quantidade_pecas,
                    data_movimento=data_hoje,
                    usuario_id=current_user.id if current_user else 1,
                    log=False,
                    produtos_processados=produtos_processados,
                    materiais_necessarios=materiais_necessarios
                )
            except Exception as e:
                logger.warning(f'Erro ao calcular consumo para produto composto {produto_id}: {str(e)}')
                continue
            
            # Acumular consumo por material
            for estoque_id, info in materiais_necessarios.items():
                estoque = info['estoque']
                if estoque and estoque.material_id:
                    material_id = estoque.material_id
                    quantidade = float(info['quantidade']) or 0
                    
                    if material_id not in consumo_futuro:
                        consumo_futuro[material_id] = 0
                    consumo_futuro[material_id] += quantidade
        
        return jsonify({
            'success': True,
            'consumo_futuro': consumo_futuro
        }), 200
        
    except Exception as e:
        logger.error(f'Erro ao calcular consumo futuro: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
