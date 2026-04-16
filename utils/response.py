"""
Helpers para respostas JSON padronizadas.

Elimina a inconsistência entre 'error' vs 'erro', 'success' vs 'message'
espalhada pelos controllers. Importe sempre daqui.

Uso:
    from utils.response import json_sucesso, json_erro

    return json_sucesso(message='Salvo com sucesso.')
    return json_erro('Registro não encontrado.', 404)
    return json_sucesso(data={'id': obj.id, 'nome': obj.nome})
"""
from flask import jsonify


def json_sucesso(data=None, message: str = '', status_code: int = 200):
    """
    Retorna resposta JSON de sucesso padronizada.

    Args:
        data: Dados a incluir no campo 'data' (opcional).
        message: Mensagem descritiva de sucesso (opcional).
        status_code: Código HTTP (padrão 200).

    Retorna:
        Tupla (Response, int) compatível com Flask.
    """
    payload = {'success': True}
    if message:
        payload['message'] = message
    if data is not None:
        payload['data'] = data
    return jsonify(payload), status_code


def json_erro(message: str = 'Erro interno do servidor', status_code: int = 400):
    """
    Retorna resposta JSON de erro padronizada.

    Args:
        message: Mensagem de erro legível pelo usuário.
        status_code: Código HTTP (padrão 400).

    Retorna:
        Tupla (Response, int) compatível com Flask.
    """
    return jsonify({'success': False, 'error': message}), status_code


def json_nao_autorizado(message: str = 'Acesso não autorizado.'):
    """Atalho para erro 403."""
    return json_erro(message, 403)


def json_nao_encontrado(message: str = 'Registro não encontrado.'):
    """Atalho para erro 404."""
    return json_erro(message, 404)
