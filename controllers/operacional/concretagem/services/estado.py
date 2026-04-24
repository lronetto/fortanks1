"""Regras de estado / completude de uma concretagem (sem Flask)."""

import json

from models.concreto import peca_obj_ja_produzida
from models.tanque import TanquesPecas


def parse_cordoalhas(conc):
    """Retorna o dict parseado de cordoalhas ou None."""
    if not conc.cordoalhas or not conc.cordoalhas.strip():
        return None
    try:
        cord = json.loads(conc.cordoalhas) if isinstance(conc.cordoalhas, str) else conc.cordoalhas
        return cord if isinstance(cord, dict) else None
    except (TypeError, json.JSONDecodeError):
        return None


def concretagem_tem_alongamentos(conc):
    """True se cordoalhas válidas: 16+ alongamentos válidos e 1+ bobina(s)."""
    cord = parse_cordoalhas(conc)
    if not cord:
        return False
    along = cord.get('alongamentos')
    if not isinstance(along, list):
        return False
    validos = 0
    for a in along:
        if a is None or a == '' or (isinstance(a, str) and str(a).strip() == ''):
            continue
        try:
            v = float(a) if not isinstance(a, (int, float)) else a
            if v == 0:
                continue
            validos += 1
        except (ValueError, TypeError):
            continue
    if validos < 16:
        return False
    bobinas = cord.get('bobinas')
    if not isinstance(bobinas, list) or len(bobinas) < 1:
        return False
    return True


def concretagem_tem_usinagens(conc):
    """True se pelo menos uma peça tem séries (usinagens) referenciadas."""
    pecas = conc.get_pecas()
    if not pecas:
        return False
    for peca_item in pecas:
        nome = peca_item.get('nome') or peca_item.get('placa')
        tanque_id = peca_item.get('tanque_id') or peca_item.get('tanque')
        if not nome or tanque_id is None:
            continue
        try:
            tid = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
            peca = TanquesPecas.query.filter_by(nome=nome, tanque_id=tid).first()
            if peca and peca.get_series_de_pecas():
                return True
        except (ValueError, TypeError):
            continue
    return False


def concretagem_formas_ok(conc):
    """True se todas as peças têm forma definida e formas distintas."""
    pecas = conc.get_pecas()
    if not pecas:
        return False
    formas = []
    for peca_item in pecas:
        forma = peca_item.get('forma')
        if forma is None or forma == '' or forma == 0 or str(forma).strip() == '':
            return False
        try:
            f = int(forma) if not isinstance(forma, int) else forma
            formas.append(f)
        except (ValueError, TypeError):
            return False
    return len(formas) == len(set(formas))


def concretagem_alongamentos_ok(conc):
    return concretagem_tem_alongamentos(conc)


def concretagem_todas_pecas_tem_serie(conc):
    pecas = conc.get_pecas()
    if not pecas:
        return False
    for peca_item in pecas:
        nome = peca_item.get('nome') or peca_item.get('placa')
        tanque_id = peca_item.get('tanque_id') or peca_item.get('tanque')
        if not nome or tanque_id is None:
            return False
        try:
            tid = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
            peca = TanquesPecas.query.filter_by(nome=nome, tanque_id=tid).first()
            if not peca or not peca.get_series_de_pecas():
                return False
        except (ValueError, TypeError):
            return False
    return True


def concretagem_produzida(conc):
    """True se todas as peças já têm data_producao."""
    pecas = conc.get_pecas()
    if not pecas:
        return False
    for peca_item in pecas:
        nome = peca_item.get('nome') or peca_item.get('placa')
        tanque_id = peca_item.get('tanque_id') or peca_item.get('tanque')
        if not nome or tanque_id is None:
            return False
        try:
            tid = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
            peca = TanquesPecas.query.filter_by(nome=nome, tanque_id=tid).first()
            if not peca or not peca_obj_ja_produzida(peca):
                return False
        except (ValueError, TypeError):
            return False
    return True


def concretagem_concluida(conc):
    return (
        concretagem_formas_ok(conc)
        and concretagem_alongamentos_ok(conc)
        and concretagem_todas_pecas_tem_serie(conc)
    )
