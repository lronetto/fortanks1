import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from sqlalchemy import func, desc, case, and_
from decimal import Decimal
from models import UnidadesConversao
from models.database import db
from models.tanque import Tanques, TanquesGrupos, TanquesPecas, TanquesProdutoComposto
from models.usuario import Usuario
from models.nota_fiscal import CNPJS_MATRIZ, NotaFiscal, NotaFiscalItem
from models.material import Materiais
from models.centro_custo import CentroCusto
from models.contrato import Contrato
from models.solicitacao import Solicitacoes, SolicitacoesItens
from models.estoque import Estoque, EstoqueMovimentacoes
from models.concreto import ConcretoConcretagens, ConcretoConcretagensTanques, ConcretoTracos, ConcretoTracosItens, ConcretoUsinagensMateriais, ConcretoUsinagens
from models.unidade import Unidades
from models.dados_analiticos import DadoAnalitico
from models.epi import Epi, EpiEntregas
from models.produto_composto import ProdutoComposto, ProdutoCompostoItem
from models.colaborador import Colaborador
from models.dados_analiticos import PL_CUSTO, PL_RECOP
from models.plano_conta import PlanoConta

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    return redirect(url_for('dashboard.meu_dashboard'))

@dashboard_bp.route('/meu-dashboard')
@login_required
def meu_dashboard():
    """
    Dashboard personalizado por usuário, exibindo informações relevantes
    baseadas no cargo e permissões do usuário.
    """

        
    # Dados específicos por perfil de usuário
    dados_especificos = {}
    # Novo: Dados para o card de estoque de materiais de usinagem
    materiais_usinagem_estoque_data = []
    exibir_card_materiais_usinagem = False

    if current_user.colaborador and current_user.is_permissao('dashboard_materiais_usinagem'):
        print("exibir_card_materiais_usinagem")
        exibir_card_materiais_usinagem = True
        materiais_usinagem_estoque_data = card_materiais_usinagem()
        # Subquery para obter IDs de materiais distintos usados em UsinagemMaterial

    # Novo Card: Resumo Analítico por Centro de Custo
    exibir_card_analitico = False
    centros_custo_analitico_data = []
    if current_user.colaborador and current_user.is_permissao('dashboard_analitico'):
        print("exibir_card_analitico")
        exibir_card_analitico = True
        centros_custo_analitico_data = CentroCusto.query.filter_by(ativo=True).order_by(CentroCusto.nome).all()


    exibir_card_epis_vencimento = False
    epis_vencimento = []
    if current_user.colaborador and current_user.is_permissao('dashboard_epis_vencimento'):
        print("exibir_card_epis_vencimento")
        exibir_card_epis_vencimento = True
        epis_vencimento = card_epis_vencimento()

    exibir_card_epis_estoque_critico = False
    epis_criticos_data = []
    if current_user.colaborador and current_user.is_permissao('dashboard_epis_estoque_critico'):
        print("exibir_card_epis_estoque_critico")
        exibir_card_epis_estoque_critico = True
        epis_criticos_data = card_epis_estoque_critico()

    exibir_card_concretagens_recentes = False
    concretagens_recentes_op = []
    if current_user.colaborador and current_user.is_permissao('dashboard_concretagens_recentes'):
        print("exibir_card_concretagens_recentes")
        exibir_card_concretagens_recentes = True
        concretagens_recentes_op = card_concretagens_recentes()

    
    exibir_card_historico_concretagem_semanal = False
    historico_concretagem_semanal = []
    if current_user.colaborador and current_user.is_permissao('dashboard_historico_concretagem_semanal'):
        print("exibir_card_historico_concretagem_semanal")
        exibir_card_historico_concretagem_semanal = True
        historico_concretagem_semanal = card_historico_concretagem_semanal()
    
    exibir_card_resumo_placas = False
    resumo_placas = []
    agrupar_por_grupo = request.args.get('agrupar_por_grupo', 'true').lower() == 'true'
    data_ate_str = request.args.get('data_ate')
    data_ate = date.today()
    if data_ate_str:
        try:
            data_ate = datetime.strptime(data_ate_str, '%Y-%m-%d').date()
        except ValueError:
            data_ate = date.today()
    if current_user.colaborador and current_user.is_permissao('dashboard_resumo_placas'):
        print("exibir_card_resumo_placas")
        exibir_card_resumo_placas = True
        resumo_placas = card_resumo_placas(agrupar_por_grupo=agrupar_por_grupo, data_ate=data_ate)
   
    exibir_card_resumo_notas = False
    resumo_notas = []
    contratos = []
    if current_user.colaborador and current_user.is_permissao('dashboard_resumo_notas'):
        print("exibir_card_resumo_notas")
        exibir_card_resumo_notas = True
        resumo_notas = card_resumo_notas()
        contratos = [ contrato.to_dict() for contrato in Contrato.query.all() ]

    # Renderizar o template apropriado com base no cargo do usuário
    return render_template(
        'dashboard/meu_dashboard.html',
        usuario=current_user,
        cards={
            'materiais_usinagem': {
                'dados': materiais_usinagem_estoque_data,
                'exibir': exibir_card_materiais_usinagem
            },
            'analitico': {
                'dados': centros_custo_analitico_data,
                'exibir': exibir_card_analitico
            },
            'epis_vencimento': {
                'dados': epis_vencimento,
                'exibir': exibir_card_epis_vencimento
            },
            'epis_estoque_critico': {
                'dados': epis_criticos_data,
                'exibir': exibir_card_epis_estoque_critico
            },
            'concretagens_recentes': {
                'dados': concretagens_recentes_op,
                'exibir': exibir_card_concretagens_recentes
            },
            'historico_concretagem_semanal': {
                'dados': historico_concretagem_semanal,
                'exibir': exibir_card_historico_concretagem_semanal
            },
            'resumo_placas': {
                'dados': resumo_placas,
                'data_ate': data_ate.strftime('%Y-%m-%d'),
                'exibir': exibir_card_resumo_placas
            },
            'resumo_notas': {
                'dados': resumo_notas,
                'contratos': contratos,
                'exibir': exibir_card_resumo_notas
            }
        }
    )

def card_epis_estoque_critico():
    epis_criticos_tst = Epi.query.join(Estoque, Estoque.material_id == Epi.material_id).filter(
        Estoque.quantidade <= Epi.estoque_minimo
    ).limit(5).all()
    return epis_criticos_tst

def card_historico_concretagem_semanal():
    num_semanas = 8
    concretagens_semanais_api = []
    volume_usinado_semanal_api = [] # Nova lista para volume
    hoje = datetime.now().date()
    
    for i in range(num_semanas):
        # Correção da lógica para as semanas:
        # Semana 0: Domingo desta semana até hoje.
        # Semana 1: Domingo da semana passada até Sábado da semana passada.
        # ...
        # Semana N: Domingo de (N semanas atrás) até Sábado de (N semanas atrás).

        if i == 0: # Semana corrente
            fim_periodo = hoje
            # Início do período é o domingo da semana corrente
            inicio_periodo = hoje - timedelta(days=(hoje.weekday() + 1) % 7)
        else: # Semanas anteriores completas
            # Ajuste para garantir que o fim_periodo seja o sábado da semana i-ésima anterior
            dias_ate_ultimo_domingo = (hoje.weekday() + 1) % 7
            sabado_da_semana_anterior_i = hoje - timedelta(days=(dias_ate_ultimo_domingo + 1 + (i-1)*7))
            fim_periodo = sabado_da_semana_anterior_i
            # Início do período é o domingo da semana (i) semanas atrás
            inicio_periodo = fim_periodo - timedelta(days=6)

        qtd_concretagens = 0
        concretagens = ConcretoConcretagens.query.filter(
            ConcretoConcretagens.data_concretagem >= inicio_periodo,
            ConcretoConcretagens.data_concretagem <= fim_periodo
        ).all()
        for concretagem in concretagens:
            qtd_concretagens += 1
        
        # Cálculo do volume usinado diretamente de ConcretoUsinagens (baseado na data da usinagem)
        # Usamos func.date para comparar a parte da data de data_usinagem (DateTime) com inicio_periodo e fim_periodo (date)
        volume_total_periodo_usinagem = db.session.query(func.sum(ConcretoUsinagens.volume)).filter(
            func.date(ConcretoUsinagens.data_usinagem) >= inicio_periodo,
            func.date(ConcretoUsinagens.data_usinagem) <= fim_periodo
        ).scalar() or 0

        
        if i == 0:
            rotulo_semana = f"Atual ({inicio_periodo.strftime('%d/%m')} - {fim_periodo.strftime('%d/%m')})"
        else:
            rotulo_semana = f"Sem {num_semanas - i} ({inicio_periodo.strftime('%d/%m')} - {fim_periodo.strftime('%d/%m')})"
        
        concretagens_semanais_api.append({
            'semana': rotulo_semana,
            'quantidade': qtd_concretagens
        })
        
        volume_usinado_semanal_api.append({
            'semana': rotulo_semana,
            'volume': float(volume_total_periodo_usinagem) # Converter Decimal para float para JSON
        })
    
    concretagens_semanais_api.reverse()
    volume_usinado_semanal_api.reverse()

    # Volume usinado mensal (últimos 12 meses)
    num_meses = 12
    volume_usinado_mensal_api = []
    for i in range(num_meses):
        # i=0: mês atual (do dia 1 até hoje); i>=1: mês completo (i meses atrás)
        if i == 0:
            inicio_periodo = hoje.replace(day=1)
            fim_periodo = hoje
            rotulo_mes = f"{inicio_periodo.strftime('%b/%Y')} (atual)"
        else:
            # Primeiro dia do mês i meses atrás
            ano = hoje.year
            mes = hoje.month - i
            while mes <= 0:
                mes += 12
                ano -= 1
            inicio_periodo = date(ano, mes, 1)
            # Último dia do mês
            if mes == 12:
                fim_periodo = date(ano, 12, 31)
            else:
                fim_periodo = date(ano, mes + 1, 1) - timedelta(days=1)
            rotulo_mes = inicio_periodo.strftime('%b/%Y')

        # Cálculo do volume usinado mensal diretamente de ConcretoUsinagens
        volume_total_mes = db.session.query(func.sum(ConcretoUsinagens.volume)).filter(
            func.date(ConcretoUsinagens.data_usinagem) >= inicio_periodo,
            func.date(ConcretoUsinagens.data_usinagem) <= fim_periodo
        ).scalar() or 0
        volume_usinado_mensal_api.append({
            'mes': rotulo_mes,
            'volume': float(volume_total_mes)
        })

    volume_usinado_mensal_api.reverse()
    return {
        'concretagens_semanais': concretagens_semanais_api,
        'volume_usinado_semanal': volume_usinado_semanal_api,
        'volume_usinado_mensal': volume_usinado_mensal_api
    }


def card_historico_semanal_concretagens():
    """Retorna dados de concretagens semanais para o gráfico"""
    num_semanas = 20
    concretagens_semanais_api = []
    hoje = datetime.now().date()
    
    for i in range(num_semanas):
        # Correção da lógica para as semanas:
        # Semana 0: Domingo desta semana até hoje.
        # Semana 1: Domingo da semana passada até Sábado da semana passada.
        # ...
        # Semana N: Domingo de (N semanas atrás) até Sábado de (N semanas atrás).

        if i == 0: # Semana corrente
            fim_periodo = hoje
            # Início do período é o domingo da semana corrente
            inicio_periodo = hoje - timedelta(days=(hoje.weekday() + 1) % 7)
        else: # Semanas anteriores completas
            # Ajuste para garantir que o fim_periodo seja o sábado da semana i-ésima anterior
            dias_ate_ultimo_domingo = (hoje.weekday() + 1) % 7
            sabado_da_semana_anterior_i = hoje - timedelta(days=(dias_ate_ultimo_domingo + 1 + (i-1)*7))
            fim_periodo = sabado_da_semana_anterior_i
            # Início do período é o domingo da semana (i) semanas atrás
            inicio_periodo = fim_periodo - timedelta(days=6)

        # Contagem de concretagens (baseado na data da concretagem)
        qtd_concretagens = ConcretoConcretagens.query.filter(
            ConcretoConcretagens.data_concretagem >= inicio_periodo,
            ConcretoConcretagens.data_concretagem <= fim_periodo
        ).count()
        
        if i == 0:
            rotulo_semana = f"Atual ({inicio_periodo.strftime('%d/%m')} - {fim_periodo.strftime('%d/%m')})"
        else:
            rotulo_semana = f"Sem {i} ({inicio_periodo.strftime('%d/%m')} - {fim_periodo.strftime('%d/%m')})"
        
        concretagens_semanais_api.append({
            'semana': rotulo_semana,
            'quantidade': qtd_concretagens
        })
    
    concretagens_semanais_api.reverse()
   #print("concretagens_semanais_api", concretagens_semanais_api)
    return {
        'concretagens_semanais': concretagens_semanais_api
    }

def card_concretagens_recentes():
    # Concretagens recentes
    concretagens_recentes_op = ConcretoConcretagens.query.order_by(
        desc(ConcretoConcretagens.data_concretagem)
    ).limit(5).all()
    
    # Total de peças concretadas nos últimos 30 dias
    # Contar peças do campo JSON 'pecas' das concretagens dos últimos 30 dias
    data_limite = datetime.now().date() - timedelta(days=30)
    concretagens_recentes = ConcretoConcretagens.query.filter(
        ConcretoConcretagens.data_concretagem >= data_limite
    ).all()
    
    total_pecas_recentes = 0
    for concretagem in concretagens_recentes:
        total_pecas_recentes += concretagem.get_quantidade_pecas_json()

    dados_especificos = {
        'concretagens_recentes': concretagens_recentes_op,
        'total_pecas_recentes': total_pecas_recentes,
    }
    return dados_especificos
def card_epis_vencimento():
     # EPIs com estoque crítico
    epis_criticos_tst = Epi.query.join(Estoque, Estoque.material_id == Epi.material_id).filter(
        Estoque.quantidade <= Epi.estoque_minimo
    ).limit(10).all()
    
    # EPIs próximos ao vencimento (30 dias)
    data_limite = datetime.now().date() + timedelta(days=30)
    epis_vencimento = Epi.query.filter(
        Epi.data_validade <= data_limite,
        Epi.data_validade >= datetime.now().date()
    ).order_by(Epi.data_validade).limit(10).all()
    
    # Entregas de EPIs recentes
    entregas_recentes = EpiEntregas.query.order_by(
        desc(EpiEntregas.data_entrega)
    ).limit(10).all()
    
    # Colaboradores com mais EPIs
    colaboradores_epis = db.session.query(
        Colaborador.id, 
        Colaborador.nome,
        func.count(EpiEntregas.id).label('total_epis')
    ).join(EpiEntregas, EpiEntregas.colaborador_id == Colaborador.id
    ).group_by(Colaborador.id
    ).order_by(desc('total_epis')
    ).limit(5).all()
    
    dados_especificos = {
        'epis_criticos': epis_criticos_tst,
        'epis_vencimento': epis_vencimento,
        'entregas_recentes': entregas_recentes,
        'colaboradores_epis': colaboradores_epis
    }
    return dados_especificos
def card_materiais_usinagem():
    materiais_usinagem_estoque_data = []

    subquery_materiais_usados_ids = db.session.query(ConcretoUsinagensMateriais.material_id).distinct().subquery()
    
    # Query principal para buscar nome do material, quantidade em estoque e unidade
    materiais_com_estoque_info = db.session.query(
        Materiais.id.label('material_id'),
        Materiais.nome.label('material_nome'),
        Materiais.unidade_id.label('estoque_unidade_id'),
        Unidades.nome.label('estoque_unidade_nome'),
        Estoque.quantidade.label('estoque_quantidade')
    ).select_from(Materiais).join(
        subquery_materiais_usados_ids, Materiais.id == subquery_materiais_usados_ids.c.material_id
    ).join(
        Estoque, Estoque.material_id == Materiais.id
    ).outerjoin( # Usar outerjoin caso um material não tenha unidade_obj definida, mas tenha unidade_id
        Unidades, Materiais.unidade_id == Unidades.id
    ).order_by(Materiais.nome).all()
    
    for mat_info in materiais_com_estoque_info:
        estoque_atual_decimal = mat_info.estoque_quantidade if mat_info.estoque_quantidade is not None else Decimal(0.0)
        unidade_estoque_id_val = mat_info.estoque_unidade_id
        # unidade_estoque_nome_val = mat_info.estoque_unidade_nome or '-' # Não usado diretamente na exibição final

        item_traco_ref = (db.session.query(
            ConcretoTracosItens.quantidade.label('traco_consumo_por_m3'),
            ConcretoTracosItens.unidade_id.label('traco_unidade_id'),
            Unidades.nome.label('traco_unidade_nome')
        ).join(Unidades, ConcretoTracosItens.unidade_id == Unidades.id)
            .join(ConcretoTracos, ConcretoTracosItens.traco_id == ConcretoTracos.id)
            .filter(ConcretoTracosItens.material_id == mat_info.material_id)
            .filter(ConcretoTracos.status == 'Ativo')
            .order_by(ConcretoTracos.id.desc()) # Pega de um traço ativo mais recente, se houver múltiplos
            .first())

        if not item_traco_ref:
            item_traco_ref = (db.session.query(
                ConcretoTracosItens.quantidade.label('traco_consumo_por_m3'),
                ConcretoTracosItens.unidade_id.label('traco_unidade_id'),
                Unidades.nome.label('traco_unidade_nome')
            ).join(Unidades, ConcretoTracosItens.unidade_id == Unidades.id)
                .filter(ConcretoTracosItens.material_id == mat_info.material_id)
                .order_by(ConcretoTracosItens.traco_id.desc()) # Pega de qualquer traço mais recente
                .first())

        estoque_na_unidade_traco = Decimal(0.0)
        potencial_m3_concreto = Decimal(0.0)
        consumo_no_traco_val = Decimal(0.0)
        unidade_traco_final_nome = '-'

        if item_traco_ref:
            unidade_traco_id_val = item_traco_ref.traco_unidade_id
            unidade_traco_final_nome = item_traco_ref.traco_unidade_nome or '-'
            consumo_no_traco_val = item_traco_ref.traco_consumo_por_m3 if item_traco_ref.traco_consumo_por_m3 else Decimal(0.0)

            if unidade_estoque_id_val and unidade_traco_id_val:
                if unidade_estoque_id_val == unidade_traco_id_val:
                    estoque_na_unidade_traco = estoque_atual_decimal
                else:
                    fator = UnidadesConversao.obter_fator_conversao(
                        unidade_origem_id=unidade_estoque_id_val, 
                        unidade_destino_id=unidade_traco_id_val, 
                        material_id=mat_info.material_id
                    )
                    if fator is not None:
                        estoque_na_unidade_traco = estoque_atual_decimal * Decimal(str(fator))
                    # else: estoque_na_unidade_traco permanece 0.0, conversão falhou
            # else: Alguma unidade ID está faltando, não pode converter, estoque_na_unidade_traco permanece 0.0
            
            if consumo_no_traco_val > 0 and estoque_na_unidade_traco > 0:
                potencial_m3_concreto = estoque_na_unidade_traco / consumo_no_traco_val
        
        materiais_usinagem_estoque_data.append({
            'nome': mat_info.material_nome,
            'estoque_convertido': estoque_na_unidade_traco,
            'unidade_traco': unidade_traco_final_nome,
            'consumo_por_m3': consumo_no_traco_val,
            'potencial_m3': potencial_m3_concreto
        })
    return materiais_usinagem_estoque_data
def acerto_data_concretagem():
    concretagens = ConcretoConcretagens.query.all()
    for concretagem in concretagens:
        # Obter peças do campo JSON
        if concretagem.pecas:
            try:
                pecas_json = json.loads(concretagem.pecas) if isinstance(concretagem.pecas, str) else concretagem.pecas
                if isinstance(pecas_json, list):
                    for peca_id in pecas_json:
                        peca1 = TanquesPecas.query.filter_by(id=peca_id).first()
                        if peca1 and (peca1.data_concretagem is None or peca1.data_concretagem == ''):
                            TanquesPecas.query.filter_by(id=peca_id).update({'data_concretagem': concretagem.data_concretagem})
                            db.session.commit()
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue
    return True
def card_resumo_placas(agrupar_por_grupo=False, data_ate=None):
    """
    Gera resumo de placas por tanque ou agrupado por grupo de tanques até a data informada.
    data_ate: date ou None (usa data atual).
    """
    data_ate = data_ate or date.today()
    tanques = Tanques.query.order_by(Tanques.contrato_id, Tanques.nome).all()
    dados_especificosb = []
    for tanque in tanques:
        statistics = tanque.get_statistics(data_ate=data_ate)
        
        dados_especificosb.append({

            'id': tanque.id,
            'tanque': tanque.nome,
            'concretadas': statistics['concretadas'],
            'acabadas': statistics['acabadas'],
            'transportadas': statistics['transportadas'],
            'total_pecas': statistics['total_pecas'],
            'em_estoque': statistics['em_estoque'],
            'nfs_emitidas_quantidade': statistics['nfs_emitidas_quantidade'],
            'prontas_transportar': statistics['prontas_transportar'],
            'nfs_emitidas': "{:,.0f}".format(statistics['nfs_emitidas_total']),
            'percas': statistics['percas']
        })
    if not agrupar_por_grupo:
        return dados_especificosb
    else:
        dados_especificos = []
        grupos = TanquesGrupos.query.order_by(TanquesGrupos.nome).all()
        
        # Criar um dicionário para acesso rápido aos dados por tanque_id
        dados_por_tanque = {dados['id']: dados for dados in dados_especificosb}
        
        for grupo in grupos:
            if not grupo.tanques:
                continue
                
            # Inicializar acumuladores
            concretadas_total = 0
            nfs_emitidas_quantidade_total = 0
            acabadas_total = 0
            transportadas_total = 0
            total_pecas_total = 0
            em_estoque_total = 0
            prontas_transportar_total = 0
            nfs_emitidas_total = 0
            percas_total = 0
            num_tanques = 0

            # Somarizar dados de todos os tanques do grupo
            for tanque in grupo.tanques:
                if tanque.id in dados_por_tanque:
                    dados = dados_por_tanque[tanque.id]
                    concretadas_total += dados['concretadas']
                    nfs_emitidas_quantidade_total += dados['nfs_emitidas_quantidade']
                    acabadas_total += dados['acabadas']
                    transportadas_total += dados['transportadas']
                    total_pecas_total += dados['total_pecas']
                    em_estoque_total += dados['em_estoque']
                    prontas_transportar_total += dados['prontas_transportar']
                    percas_total += dados.get('percas', 0)
                    # Para nfs_emitidas, precisamos converter de string formatada para número
                    # O formato usa vírgula como separador de milhar (ex: "1,234")
                    nfs_str = dados['nfs_emitidas'].replace(',', '').strip()
                    try:
                        nfs_emitidas_total += int(nfs_str) if nfs_str else 0
                    except (ValueError, AttributeError):
                        pass
                    num_tanques += 1
            
            # Dividir nfs_emitidas pelo número de tanques no grupo
            nfs_emitidas_media = 0
            if num_tanques > 0:
                nfs_emitidas_media = nfs_emitidas_total / num_tanques
            
            dados_especificos.append({
                'id': grupo.id,
                'tanque': grupo.nome,  # Usa 'tanque' para compatibilidade com o template
                'concretadas': concretadas_total,
                'acabadas': acabadas_total,
                'transportadas': transportadas_total,
                'nfs_emitidas_quantidade': nfs_emitidas_quantidade_total,
                'total_pecas': total_pecas_total,
                'em_estoque': em_estoque_total,
                'prontas_transportar': prontas_transportar_total,
                'nfs_emitidas': "{:,.0f}".format(nfs_emitidas_media),
                'percas': percas_total
            })
    
    return dados_especificos

@dashboard_bp.route('/api/resumo-placas')
@login_required
def api_resumo_placas():
    """
    API para retornar resumo de placas com opção de agrupar por grupo e data até.
    Query params: agrupar_por_grupo (true|false), data_ate (YYYY-MM-DD, padrão: hoje).
    """
    agrupar_por_grupo = request.args.get('agrupar_por_grupo', 'true').lower() == 'true'
    data_ate_str = request.args.get('data_ate')
    data_ate = date.today()
    if data_ate_str:
        try:
            data_ate = datetime.strptime(data_ate_str, '%Y-%m-%d').date()
        except ValueError:
            data_ate = date.today()

    if not (current_user.colaborador and current_user.colaborador.departamento_id == 4):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    try:
        dados = card_resumo_placas(agrupar_por_grupo=agrupar_por_grupo, data_ate=data_ate)
        return jsonify({
            'success': True,
            'dados': dados,
            'agrupar_por_grupo': agrupar_por_grupo,
            'data_ate': data_ate.isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def card_resumo_notas():
    projetos = Contrato.query.all()
    dados_especificos = []

    return dados_especificos

@dashboard_bp.route('/api/dados-resumo-notas')
@login_required
def api_dados_resumo_notas():
    #print(request.form)
    contrato_id = request.args.get('contrato_id')
    notas = db.session.query(NotaFiscal.numero_nf, 
                     NotaFiscal.data_emissao, 
                     NotaFiscal.valor_total, 
                     NotaFiscalItem.quantidade,
                     ).join(NotaFiscalItem, NotaFiscalItem.nf_id == NotaFiscal.id).\
                     join(Tanques, Tanques.item_nf == NotaFiscalItem.codigo).\
                     join(Contrato, Contrato.id == Tanques.contrato_id).\
                     order_by(NotaFiscal.data_emissao.desc()).\
                     filter(Contrato.id == contrato_id, 
                            NotaFiscal.cnpj_emitente == '27126997000187').all()
    
    dados = []
    total_valor = 0
    pecas_total =0
    for nota in notas:
        dados.append({
            'numero_nf': nota.numero_nf,
            'data_emissao': nota.data_emissao.strftime('%d/%m/%Y'),
            'valor_total': nota.valor_total,
            'quantidade': nota.quantidade
        })
        total_valor += nota.valor_total
        pecas_total += nota.quantidade
    return jsonify({
        'dados': dados,
        'total_valor': total_valor,
        'pecas_total': pecas_total
    })

def index1():

    """
    Rota principal do dashboard
    """
    # Estatísticas gerais
    total_usuarios = Usuario.query.count()
    total_solicitacoes = Solicitacoes.query.count()
    total_notas = NotaFiscal.query.count()
    total_materiais = Materiais.query.count()
    
    # Estatísticas de solicitações por status
    total_solicitacoes_aprovadas = Solicitacoes.query.filter_by(status='aprovada').count()
    total_solicitacoes_pendentes = Solicitacoes.query.filter_by(status='pendente').count()
    total_solicitacoes_rejeitadas = Solicitacoes.query.filter_by(status='rejeitada').count()
    total_solicitacoes_finalizadas = Solicitacoes.query.filter_by(status='finalizada').count()
    
    # Solicitações recentes
    solicitacoes_recentes = Solicitacoes.query.order_by(
        desc(Solicitacoes.data_solicitacao)
    ).limit(5).all()
    
    # Notas fiscais recentes
    notas_recentes = NotaFiscal.query.order_by(
        desc(NotaFiscal.data_emissao)
    ).limit(5).all()
    
    # Contratos ativos
    contratos_ativos = Contrato.query.filter_by(status='ativo').order_by(
        desc(Contrato.data_inicio)
    ).limit(5).all()
    
    # Dados para gráficos
    # Solicitações por status
    status_processamento = {
        'pendente': total_solicitacoes_pendentes,
        'aprovada': total_solicitacoes_aprovadas,
        'rejeitada': total_solicitacoes_rejeitadas,
        'finalizada': total_solicitacoes_finalizadas
    }
    
    # Renderizar o template com os dados
    return render_template(
        'dashboard/index.html',
        total_usuarios=total_usuarios,
        total_solicitacoes=total_solicitacoes,
        total_notas=total_notas,
        total_materiais=total_materiais,
        total_solicitacoes_aprovadas=total_solicitacoes_aprovadas,
        total_solicitacoes_pendentes=total_solicitacoes_pendentes,
        total_solicitacoes_rejeitadas=total_solicitacoes_rejeitadas,
        total_solicitacoes_finalizadas=total_solicitacoes_finalizadas,
        solicitacoes_recentes=solicitacoes_recentes,
        notas_recentes=notas_recentes,
        contratos_ativos=contratos_ativos,
        status_processamento=status_processamento
    )

@dashboard_bp.route('/minhas-solicitacoes')
@login_required
def minhas_solicitacoes():
    """
    Rota para exibir as solicitações do usuário logado
    """
    return redirect(url_for('solicitacao.index'))

@dashboard_bp.route('/solicitacoes-pendentes')
@login_required
def solicitacoes_pendentes():
    """
    Rota para exibir as solicitações pendentes (para aprovadores)
    """
    # Verifica se o usuário tem permissão para aprovar solicitações
    if not current_user.is_gerente_ou_superior:
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    return redirect(url_for('solicitacao.index'))


@dashboard_bp.route('/api/dados-analiticos')
@login_required
def api_dados_analiticos():
    """
    Retorna dados analíticos (custo e receita realizada) para um centro de custo específico ou todos.
    Aceita 'cc_id' como query parameter. cc_id=0 para todos.
    """
    if not (current_user.colaborador and current_user.colaborador.departamento_id == 4):
        return jsonify({'erro': 'Acesso não autorizado para este recurso.'}), 403

    try:
        centro_custo_id_str = request.args.get('cc_id', '0') # Default para '0' se não fornecido
        centro_custo_id = int(centro_custo_id_str)
    except ValueError:
        return jsonify({'erro': 'ID de Centro de Custo inválido.'}), 400

    # Query base para Custo Realizado
    query_custo = db.session.query(func.sum(DadoAnalitico.valor)).select_from(DadoAnalitico)\
        .filter(DadoAnalitico.plano_conta_id.in_(PL_CUSTO))

    # Query base para Receita Realizada
    query_receita = db.session.query(func.sum(DadoAnalitico.valor)).select_from(DadoAnalitico)\
        .filter(DadoAnalitico.plano_conta_id.in_(PL_RECOP))

    if centro_custo_id != 0:
        query_custo = query_custo.filter(DadoAnalitico.centro_custo_id == centro_custo_id)
        query_receita = query_receita.filter(DadoAnalitico.centro_custo_id == centro_custo_id)
    
    custo_realizado = query_custo.scalar() or Decimal(0.0)
    receita_realizada = query_receita.scalar() or Decimal(0.0)

    #print(f"custo_realizado: {custo_realizado}")
    #print(f"receita_realizada: {receita_realizada}")

    return jsonify({
        'custo_realizado': float(custo_realizado),
        'receita_realizada': float(receita_realizada)
    }) 