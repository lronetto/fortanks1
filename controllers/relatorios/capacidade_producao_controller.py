from flask import Blueprint, render_template, request, send_file, jsonify
from flask_login import login_required
from models.tanque import Tanques, TanquesPecas, TanquesProdutoComposto
from models.produto_composto import ProdutoComposto, ProdutoCompostoItem
from models.contrato import Contrato
from models.database import db
from models.estoque import Estoque
from collections import defaultdict
from datetime import datetime
import json
import pandas as pd
import io
from weasyprint import HTML, CSS
import os
from sqlalchemy import case, func
from sqlalchemy.orm import selectinload
from decimal import Decimal

capacidade_producao_bp = Blueprint('relatorios_capacidade_producao', __name__, url_prefix='/relatorios/capacidade-producao')


def _peca_qualidade_tem_data_producao(qualidade_raw):
    """
    True se a peça tem registro de produção (data_producao preenchida no JSON qualidade).
    Considera formato na raiz ou em dados_adicionais (compatível com cadastros antigos).
    """
    if not qualidade_raw:
        return False
    try:
        q = json.loads(qualidade_raw) if isinstance(qualidade_raw, str) else qualidade_raw
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(q, dict):
        return False

    def _truthy(val):
        if val is None:
            return False
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        return s not in ("", "null", "none")

    if _truthy(q.get("data_producao")):
        return True
    da = q.get("dados_adicionais")
    if isinstance(da, dict) and _truthy(da.get("data_producao")):
        return True
    return False


def _contagem_produzidas_por_tanque_tipo(tanque_id_list):
    """Quantidade de placas já produzidas (data_producao) por (tanque_id, tipo)."""
    if not tanque_id_list:
        return {}
    rows = (
        db.session.query(
            TanquesPecas.tanque_id,
            TanquesPecas.tipo,
            TanquesPecas.qualidade,
        )
        .filter(TanquesPecas.tanque_id.in_(tanque_id_list))
        .all()
    )
    counts = defaultdict(int)
    for tanque_id, tipo, qualidade in rows:
        if _peca_qualidade_tem_data_producao(qualidade):
            counts[(tanque_id, tipo)] += 1
    return counts


def _contagem_produzidas_por_tanque(tanque_id_list):
    """Total de placas já produzidas por tanque (todas as peças do tanque)."""
    if not tanque_id_list:
        return {}
    rows = (
        db.session.query(TanquesPecas.tanque_id, TanquesPecas.qualidade)
        .filter(TanquesPecas.tanque_id.in_(tanque_id_list))
        .all()
    )
    counts = defaultdict(int)
    for tanque_id, qualidade in rows:
        if _peca_qualidade_tem_data_producao(qualidade):
            counts[tanque_id] += 1
    return counts


def _pecas_metricas_por_tanque_tipo(tanque_id_list):
    """
    Por (tanque_id, tipo): (prevista, produzidas, concretadas).
    concretadas = data_concretagem preenchida; produzidas = data_producao no JSON qualidade.
    """
    if not tanque_id_list:
        return {}
    rows_agg = (
        db.session.query(
            TanquesPecas.tanque_id,
            TanquesPecas.tipo,
            func.count(TanquesPecas.id).label("qtd_prevista"),
            func.sum(
                case((TanquesPecas.data_concretagem.isnot(None), 1), else_=0)
            ).label("qtd_concretada"),
        )
        .filter(TanquesPecas.tanque_id.in_(tanque_id_list))
        .group_by(TanquesPecas.tanque_id, TanquesPecas.tipo)
        .all()
    )
    produzidas = _contagem_produzidas_por_tanque_tipo(tanque_id_list)
    out = {}
    for row in rows_agg:
        key = (row.tanque_id, row.tipo)
        out[key] = (
            int(row.qtd_prevista or 0),
            int(produzidas.get(key, 0)),
            int(row.qtd_concretada or 0),
        )
    return out


def _expandir_materiais_produto_composto(produto_id, quantidade_base=1.0, caminho_atual=None):
    """
    Função recursiva para expandir todos os componentes de um produto composto
    até chegar apenas em materiais, considerando produtos compostos aninhados.
    Retorna um dicionário agrupado por material_id com as quantidades totais.
    """
    if caminho_atual is None:
        caminho_atual = []
    
    # Evitar loops infinitos
    if produto_id in caminho_atual:
        return {}
    
    novo_caminho = caminho_atual + [produto_id]
    
    produto = ProdutoComposto.query.get(produto_id)
    if not produto:
        return {}
    
    materiais_agrupados = {}  # material_id -> {'material_nome': ..., 'quantidade': ..., 'unidade': ...}
    
    for componente in produto.componentes:
        if not componente.estoque:
            continue
        
        quantidade_componente = float(componente.quantidade) * quantidade_base
        
        if componente.estoque.tipo_item == 'material' and componente.estoque.material:
            # É um material direto
            material_id = componente.estoque.material.id
            if material_id in materiais_agrupados:
                materiais_agrupados[material_id]['quantidade'] += quantidade_componente
            else:
                unidade = componente.estoque.material.unidade_obj.nome if (
                    componente.estoque.material.unidade_obj and 
                    hasattr(componente.estoque.material.unidade_obj, 'nome')
                ) else ''
                materiais_agrupados[material_id] = {
                    'material_id': material_id,
                    'material_nome': componente.estoque.material.nome,
                    'quantidade': quantidade_componente,
                    'unidade': unidade,
                    'estoque_id': componente.estoque_id
                }
        elif componente.estoque.tipo_item == 'produto_composto' and componente.estoque.ProdComp_id:
            # É um produto composto aninhado - processar recursivamente
            produto_composto_id = componente.estoque.ProdComp_id
            materiais_aninhados = _expandir_materiais_produto_composto(
                produto_composto_id,
                quantidade_componente,
                novo_caminho
            )
            # Agrupar materiais aninhados
            for material_id, info in materiais_aninhados.items():
                if material_id in materiais_agrupados:
                    materiais_agrupados[material_id]['quantidade'] += info['quantidade']
                else:
                    materiais_agrupados[material_id] = info
    
    return materiais_agrupados


def _totais_estoque_por_material(material_ids):
    """
    Soma estoque atual por material_id em uma leitura de Estoque (evita N queries).
    """
    if not material_ids:
        return {}
    itens = Estoque.query.filter(
        Estoque.material_id.in_(material_ids),
        Estoque.tipo_item == "material",
    ).all()
    por_material = defaultdict(list)
    for item in itens:
        if item.material_id is not None:
            por_material[item.material_id].append(item)
    totais = {}
    for mid in material_ids:
        total = 0.0
        for item_estoque in por_material.get(mid, ()):
            try:
                if hasattr(item_estoque, "get_estoque_atual"):
                    estoque_item = item_estoque.get_estoque_atual()
                else:
                    estoque_item = float(item_estoque.quantidade or 0)
                total += float(estoque_item)
            except Exception:
                total += float(item_estoque.quantidade or 0)
        totais[mid] = total
    return totais


def get_dados_materiais_agrupados(
    contrato_id=None,
    tanque_id=None,
    tanque_ids=None,
    incluir_produtos_compostos=False,
    pecas_prev_prod_map=None,
):
    """
    Busca dados de materiais agrupados por material, com somatórios nas colunas.
    tanque_id: um único tanque (legado). tanque_ids: lista de IDs para múltipla seleção.
    pecas_prev_prod_map: opcional, dict (tanque_id, tipo) -> (prevista, produzidas, concretadas).
    """
    print("iniciando get_dados_materiais_agrupados")
    # Sem join em coleção 1:N: evita linhas duplicadas de Tanques e custo inútil.
    # Vinculações e produto_composto vêm em 2 queries extras (selectinload), não N+1.
    query = Tanques.query.options(
        selectinload(Tanques.produtos_compostos_vinculados).selectinload(
            TanquesProdutoComposto.produto_composto
        )
    )

    tiniciao = datetime.now()
    # Aplicar filtros (tanque_ids tem prioridade sobre tanque_id)
    if tanque_ids:
        query = query.filter(Tanques.id.in_(tanque_ids))
    elif tanque_id:
        query = query.filter(Tanques.id == tanque_id)

    if contrato_id:
        query = query.filter(Tanques.contrato_id == contrato_id)

    tanques = query.order_by(Tanques.nome).all()
    fim = datetime.now()
    print(f'Tempo de execução11: {fim - tiniciao}')
    tiniciao = datetime.now()

    # Por (tanque_id, tipo): prevista em TanquesPecas e placas já produzidas (data_producao em qualidade).
    tanque_id_list = [t.id for t in tanques]
    if pecas_prev_prod_map is not None:
        pecas_por_tanque_tipo = pecas_prev_prod_map
    else:
        pecas_por_tanque_tipo = (
            _pecas_metricas_por_tanque_tipo(tanque_id_list) if tanque_id_list else {}
        )

    # Pré-cálculo: expansão por produto (evita recursão/query repetida por vínculo) + estoque em lote.
    produto_composto_ids = set()
    for t in tanques:
        for v in t.produtos_compostos_vinculados:
            if v and v.produto_composto:
                produto_composto_ids.add(v.produto_composto.id)
    expandir_por_produto = {
        pc_id: _expandir_materiais_produto_composto(pc_id, 1.0) for pc_id in produto_composto_ids
    }
    material_ids_afetados = set()
    for materiais_map in expandir_por_produto.values():
        material_ids_afetados.update(materiais_map.keys())
    estoque_total_por_material = _totais_estoque_por_material(material_ids_afetados)

    print(f'Tempo de execução12: {datetime.now() - tiniciao}')
    # Dicionário para agrupar materiais: material_id -> dados do material
    materiais_agrupados = {}
    # Dicionário para rastrear produtos compostos por material
    produtos_compostos_por_material = {}  # material_id -> lista de produtos compostos
    
    for tanque in tanques:
        # Buscar TODOS os produtos compostos vinculados ao tanque
        #vinculacoes = TanquesProdutoComposto.query.filter_by(
        #    tanque_id=tanque.id
        #).all()
        vinculacoes = tanque.produtos_compostos_vinculados
        # Processar cada produto composto vinculado
        for vinculacao in vinculacoes:
            if not vinculacao or not vinculacao.produto_composto:
                continue
                
            produto_composto = vinculacao.produto_composto
            tipo_peca = vinculacao.tipo_peca

            quantidade_prevista, pecas_produzidas, pecas_concretadas = pecas_por_tanque_tipo.get(
                (tanque.id, tipo_peca), (0, 0, 0)
            )

            pecas_restantes = quantidade_prevista - pecas_produzidas

            materiais_por_peca = expandir_por_produto.get(produto_composto.id) or {}

            # Agrupar materiais
            for material_id, info_por_peca in materiais_por_peca.items():
                quantidade_por_peca = info_por_peca['quantidade']

                if material_id not in materiais_agrupados:
                    estoque_total = float(estoque_total_por_material.get(material_id, 0.0))

                    materiais_agrupados[material_id] = {
                        'material_id': material_id,
                        'material_nome': info_por_peca['material_nome'],
                        'unidade': info_por_peca['unidade'],
                        'estoque_atual': estoque_total,  # Já é float
                        'quantidade_necessaria': 0.0,
                        'quantidade_prevista_total': 0.0,
                        'quantidade_concretada_total': 0.0,
                        'quantidade_restante_total': 0.0
                    }
                    produtos_compostos_por_material[material_id] = []
                
                # Rastrear produto composto para este material
                if incluir_produtos_compostos:
                    produto_info = {
                        'produto_composto_id': produto_composto.id,
                        'produto_composto_nome': produto_composto.nome,
                        'tanque_id': tanque.id,
                        'tanque_nome': tanque.nome,
                        'tipo_peca': tipo_peca,
                        'quantidade_por_peca': float(quantidade_por_peca),
                        'quantidade_prevista': quantidade_prevista,
                        'pecas_produzidas': pecas_produzidas,
                        'pecas_concretadas': pecas_concretadas,
                        'pecas_restantes': pecas_restantes,
                        'quantidade_prevista_total': float(quantidade_por_peca) * float(quantidade_prevista),
                        'quantidade_concretada_total': float(quantidade_por_peca) * float(pecas_produzidas),
                        'quantidade_restante_total': float(quantidade_por_peca) * float(pecas_restantes)
                    }
                    produtos_compostos_por_material[material_id].append(produto_info)
                
                # Somar quantidades (garantir que são floats)
                quantidade_por_peca_float = float(quantidade_por_peca)
                pecas_restantes_float = float(pecas_restantes)
                quantidade_prevista_float = float(quantidade_prevista)
                pecas_produzidas_float = float(pecas_produzidas)
                
                materiais_agrupados[material_id]['quantidade_necessaria'] += quantidade_por_peca_float * pecas_restantes_float
                materiais_agrupados[material_id]['quantidade_prevista_total'] += quantidade_por_peca_float * quantidade_prevista_float
                materiais_agrupados[material_id]['quantidade_concretada_total'] += quantidade_por_peca_float * pecas_produzidas_float
                materiais_agrupados[material_id]['quantidade_restante_total'] += quantidade_por_peca_float * pecas_restantes_float
    fim = datetime.now()
    print(f'Tempo de execução13: {fim - tiniciao}')
    tiniciao = datetime.now()
    # Converter para lista e calcular valores finais
    dados = []
    for material_id, info in materiais_agrupados.items():
        # Converter para float para evitar problemas com Decimal
        estoque_atual = float(info['estoque_atual'])
        quantidade_necessaria = float(info['quantidade_necessaria'])
        
        estoque_disponivel = estoque_atual - quantidade_necessaria
        percentual_uso = (quantidade_necessaria / estoque_atual * 100) if estoque_atual > 0 else 0
        
        item_dados = {
            'material_id': material_id,
            'material_nome': info['material_nome'],
            'unidade': info['unidade'],
            'estoque_atual': round(estoque_atual, 2),
            'quantidade_necessaria': round(quantidade_necessaria, 2),
            'quantidade_prevista_total': round(float(info['quantidade_prevista_total']), 2),
            'quantidade_concretada_total': round(float(info['quantidade_concretada_total']), 2),
            'quantidade_restante_total': round(float(info['quantidade_restante_total']), 2),
            'estoque_disponivel': round(estoque_disponivel, 2),
            'percentual_uso': round(percentual_uso, 2),
            'suficiente': estoque_disponivel >= 0
        }
        
        if incluir_produtos_compostos and material_id in produtos_compostos_por_material:
            item_dados['produtos_compostos'] = produtos_compostos_por_material[material_id]
        
        dados.append(item_dados)
    print(f'Tempo de execução13: {datetime.now() - tiniciao}')
    # Ordenar por nome do material
    dados.sort(key=lambda x: x['material_nome'])
    
    return dados

def get_dados_capacidade_producao(contrato_id=None, tanque_id=None, tanque_ids=None):
    """
    Busca dados de capacidade de produção por tanque, considerando produto composto vinculado.
    tanque_id: um único tanque (legado). tanque_ids: lista de IDs para múltipla seleção.
    """
    query = Tanques.query
    
    # Aplicar filtros
    if tanque_ids:
        query = query.filter(Tanques.id.in_(tanque_ids))
    elif tanque_id:
        query = query.filter(Tanques.id == tanque_id)
    
    if contrato_id:
        query = query.filter(Tanques.contrato_id == contrato_id)
    
    tanques = query.order_by(Tanques.nome).all()
    tanque_ids_cap = [t.id for t in tanques]
    produzidas_por_tanque = _contagem_produzidas_por_tanque(tanque_ids_cap)

    dados = []
    for tanque in tanques:
        # Calcular quantidade prevista: (placas_normais + placas_fecho) * quantidade
        placas_normais = tanque.placas_normais or 0
        placas_fecho = tanque.placas_fecho or 0
        quantidade_tanques = tanque.quantidade or 1
        quantidade_prevista = (placas_normais + placas_fecho) * quantidade_tanques

        pecas_produzidas = int(produzidas_por_tanque.get(tanque.id, 0))
        
        # Buscar TODOS os produtos compostos vinculados ao tanque
        vinculacoes = TanquesProdutoComposto.query.filter_by(
            tanque_id=tanque.id
        ).all()
        
        # Para esta função, vamos considerar apenas o primeiro produto composto
        # (mantendo compatibilidade com código existente)
        produto_composto = None
        tempo_producao_por_peca = 0
        tempo_total_estimado = 0
        tempo_utilizado = 0
        capacidade_restante_horas = 0
        capacidade_restante_pecas = 0
        percentual_utilizacao = 0
        
        if vinculacoes and len(vinculacoes) > 0 and vinculacoes[0].produto_composto:
            produto_composto = vinculacoes[0].produto_composto
            # Tempo de produção por peça (em horas)
            tempo_producao_por_peca = float(produto_composto.tempo_producao or 0)
            
            # Calcular tempo total estimado para produção completa
            tempo_total_estimado = tempo_producao_por_peca * quantidade_prevista
            
            # Tempo já utilizado: apenas placas já produzidas (registro data_producao)
            tempo_utilizado = tempo_producao_por_peca * pecas_produzidas

            # Calcular capacidade restante
            capacidade_restante_horas = tempo_total_estimado - tempo_utilizado
            capacidade_restante_pecas = quantidade_prevista - pecas_produzidas
            
            # Calcular percentual de utilização
            if tempo_total_estimado > 0:
                percentual_utilizacao = (tempo_utilizado / tempo_total_estimado) * 100
        
        dados.append({
            'id': tanque.id,
            'nome': tanque.nome,
            'contrato': tanque.contrato.nome if tanque.contrato else 'Sem contrato',
            'contrato_id': tanque.contrato_id,
            'sistema': tanque.sistema,
            'dimensoes': tanque.dimensoes,
            'quantidade_prevista': quantidade_prevista,
            'pecas_produzidas': pecas_produzidas,
            'pecas_concretadas': pecas_produzidas,
            'pecas_restantes': quantidade_prevista - pecas_produzidas,
            'produto_composto_id': produto_composto.id if produto_composto else None,
            'produto_composto_nome': produto_composto.nome if produto_composto else 'Não vinculado',
            'tempo_producao_por_peca': round(tempo_producao_por_peca, 2),
            'tempo_total_estimado': round(tempo_total_estimado, 2),
            'tempo_utilizado': round(tempo_utilizado, 2),
            'capacidade_restante_horas': round(capacidade_restante_horas, 2),
            'capacidade_restante_pecas': capacidade_restante_pecas,
            'percentual_utilizacao': round(percentual_utilizacao, 2),
            'percentual_conclusao': round((pecas_produzidas / quantidade_prevista * 100) if quantidade_prevista > 0 else 0, 2),
        })
    
    return dados

def agrupar_por_projeto(dados):
    """
    Agrupa dados de capacidade de produção por projeto
    """
    projetos = {}
    
    for item in dados:
        projeto_nome = item['contrato']
        if projeto_nome not in projetos:
            projetos[projeto_nome] = {
                'quantidade_tanques': 0,
                'quantidade_prevista': 0,
                'pecas_concretadas': 0,
                'tempo_total_estimado': 0,
                'tempo_utilizado': 0,
                'capacidade_restante_horas': 0,
            }
        
        projetos[projeto_nome]['quantidade_tanques'] += 1
        projetos[projeto_nome]['quantidade_prevista'] += item['quantidade_prevista']
        projetos[projeto_nome]['pecas_concretadas'] += item['pecas_concretadas']
        projetos[projeto_nome]['tempo_total_estimado'] += item['tempo_total_estimado']
        projetos[projeto_nome]['tempo_utilizado'] += item['tempo_utilizado']
        projetos[projeto_nome]['capacidade_restante_horas'] += item['capacidade_restante_horas']
    
    # Calcular percentuais
    for projeto_nome, dados_projeto in projetos.items():
        if dados_projeto['tempo_total_estimado'] > 0:
            dados_projeto['percentual_utilizacao'] = round(
                (dados_projeto['tempo_utilizado'] / dados_projeto['tempo_total_estimado']) * 100, 2
            )
        else:
            dados_projeto['percentual_utilizacao'] = 0
        
        if dados_projeto['quantidade_prevista'] > 0:
            dados_projeto['percentual_conclusao'] = round(
                (dados_projeto['pecas_concretadas'] / dados_projeto['quantidade_prevista']) * 100, 2
            )
        else:
            dados_projeto['percentual_conclusao'] = 0
    
    return projetos

@capacidade_producao_bp.route('/', methods=['GET'])
@login_required
def index():
    """Página principal do relatório de capacidade de produção"""
    contrato_id = request.args.get('contrato_id', type=int)
    
    # Buscar contratos ativos
    contratos = Contrato.query.filter_by(ativo=True).order_by(Contrato.nome).all()
    
    # Buscar tanques para filtro
    tanques_query = Tanques.query.outerjoin(Contrato)
    if contrato_id:
        tanques_query = tanques_query.filter(Tanques.contrato_id == contrato_id)
    tanques = tanques_query.order_by(Tanques.nome).all()
    

    return render_template(
        'relatorios/capacidade_producao/index.html',
        contratos=contratos,
        tanques=tanques,
        contrato_id=contrato_id,
        
    )

@capacidade_producao_bp.route('/api/tanques-por-projeto', methods=['GET'])
@login_required
def api_tanques_por_projeto():
    """API para buscar tanques filtrados por projeto"""
    contrato_id = request.args.get('contrato_id', type=int)
    
    query = Tanques.query.outerjoin(Contrato)
    
    if contrato_id:
        query = query.filter(Tanques.contrato_id == contrato_id)
    
    tanques = query.order_by(Tanques.nome).all()
    
    tanques_json = [{'id': t.id, 'nome': t.nome} for t in tanques]
    
    return jsonify({'tanques': tanques_json})

@capacidade_producao_bp.route('/api/detalhes-tanque/<int:tanque_id>', methods=['GET'])
@login_required
def api_detalhes_tanque(tanque_id):
    """API para buscar detalhes de capacidade de produção de um tanque específico"""
    try:
        tanque = Tanques.query.get_or_404(tanque_id)
        
        # Calcular quantidade prevista
        placas_normais = tanque.placas_normais or 0
        placas_fecho = tanque.placas_fecho or 0
        quantidade_tanques = tanque.quantidade or 1
        quantidade_prevista = (placas_normais + placas_fecho) * quantidade_tanques

        pecas_produzidas = int(
            _contagem_produzidas_por_tanque([tanque.id]).get(tanque.id, 0)
        )

        # Buscar TODOS os produtos compostos vinculados
        vinculacoes = TanquesProdutoComposto.query.filter_by(
            tanque_id=tanque.id
        ).all()
        
        produto_composto = None
        componentes = []
        tempo_producao_por_peca = 0
        tempo_total_estimado = 0
        tempo_utilizado = 0
        capacidade_restante_horas = 0
        capacidade_restante_pecas = 0
        percentual_utilizacao = 0
        
        # Para esta função de detalhes, vamos considerar apenas o primeiro produto composto
        if vinculacoes and len(vinculacoes) > 0 and vinculacoes[0].produto_composto:
            produto_composto = vinculacoes[0].produto_composto
            tempo_producao_por_peca = float(produto_composto.tempo_producao or 0)
            tempo_total_estimado = tempo_producao_por_peca * quantidade_prevista
            tempo_utilizado = tempo_producao_por_peca * pecas_produzidas
            capacidade_restante_horas = tempo_total_estimado - tempo_utilizado
            capacidade_restante_pecas = quantidade_prevista - pecas_produzidas
            
            if tempo_total_estimado > 0:
                percentual_utilizacao = (tempo_utilizado / tempo_total_estimado) * 100
            
            # Buscar componentes do produto composto (visão direta)
            for componente in produto_composto.componentes:
                try:
                    estoque = componente.estoque.get_estoque_atual() if hasattr(componente.estoque, 'get_estoque_atual') else (float(componente.estoque.quantidade) if componente.estoque else 0)
                except:
                    estoque = float(componente.estoque.quantidade) if componente.estoque and componente.estoque.quantidade else 0
                
                capacidade = 0
                if componente.quantidade > 0 and estoque > 0:
                    capacidade = estoque / float(componente.quantidade)
                
                componentes.append({
                    'estoque_id': componente.estoque_id,
                    'quantidade': format(float(componente.quantidade), '.2f'),
                    'quantidade_total': format(float(componente.quantidade * quantidade_prevista), '.2f'),
                    'nome': componente.estoque.material.nome if componente.estoque.material_id else (componente.estoque.produto_composto.nome if componente.estoque.produto_composto else 'N/A'),
                    'estoque': format(float(estoque if estoque else 0), '.2f'),
                    'capacidade': format(float(capacidade), '.2f'),
                    'valor_unitario': format(float(componente.get_valor_unitario()), '.2f'),
                    'valor_total': format(float(componente.get_valor_total() * quantidade_prevista), '.2f')
                })
            
            # Expandir materiais para uso futuro: placas ainda não produzidas
            pecas_restantes = quantidade_prevista - pecas_produzidas
            materiais_expandidos = _expandir_materiais_produto_composto(produto_composto.id, pecas_restantes)
            
            # Calcular estoque e previsto para cada material
            materiais_estoque = []
            for material_id, info in materiais_expandidos.items():
                # Buscar todos os itens de estoque deste material
                itens_estoque = Estoque.query.filter_by(material_id=material_id, tipo_item='material').all()
                estoque_total = 0
                for item_estoque in itens_estoque:
                    try:
                        estoque_item = item_estoque.get_estoque_atual() if hasattr(item_estoque, 'get_estoque_atual') else float(item_estoque.quantidade or 0)
                        estoque_total += estoque_item
                    except:
                        estoque_total += float(item_estoque.quantidade or 0)
                
                quantidade_necessaria = info['quantidade']
                estoque_disponivel = estoque_total - quantidade_necessaria
                percentual_uso = (quantidade_necessaria / estoque_total * 100) if estoque_total > 0 else 0
                
                materiais_estoque.append({
                    'material_id': material_id,
                    'material_nome': info['material_nome'],
                    'unidade': info['unidade'],
                    'quantidade_necessaria': format(quantidade_necessaria, '.2f'),
                    'estoque_atual': format(estoque_total, '.2f'),
                    'estoque_disponivel': format(estoque_disponivel, '.2f'),
                    'percentual_uso': round(percentual_uso, 2),
                    'suficiente': estoque_disponivel >= 0
                })
            
            # Ordenar por nome do material
            materiais_estoque.sort(key=lambda x: x['material_nome'])
        else:
            # Se não há produto composto vinculado, inicializar variáveis vazias
            materiais_estoque = []
        
        return jsonify({
            'success': True,
            'tanque': {
                'id': tanque.id,
                'nome': tanque.nome,
                'contrato': tanque.contrato.nome if tanque.contrato else 'Sem contrato',
                'sistema': tanque.sistema,
                'dimensoes': tanque.dimensoes,
            },
            'produto_composto': {
                'id': produto_composto.id if produto_composto else None,
                'nome': produto_composto.nome if produto_composto else 'Não vinculado',
            },
            'quantidade_prevista': quantidade_prevista,
            'pecas_produzidas': pecas_produzidas,
            'pecas_concretadas': pecas_produzidas,
            'pecas_restantes': quantidade_prevista - pecas_produzidas,
            'tempo_producao_por_peca': round(tempo_producao_por_peca, 2),
            'tempo_total_estimado': round(tempo_total_estimado, 2),
            'tempo_utilizado': round(tempo_utilizado, 2),
            'capacidade_restante_horas': round(capacidade_restante_horas, 2),
            'capacidade_restante_pecas': capacidade_restante_pecas,
            'percentual_utilizacao': round(percentual_utilizacao, 2),
            'percentual_conclusao': round((pecas_produzidas / quantidade_prevista * 100) if quantidade_prevista > 0 else 0, 2),
            'componentes': componentes,
            'materiais_estoque': materiais_estoque,
            'valor_total': format(float(produto_composto.get_valor_total() * quantidade_prevista), '.2f') if produto_composto else '0.00'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao obter detalhes: {str(e)}'}), 500

@capacidade_producao_bp.route('/api/dados', methods=['GET'])
@login_required
def api_dados():
    """Endpoint AJAX para buscar dados do relatório"""
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_id = request.args.get('tanque_id', type=int)
    
    dados = get_dados_capacidade_producao(contrato_id=contrato_id, tanque_id=tanque_id)
    projetos = agrupar_por_projeto(dados)
    
    # Calcular totais
    total_tanques = len(dados)
    total_previsto = sum([item['quantidade_prevista'] for item in dados])
    total_concretadas = sum([item['pecas_concretadas'] for item in dados])
    total_tempo_estimado = sum([item['tempo_total_estimado'] for item in dados])
    total_tempo_utilizado = sum([item['tempo_utilizado'] for item in dados])
    total_capacidade_restante = sum([item['capacidade_restante_horas'] for item in dados])
    percentual_geral_utilizacao = round((total_tempo_utilizado / total_tempo_estimado * 100) if total_tempo_estimado > 0 else 0, 2)
    percentual_geral_conclusao = round((total_concretadas / total_previsto * 100) if total_previsto > 0 else 0, 2)
    
    # Preparar dados para gráficos
    labels_projetos = list(projetos.keys()) if projetos else []
    valores_utilizacao = [projetos[p]['percentual_utilizacao'] for p in labels_projetos] if labels_projetos else []
    valores_tempo_estimado = [projetos[p]['tempo_total_estimado'] for p in labels_projetos] if labels_projetos else []
    valores_tempo_utilizado = [projetos[p]['tempo_utilizado'] for p in labels_projetos] if labels_projetos else []
    
    return jsonify({
        'dados': dados,
        'projetos': projetos,
        'labels_projetos': labels_projetos,
        'valores_utilizacao': valores_utilizacao,
        'valores_tempo_estimado': valores_tempo_estimado,
        'valores_tempo_utilizado': valores_tempo_utilizado,
        'total_tanques': total_tanques,
        'total_previsto': total_previsto,
        'total_concretadas': total_concretadas,
        'total_tempo_estimado': round(total_tempo_estimado, 2),
        'total_tempo_utilizado': round(total_tempo_utilizado, 2),
        'total_capacidade_restante': round(total_capacidade_restante, 2),
        'percentual_geral_utilizacao': percentual_geral_utilizacao,
        'percentual_geral_conclusao': percentual_geral_conclusao
    })

def _parse_tanque_ids():
    """Obtém lista de IDs de tanques a partir da requisição (suporta múltipla seleção)."""
    tanque_ids = request.args.getlist('tanque_id') or request.args.getlist('tanque_id[]')
    if not tanque_ids:
        return None
    result = []
    for tid in tanque_ids:
        try:
            result.append(int(tid))
        except (TypeError, ValueError):
            continue
    return result if result else None


def _parse_filtro_flag(nome_param):
    """Interpreta 1/true da query string como filtro ativo."""
    v = request.args.get(nome_param)
    if v is None or v == "":
        return False
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes", "on"):
        return True
    try:
        return int(v) == 1
    except (TypeError, ValueError):
        return False


def _filtrar_materiais_relatorio(dados, apenas_restante, apenas_insuficientes):
    """Filtra linhas de materiais: restante > 0 e/ou estoque insuficiente."""
    if not dados:
        return []
    out = list(dados)
    if apenas_restante:
        out = [
            x
            for x in out
            if float(x.get("quantidade_restante_total", 0) or 0) > 0
        ]
    if apenas_insuficientes:
        out = [x for x in out if not x.get("suficiente", True)]
    return out


def _filtrar_produtos_compostos_restante(produtos_lista, apenas_restante):
    """Mantém apenas produtos com peças restantes > 0."""
    if not apenas_restante or not produtos_lista:
        return produtos_lista
    return [
        p
        for p in produtos_lista
        if int(p.get("total_pecas_restantes", 0) or 0) > 0
    ]


@capacidade_producao_bp.route('/api/dados-materiais', methods=['GET'])
@login_required
def api_dados_materiais():
    """Endpoint AJAX para buscar dados de materiais em formato DataTables"""
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_ids = _parse_tanque_ids()
    tanque_id = request.args.get('tanque_id', type=int) if not tanque_ids else None
    apenas_restante = _parse_filtro_flag('apenas_restante')
    apenas_insuficientes = _parse_filtro_flag('apenas_insuficientes')
    tiniciao = datetime.now()
    print("iniciando api_dados_materiais")
    query_tanques_pre = Tanques.query
    if tanque_ids:
        query_tanques_pre = query_tanques_pre.filter(Tanques.id.in_(tanque_ids))
    elif tanque_id:
        query_tanques_pre = query_tanques_pre.filter(Tanques.id == tanque_id)
    if contrato_id:
        query_tanques_pre = query_tanques_pre.filter(Tanques.contrato_id == contrato_id)
    ids_pre = [t.id for t in query_tanques_pre.order_by(Tanques.nome).all()]
    pecas_map_unificado = _pecas_metricas_por_tanque_tipo(ids_pre)

    dados = get_dados_materiais_agrupados(
        contrato_id=contrato_id,
        tanque_id=tanque_id,
        tanque_ids=tanque_ids,
        incluir_produtos_compostos=True,
        pecas_prev_prod_map=pecas_map_unificado,
    )
    fim = datetime.now()
    print(f'Tempo de execução1: {fim - tiniciao}')
    tiniciao = datetime.now()
    dados = _filtrar_materiais_relatorio(dados, apenas_restante, apenas_insuficientes)
    # Calcular totais (sobre o conjunto já filtrado)
    total_estoque_atual = sum([item['estoque_atual'] for item in dados])
    total_quantidade_necessaria = sum([item['quantidade_necessaria'] for item in dados])
    total_quantidade_prevista = sum([item['quantidade_prevista_total'] for item in dados])
    total_quantidade_concretada = sum([item['quantidade_concretada_total'] for item in dados])
    total_quantidade_restante = sum([item['quantidade_restante_total'] for item in dados])
    total_estoque_disponivel = sum([item['estoque_disponivel'] for item in dados])
    fim = datetime.now()
    print(f'Tempo de execução2: {fim - tiniciao}')
    # Agrupar produtos compostos únicos baseado nos tanques, não nos materiais
    # Precisamos recalcular os totais diretamente dos tanques vinculados
    produtos_compostos_agregados = {}
    
    # Buscar tanques novamente para calcular totais unitários por produto composto
    query_tanques = Tanques.query
    if tanque_ids:
        query_tanques = query_tanques.filter(Tanques.id.in_(tanque_ids))
    elif tanque_id:
        query_tanques = query_tanques.filter(Tanques.id == tanque_id)
    if contrato_id:
        query_tanques = query_tanques.filter(Tanques.contrato_id == contrato_id)
    
    tanques_para_calculo = query_tanques.order_by(Tanques.nome).all()

    for tanque in tanques_para_calculo:
        # Buscar TODOS os produtos compostos vinculados ao tanque
        vinculacoes = TanquesProdutoComposto.query.filter_by(
            tanque_id=tanque.id
        ).all()
        
        # Processar cada produto composto vinculado
        for vinculacao in vinculacoes:
            if not vinculacao or not vinculacao.produto_composto:
                continue
                
            produto_composto = vinculacao.produto_composto
            produto_id = produto_composto.id
            tipo_peca = vinculacao.tipo_peca

            quantidade_prevista, pecas_produzidas, pecas_concretadas = pecas_map_unificado.get(
                (tanque.id, tipo_peca), (0, 0, 0)
            )
            pecas_restantes = quantidade_prevista - pecas_produzidas
            pecas_pendente_produzir = max(0, pecas_concretadas - pecas_produzidas)

            if produto_id not in produtos_compostos_agregados:
                produtos_compostos_agregados[produto_id] = {
                    'produto_composto_id': produto_id,
                    'produto_composto_nome': produto_composto.nome,
                    'tanques': [],
                    'total_pecas_previstas': 0,
                    'total_placas_concretadas': 0,
                    'total_placas_produzidas': 0,
                    'total_pendente_produzir': 0,
                    'total_pecas_restantes': 0,
                }

            tanque_info = {
                'tanque_id': tanque.id,
                'tanque_nome': tanque.nome,
                'tipo_peca': tipo_peca,
                'quantidade_prevista': quantidade_prevista,
                'pecas_concretadas': pecas_concretadas,
                'pecas_produzidas': pecas_produzidas,
                'pecas_pendente_produzir': pecas_pendente_produzir,
                'pecas_restantes': pecas_restantes,
            }
            produtos_compostos_agregados[produto_id]['tanques'].append(tanque_info)

            produtos_compostos_agregados[produto_id]['total_pecas_previstas'] += quantidade_prevista
            produtos_compostos_agregados[produto_id]['total_placas_concretadas'] += pecas_concretadas
            produtos_compostos_agregados[produto_id]['total_placas_produzidas'] += pecas_produzidas
            produtos_compostos_agregados[produto_id]['total_pendente_produzir'] += pecas_pendente_produzir
            produtos_compostos_agregados[produto_id]['total_pecas_restantes'] += pecas_restantes
    
    # Converter para lista - os totais são unitários (por peça)
    # Como são totais unitários, mostramos apenas as peças, não quantidades de materiais
    produtos_compostos_lista = []
    for produto_id, info in produtos_compostos_agregados.items():
        # Os totais são unitários: representam o número de peças do produto composto
        # Não são somas de materiais, mas sim contagens de peças
        produtos_compostos_lista.append({
            'produto_composto_id': info['produto_composto_id'],
            'produto_composto_nome': info['produto_composto_nome'],
            'tanques': info['tanques'],
            'total_quantidade_prevista': info['total_pecas_previstas'],
            'total_placas_concretadas': info['total_placas_concretadas'],
            'total_placas_produzidas': info['total_placas_produzidas'],
            'total_pendente_produzir': info['total_pendente_produzir'],
            'total_quantidade_restante': info['total_pecas_restantes'],
            'total_quantidade_concretada': info['total_placas_produzidas'],
            'total_pecas_previstas': info['total_pecas_previstas'],
            'total_pecas_concretadas': info['total_placas_concretadas'],
            'total_pecas_produzidas': info['total_placas_produzidas'],
            'total_pecas_pendente_produzir': info['total_pendente_produzir'],
            'total_pecas_restantes': info['total_pecas_restantes'],
        })

    produtos_compostos_lista = _filtrar_produtos_compostos_restante(
        produtos_compostos_lista, apenas_restante
    )

    # Formatar dados para DataTables
    data = []
    for item in dados:
        data.append({
            'material_id': item['material_id'],
            'material_nome': item['material_nome'],
            'unidade': item['unidade'] or '-',
            'estoque_atual': item['estoque_atual'],
            'quantidade_prevista_total': item['quantidade_prevista_total'],
            'quantidade_concretada_total': item['quantidade_concretada_total'],
            'quantidade_restante_total': item['quantidade_restante_total'],
            'quantidade_necessaria': item['quantidade_necessaria'],
            'estoque_disponivel': item['estoque_disponivel'],
            'percentual_uso': item['percentual_uso'],
            'suficiente': item['suficiente']
        })
    
    return jsonify({
        'data': data,
        'totais': {
            'estoque_atual': round(total_estoque_atual, 2),
            'quantidade_necessaria': round(total_quantidade_necessaria, 2),
            'quantidade_prevista': round(total_quantidade_prevista, 2),
            'quantidade_concretada': round(total_quantidade_concretada, 2),
            'quantidade_restante': round(total_quantidade_restante, 2),
            'estoque_disponivel': round(total_estoque_disponivel, 2)
        },
        'produtos_compostos': produtos_compostos_lista
    })

@capacidade_producao_bp.route('/exportar/excel', methods=['GET'])
@login_required
def exportar_excel():
    """Exportar relatório em formato Excel"""
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_ids = _parse_tanque_ids()
    tanque_id = request.args.get('tanque_id', type=int) if not tanque_ids else None
    apenas_restante = _parse_filtro_flag('apenas_restante')
    apenas_insuficientes = _parse_filtro_flag('apenas_insuficientes')

    dados = get_dados_materiais_agrupados(
        contrato_id=contrato_id,
        tanque_id=tanque_id,
        tanque_ids=tanque_ids,
        incluir_produtos_compostos=False
    )
    dados = _filtrar_materiais_relatorio(dados, apenas_restante, apenas_insuficientes)

    if not dados:
        from flask import flash, redirect, url_for
        flash('Nenhum dado encontrado para exportar.', 'warning')
        return redirect(url_for('relatorios_capacidade_producao.index'))
    
    # Criar DataFrame
    df = pd.DataFrame(dados)
    
    # Renomear colunas
    df.rename(columns={
        'material_nome': 'Material',
        'unidade': 'Unidade',
        'estoque_atual': 'Estoque Atual',
        'quantidade_prevista_total': 'Quantidade Prevista Total',
        'quantidade_concretada_total': 'Consumida (placas produzidas)',
        'quantidade_restante_total': 'Quantidade Restante Total',
        'quantidade_necessaria': 'Previsto de Uso Futuro',
        'estoque_disponivel': 'Estoque Após Uso',
        'percentual_uso': '% de Uso',
    }, inplace=True)
    
    # Selecionar colunas para exportação
    colunas_exportacao = [
        'Material', 'Unidade', 'Estoque Atual',
        'Quantidade Prevista Total', 'Consumida (placas produzidas)', 'Quantidade Restante Total',
        'Previsto de Uso Futuro', 'Estoque Após Uso', '% de Uso'
    ]
    df_export = df[colunas_exportacao]
    
    # Adicionar linha de totais
    totais = {
        'Material': 'TOTAL',
        'Unidade': '',
        'Estoque Atual': df['Estoque Atual'].sum(),
        'Quantidade Prevista Total': df['Quantidade Prevista Total'].sum(),
        'Consumida (placas produzidas)': df['Consumida (placas produzidas)'].sum(),
        'Quantidade Restante Total': df['Quantidade Restante Total'].sum(),
        'Previsto de Uso Futuro': df['Previsto de Uso Futuro'].sum(),
        'Estoque Após Uso': df['Estoque Após Uso'].sum(),
        '% de Uso': '',
    }
    
    df_totais = pd.DataFrame([totais])
    df_export = pd.concat([df_export, df_totais], ignore_index=True)
    
    # Criar Excel na memória
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Capacidade de Produção')
        
        # Ajustar largura das colunas
        worksheet = writer.sheets['Capacidade de Produção']
        for idx, col in enumerate(df_export.columns):
            max_length = max(
                df_export[col].astype(str).apply(len).max(),
                len(col)
            )
            adjusted_width = min(max_length + 2, 50)
            worksheet.set_column(idx, idx, adjusted_width)
        
        # Formatar linha de totais
        last_row = len(df_export)
        header_format = writer.book.add_format({'bold': True, 'bg_color': '#D3D3D3'})
        for col_idx in range(len(df_export.columns)):
            worksheet.write(last_row, col_idx, df_export.iloc[last_row - 1, col_idx], header_format)
    
    output.seek(0)
    
    # Nome do arquivo
    nome_arquivo = f"relatorio_capacidade_producao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nome_arquivo
    )

@capacidade_producao_bp.route('/exportar/pdf', methods=['GET'])
@login_required
def exportar_pdf():
    """Exportar relatório em formato PDF"""
    contrato_id = request.args.get('contrato_id', type=int)
    tanque_ids = _parse_tanque_ids()
    tanque_id = request.args.get('tanque_id', type=int) if not tanque_ids else None
    
    dados = get_dados_capacidade_producao(
        contrato_id=contrato_id,
        tanque_id=tanque_id,
        tanque_ids=tanque_ids
    )
    projetos = agrupar_por_projeto(dados)
    
    # Calcular totais
    total_tanques = len(dados)
    total_previsto = sum([item['quantidade_prevista'] for item in dados])
    total_concretadas = sum([item['pecas_concretadas'] for item in dados])
    total_tempo_estimado = sum([item['tempo_total_estimado'] for item in dados])
    total_tempo_utilizado = sum([item['tempo_utilizado'] for item in dados])
    total_capacidade_restante = sum([item['capacidade_restante_horas'] for item in dados])
    percentual_geral_utilizacao = round((total_tempo_utilizado / total_tempo_estimado * 100) if total_tempo_estimado > 0 else 0, 2)
    percentual_geral_conclusao = round((total_concretadas / total_previsto * 100) if total_previsto > 0 else 0, 2)
    
    # Buscar nome do projeto se filtrado
    projeto_nome = None
    if contrato_id:
        contrato = Contrato.query.get(contrato_id)
        if contrato:
            projeto_nome = contrato.nome
    
    # Caminho absoluto da logo para o WeasyPrint
    logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
    logo_path_uri = 'file:///' + logo_path.replace('\\', '/').replace('\\', '/')
    
    html = render_template(
        'relatorios/capacidade_producao/pdf.html',
        dados=dados,
        projetos=projetos,
        projeto_nome=projeto_nome,
        total_tanques=total_tanques,
        total_previsto=total_previsto,
        total_concretadas=total_concretadas,
        total_tempo_estimado=round(total_tempo_estimado, 2),
        total_tempo_utilizado=round(total_tempo_utilizado, 2),
        total_capacidade_restante=round(total_capacidade_restante, 2),
        percentual_geral_utilizacao=percentual_geral_utilizacao,
        percentual_geral_conclusao=percentual_geral_conclusao,
        now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        logo_path=logo_path_uri
    )
    
    pdf_bytes = HTML(string=html).write_pdf(
        stylesheets=[CSS(string='body { font-family: Arial, sans-serif;}')]
    )
    
    pdf_io = io.BytesIO(pdf_bytes)
    pdf_io.seek(0)
    
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='relatorio_capacidade_producao.pdf'
    )

