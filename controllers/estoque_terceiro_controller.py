import json as json_lib
import logging
import os
import tempfile
from datetime import datetime
from decimal import Decimal

import pandas as pd
import io

from flask import Blueprint, current_app, flash, jsonify, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import cast, func, or_, union_all
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import null
from sqlalchemy.types import Integer, String
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
                    try:
                        codigo_erp_int = int(str(codigo_erp).replace('.0', '').strip())
                    except (ValueError, TypeError):
                        erros.append(f'Linha {idx + 2}: código ERP inválido "{codigo_erp}"')
                        continue
                    
                    # Obter valores usando índice ou nome da coluna
                    if isinstance(mapeamento.get('tipo item'), int):
                        tipo_val = row.iloc[mapeamento['tipo item']]
                        nome_val = row.iloc[mapeamento['nome']] if 'nome' in mapeamento else None
                        unidade_val = row.iloc[mapeamento['unidade']]
                        quantidade_val = row.iloc[mapeamento['quantidade']]
                        valor_unitario_val = row.iloc[mapeamento['valor unitario']]
                        valor_total_val = row.iloc[mapeamento['valor total']]
                    else:
                        tipo_val = row[mapeamento['tipo item']]
                        nome_val = row[mapeamento['nome']] if 'nome' in mapeamento else None
                        unidade_val = row[mapeamento['unidade']]
                        quantidade_val = row[mapeamento['quantidade']]
                        valor_unitario_val = row[mapeamento['valor unitario']]
                        valor_total_val = row[mapeamento['valor total']]
                    
                    tipo = str(tipo_val).strip() if pd.notna(tipo_val) else None
                    nome = str(nome_val).strip() if pd.notna(nome_val) and nome_val is not None else None
                    unidade = str(unidade_val).strip() if pd.notna(unidade_val) else None
                    
                    quantidade = Decimal(str(quantidade_val)) if pd.notna(quantidade_val) else Decimal('0')
                    valor_unitario = Decimal(str(valor_unitario_val)) if pd.notna(valor_unitario_val) else None
                    valor_total = Decimal(str(valor_total_val)) if pd.notna(valor_total_val) else None
                    
                    if codigo_erp_int not in cods_existentes:
                        # Criar novo registro (codigo_erp e tipo como int)
                        item = EstoqueTerceiro(
                            data=data_importacao,
                            codigo_erp=codigo_erp_int,
                            nome=nome,
                            tipo=int(tipo.replace('.0', '')) if tipo and str(tipo).replace('.0', '').strip().isdigit() else None,
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
        draw = int(request.args.get('draw', 1))
        
        # Filtro de data (opcional); filtros e ordenação são no frontend
        data_filtro = request.args.get('data_filtro', '')
        data_filtro_date = None
        if data_filtro:
            try:
                data_filtro_date = datetime.strptime(data_filtro, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Filtros e ordenação são feitos no frontend; backend retorna todos os dados
        # Collation única para evitar "Illegal mix of collations" no UNION
        collation = 'utf8mb4_unicode_ci'
        
        # Comparação codigo_erp: Materiais é String(50), EstoqueTerceiro é Integer — comparar como int
        join_codigo_erp = cast(Materiais.codigo_erp, Integer) == EstoqueTerceiro.codigo_erp
        # EstoqueTerceiro.tipo é Integer; filtrar por 10
        tipo_filtro = 10

        # Query 1: materiais que têm codigo_erp e estoque terceiro (match sistema + terceiro)
        q_matched = db.session.query(
            Materiais.id.label('material_id'),
            Materiais.nome.collate(collation).label('material_nome'),
            cast(Materiais.codigo_erp, String(50)).label('codigo_erp'),
            EstoqueTerceiro.quantidade.label('estoque_terceiro'),
            cast(EstoqueTerceiro.tipo, String(50)).label('tipo'),
            EstoqueTerceiro.unidade.collate(collation).label('unidade'),
            EstoqueTerceiro.ValorUnitario.label('valor_unitario'),
            EstoqueTerceiro.ValorTotal.label('valor_total'),
            EstoqueTerceiro.data.label('data_estoque_terceiro')
        ).outerjoin(EstoqueTerceiro, join_codigo_erp).filter(
            Materiais.codigo_erp.isnot(None),
            Materiais.codigo_erp != '',
            EstoqueTerceiro.tipo == tipo_filtro,
            EstoqueTerceiro.quantidade > 0
        )
        if data_filtro_date:
            q_matched = q_matched.filter(EstoqueTerceiro.data == data_filtro_date)
        
        # Query 2: registros que existem no terceiro mas não no sistema (codigo_erp sem material cadastrado)
        codigos_no_sistema = db.session.query(cast(Materiais.codigo_erp, Integer)).filter(
            Materiais.codigo_erp.isnot(None),
            Materiais.codigo_erp != ''
        ).distinct()
        # Nome do material do terceiro (se existir), senão codigo_erp (cast int para string no coalesce)
        nome_terceiro = func.coalesce(
            EstoqueTerceiro.nome.collate(collation),
            cast(EstoqueTerceiro.codigo_erp, String(50))
        ).label('material_nome')
        q_terceiro_only = db.session.query(
            null().label('material_id'),
            nome_terceiro,
            cast(EstoqueTerceiro.codigo_erp, String(50)).label('codigo_erp'),
            EstoqueTerceiro.quantidade.label('estoque_terceiro'),
            cast(EstoqueTerceiro.tipo, String(50)).label('tipo'),
            EstoqueTerceiro.unidade.collate(collation).label('unidade'),
            EstoqueTerceiro.ValorUnitario.label('valor_unitario'),
            EstoqueTerceiro.ValorTotal.label('valor_total'),
            EstoqueTerceiro.data.label('data_estoque_terceiro')
        ).filter(
            EstoqueTerceiro.tipo == tipo_filtro,
            ~EstoqueTerceiro.codigo_erp.in_(codigos_no_sistema),
            EstoqueTerceiro.quantidade > 0
        )
        if data_filtro_date:
            q_terceiro_only = q_terceiro_only.filter(EstoqueTerceiro.data == data_filtro_date)
        
        # União: matched + só terceiro
        subq = q_matched.union(q_terceiro_only).subquery()
        query_final = db.session.query(subq)
        
        # Busca também no frontend; não filtrar por search_value aqui
        total_records = query_final.count()
        registros_temp = query_final.all()
        
        # Consumo futuro por peça/tipo: lista de grupos (tipo + produto composto) com consumo por material
        # O frontend usa esse breakdown para calcular consumo por material e depois estoque_futuro/diferenca_futura
        consumo_por_peca_tipo = []  # list of { chave_grupo, tipo, produto_composto_id, produto_nome, quantidade_pecas, materiais: { material_id: float } }
        consumo_futuro_por_material = {}  # material_id -> total (float), para preencher row e ordenação
        if data_filtro_date:
            try:
                quantidades_simuladas_str = request.args.get('quantidades_simuladas', '{}')
                quantidades_simuladas = {}
                try:
                    quantidades_simuladas = json_lib.loads(quantidades_simuladas_str) if quantidades_simuladas_str else {}
                except (TypeError, ValueError):
                    quantidades_simuladas = {}
                
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
                
                grupos_consumo = {}
                for peca_cons, vinculacao_cons in pecas_consumo:
                    tipo_peca = peca_cons.tipo
                    produto_id = vinculacao_cons.produto_composto_id
                    chave_grupo = f"{tipo_peca}_{produto_id}"
                    if chave_grupo not in grupos_consumo:
                        grupos_consumo[chave_grupo] = {'produto_id': produto_id, 'tipo': tipo_peca, 'count': 0}
                    grupos_consumo[chave_grupo]['count'] += 1
                
                for chave_grupo, grupo_info in grupos_consumo.items():
                    produto_id = grupo_info['produto_id']
                    tipo_peca = grupo_info['tipo']
                    qty_real = grupo_info['count']
                    qty_simulada = quantidades_simuladas.get(chave_grupo, qty_real)
                    quantidade_pecas = float(qty_simulada) if qty_simulada is not None else float(qty_real)
                    if quantidade_pecas <= 0:
                        continue
                    
                    produto_composto_cons = ProdutoComposto.query.get(produto_id)
                    if not produto_composto_cons:
                        continue
                    
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
                        materiais_grupo = {}  # material_id -> float
                        for estoque_id, info in materiais_necessarios.items():
                            estoque = info['estoque']
                            if not estoque or estoque.tipo_item != 'material' or not estoque.material_id:
                                continue
                            qtd = info.get('quantidade')
                            if qtd is None:
                                continue
                            qtd_float = float(qtd) if not isinstance(qtd, float) else qtd
                            mid = estoque.material_id
                            materiais_grupo[mid] = materiais_grupo.get(mid, 0.0) + qtd_float
                            consumo_futuro_por_material[mid] = consumo_futuro_por_material.get(mid, 0.0) + qtd_float
                        produto_nome = (produto_composto_cons.nome or '').strip()
                        consumo_por_peca_tipo.append({
                            'chave_grupo': chave_grupo,
                            'tipo': tipo_peca,
                            'produto_composto_id': produto_id,
                            'produto_nome': produto_nome,
                            'quantidade_pecas': quantidade_pecas,
                            'materiais': materiais_grupo
                        })
                    except Exception as e:
                        logger.warning(f'Erro ao calcular consumo para produto composto {produto_id}: {str(e)}')
                        continue
            except Exception as e:
                logger.warning(f'Erro ao montar consumo por peça/tipo: {str(e)}')
        
        # Calcular estoque do sistema baseado em movimentações para cada registro
        data_temp = []
        for registro in registros_temp:
            # Registros "só terceiro" têm material_id None (existem no terceiro e não no sistema)
            so_terceiro = registro.material_id is None
            
            material = Materiais.query.get(registro.material_id) if registro.material_id else None
            unidade_sistema = None
            if material and material.unidade_obj:
                unidade_sistema = material.unidade_obj.nome
            
            unidade_terceiro = registro.unidade or ''
            
            # Estoque do sistema: zero quando não há material cadastrado
            estoques_material = Estoque.query.filter_by(material_id=registro.material_id).all() if registro.material_id else []
            
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
                material_id=registro.material_id,
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
            
            # Quando há conversão de unidade, converter também o valor unitário (R$ por unidade terceiro -> R$ por unidade sistema)
            # 1 unidade sistema = 1/fator_conversao unidades terceiro, então valor_unitario_sistema = valor_unitario_terceiro / fator
            valor_unitario_original = float(registro.valor_unitario) if registro.valor_unitario else 0
            if unidade_convertida and fator_conversao and fator_conversao != 0:
                valor_unitario_exibir = valor_unitario_original / fator_conversao
                valor_total_exibir = estoque_terceiro_convertido * valor_unitario_exibir  # qtd sistema × valor/un sistema
            else:
                valor_unitario_exibir = valor_unitario_original
                valor_total_exibir = float(registro.valor_total) if registro.valor_total else 0
            
            # Calcular diferença usando valores convertidos
            diferenca = estoque_terceiro_convertido - estoque_sistema_float
            
            # Calcular diferença percentual
            if estoque_sistema_float != 0:
                diferenca_percentual = (diferenca / estoque_sistema_float) * 100
            elif estoque_terceiro_convertido != 0:
                diferenca_percentual = 100  # Terceiro tem estoque mas sistema não
            else:
                diferenca_percentual = 0
            
            # Consumo futuro por material (agregado a partir do consumo por peça/tipo); estoque_futuro e diferenca_futura calculados no frontend
            consumo_futuro_material = float(consumo_futuro_por_material.get(registro.material_id, 0) or 0)
            
            if so_terceiro:
                nome_ou_codigo = (registro.material_nome or registro.codigo_erp or '').replace('.0', '')
                material_nome_exib = nome_ou_codigo
            else:
                material_nome_exib = (registro.material_nome or '').replace('.0', '')
            valor_sistema = float(estoque_sistema_float * valor_unitario_exibir)
            valor_terceiro = valor_total_exibir

            data_temp.append({
                'material_id': registro.material_id,
                'material_nome': material_nome_exib,
                'codigo_erp': (registro.codigo_erp or '').replace('.0', '') if registro.codigo_erp else '',
                'estoque_sistema': estoque_sistema_float,
                'estoque_terceiro': estoque_terceiro_convertido,  # Valor convertido para unidade do sistema
                'estoque_terceiro_original': estoque_terceiro_original,  # Valor original do terceiro
                'diferenca': diferenca,
                'diferenca_percentual': round(diferenca_percentual, 2),
                'valor_diferenca': float(diferenca * valor_unitario_exibir),
                'consumo_futuro': consumo_futuro_material,
                'estoque_futuro': 0,
                'diferenca_futura': 0,
                'unidade_sistema': unidade_sistema or '',
                'unidade_terceiro': unidade_terceiro or '',
                'unidade_convertida': unidade_convertida,
                'fator_conversao': fator_conversao if unidade_convertida else 1.0,
                'valor_unitario': valor_unitario_exibir,
                'valor_unitario_original': valor_unitario_original,
                'valor_sistema': valor_sistema,
                'valor_terceiro': valor_terceiro,
            })
        
        # Exportação Excel: aplicar filtros opcionais e gerar arquivo
        if request.args.get('format') == 'excel':
            filtro_qty_zero = request.args.get('filtro_quantidade_zero', '').lower() in ('1', 'true', 's', 'sim', 'on')
            filtro_sem_mat = request.args.get('filtro_sem_material_sistema', '').lower() in ('1', 'true', 's', 'sim', 'on')
            filtro_ter_os_dois = request.args.get('filtro_ter_os_dois', '').lower() in ('1', 'true', 's', 'sim', 'on')
            if filtro_qty_zero:
                data_temp = [r for r in data_temp if (float(r.get('estoque_sistema') or 0) != 0 or float(r.get('estoque_terceiro') or 0) != 0)]
            if filtro_sem_mat:
                data_temp = [r for r in data_temp if r.get('material_id') is None]
            if filtro_ter_os_dois:
                data_temp = [r for r in data_temp if r.get('material_id') is not None and r.get('material_id') != '']
            for r in data_temp:
                cf = float(r.get('consumo_futuro') or 0)
                es = float(r.get('estoque_sistema') or 0)
                et = float(r.get('estoque_terceiro') or 0)
                r['estoque_futuro'] = es - cf
                r['diferenca_futura'] = et - (es - cf)
            colunas_excel = [
                'codigo_erp', 'material_nome', 'unidade_sistema', 'unidade_terceiro',
                'estoque_sistema', 'estoque_terceiro', 'valor_unitario', 'diferenca', 'diferenca_percentual', 'valor_diferenca',
                'consumo_futuro', 'estoque_futuro', 'diferenca_futura',
                'valor_sistema', 'valor_terceiro'
            ]
            df = pd.DataFrame(data_temp, columns=colunas_excel)
            df.columns = [
                'Código ERP', 'Material', 'Unidade Sistema', 'Unidade Terceiro',
                'Estoque Sistema', 'Estoque Terceiro', 'Valor Unitário', 'Diferença', 'Diferença %', 'Valor da Diferença',
                'Consumo Futuro', 'Estoque Futuro', 'Diferença Futura',
                'Valor Sistema', 'Valor Terceiro'
            ]
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Comparativo')
            output.seek(0)
            nome_arquivo = f'comparativo_estoques_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=nome_arquivo
            )
        
        return jsonify({
            'draw': draw,
            'recordsTotal': len(data_temp),
            'recordsFiltered': len(data_temp),
            'data': data_temp,
            'consumo_por_peca_tipo': consumo_por_peca_tipo
        }), 200
        
    except Exception as e:
        logger.error(f'Erro ao buscar comparativo: {str(e)}', exc_info=True)
        return jsonify({
            'draw': draw,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'consumo_por_peca_tipo': [],
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
    Retorna peças não produzidas agrupadas por tipo/produto composto, filtradas pela data do estoque terceiro até hoje
    """
    try:
        # Parâmetro de data do estoque terceiro
        data_estoque_str = request.args.get('data_estoque', '')
        data_hoje = datetime.now().date()
        
        if not data_estoque_str:
            return jsonify({
                'success': True,
                'grupos': []
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
            TanquesPecas.tipo,
            TanquesProdutoComposto.produto_composto_id,
            Tanques.nome,
            TanquesPecas.numero_sequencial
        ).all()
        
        # Agrupar por tipo e produto composto
        grupos = {}
        for peca, vinculacao, tanque in pecas_query:
            tipo_peca = peca.tipo
            produto_id = vinculacao.produto_composto_id
            produto_nome = vinculacao.produto_composto.nome if vinculacao.produto_composto else ''
            
            # Chave de agrupamento: tipo + produto_composto_id
            chave_grupo = f"{tipo_peca}_{produto_id}"
            
            if chave_grupo not in grupos:
                grupos[chave_grupo] = {
                    'tipo': tipo_peca,
                    'produto_composto_id': produto_id,
                    'produto_composto_nome': produto_nome,
                    'quantidade_real': 0,
                    'pecas': []
                }
            
            grupos[chave_grupo]['quantidade_real'] += 1
            grupos[chave_grupo]['pecas'].append({
                'id': peca.id,
                'nome': peca.nome,
                'tanque_id': tanque.id,
                'tanque_nome': tanque.nome,
                'numero_sequencial': peca.numero_sequencial,
                'data_cadastro': peca.data_cadastro.isoformat() if peca.data_cadastro else None
            })
        
        # Converter para lista e ordenar
        resultado = list(grupos.values())
        resultado.sort(key=lambda x: (x['tipo'], x['produto_composto_nome']))
        
        return jsonify({
            'success': True,
            'grupos': resultado
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
