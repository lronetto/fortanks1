import json as json_lib
import logging
import os
import tempfile
import zipfile
from datetime import datetime
from decimal import Decimal

import pandas as pd
import io

from flask import Blueprint, current_app, flash, jsonify, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, cast, func, or_, union_all
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import null
from sqlalchemy.types import Integer, String
from werkzeug.utils import secure_filename

from models.database import db
from models.estoque import Estoque
from models.estoque_terceiro import EstoqueTerceiro
from models.material import Materiais
from models.unidade import get_conversao_unidade, normalizar_unidade, comparar_unidades
from models.tanque import TanquesPecas, TanquesProdutoComposto, Tanques, TanquesGrupos
from models.produto_composto import ProdutoComposto
from utils.utils import parse_dados_json

logger = logging.getLogger(__name__)

# Criar blueprint
estoque_terceiro_bp = Blueprint('estoque_terceiro', __name__, url_prefix='/estoque-terceiro')


@estoque_terceiro_bp.route('/')
@login_required
def index():
    """
    Página principal com tabela comparativa de estoques
    """
    return render_template('estoque_terceiro/comparativo_terceiro/index.html')


@estoque_terceiro_bp.route('/comparativo-datas')
@login_required
def comparativo_datas():
    """
    Comparativo lado a lado entre duas datas de estoque de terceiros (importações).
    """
    return render_template('estoque_terceiro/comparativo_datas/index.html')


@estoque_terceiro_bp.route('/lista')
@login_required
def lista():
    """
    Página de consulta do estoque de terceiros com filtros simples.
    """
    return render_template('estoque_terceiro/estoque_terceiro/index.html')


def _tipos_filtro_estoque_terceiro():
    """Mesma regra do api_comparativo: tipos via querystring ou padrão [10]."""
    tipos_raw = (request.args.get('tipos') or '').strip()
    tipos_selecionados = []
    if tipos_raw:
        for parte in tipos_raw.split(','):
            p = (parte or '').strip()
            if p.isdigit():
                tipos_selecionados.append(int(p))
    if not tipos_selecionados:
        tipos_selecionados = [10]
    return tipos_selecionados


def _agrupar_estoque_terceiro_por_data(data_ref, tipos_selecionados):
    """
    Agrega quantidades por (codigo_erp, tipo) em uma data.
    Retorna dict chave (codigo_erp_int, tipo_int) -> { nome, unidade, quantidade, valor_unitario, valor_total }.
    """
    tipo_col = func.coalesce(EstoqueTerceiro.tipo, 0)
    rows = (
        db.session.query(
            EstoqueTerceiro.codigo_erp,
            tipo_col.label('tipo_ag'),
            func.max(EstoqueTerceiro.nome).label('nome'),
            func.max(EstoqueTerceiro.unidade).label('unidade'),
            func.sum(EstoqueTerceiro.quantidade).label('quantidade'),
            func.avg(EstoqueTerceiro.ValorUnitario).label('valor_unitario'),
        )
        .filter(
            EstoqueTerceiro.data == data_ref,
            EstoqueTerceiro.tipo.in_(tipos_selecionados),
        )
        .group_by(EstoqueTerceiro.codigo_erp, tipo_col)
        .all()
    )
    out = {}
    for r in rows:
        ce = int(r.codigo_erp) if r.codigo_erp is not None else 0
        tipo_v = int(r.tipo_ag) if r.tipo_ag is not None else 0
        key = (ce, tipo_v)
        q = float(r.quantidade or 0)
        vu = float(r.valor_unitario or 0)
        out[key] = {
            'codigo_erp': ce,
            'tipo': tipo_v,
            'nome_terceiro': (r.nome or '').strip(),
            'unidade': (r.unidade or '').strip(),
            'quantidade': q,
            'valor_unitario': vu,
            'valor_total': q * vu,
        }
    return out


@estoque_terceiro_bp.route('/api/comparativo-entre-datas', methods=['GET'])
@login_required
def api_comparativo_entre_datas():
    """
    API para DataTables: duas datas de estoque terceiro, colunas lado a lado e diferenças.
    """
    draw = int(request.args.get('draw', 1))
    try:
        data_a_str = (request.args.get('data_a') or '').strip()
        data_b_str = (request.args.get('data_b') or '').strip()
        if not data_a_str or not data_b_str:
            return jsonify({
                'draw': draw,
                'recordsTotal': 0,
                'recordsFiltered': 0,
                'data': [],
                'error': 'Informe data_a e data_b (YYYY-MM-DD).',
            }), 400
        data_a = datetime.strptime(data_a_str, '%Y-%m-%d').date()
        data_b = datetime.strptime(data_b_str, '%Y-%m-%d').date()
        tipos = _tipos_filtro_estoque_terceiro()

        map_a = _agrupar_estoque_terceiro_por_data(data_a, tipos)
        map_b = _agrupar_estoque_terceiro_por_data(data_b, tipos)
        todas_chaves = set(map_a.keys()) | set(map_b.keys())

        codigos = {k[0] for k in todas_chaves if k[0]}
        nomes_sistema = {}
        if codigos:
            lista_codigos = set(int(c) for c in codigos if c)
            # `codigo_alterdata` agora fica em `Materiais.dados_adicionais` (JSON em TEXT).
            # Fazemos o match em Python para evitar dependência de JSON functions no MySQL/SQLite.
            rows = (
                db.session.query(Materiais.nome, Materiais.dados_adicionais)
                .filter(Materiais.dados_adicionais.isnot(None), Materiais.dados_adicionais != "")
                .all()
            )
            for nome, dados in rows:
                extras = parse_dados_json(dados)
                v = extras.get("codigo_alterdata")
                try:
                    c = int(float(str(v).strip())) if v not in (None, "") else None
                except (TypeError, ValueError):
                    c = None
                if c and c in lista_codigos and c not in nomes_sistema:
                    nomes_sistema[c] = (nome or "").strip()

        vazio = {
            'nome_terceiro': '',
            'unidade': '',
            'quantidade': 0.0,
            'valor_unitario': 0.0,
            'valor_total': 0.0,
        }

        data_rows = []
        for key in sorted(todas_chaves, key=lambda x: (x[0], x[1])):
            a = map_a.get(key, vazio)
            b = map_b.get(key, vazio)
            qa, qb = a['quantidade'], b['quantidade']
            dif_q = qb - qa
            va_t, vb_t = a['valor_total'], b['valor_total']
            dif_v = vb_t - va_t
            if qa != 0:
                dif_pct = (dif_q / qa) * 100.0
            elif qb != 0:
                dif_pct = 100.0
            else:
                dif_pct = 0.0

            ce = key[0]
            tipo_v = key[1]
            nome_mat = nomes_sistema.get(ce, '')
            nome_exibir = nome_mat or a['nome_terceiro'] or b['nome_terceiro'] or str(ce)
            ua, ub = a['unidade'], b['unidade']
            if ua and ub and ua != ub:
                unidade_exibir = f'{ua} / {ub}'
            else:
                unidade_exibir = ua or ub or ''

            data_rows.append({
                'codigo_erp': str(ce),
                'tipo': str(tipo_v),
                'material_nome': nome_exibir,
                'nome_terceiro': a['nome_terceiro'] or b['nome_terceiro'],
                'unidade': unidade_exibir,
                'qtd_data_a': qa,
                'qtd_data_b': qb,
                'diferenca_qtd': dif_q,
                'diferenca_percentual': round(dif_pct, 2),
                'valor_total_a': round(va_t, 2),
                'valor_total_b': round(vb_t, 2),
                'diferenca_valor': round(dif_v, 2),
                'valor_unitario_a': round(a['valor_unitario'], 4),
                'valor_unitario_b': round(b['valor_unitario'], 4),
                'label_data_a': data_a.isoformat(),
                'label_data_b': data_b.isoformat(),
            })

        return jsonify({
            'draw': draw,
            'recordsTotal': len(data_rows),
            'recordsFiltered': len(data_rows),
            'data': data_rows,
        }), 200

    except ValueError as e:
        return jsonify({
            'draw': draw,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': f'Data inválida: {e}',
        }), 400
    except Exception as e:
        logger.error(f'Erro api_comparativo_entre_datas: {e}', exc_info=True)
        return jsonify({
            'draw': draw,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e),
        }), 500


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
        
        patched_path = None
        try:
            def _patch_xlsx_xml_attrs(src_path: str) -> str | None:
                """
                Alguns exports de Excel/WPS geram atributos fora do padrão em XMLs internos do .xlsx,
                o que quebra o openpyxl (ex.: WindowWidth ao invés de windowWidth, firstPageNo, etc).
                Aqui criamos uma cópia "higienizada" do xlsx apenas quando necessário.
                """
                if not str(src_path).lower().endswith('.xlsx'):
                    return None

                try:
                    with zipfile.ZipFile(src_path, 'r') as zin:
                        names = zin.namelist()
                        # Se nem tiver o workbook, provavelmente não é um xlsx válido pro openpyxl
                        if 'xl/workbook.xml' not in names:
                            return None
                        xml_files = [n for n in names if n.lower().endswith('.xml')]
                        xml_payloads = {n: zin.read(n) for n in xml_files}
                except Exception:
                    return None

                replacements = {
                    b'WindowWidth=': b'windowWidth=',
                    b'WindowHeight=': b'windowHeight=',
                    b'WindowX=': b'xWindow=',
                    b'WindowY=': b'yWindow=',
                    # aparece em alguns arquivos como atributo inválido de pageSetup
                    b'firstPageNo=': b'firstPageNumber=',
                }

                mudou_algo = False
                patched_payloads = {}
                for name, payload in xml_payloads.items():
                    patched = payload
                    for old, new in replacements.items():
                        if old in patched:
                            patched = patched.replace(old, new)
                    if patched != payload:
                        mudou_algo = True
                    patched_payloads[name] = patched

                if not mudou_algo:
                    return None

                dst_path = os.path.join(
                    tempfile.gettempdir(),
                    f'patched_{os.path.basename(src_path)}'
                )
                try:
                    with zipfile.ZipFile(src_path, 'r') as zin, zipfile.ZipFile(dst_path, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
                        for item in zin.infolist():
                            data = zin.read(item.filename)
                            if item.filename in patched_payloads:
                                data = patched_payloads[item.filename]
                            zout.writestr(item, data)
                    return dst_path
                except Exception:
                    try:
                        if os.path.exists(dst_path):
                            os.remove(dst_path)
                    except Exception:
                        pass
                    return None

            def _read_excel_robusto(path: str) -> pd.DataFrame:
                logger.info(f'Lendo planilha: {path}')
                try:
                    return pd.read_excel(path)
                except TypeError as e:
                    msg = str(e)
                    # Casos clássicos: XMLs com atributos inválidos (BookView / PrintPageSetup etc)
                    if (
                        'BookView.__init__' in msg
                        or 'PrintPageSetup.__init__' in msg
                        or 'WindowWidth' in msg
                        or 'firstPageNo' in msg
                    ):
                        nonlocal patched_path
                        patched_path = _patch_xlsx_xml_attrs(path)
                        if patched_path:
                            logger.warning('Arquivo xlsx com atributos inválidos detectado. Tentando leitura após higienização do XML interno.')
                            return pd.read_excel(patched_path)
                    raise

            # Ler planilha - tentar primeiro com cabeçalhos
            df = _read_excel_robusto(temp_path)
            logger.info(f'Planilha lida com sucesso. Colunas encontradas: {list(df.columns)}')
            
            def _norm_col(val: object) -> str:
                s = str(val).lower().strip()
                # normalizações simples pra lidar com acentos e variações comuns
                s = (
                    s.replace('código', 'codigo')
                    .replace('cód.', 'cod')
                    .replace('cód', 'cod')
                    .replace('unid.', 'unidade')
                    .replace('vl unit', 'valor unitario')
                    .replace('vl. unit', 'valor unitario')
                    .replace('vl unitario', 'valor unitario')
                    .replace('vl total', 'total')
                    .replace('valor total', 'total')
                    .replace('valor', 'valor')
                )
                s = ' '.join(s.split())
                return s

            # Padrão de importação por posição:
            # 0=codigo, 1=tipo item, 2=nome, 3=unidade, 4=quantidade, 5=valor unitario, 6=total
            mapeamento_posicional = {
                'codigo': 0,
                'tipo item': 1,
                'nome': 2,
                'unidade': 3,
                'quantidade': 4,
                'valor unitario': 5,
                'total': 6,
            }

            # Se a primeira linha for dado, o pandas pode "promover" esses valores a cabeçalho.
            # Então: só consideramos que há cabeçalho se conseguirmos mapear a maioria das colunas esperadas.
            colunas_arquivo_norm = [_norm_col(col) for col in df.columns]
            logger.info(f'Colunas normalizadas: {colunas_arquivo_norm}')

            # Verificar colunas esperadas (com sinônimos)
            colunas_esperadas = ['codigo', 'tipo item', 'nome', 'unidade', 'quantidade', 'valor unitario', 'total']
            sinonimos = {
                'codigo': ['codigo', 'codigo alterdata', 'cod', 'cod alterdata', 'codigo erp', 'cod erp'],
                'tipo item': ['tipo item', 'tipo', 'tipo_item'],
                'nome': ['nome', 'descricao', 'descrição', 'produto', 'item'],
                'unidade': ['unidade', 'un', 'und'],
                'quantidade': ['quantidade', 'qtd', 'qtde'],
                'valor unitario': ['valor unitario', 'unitario', 'valor unit', 'vl unit', 'preco unitario', 'preço unitario'],
                'total': ['total', 'valor total', 'vl total'],
            }

            mapeamento = {}
            for col_padrao in colunas_esperadas:
                possiveis = [(_norm_col(x)) for x in sinonimos.get(col_padrao, [col_padrao])]
                for idx, col_norm in enumerate(colunas_arquivo_norm):
                    if any(p in col_norm or col_norm in p for p in possiveis):
                        mapeamento[col_padrao] = df.columns[idx]
                        logger.info(f'Mapeado: {col_padrao} -> {df.columns[idx]}')
                        break

            logger.info(f'Mapeamento (tentativa por cabeçalho): {mapeamento}')

            # Considerar que tem cabeçalho apenas se mapeou bem (>= 5/7).
            tem_cabecalho_util = len(mapeamento) >= 5 and not all(str(col).startswith('Unnamed') for col in df.columns)
            if not tem_cabecalho_util:
                logger.info('Cabeçalho ausente/ruim detectado (ou 1ª linha é dado). Lendo sem header e usando posições fixas.')
                df = pd.read_excel(temp_path, header=None)
                logger.info(f'Planilha relida sem cabeçalhos. Total de colunas: {len(df.columns)}')

                if len(df.columns) < 7:
                    return jsonify({
                        'success': False,
                        'message': f'A planilha deve ter pelo menos 7 colunas (codigo, tipo item, nome, unidade, quantidade, valor unitario, total). Encontradas: {len(df.columns)}'
                    }), 400

                mapeamento = dict(mapeamento_posicional)
                logger.info(f'Mapeamento por posição: {mapeamento}')
            
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
                    if isinstance(mapeamento.get('codigo'), int):
                        codigo_erp = str(row.iloc[mapeamento['codigo']]).strip()
                    else:
                        codigo_erp = str(row[mapeamento['codigo']]).strip()
                    
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
                        valor_total_val = row.iloc[mapeamento['total']]
                    else:
                        tipo_val = row[mapeamento['tipo item']]
                        nome_val = row[mapeamento['nome']] if 'nome' in mapeamento else None
                        unidade_val = row[mapeamento['unidade']]
                        quantidade_val = row[mapeamento['quantidade']]
                        valor_unitario_val = row[mapeamento['valor unitario']]
                        valor_total_val = row[mapeamento['total']]
                    
                    tipo = str(tipo_val).strip() if pd.notna(tipo_val) else None
                    nome = str(nome_val).strip() if pd.notna(nome_val) and nome_val is not None else None
                    unidade = str(unidade_val).strip() if pd.notna(unidade_val) else None
                    
                    quantidade = Decimal(str(quantidade_val)) if pd.notna(quantidade_val) else Decimal('0')
                    valor_unitario = Decimal(str(valor_unitario_val)) if pd.notna(valor_unitario_val) else None
                    valor_total = Decimal(str(valor_total_val)) if pd.notna(valor_total_val) else None

                    # Se não veio total (ou veio zerado), calcular pelo padrão quantidade * valor_unitario quando possível
                    if (valor_total is None or valor_total == Decimal('0')) and valor_unitario is not None:
                        try:
                            valor_total = (quantidade * valor_unitario) if quantidade is not None else valor_total
                        except Exception:
                            pass
                    
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
            if patched_path and os.path.exists(patched_path):
                try:
                    os.remove(patched_path)
                except Exception:
                    pass
                
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

        # Filtro de tipo do estoque terceiro (múltipla seleção).
        # Por compatibilidade com o comportamento atual, se não informar nada, mantém o tipo 10.
        tipos_raw = (request.args.get('tipos') or '').strip()
        tipos_selecionados = []
        if tipos_raw:
            for parte in tipos_raw.split(','):
                p = (parte or '').strip()
                if p.isdigit():
                    tipos_selecionados.append(int(p))
        if not tipos_selecionados:
            tipos_selecionados = [10]
        
        # Filtros e ordenação são feitos no frontend; backend retorna todos os dados
        # Collation única para evitar "Illegal mix of collations" no UNION
        collation = 'utf8mb4_unicode_ci'
        
        # Comparação por código Alterdata: fica em `Materiais.dados_adicionais` (JSON em TEXT).
        dados_adicionais_json = func.if_(
            func.json_valid(Materiais.dados_adicionais),
            Materiais.dados_adicionais,
            '{}'
        )
        codigo_alterdata_texto = func.nullif(
            func.json_unquote(func.json_extract(dados_adicionais_json, '$.codigo_alterdata')),
            ''
        )
        codigo_alterdata_int = cast(codigo_alterdata_texto, Integer)
        join_codigo_erp = (codigo_alterdata_int == EstoqueTerceiro.codigo_erp)
                      

        # Query 1: materiais que têm código Alterdata e estoque terceiro (match sistema + terceiro)
        q_matched = db.session.query(
            Materiais.id.label('material_id'),
            Materiais.nome.collate(collation).label('material_nome'),
            cast(codigo_alterdata_int, String(50)).label('codigo_erp'),
            EstoqueTerceiro.quantidade.label('estoque_terceiro'),
            cast(EstoqueTerceiro.tipo, String(50)).label('tipo'),
            EstoqueTerceiro.unidade.collate(collation).label('unidade'),
            EstoqueTerceiro.ValorUnitario.label('valor_unitario'),
            EstoqueTerceiro.ValorTotal.label('valor_total'),
            EstoqueTerceiro.data.label('data_estoque_terceiro')
        ).outerjoin(EstoqueTerceiro, join_codigo_erp).filter(
            codigo_alterdata_texto.isnot(None),
            EstoqueTerceiro.tipo.in_(tipos_selecionados),
            EstoqueTerceiro.quantidade > 0
        )
        if data_filtro_date:
            q_matched = q_matched.filter(EstoqueTerceiro.data == data_filtro_date)
        
        # Query 2: registros que existem no terceiro mas não no sistema (codigo_erp sem material cadastrado)
        codigos_no_sistema_codigo_alterdata = db.session.query(codigo_alterdata_int).filter(
            codigo_alterdata_texto.isnot(None)
        )
        codigos_no_sistema = codigos_no_sistema_codigo_alterdata.distinct()
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
            (EstoqueTerceiro.quantidade * EstoqueTerceiro.ValorUnitario).label('valor_total'),
            EstoqueTerceiro.data.label('data_estoque_terceiro')
        ).filter(
            EstoqueTerceiro.tipo.in_(tipos_selecionados),
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
                logger.warning(f'material_id: {registro.material_id}, terceiro: {registro.codigo_erp}, ')
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
                'tipo': str(registro.tipo) if registro.tipo else '',
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
                'data_estoque_terceiro': registro.data_estoque_terceiro.isoformat() if registro.data_estoque_terceiro else ''
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


@estoque_terceiro_bp.route('/api/lista', methods=['GET'])
@login_required
def api_lista():
    """
    API específica da tela "Estoque de Terceiros" (lista simples com filtros).
    Filtros:
      - nome: busca parcial em EstoqueTerceiro.nome
      - tipos: CSV de inteiros (ex: 10,15,18)
      - data_filtro: YYYY-MM-DD
    """
    try:
        nome = (request.args.get('nome') or '').strip()
        tipos_raw = (request.args.get('tipos') or '').strip()
        data_filtro = (request.args.get('data_filtro') or '').strip()

        tipos = []
        if tipos_raw:
            for parte in tipos_raw.split(','):
                parte_limpa = (parte or '').strip()
                if parte_limpa.isdigit():
                    tipos.append(int(parte_limpa))

        data_filtro_date = None
        if data_filtro:
            try:
                data_filtro_date = datetime.strptime(data_filtro, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Data inválida. Use o formato YYYY-MM-DD.'
                }), 400

        q = db.session.query(EstoqueTerceiro)

        if data_filtro_date:
            q = q.filter(EstoqueTerceiro.data == data_filtro_date)
        if tipos:
            q = q.filter(EstoqueTerceiro.tipo.in_(tipos))
        if nome:
            q = q.filter(EstoqueTerceiro.nome.ilike(f'%{nome}%'))

        rows = q.order_by(
            EstoqueTerceiro.data.desc(),
            EstoqueTerceiro.tipo.asc(),
            EstoqueTerceiro.nome.asc(),
            EstoqueTerceiro.codigo_erp.asc()
        ).all()

        data = []
        for row in rows:
            qtd = float(row.quantidade or 0)
            valor_unit = float(row.ValorUnitario or 0)
            valor_total = float(row.ValorTotal) if row.ValorTotal is not None else (qtd * valor_unit)
            data.append({
                'id': row.id,
                'codigo_erp': str(row.codigo_erp) if row.codigo_erp is not None else '',
                'material_nome': (row.nome or '').strip(),
                'tipo': str(row.tipo) if row.tipo is not None else '',
                'data_estoque_terceiro': row.data.isoformat() if row.data else '',
                'unidade_terceiro': (row.unidade or '').strip(),
                'quantidade_terceiro': qtd,
                'valor_unitario_original': valor_unit,
                'valor_terceiro': valor_total,
            })

        return jsonify({
            'success': True,
            'recordsTotal': len(data),
            'recordsFiltered': len(data),
            'data': data
        }), 200

    except Exception as e:
        logger.error(f'Erro ao buscar lista de estoque terceiro: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'message': str(e)
        }), 500


@estoque_terceiro_bp.route('/api/tipos-disponiveis', methods=['GET'])
@login_required
def api_tipos_disponiveis():
    """
    Retorna lista de tipos (EstoqueTerceiro.tipo) disponíveis para filtro.
    Pode ser filtrado por data do estoque terceiro (data_filtro=YYYY-MM-DD).
    """
    try:
        data_filtro = request.args.get('data_filtro', '')
        data_filtro_date = None
        if data_filtro:
            try:
                data_filtro_date = datetime.strptime(data_filtro, '%Y-%m-%d').date()
            except ValueError:
                data_filtro_date = None

        q = db.session.query(EstoqueTerceiro.tipo).filter(EstoqueTerceiro.tipo.isnot(None)).distinct()
        if data_filtro_date:
            q = q.filter(EstoqueTerceiro.data == data_filtro_date)

        tipos = [t[0] for t in q.order_by(EstoqueTerceiro.tipo.asc()).all() if t and t[0] is not None]

        return jsonify({'success': True, 'tipos': tipos}), 200
    except Exception as e:
        logger.error(f'Erro ao buscar tipos disponíveis: {str(e)}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

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
            TanquesPecas.data_concretagem.is_(None)
        ).order_by(
            TanquesPecas.tipo,
            TanquesProdutoComposto.produto_composto_id,
            Tanques.nome,
            TanquesPecas.numero_sequencial
        ).all()
        print('pecas_query', len(pecas_query));
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
        print('resultado', resultado);
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


@estoque_terceiro_bp.route('/api/simulacao/opcoes', methods=['GET'])
@login_required
def api_simulacao_opcoes():
    """
    Retorna opções (tanque + tipo de peça) com produto composto vinculado e
    quantidade produzida (concretada) até o momento.
    """
    try:
        tanque_id = request.args.get('tanque_id', '').strip()
        tanque_id_int = int(tanque_id) if tanque_id.isdigit() else None

        join_pecas_produzidas = db.and_(
            TanquesPecas.tanque_id == TanquesProdutoComposto.tanque_id,
            TanquesPecas.tipo == TanquesProdutoComposto.tipo_peca,
            TanquesPecas.data_concretagem.isnot(None),
        )

        q = db.session.query(
            TanquesProdutoComposto.id.label('vinculo_id'),
            Tanques.id.label('tanque_id'),
            Tanques.nome.label('tanque_nome'),
            func.coalesce(func.group_concat(func.distinct(TanquesGrupos.nome)), '').label('tanques_grupos'),
            TanquesProdutoComposto.tipo_peca.label('tipo_peca'),
            ProdutoComposto.id.label('produto_composto_id'),
            ProdutoComposto.nome.label('produto_composto_nome'),
            func.count(TanquesPecas.id).label('quantidade_produzida'),
        ).join(
            Tanques, Tanques.id == TanquesProdutoComposto.tanque_id
        ).join(
            ProdutoComposto, ProdutoComposto.id == TanquesProdutoComposto.produto_composto_id
        ).outerjoin(
            TanquesGrupos, Tanques.grupos
        ).outerjoin(
            TanquesPecas, join_pecas_produzidas
        )

        if tanque_id_int:
            q = q.filter(TanquesProdutoComposto.tanque_id == tanque_id_int)

        rows = q.group_by(
            TanquesProdutoComposto.id,
            Tanques.id,
            Tanques.nome,
            TanquesProdutoComposto.tipo_peca,
            ProdutoComposto.id,
            ProdutoComposto.nome,
        ).order_by(Tanques.nome.asc(), TanquesProdutoComposto.tipo_peca.asc(), ProdutoComposto.nome.asc()).all()

        # Agregar por (grupo_label, tipo_peca, produto_composto_id)
        agregados = {}  # (grupo_label, tipo_peca, produto_id) -> dict
        for r in rows:
            grupos_lista = []
            if r.tanques_grupos:
                try:
                    grupos_lista = [g.strip() for g in str(r.tanques_grupos).split(',') if g and str(g).strip()]
                except Exception:
                    grupos_lista = []

            grupos_efetivos = grupos_lista if grupos_lista else ['Sem grupo']
            for grupo_label in grupos_efetivos:
                chave = (grupo_label, r.tipo_peca, int(r.produto_composto_id))
                if chave not in agregados:
                    agregados[chave] = {
                        'grupo_label': grupo_label,
                        'tipo_peca': r.tipo_peca,
                        'produto_composto_id': int(r.produto_composto_id),
                        'produto_composto_nome': r.produto_composto_nome,
                        'quantidade_produzida': 0,
                    }
                agregados[chave]['quantidade_produzida'] += int(r.quantidade_produzida or 0)

        opcoes = list(agregados.values())
        opcoes.sort(key=lambda x: (x.get('grupo_label') or '', x.get('tipo_peca') or '', x.get('produto_composto_nome') or ''))
        return jsonify({'success': True, 'opcoes': opcoes}), 200
    except Exception as e:
        logger.error(f'Erro ao buscar opções da simulação: {str(e)}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@estoque_terceiro_bp.route('/api/simulacao/produtos-estrutura', methods=['GET'])
@login_required
def api_simulacao_produtos_estrutura():
    """
    Retorna a estrutura de materiais por unidade para uma lista de produtos compostos.
    Resposta:
      {
        success: true,
        estruturas: {
          "<produto_id>": { "<material_id>": qtd_por_unidade, ... }
        }
      }
    """
    try:
        ids_raw = (request.args.get('ids') or '').strip()
        if not ids_raw:
            return jsonify({'success': True, 'estruturas': {}}), 200

        produto_ids = []
        for token in ids_raw.split(','):
            s = (token or '').strip()
            if not s:
                continue
            try:
                produto_ids.append(int(s))
            except (TypeError, ValueError):
                continue

        if not produto_ids:
            return jsonify({'success': True, 'estruturas': {}}), 200

        estruturas = {}
        produtos = ProdutoComposto.query.filter(ProdutoComposto.id.in_(produto_ids)).all()
        hoje = datetime.now().date()

        for produto in produtos:
            if not produto:
                continue

            materiais_necessarios = {}
            produtos_processados = set()
            try:
                produto.produzir(
                    quantidade=1,
                    data_movimento=hoje,
                    usuario_id=current_user.id if current_user else 1,
                    log=False,
                    produtos_processados=produtos_processados,
                    materiais_necessarios=materiais_necessarios,
                )
            except Exception as e:
                logger.warning(
                    f'Erro ao calcular estrutura para produto composto {produto.id}: {str(e)}'
                )
                continue

            estrutura_produto = {}
            for _, info in (materiais_necessarios or {}).items():
                estoque = info.get('estoque') if isinstance(info, dict) else None
                if not estoque or getattr(estoque, 'tipo_item', None) != 'material' or not estoque.material_id:
                    continue

                qtd = info.get('quantidade') if isinstance(info, dict) else 0
                try:
                    qtd_float = float(qtd or 0)
                except (TypeError, ValueError):
                    qtd_float = 0.0

                if qtd_float == 0:
                    continue

                mid = str(int(estoque.material_id))
                estrutura_produto[mid] = estrutura_produto.get(mid, 0.0) + qtd_float

            estruturas[str(produto.id)] = estrutura_produto

        return jsonify({'success': True, 'estruturas': estruturas}), 200
    except Exception as e:
        logger.error(f'Erro ao buscar estrutura de produtos para simulação: {str(e)}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@estoque_terceiro_bp.route('/api/simulacao/consumo', methods=['POST'])
@login_required
def api_simulacao_consumo():
    """
    Calcula consumo por material baseado em itens da simulação.
    Espera JSON: { itens: [{ grupo_label, tipo_peca, produto_composto_id, quantidade }] }
    Onde `quantidade` é a quantidade A PRODUZIR (futura) para aquele grupo/tipo/produto.
    """
    try:
        payload = request.get_json(silent=True) or {}
        itens = payload.get('itens') or []
        if not isinstance(itens, list):
            return jsonify({'success': False, 'message': 'Payload inválido: itens deve ser lista.'}), 400

        consumo_por_material: dict[int, float] = {}
        grupos = []
        hoje = datetime.now().date()

        for item in itens:
            if not isinstance(item, dict):
                continue
            grupo_label = (item.get('grupo_label') or '').strip()
            tipo_peca = (item.get('tipo_peca') or '').strip()
            produto_id = item.get('produto_composto_id')
            try:
                quantidade = float(item.get('quantidade') or 0)
            except (TypeError, ValueError):
                quantidade = 0

            if not produto_id or not tipo_peca or quantidade <= 0:
                continue

            produto = ProdutoComposto.query.get(int(produto_id))
            if not produto:
                continue

            materiais_necessarios = {}
            produtos_processados = set()
            try:
                produto.produzir(
                    quantidade=quantidade,
                    data_movimento=hoje,
                    usuario_id=current_user.id if current_user else 1,
                    log=False,
                    produtos_processados=produtos_processados,
                    materiais_necessarios=materiais_necessarios,
                )
            except Exception as e:
                logger.warning(f'Erro ao calcular consumo simulado para produto {produto_id}: {str(e)}')
                continue

            materiais_grupo: dict[int, float] = {}
            for estoque_id, info in materiais_necessarios.items():
                estoque = info.get('estoque')
                if not estoque or getattr(estoque, 'tipo_item', None) != 'material' or not estoque.material_id:
                    continue
                qtd = info.get('quantidade')
                if qtd is None:
                    continue
                try:
                    qtd_float = float(qtd)
                except (TypeError, ValueError):
                    qtd_float = 0.0
                if qtd_float == 0:
                    continue
                mid = int(estoque.material_id)
                materiais_grupo[mid] = materiais_grupo.get(mid, 0.0) + qtd_float
                consumo_por_material[mid] = consumo_por_material.get(mid, 0.0) + qtd_float

            chave_grupo = f"{grupo_label}_{tipo_peca}_{int(produto_id)}"
            grupos.append({
                'chave_grupo': chave_grupo,
                'grupo_label': grupo_label,
                'tipo': tipo_peca,
                'produto_composto_id': int(produto_id),
                'produto_nome': (produto.nome or '').strip(),
                'quantidade_pecas': float(quantidade),
                'materiais': materiais_grupo,
            })

        return jsonify({
            'success': True,
            'consumo_por_material': consumo_por_material,
            'grupos': grupos,
        }), 200
    except Exception as e:
        logger.error(f'Erro ao calcular consumo da simulação: {str(e)}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
