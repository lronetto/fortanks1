"""
Numeração hierárquica de itens de cronograma (ex.: 1, 1.1, 1.1.1).
indice_sort guarda segmentos com zero-padding para ORDER BY lexicográfico correto.
"""
import re

_INDICE_RE = re.compile(r'^\d+(\.\d+)*$')


def normalizar_indice(s):
    """Retorna a string do índice ou None se inválido."""
    s = (s or '').strip()
    if not s:
        return None
    if not _INDICE_RE.match(s):
        return None
    return s


def indice_para_sort_key(s):
    """Ex.: '1.2.10' -> '000001.000002.000010' para ordenação no banco."""
    norm = normalizar_indice(s)
    if not norm:
        return ''
    parts = norm.split('.')
    return '.'.join(f'{int(p):06d}' for p in parts)


def mensagem_indice_invalido():
    return (
        'Use numeração hierárquica com números e pontos (ex.: 1, 1.1, 1.1.1, 1.2). '
        'Sem espaços no início/fim; cada trecho deve ser um inteiro.'
    )
