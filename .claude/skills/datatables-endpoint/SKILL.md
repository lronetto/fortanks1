---
name: datatables-endpoint
description: >-
  Implementa endpoints Flask server-side para jQuery DataTables usando
  utils.datatable_helper.DataTableParams e resposta dt.resposta(). Cobre rota fina,
  service com filtros/busca/ordenação/página e contrato recordsTotal vs
  recordsFiltered. Use ao criar ou alterar GET/POST /api/datatables, ao integrar
  FT.dtOpcoes no front com ajax, ou quando o usuário pedir endpoint DataTables em
  Flask neste repositório.
metadata:
  author: fortanks
  version: '1.0.0'
---

# Endpoint DataTables server-side (Flask)

## Helper obrigatório do projeto

Todo endpoint deve usar **`utils/datatable_helper.DataTableParams`**:

| Atributo | Origem típica | Uso |
|----------|----------------|-----|
| `draw` | `draw` | Eco do pedido (obrigatório no JSON) |
| `start` | `start` | Índice inicial da página |
| `length` | `length` | Tamanho da página (-1 = “todos” em convenções deste repo) |
| `search` | `search[value]` | Busca global |
| `order_col` | `order[0][column]` | Índice da coluna ordenada (0-based, alinhar ao front) |
| `order_dir` | `order[0][dir]` | `asc` / `desc` |
| `page` | derivado | `(start // length) + 1` para `query.paginate()` |

`DataTableParams` lê **`request.values`** (GET + POST). Resposta JSON padronizada: **`dt.resposta(data, recordsTotal, recordsFiltered)`** → campos `draw`, `recordsTotal`, `recordsFiltered`, `data`.

Referência de implementação: **`utils/datatable_helper.py`**.

## Separação rota × service

Padrão validado em **`controllers/operacional/acabamento_transporte/`**:

1. **`routes/datatables.py`** (ou equivalente): instancia `dt = DataTableParams()` **antes** do `try`, monta dict de filtros extras com `request.args` / `request.form`, chama uma função no service que retorna **`dt.resposta(...)`** ou delega retorno direto. No `except`, devolver JSON de erro com **`draw: dt.draw`** para o DataTables não travar.

2. **`services/datatables.py`**: recebe **`(dt: DataTableParams, filtros: dict)`** (ou filtros já explícitos). Contém queries, montagem de linhas (dicts ou arrays), busca em memória, ordenação e fatia da página. Finaliza com **`return dt.resposta(data, records_total, records_filtered)`**.

Evitar ler `draw`/`start`/`length` manualmente com `request.args.get` repetido — isso já está encapsulado no helper.

## Contrato `recordsTotal` e `recordsFiltered`

O DataTables distingue:

- **`recordsTotal`**: total de registros **antes** da busca global `search[value]` (no dataset já filtrado pelos filtros de tela, se aplicável ao desenho).
- **`recordsFiltered`**: total **depois** de aplicar a busca global no conjunto que entra na tabela.

No exemplo **acabamento_transporte**, calcula-se primeiro todas as linhas por `get_pecas(filtros)`, `records_total = len(rows)`, aplica-se `dt.search` sobre `rows`, depois `records_filtered = len(rows)`. Ordenação e paginação (`dt.start`, `dt.length`) vêm **por último**, sobre `rows` já filtradas pela busca.

Se a listagem for **paginada no SQL** (como **`controllers/nota_fiscal/routes/datatables.py`**), usar `dt.page`, `total_geral`/`total_filtrado` via `count()` na query e `paginate(per_page=min(dt.length, 500))`; tratar **`dt.length == -1`** com `offset(dt.start).all()` quando necessário.

## Ordenação por índice de coluna

Manter uma tupla **`COLUMN_KEYS`** (ou dict índice → campo) na mesma ordem das colunas enviadas pelo front (`columns` / `data` no JS). Validar **`0 <= dt.order_col < len(COLUMN_KEYS)`** antes de ordenar — colunas extras (checkbox, ações) costumam deslocar índices: o índice no DataTables deve bater com o **`order[0][column]`** que o cliente envia.

## Paginação no service (dados já em lista)

Convenção usada em **acabamento_transporte**:

```text
if dt.length == -1:
    data = rows[dt.start:]
else:
    per_page = max(1, min(dt.length, 500))
    data = rows[dt.start : dt.start + per_page]
```

Limitar `per_page` evita respostas gigantes acidentais.

## Front (resumo)

Em **`CLAUDE.md`** / **`static/js/ft-table.js`**: `ajax.data` deve enviar filtros do formulário; colunas podem ser índices numéricos (`data: N`). Garantir que a ordem das colunas ordenáveis no HTML/JS corresponda a **`COLUMN_KEYS`** no backend.

## Checklist rápido

- [ ] Importar `DataTableParams` e usar `dt.resposta` para sucesso.
- [ ] `dt` criado antes do `try` se houver tratamento de erro com `draw`.
- [ ] Resposta de erro HTTP 500 ainda inclui `draw`, `recordsTotal`, `recordsFiltered`, `data` (lista vazia).
- [ ] `recordsTotal` / `recordsFiltered` coerentes com o momento em que a busca global é aplicada.
- [ ] Front: `ajax.url` apontando para a rota registrada no blueprint com o mesmo método (GET típico).

Para **HTML pré-renderizado** em células e **dropdown de ações**, seguir as convenções UI do **`CLAUDE.md`** (classes `ft-acoes-dropdown`, delegação jQuery).
