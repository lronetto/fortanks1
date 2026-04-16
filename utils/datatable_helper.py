"""
Helper para endpoints DataTables server-side.

Centraliza o boilerplate repetido em 25+ controllers:
    draw / start / length / search / order_col / order_dir / page

Uso:
    from utils.datatable_helper import DataTableParams

    dt = DataTableParams()
    # filtros...
    query = Modelo.query.filter(...)
    total_geral    = Modelo.query.count()
    total_filtrado = query.count()
    itens = query.order_by(...).paginate(page=dt.page, per_page=dt.length, error_out=False).items
    return jsonify(dt.resposta(data, total_geral, total_filtrado))
"""
from flask import request, jsonify


class DataTableParams:
    """
    Lê e expõe os parâmetros padrão enviados pelo DataTables.

    Suporta tanto GET (request.args) quanto POST (request.form) via request.values,
    que combina ambos automaticamente no Flask.
    """

    def __init__(self):
        v = request.values  # combina args + form

        self.draw   = v.get('draw',   1,  type=int)
        self.start  = v.get('start',  0,  type=int)
        self.length = v.get('length', 25, type=int)

        # Busca global do DataTables
        self.search = v.get('search[value]', '').strip()

        # Ordenação
        self.order_col = v.get('order[0][column]', 0,     type=int)
        self.order_dir = v.get('order[0][dir]',    'asc')

        # Página para SQLAlchemy .paginate()
        self.page = (self.start // self.length) + 1 if self.length > 0 else 1

    def resposta(self, data: list, total_geral: int, total_filtrado: int):
        """
        Monta o dicionário de resposta padrão exigido pelo DataTables.

        Args:
            data: Lista de linhas (array de arrays ou array de dicts).
            total_geral: Total de registros sem filtro (recordsTotal).
            total_filtrado: Total após aplicação de filtros (recordsFiltered).

        Retorna:
            Response JSON do Flask.
        """
        return jsonify({
            'draw':            self.draw,
            'recordsTotal':    total_geral,
            'recordsFiltered': total_filtrado,
            'data':            data,
        })
