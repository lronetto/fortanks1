---
name: controller-refactoring
description: >-
  Refatora controllers Flask monolíticos em pacotes com routes/ e services/
  (blueprint único, imports por arquivo). Use ao quebrar um *_controller.py
  grande em módulos, ao criar novo domínio de rotas no estilo nota_fiscal ou
  acabamento_transporte, ou quando o usuário pedir rotas/services separados em
  controllers/.
metadata:
  author: fortanks
  version: '1.0.0'
---

# Refatoração de controllers Flask (pacote `routes/` + `services/`)

Padrão de referência no repositório:

- **`controllers/nota_fiscal/`** — blueprint central, vários `routes/*.py`, `services/` por tópico (`query_notas.py`, etc.).
- **`controllers/operacional/acabamento_transporte/`** — mesmo modelo após extração de um único arquivo.

## Objetivo

Separar **HTTP** (request, response, templates, jsonify, status) de **regra de negócio e consultas** (SQLAlchemy, pandas, montagem de payloads), mantendo **um blueprint** e **URLs estáveis**.

## Estrutura alvo

```
controllers/<pacote>/
├── __init__.py              # Blueprint + imports side-effect das rotas
├── routes/
│   ├── core.py              # páginas HTML principais + formulários/modais GET/POST grossos opcionais
│   ├── api.py               # endpoints JSON REST auxiliares
│   ├── datatables.py        # servidor DataTables (se existir)
│   ├── exportacao.py        # download PDF/Excel (se existir)
│   └── …                    # importacoes.py, analises.py — por domínio de rota
└── services/
    ├── __init__.py          # opcional; docstring ou vazio
    ├── <dominio>.py         # queries, agregações, transforms sem Flask request
    └── …
```

**Nome dos arquivos**: substantivos em português alinhados ao negócio (`pecas.py`, `notas_transporte.py`), não genéricos (`utils2.py`).

## Regras obrigatórias

### Blueprint

- Declarar **uma vez** em `__init__.py`: `nome_bp = Blueprint("nome_curto", __name__)`.
- **`name` do blueprint** (`primeiro argumento`) **não mudar** se já existe `url_for('nome_curto.funcao')` em templates — senão quebra links.
- Registrar rotas só via **`from .routes.<modulo> import *`** (side-effect dos decoradores), na ordem que fizer sentido (ex.: `core` → `datatables` → `api` → `exportacao`).

### `routes/*.py`

- Importar o blueprint: `from .. import nome_bp` (ou `from .. import nome_bp as ...` se necessário).
- Importar serviços: `from ..services.pecas import get_foo`.
- Contém: `request`, `render_template`, `jsonify`, `send_file`, `redirect`, `abort`, CSRF quando aplicável.
- **Evitar** queries grandes e lógica de negócio repetida — delegar para `services/`.

### `services/*.py`

- Sem dependência de `request` quando for fácil: funções `(args explícitos)` ou dict de filtros já montado pela rota.
- SQLAlchemy, montagem de DataFrames, HTML de colunas para DataTables, serialização para JSON — aqui.
- Funções **testáveis** e reutilizáveis entre rotas.

### Agrupamento em `controllers/<grupo>/__init__.py`

Se o projeto exporta blueprints agrupados (ex.: `from controllers.operacional import foo_bp`), atualizar para o **pacote novo**:

`from controllers.operacional.acabamento_transporte import nome_bp`.

## Passo a passo sugerido

1. **Inventário**: `grep` imports do `*_controller.py` antigo e `url_for('blueprint.')` nos templates.
2. Criar pasta do pacote com `__init__.py` só com o Blueprint (ainda sem import de routes).
3. Mover **services** primeiro (copiar funções privadas_helpers junto ao arquivo que mais usa).
4. Criar **`routes`** fatiando por rota ou por recurso (`api`, `datatables`), espelhando **nota_fiscal** quando o domínio for parecido.
5. No `__init__.py`, importar todos os `routes.*` com `import *` e `# noqa: E402,F401,F403`.
6. Remover o arquivo monolítico antigo **depois** de atualizar todos os imports para o pacote.
7. Verificar sintaxe (`python -m py_compile` nos arquivos tocados).

## Referências rápidas no repo

| Peça | Onde ver |
|------|-----------|
| Ordem de imports de rotas | `controllers/nota_fiscal/__init__.py` |
| Rota fina + service | `controllers/operacional/acabamento_transporte/routes/api.py` + `services/notas_transporte.py` |
| Blueprint + pacote | `controllers/operacional/acabamento_transporte/__init__.py` |

## Anti-patterns

- Dois blueprints para o mesmo prefixo sem necessidade — preferir um blueprint, vários arquivos de rota.
- Renomear funções view registradas nas URLs sem atualizar todos os **`url_for`** e testes.
- Service importando Flask `request` só para ler um parâmetro — prefira passar valores da rota (facilita testes).
- `routes.py` na raiz **e** pasta `routes/` ao mesmo tempo — escolha o pacote e um único estilo.

## Integração com CLAUDE.md / app.py

- `app.py` costuma registrar `nome_bp` com `url_prefix` — não duplicar prefixo nas rotas internas salvo se o projeto já fizer assim.
- Manter convenção de texto em **português** (mensagens Flash, docstrings novas).

Para detalhes de UI (DataTables, dropdown de ações), seguir **`CLAUDE.md`** e regras do workspace; esta skill cobre só **estrutura de pacote e separação routes/services**.
