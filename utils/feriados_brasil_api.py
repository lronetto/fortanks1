"""
Fontes de feriados:
- Nacionais: Brasil API — https://brasilapi.com.br/api/feriados/v1/{ano}
- Estaduais / municipais: dataset feriados-brasil (GitHub)
  estadual: .../dados/feriados/estadual/json/{ano}.json
  municipal: .../dados/feriados/municipal/json/{ano}.json (lista grande; filtro por codigo_ibge)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

BRASIL_API_FERIADOS = 'https://brasilapi.com.br/api/feriados/v1/{ano}'
FERIADOS_ESTADUAIS_JSON = (
    'https://raw.githubusercontent.com/joaopbini/feriados-brasil/master/'
    'dados/feriados/estadual/json/{ano}.json'
)
FERIADOS_MUNICIPAIS_JSON = (
    'https://raw.githubusercontent.com/joaopbini/feriados-brasil/master/'
    'dados/feriados/municipal/json/{ano}.json'
)

UFS_BR = (
    'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT',
    'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO',
)

_TIMEOUT = 20
_TIMEOUT_MUNICIPAL_JSON = 60

# JSON municipal por ano é grande (~1,5 MB); cache em memória por processo.
_MUNICIPAL_JSON_CACHE: Dict[int, List[Dict[str, Any]]] = {}


def parse_codigo_ibge_municipio(val: Any) -> Optional[int]:
    """Normaliza código IBGE de município (7 dígitos)."""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        n = val
    else:
        s = str(val).strip().replace(' ', '')
        if not s.isdigit():
            return None
        n = int(s)
    if n < 1_000_000 or n > 9_999_999:
        return None
    return n


def _parse_data_br(s: str) -> Optional[date]:
    s = (s or '').strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], '%d/%m/%Y').date()
    except ValueError:
        return None


def buscar_feriados_nacionais(ano: int) -> List[Dict[str, Any]]:
    """
    Retorna lista de dicts: date (date), name (str), type (str, ex.: national).
    Levanta requests.RequestException em falha de rede/HTTP.
    """
    url = BRASIL_API_FERIADOS.format(ano=ano)
    r = requests.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        ds = item.get('date')
        if not ds:
            continue
        try:
            d = datetime.strptime(str(ds)[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        nome = (item.get('name') or 'Feriado nacional').strip()
        out.append({
            'data': d,
            'nome': nome,
            'tipo': (item.get('type') or 'national'),
            'fonte': 'Brasil API (nacional)',
        })
    return out


def buscar_feriados_estaduais(ano: int, uf: str) -> List[Dict[str, Any]]:
    """
    Filtra feriados estaduais do dataset feriados-brasil para a UF informada (2 letras).
    """
    u = (uf or '').strip().upper()
    if len(u) != 2:
        return []
    url = FERIADOS_ESTADUAIS_JSON.format(ano=ano)
    r = requests.get(url, timeout=_TIMEOUT)
    if r.status_code == 404:
        logger.warning('Arquivo estadual %s não encontrado no dataset (ano sem dados).', ano)
        return []
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if (item.get('uf') or '').strip().upper() != u:
            continue
        d = _parse_data_br(item.get('data') or '')
        if not d:
            continue
        nome = (item.get('nome') or 'Feriado estadual').strip()
        out.append({
            'data': d,
            'nome': nome,
            'tipo': 'state',
            'fonte': f'feriados-brasil ({u})',
        })
    return out


def _carregar_lista_municipal_ano(ano: int) -> List[Dict[str, Any]]:
    if ano in _MUNICIPAL_JSON_CACHE:
        return _MUNICIPAL_JSON_CACHE[ano]
    url = FERIADOS_MUNICIPAIS_JSON.format(ano=ano)
    r = requests.get(url, timeout=_TIMEOUT_MUNICIPAL_JSON)
    if r.status_code == 404:
        logger.warning('Arquivo municipal %s não encontrado no dataset.', ano)
        _MUNICIPAL_JSON_CACHE[ano] = []
        return []
    r.raise_for_status()
    data = r.json()
    lst = data if isinstance(data, list) else []
    _MUNICIPAL_JSON_CACHE[ano] = lst
    return lst


def buscar_feriados_municipais(ano: int, codigo_ibge: int) -> List[Dict[str, Any]]:
    """
    Filtra feriados municipais do dataset feriados-brasil pelo código IBGE do município.
    """
    cod = parse_codigo_ibge_municipio(codigo_ibge)
    if cod is None:
        return []
    out: List[Dict[str, Any]] = []
    for item in _carregar_lista_municipal_ano(ano):
        if not isinstance(item, dict):
            continue
        c = item.get('codigo_ibge')
        if isinstance(c, str) and c.strip().isdigit():
            c = int(c.strip())
        if c != cod:
            continue
        d = _parse_data_br(item.get('data') or '')
        if not d:
            continue
        nome = (item.get('nome') or 'Feriado municipal').strip()
        out.append({
            'data': d,
            'nome': nome,
            'tipo': 'municipal',
            'fonte': f'feriados-brasil (IBGE {cod})',
        })
    return out


def consolidar_feriados_para_importacao(
    ano: int,
    uf: Optional[str],
    incluir_nacionais: bool,
    incluir_estaduais: bool,
    incluir_municipais: bool = False,
    codigo_ibge: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Busca nas APIs e consolida por data (uma entrada por data).
    Retorna (lista com chaves data, nome, observacao), mensagem_erro ou None.
    """
    por_data: Dict[date, Dict[str, Any]] = {}
    erros: List[str] = []

    if incluir_nacionais:
        try:
            for it in buscar_feriados_nacionais(ano):
                d = it['data']
                if d not in por_data:
                    por_data[d] = {
                        'data': d,
                        'nome': it['nome'],
                        'observacao': f"Importado: {it['fonte']}.",
                    }
                else:
                    ex = por_data[d]
                    ex['nome'] = f"{ex['nome']} · {it['nome']}"[:200]
                    ex['observacao'] = (ex.get('observacao') or '') + f" Nacional: {it['nome']}."
        except requests.RequestException as e:
            logger.exception('Falha Brasil API feriados')
            erros.append(f'Nacionais: {e}')

    if incluir_estaduais:
        u = (uf or '').strip().upper()
        if len(u) != 2 or u not in UFS_BR:
            erros.append('Para feriados estaduais informe uma UF válida.')
        else:
            try:
                for it in buscar_feriados_estaduais(ano, u):
                    d = it['data']
                    if d not in por_data:
                        por_data[d] = {
                            'data': d,
                            'nome': it['nome'],
                            'observacao': f"Importado: {it['fonte']}.",
                        }
                    else:
                        ex = por_data[d]
                        ex['nome'] = f"{ex['nome']} · [{u}] {it['nome']}"[:200]
                        ex['observacao'] = (ex.get('observacao') or '') + f" Estadual ({u}): {it['nome']}."
            except requests.RequestException as e:
                logger.exception('Falha dataset estadual')
                erros.append(f'Estaduais: {e}')

    if incluir_municipais:
        cod_mun = parse_codigo_ibge_municipio(codigo_ibge)
        if cod_mun is None:
            erros.append('Para feriados municipais informe o código IBGE do município (7 dígitos).')
        else:
            try:
                for it in buscar_feriados_municipais(ano, cod_mun):
                    d = it['data']
                    if d not in por_data:
                        por_data[d] = {
                            'data': d,
                            'nome': it['nome'],
                            'observacao': f"Importado: {it['fonte']}.",
                        }
                    else:
                        ex = por_data[d]
                        ex['nome'] = f"{ex['nome']} · [mun] {it['nome']}"[:200]
                        ex['observacao'] = (
                            (ex.get('observacao') or '') + f" Municipal (IBGE {cod_mun}): {it['nome']}."
                        )
            except requests.RequestException as e:
                logger.exception('Falha dataset municipal')
                erros.append(f'Municipais: {e}')

    lista = sorted(por_data.values(), key=lambda x: x['data'])
    msg_erro = '; '.join(erros) if erros else None
    return lista, msg_erro
