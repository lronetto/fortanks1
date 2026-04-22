# CLAUDE.md

Guia enxuto para trabalhar no projeto **Fortanks** com foco em velocidade e consistência.

## 1) Contexto rápido

- Stack principal: Flask + SQLAlchemy + Jinja2 + DataTables.
- Idioma do código, comentários, templates e textos: **português**.
- Estrutura principal:
  - `app.py` (entrada da aplicação)
  - `controllers/` (blueprints/rotas)
  - `models/` (ORM e regras de domínio)
  - `templates/` e `static/` (UI)
  - `utils/` (helpers compartilhados)

## 2) Execução local

```bash
uv sync
python app.py
```

Opcional:

```bash
python scheduler_service.py
flask db upgrade
```

## 3) Regras obrigatórias de implementação

- Fazer mudanças cirúrgicas: alterar só o necessário para a tarefa.
- Manter compatibilidade de imports públicos já usados no projeto.
- Não quebrar padrão de blueprint existente ao criar/editar rotas.
- Em templates que estendem base, evitar CSS inline (usar CSS do módulo).
- Antes de criar qualquer função nova de **formatação** ou **normalização**, consultar `utils/` para reutilizar função existente e evitar duplicidade.

## 4) Skills obrigatórios por tipo de tarefa

Sempre que a tarefa cair nos cenários abaixo, **usar explicitamente** os skills:

- `/models-domain-package`
  - Quando criar/refatorar domínio em `models/<dominio>/`.
  - Quando separar em `entities/`, `services/`, `utils/`, `constants.py`.
  - Quando precisar preservar `from models.<dominio> import ...` via `__init__.py`.

- `/datatables-endpoint`
  - Quando criar/alterar endpoint DataTables server-side.
  - Obrigatório usar `DataTableParams` (`utils/datatable_helper.py`) e retorno `dt.resposta(...)`.
  - Respeitar contrato `recordsTotal` vs `recordsFiltered` e paginação/ordenação do DataTables.

## 5) Convenções críticas de DataTables (resumo)

- Front usa `FT.dtOpcoes(...)` e envia filtros em `ajax.data`.
- Backend deve responder com `draw`, `recordsTotal`, `recordsFiltered`, `data`.
- Em erro, manter `draw` na resposta para não travar a tabela no front.
- Colunas de ações seguem dropdown padrão `ft-acoes-dropdown`.

## 6) Checklist antes de finalizar alteração

- Imports novos funcionam sem ciclo evidente.
- Rotas registradas e acessíveis no blueprint correto.
- Migração criada quando houver mudança de schema.
- Lint/teste básico do trecho alterado executado.
- Sem alterações colaterais fora do escopo da tarefa.
