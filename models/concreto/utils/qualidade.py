"""Funções auxiliares para JSON de qualidade de peças e usinagens."""

from datetime import timedelta
from flask import json


def qualidade_dict_tem_data_producao(q):
    """
    True se o dict de qualidade já registra data de produção.
    Canônico: apenas na raiz (`data_producao`). Ainda lê `dados_adicionais.data_producao` por legado.
    """
    if not q or not isinstance(q, dict):
        return False
    if q.get('data_producao') and q['data_producao'] is not None:
        return True
    da = q.get('dados_adicionais')
    if isinstance(da, dict) and da.get('data_producao'):
        return True
    return False


def qualidade_peca_remover_data_producao_de_dados_adicionais(q):
    """
    Em TanquesPecas.qualidade, `data_producao` deve existir só na raiz do JSON.
    Remove a chave duplicada de dentro de `dados_adicionais` (formato legado).
    """
    if not isinstance(q, dict):
        return
    da = q.get('dados_adicionais')
    if isinstance(da, dict) and 'data_producao' in da:
        da.pop('data_producao', None)


def peca_obj_ja_produzida(peca_obj):
    """True se TanquesPecas já tem data_producao na qualidade (verificação por peça)."""
    if not peca_obj or not peca_obj.qualidade:
        return False
    try:
        q = json.loads(peca_obj.qualidade) if isinstance(peca_obj.qualidade, str) else peca_obj.qualidade
        return bool(q) and qualidade_dict_tem_data_producao(q)
    except (ValueError, TypeError, json.JSONDecodeError):
        return False


def limpar_data_producao_em_qualidade_str(qualidade_raw):
    """
    Retorna JSON de qualidade com data_producao null na raiz e sem duplicata em dados_adicionais.
    """
    if not qualidade_raw or not str(qualidade_raw).strip():
        return None
    try:
        q = json.loads(qualidade_raw) if isinstance(qualidade_raw, str) else qualidade_raw
    except (ValueError, TypeError, json.JSONDecodeError):
        q = {}
    if not isinstance(q, dict):
        q = {}
    q['data_producao'] = None
    qualidade_peca_remover_data_producao_de_dados_adicionais(q)
    return json.dumps(q, ensure_ascii=False)


def limpar_data_producao_dados_adicionais_usinagem_str(dados_raw):
    """
    ConcretoUsinagens.dados_adicionais: JSON com data_producao na raiz deste objeto (coluna dados_adicionais).
    Define data_producao como null preservando demais chaves (ex.: redosagem).
    Retorna None se não houver JSON para atualizar.
    """
    if dados_raw is None:
        return None
    if isinstance(dados_raw, str) and not dados_raw.strip():
        return None
    try:
        d = json.loads(dados_raw) if isinstance(dados_raw, str) else dados_raw
    except (ValueError, TypeError, json.JSONDecodeError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    d['data_producao'] = None
    return json.dumps(d, ensure_ascii=False)
    
def calcular_data_rompimento_28_dias(data_moldagem_dt):
    """Calcula data de rompimento 28 dias após a moldagem. Se cair em domingo, adiciona 1 dia."""
    data_rompimento = data_moldagem_dt + timedelta(days=28)
    # Verificar se é domingo (weekday() retorna 6 para domingo)
    if data_rompimento.weekday() == 6:  # Domingo
        data_rompimento += timedelta(days=1)  # Adiciona 1 dia (vira segunda-feira)
    return data_rompimento
