from datetime import datetime, timedelta
import json

from sqlalchemy import case, func, literal

from models.contrato import Contrato
from models.tanque import Tanques, TanquesPecas
from models.concreto import montar_mapa_pista_por_peca
import logging
logger = logging.getLogger(__name__)
def obter_periodo_padrao():
    data_fim = datetime.now().date()
    data_inicio = data_fim - timedelta(days=180)
    return data_inicio, data_fim


def parse_data_iso(data_str):
    if not data_str:
        return None
    try:
        return datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_periodo(data_inicio_str=None, data_fim_str=None, usar_padrao=False):
    data_inicio = parse_data_iso(data_inicio_str)
    data_fim = parse_data_iso(data_fim_str)
    if usar_padrao and (not data_inicio or not data_fim):
        return obter_periodo_padrao()
    return data_inicio, data_fim


def _parse_data_acabamento(data_acabamento_raw):
    if not data_acabamento_raw:
        return None
    if isinstance(data_acabamento_raw, dict):
        return _parse_data_acabamento(data_acabamento_raw.get("data"))
    if isinstance(data_acabamento_raw, str):
        if len(data_acabamento_raw) == 10:
            return datetime.strptime(data_acabamento_raw, "%Y-%m-%d").date()
        return datetime.strptime(data_acabamento_raw, "%Y-%m-%d %H:%M:%S").date()
    return None


def _expr_iso_dia_acabamento_qualidade():
    """
    Primeiros 10 caracteres da data de acabamento no JSON (YYYY-MM-DD), para filtro no DB.
    Cobre: string em $.acabamento (operacional) ou objeto com $.acabamento.data (cadastro peças).
    """
    q = TanquesPecas.qualidade
    raw_acab = func.json_extract(q, "$.acabamento")
    data_de_objeto = func.json_unquote(func.json_extract(q, "$.acabamento.data"))
    string_direta = func.json_unquote(raw_acab)
    base = func.coalesce(
        func.nullif(data_de_objeto, literal("null")),
        case((func.json_type(raw_acab) == literal("STRING"), string_direta), else_=None),
    )
    return func.left(base, 10)


def get_dados_acabamento(data_inicio=None, data_fim=None, tanque_id=None, contrato_id=None):
    query = TanquesPecas.query.join(Tanques)

    if tanque_id:
        query = query.filter(TanquesPecas.tanque_id == tanque_id)
    if contrato_id:
        query = query.filter(Tanques.contrato_id == contrato_id)

    query = query.filter(func.json_extract(TanquesPecas.qualidade, "$.acabamento").isnot(None))

    dia_acab = _expr_iso_dia_acabamento_qualidade()
    query = query.filter(dia_acab.isnot(None))
    query = query.filter(func.length(func.trim(dia_acab)) == 10)
    if data_inicio:
        query = query.filter(dia_acab >= data_inicio.isoformat())
    if data_fim:
        query = query.filter(dia_acab <= data_fim.isoformat())

    pecas = query.all()
    pista_por_peca = montar_mapa_pista_por_peca(pecas)
    logger.info(pista_por_peca)
    logger.info([peca.to_dict() for peca in pecas])
    dados = []
    for peca in pecas:
        qualidade = peca.qualidade or "{}"
        if isinstance(qualidade, str):
            try:
                qualidade_dict = json.loads(qualidade)
            except (TypeError, json.JSONDecodeError):
                qualidade_dict = {}
        elif isinstance(qualidade, dict):
            qualidade_dict = qualidade
        else:
            qualidade_dict = {}

        try:
            data_acabamento = _parse_data_acabamento(qualidade_dict.get("acabamento"))
            if not data_acabamento:
                continue

            pista = pista_por_peca.get(peca.id)

            metros_placas = 0
            if peca.tanque and peca.tanque.altura_total:
                metros_placas = float(peca.tanque.altura_total)

            dados.append(
                {
                    "id": peca.id,
                    "nome": peca.nome,
                    "numero_sequencial": peca.numero_sequencial,
                    "tanque_nome": peca.tanque.nome if peca.tanque else "",
                    "tanque_id": peca.tanque_id,
                    "contrato_id": peca.tanque.contrato_id if peca.tanque else None,
                    "contrato_nome": peca.tanque.contrato.nome if (peca.tanque and peca.tanque.contrato) else None,
                    "data_acabamento": data_acabamento,
                    "data_concretagem": peca.data_concretagem.date() if peca.data_concretagem else None,
                    "pista": pista,
                    "tipo": peca.tipo,
                    "metros_placas": metros_placas,
                }
            )
        except (ValueError, TypeError):
            continue

    return dados


def agrupar_por_mes(dados):
    agrupado = {}
    for item in dados:
        data = item["data_acabamento"]
        chave = f"{data.year}-{data.month:02d}"
        if chave not in agrupado:
            agrupado[chave] = {
                "mes": data.month,
                "ano": data.year,
                "quantidade": 0,
                "metros_placas": 0.0,
                "pecas": [],
            }
        agrupado[chave]["quantidade"] += 1
        agrupado[chave]["metros_placas"] += item.get("metros_placas", 0)
        agrupado[chave]["pecas"].append(item)
    return dict(sorted(agrupado.items()))


def agrupar_por_semana_por_pista(dados):
    agrupado = {}
    pistas_unicas = set()

    for item in dados:
        data = item["data_acabamento"]
        pista = item.get("pista")
        if isinstance(pista, str):
            pista = pista.strip()
        if not pista:
            pista = "Sem pista"
        pistas_unicas.add(pista)

        ano, semana, dia_semana = data.isocalendar()
        chave = f"{ano}-W{semana:02d}"

        if chave not in agrupado:
            inicio_semana = data - timedelta(days=dia_semana - 1)
            agrupado[chave] = {
                "ano": ano,
                "semana": semana,
                "inicio_semana": inicio_semana,
                "fim_semana": inicio_semana + timedelta(days=6),
                "pistas": {},
            }

        if pista not in agrupado[chave]["pistas"]:
            agrupado[chave]["pistas"][pista] = 0
        agrupado[chave]["pistas"][pista] += 1

    return dict(sorted(agrupado.items())), sorted(list(pistas_unicas))


def agrupar_por_semana(dados):
    agrupado = {}
    for item in dados:
        data = item["data_acabamento"]
        ano, semana, dia_semana = data.isocalendar()
        chave = f"{ano}-W{semana:02d}"

        if chave not in agrupado:
            inicio_semana = data - timedelta(days=dia_semana - 1)
            agrupado[chave] = {
                "ano": ano,
                "semana": semana,
                "inicio_semana": inicio_semana,
                "fim_semana": inicio_semana + timedelta(days=6),
                "quantidade": 0,
                "metros_placas": 0.0,
                "pecas": [],
            }
        agrupado[chave]["quantidade"] += 1
        agrupado[chave]["metros_placas"] += item.get("metros_placas", 0)
        agrupado[chave]["pecas"].append(item)

    return dict(sorted(agrupado.items()))


def montar_dados_grafico_semana(dados_semana, pistas):
    labels_semana = []
    for valor in dados_semana.values():
        inicio = valor.get("inicio_semana")
        fim = valor.get("fim_semana")
        if inicio and fim:
            periodo = f"{inicio.strftime('%d/%m')} a {fim.strftime('%d/%m')}"
            labels_semana.append(f"Sem {valor['semana']}/{valor['ano']} ({periodo})")
        else:
            labels_semana.append(f"Sem {valor['semana']}/{valor['ano']}")
    dados_por_pista = {}
    medias_diarias_por_pista = {}

    for pista in pistas:
        dados_por_pista[pista] = []
        medias_diarias_por_pista[pista] = []
        for valor in dados_semana.values():
            quantidade = valor["pistas"].get(pista, 0)
            dados_por_pista[pista].append(quantidade)
            medias_diarias_por_pista[pista].append(round(quantidade / 7.0, 2) if quantidade > 0 else 0)

    return labels_semana, dados_por_pista, medias_diarias_por_pista


def calcular_total_metros_placas(dados):
    return sum(item.get("metros_placas", 0) for item in dados)


def listar_tanques_para_filtro(contrato_id=None):
    if contrato_id:
        tanques = Tanques.query.filter(Tanques.contrato_id == contrato_id).order_by(Tanques.nome).all()
        return [tanque for tanque in tanques if tanque.contrato and tanque.contrato.ativo]

    tanques = Tanques.query.all()
    tanques = [tanque for tanque in tanques if not tanque.contrato or tanque.contrato.ativo]
    tanques.sort(key=lambda item: item.nome)
    return tanques


def listar_tanques_json(contrato_id=None):
    if contrato_id:
        tanques = Tanques.query.filter(Tanques.contrato_id == contrato_id).order_by(Tanques.nome).all()
    else:
        tanques = Tanques.query.order_by(Tanques.nome).all()

    tanques_json = []
    for tanque in tanques:
        if tanque.contrato and not tanque.contrato.ativo:
            continue
        tanques_json.append({"id": tanque.id, "nome": tanque.nome})
    return tanques_json


def obter_contratos_ativos():
    return Contrato.query.filter(Contrato.ativo == True).order_by(Contrato.nome).all()


def obter_nomes_filtros(tanque_id=None, contrato_id=None):
    tanque_nome = None
    if tanque_id:
        tanque = Tanques.query.get(tanque_id)
        tanque_nome = tanque.nome if tanque else None

    projeto_nome = None
    if contrato_id:
        contrato = Contrato.query.get(contrato_id)
        projeto_nome = contrato.nome if contrato else None

    return tanque_nome, projeto_nome

