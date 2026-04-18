"""
Serviços de domínio para tanques (estatísticas, concretagens, dimensões).
"""

from datetime import date, datetime
import json

from sqlalchemy import distinct, func

from models.concreto import ConcretoConcretagens
from models.database import db
from models.nota_fiscal import CNPJS_MATRIZ, NotaFiscal, NotaFiscalItem

from ..utils.datas import parse_data_ate


def atualizar_dimensoes_numericas(tanque):
    """
    Extrai valores numéricos das dimensões formatadas e atualiza os campos do tanque.
    Retorna True se ok, False se erro de parse.
    """
    try:
        if tanque.tipo_tanque == 'Circular':
            valor_str = tanque.dimensoes.replace('m', '').replace('M', '').strip()
            valor_str = valor_str.replace(',', '.')
            tanque.diametro = float(valor_str)
            tanque.comprimento = None
            tanque.largura = None
        elif tanque.tipo_tanque == 'Retangular':
            partes = tanque.dimensoes.lower().replace('m', '').split('x')
            if len(partes) >= 2:
                comp_str = partes[0].strip().replace(',', '.')
                larg_str = partes[1].strip().replace(',', '.')
                tanque.comprimento = float(comp_str)
                tanque.largura = float(larg_str)
                tanque.diametro = None
        return True
    except (ValueError, IndexError) as e:
        print(f"Erro ao extrair dimensões numéricas para o tanque {tanque.id}: {str(e)}")
        return False


def obter_pecas_ids_concretadas_via_concretagens(tanque):
    """
    Retorna ids de peças deste tanque que aparecem em alguma concretagem (JSON de pecas).
    """
    from ..entities.pecas import TanquesPecas

    concretagens = ConcretoConcretagens.query.all()
    pecas_ids = []
    if concretagens:
        for concretagem in concretagens:
            pecas = concretagem.get_pecas()
            if pecas:
                for peca in pecas:
                    if peca['tanque_id'] == tanque.id:
                        peca_obj = TanquesPecas.query.filter(
                            TanquesPecas.tanque_id == tanque.id,
                            TanquesPecas.nome == peca['nome'],
                        ).first()
                        if peca_obj and peca_obj.id not in pecas_ids:
                            pecas_ids.append(peca_obj.id)
    return pecas_ids


def listar_ids_pecas_com_data_concretagem(tanque):
    """Ids de peças do tanque que possuem data_concretagem."""
    pecas_ids = []
    for peca in tanque.TanquesPecas:
        if peca.data_concretagem:
            pecas_ids.append(peca.id)
    return pecas_ids


def contar_concretadas(tanque):
    """Quantidade de peças com data de concretagem (legado: nome get_concretadas)."""
    return len(listar_ids_pecas_com_data_concretagem(tanque))


def calcular_estatisticas_tanque(tanque, data_ate=None):
    """
    Estatísticas do tanque até data_ate (inclusive). data_ate: date ou None (hoje).
    """
    data_ate = data_ate or date.today()
    if isinstance(data_ate, datetime):
        data_ate = data_ate.date()

    pecas_acabadas = 0
    pecas_transportadas = 0
    pecas_em_estoque = 0
    pecas_prontas_transportar = 0
    nfs_emitidas_total = 0
    pecas_nfs_quantidade = 0
    pecas_concretadas = 0
    pecas_perca = 0

    for peca in tanque.TanquesPecas:
        if peca.qualidade:
            try:
                qualidade_dict = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else peca.qualidade
                if qualidade_dict.get('perca') is True:
                    pecas_perca += 1

                if 'acabamento' in qualidade_dict and qualidade_dict['acabamento']:
                    acabamento = qualidade_dict['acabamento']
                    if isinstance(acabamento, dict):
                        val = acabamento.get('data')
                        if val is not None and str(val).strip() not in ('', 'null'):
                            data_acabamento = parse_data_ate(val)
                            if data_acabamento is not None and data_acabamento <= data_ate:
                                pecas_acabadas += 1
                    elif isinstance(acabamento, str):
                        if acabamento.strip() not in ('', 'null'):
                            pecas_acabadas += 1
                    else:
                        if bool(acabamento):
                            pecas_acabadas += 1

                if 'transporte' in qualidade_dict and qualidade_dict['transporte']:
                    transporte = qualidade_dict['transporte']
                    if isinstance(transporte, dict):
                        data_transporte = transporte.get('data_transporte')
                        if data_transporte is not None and str(data_transporte).strip() not in ('', 'null'):
                            dt = parse_data_ate(data_transporte)
                            if dt is not None and dt <= data_ate:
                                pecas_transportadas += 1

                if peca.data_concretagem:
                    dc = peca.data_concretagem.date() if hasattr(peca.data_concretagem, 'date') else peca.data_concretagem
                    if dc <= data_ate:
                        pecas_concretadas += 1
            except Exception:
                pass

    if tanque.item_nf is not None:
        try:
            pecas_nfs_quantidade, nfs_emitidas_total = (
                db.session.query(
                    func.coalesce(func.sum(NotaFiscalItem.quantidade), 0),
                    func.count(distinct(NotaFiscal.id)),
                )
                .select_from(NotaFiscalItem)
                .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
                .filter(
                    NotaFiscal.cnpj_emitente == CNPJS_MATRIZ,
                    func.coalesce(func.lower(NotaFiscal.status_processamento), '') != 'cancelada',
                    NotaFiscalItem.codigo.like(f'%{tanque.item_nf}%'),
                    func.date(NotaFiscal.data_emissao) <= data_ate,
                )
                .one()
            )
        except Exception:
            pecas_nfs_quantidade = 0
            nfs_emitidas_total = 0

    pecas_prontas_transportar = pecas_acabadas - pecas_transportadas
    pecas_em_estoque = pecas_concretadas - pecas_transportadas

    return {
        'concretadas': pecas_concretadas,
        'acabadas': pecas_acabadas,
        'transportadas': pecas_transportadas,
        'total_pecas': len(tanque.TanquesPecas),
        'em_estoque': pecas_em_estoque,
        'prontas_transportar': pecas_prontas_transportar,
        'nfs_emitidas_total': nfs_emitidas_total,
        'nfs_emitidas_quantidade': pecas_nfs_quantidade,
        'percas': pecas_perca,
    }
