# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Fortanks** is a Portuguese-language enterprise manufacturing management system built with Flask. It manages production operations for a tank manufacturing company, covering inventory, invoices (NF-e), purchase orders, equipment, HR, scheduling, and financial reporting.

## Running the Application

```bash
# Install dependencies
uv sync
# or
pip install -r requirements.txt

# Run the main web app
python app.py

# Run the background scheduler (separate process)
python scheduler_service.py
```

The app reads config from `.env` (see `config/config.py`). Set `FLASK_ENV=development` to use `DevelopmentConfig` (DEBUG=True, no HTTPS cookie enforcement).

## Database

Primary database is **MySQL** (default host `192.168.8.10:3306`, db `sfortanks`). Override via `DATABASE_URI` env var. **SQLite** is used for offline/testing mode.

```bash
# Apply schema migrations
flask db upgrade

# Create a new migration after model changes
flask db migrate -m "description"
```

**Offline mode** (SQLite): use scripts in `scripts/` — `setup_offline.py`, `migrar_para_sqlite.py`, `sincronizar_sqlite.py`.

## Architecture

The codebase follows an **MVC pattern** using Flask Blueprints:

- **`app.py`** — Entry point: initializes Flask, registers all ~40 blueprints, configures extensions (Login, CSRF, CORS, Mail, Rate Limiter, SSLify).
- **`models/`** — SQLAlchemy ORM models. `database.py` holds the `db` instance. `models/__init__.py` calls `configure_mappers()` which must be imported before the app starts.
- **`controllers/`** — Flask Blueprints, one per business domain. Subfolders:
  - `api/` — REST API endpoints (nota_fiscal_api, material_api)
  - `relatorios/` — Report generation controllers (PDF/Excel outputs)
  - `admin/` — Admin panel
- **`templates/`** — Jinja2 HTML templates, organized by domain and sidebar module hierarchy.
- **`forms/`** — WTForms form definitions.
- **`utils/`** — Shared utilities: PDF generation (`gerar_pdf.py`), email (`email_utils.py`), security (`security.py`, `password.py`), decorators.
- **`config/config.py`** — Three config classes: `Config` (base), `DevelopmentConfig`, `ProductionConfig`, `TestingConfig` (SQLite in-memory, CSRF disabled).
- **`scheduler_service.py`** — APScheduler background jobs: email processing (5 min), Arquivei NF-e import (hourly), weekly reports.
- **`scripts/`** — One-off data import, migration, and sync scripts.

## Templates Hierarchy (Based on `base.html`)

To keep template paths predictable and aligned with the sidebar module tree (`templates/common/base.html`), follow this structure:

- `templates/admin/`
  - `cadastros/`
    - `cargos/`
    - `centro_custo/`
    - `conversao_unidades/`
    - `departamentos/`
    - `planos_conta/`
    - `unidades/`
  - `permissoes/`
- `templates/cadastros/`
  - `clientes/`
  - `colaboradores/`
  - `contratos/`
  - `fornecedores/`
  - `pecas/`
  - `tanques/`
  - `usuarios/`
- `templates/materiais/`
  - `index.html` (cadastro de materiais)
  - `grupos/` (cadastro de grupos de materiais)
- `templates/operacional/`
  - `acabamento_transporte/`
  - `concretagens/`
  - `usinagem_concreto/`
- `templates/cadastro_operacional/`
  - `certificados/`
  - `produto_composto/`
  - `tipos_certificados/`
- `templates/relatorios/`
  - `dados_analiticos/`

Other modules that are already represented as first-level menus can stay in their own top-level folders (for example: `estoque/`, `inventario/`, `notas_fiscais/`, `relatorios/`, `seguranca/`, `cronograma/`, `plr/`).

### Path Convention

- Always use `render_template()` with the hierarchical path (example: `render_template('cadastros/clientes/index.html')`).
- Keep `modais/`, `partials/`, and feature-specific subfolders inside each module folder.
- When moving templates, update all `render_template`, `{% include %}`, and `{% extends %}` paths in the same change.

## Controllers Hierarchy (Aligned with modules)

To keep controller imports aligned with the same module hierarchy used in `templates/`, prefer these grouped packages:

- `controllers/admin/cadastros/`
  - exports: `cargo_bp`, `centro_custo_bp`, `conversao_unidade_bp`, `departamento_bp`, `plano_conta_bp`, `unidade_bp`
- `controllers/cadastros/`
  - exports: `cliente_bp`, `colaborador_bp`, `contrato_bp`, `fornecedor_bp`, `peca`, `tanque_bp`, `usuario_bp`
- `controllers/materiais/`
  - exports: `material_bp`, `grupo_material_bp`
- `controllers/operacional/`
  - exports: `acabamento_transporte_bp`, `concretagem`
- `controllers/cadastro_operacional/`
  - exports: `certificado_bp`, `produto_composto_bp`
- `controllers/relatorios/`
  - exports: `dados_analiticos_bp`, `relatorio_bp` (plus existing report-specific controllers)

### Import Convention

- In `app.py`, import blueprints from the grouped package whenever available (example: `from controllers.cadastros import cliente_bp`).
- Keep legacy controller files compatible, and centralize registration paths in grouped `__init__.py` modules.

## Key Business Domains

| Domain | Controller | Model(s) |
|---|---|---|
| Inventory | `estoque_controller.py` | `estoque.py` |
| Invoices (NF-e) | `nota_fiscal_controller.py` | `nota_fiscal.py` |
| Parts/Pieces | `peca_controller.py` | — |
| Concrete operations | `concretagem_controller.py` | `concreto.py` |
| Equipment | `equipamento_controller.py` | `equipamento.py` |
| Reimbursements | `reembolso_controller.py` | — |
| Purchase Orders | `pedido_compra_controller.py` | `pedido_compra.py` |
| Employees/HR | `colaborador_controller.py` | `colaborador.py` |
| Profit Sharing | `controllers/plr.py` | `plr.py` |
| Schedule | `controllers/cronograma.py` | `cronograma.py` |
| Analytics | `dados_analiticos_controller.py` | — |

## Authentication & Permissions

- **Flask-Login** handles session authentication (web). The `Usuario` model is the user entity.
- **JWT** handles authentication for the API mobile (Flutter). Tokens são gerados com **PyJWT** (`HS256`). O decorator `jwt_required` (`utils/decorators.py`) protege rotas e popula `g.usuario_atual`.
- A role/permission system is documented in `docs/SISTEMA_PERMISSOES.md`. Permissions are stored in the `Permissao` model and enforced via decorators in `utils/decorators.py`.
- Password hashing (Argon2id) e verificação (Argon2 + legado Werkzeug) estão como `@staticmethod` na classe `Usuario` (`models/usuario.py`): `Usuario.hash_password()`, `Usuario.check_password()`, `Usuario.is_argon2_hash()`. O arquivo `utils/password.py` apenas re-exporta essas funções para retrocompatibilidade.

## API Mobile (Flutter)

Todas as rotas da API mobile ficam sob o prefixo `/api/mobile/` e são isentas de CSRF e do `before_request` de sessão (autenticação via JWT).

### Configuração JWT

Em `config/config.py`:
- `JWT_SECRET_KEY` — lida de `JWT_SECRET_KEY` env var (fallback: `SECRET_KEY`)
- `JWT_ACCESS_TOKEN_EXPIRES` — 1 hora
- `JWT_REFRESH_TOKEN_EXPIRES` — 30 dias

### Endpoints de autenticação (`controllers/api/mobile/auth_api.py`)

| Método | Rota | Auth | Descrição |
|--------|------|------|-----------|
| `POST` | `/api/mobile/auth/login` | Nenhuma | Login com `email` + `senha`, retorna `access_token`, `refresh_token` e dados do usuário |
| `POST` | `/api/mobile/auth/refresh` | Refresh token | Renova o access token enviando `refresh_token` no body JSON |
| `GET` | `/api/mobile/auth/me` | Access token | Retorna dados do usuário autenticado |
| `POST` | `/api/mobile/auth/alterar-senha` | Access token | Altera a senha (`senha_atual`, `nova_senha`, `confirmar_senha`) |

Rotas protegidas esperam o header `Authorization: Bearer <access_token>`.

### Endpoints de equipamentos (`controllers/api/mobile/equipamento_api.py`)

| Método | Rota | Auth | Descrição |
|--------|------|------|-----------|
| `GET` | `/api/mobile/equipamentos/busca?tag=valor` | Access token | Busca equipamento por ID ou patrimônio (campo em `dados_adicionais`) |
| `GET` | `/api/mobile/equipamentos/busca-nome?nome=valor&limite=20` | Access token | Busca equipamentos por nome (parcial, case-insensitive). Limite máximo: 100 |
| `PUT` | `/api/mobile/equipamentos/<id>/tag` | Access token | Grava/atualiza o número da tag (patrimônio) no equipamento. Body: `{ "tag": "valor" }` |
| `GET` | `/api/mobile/equipamentos/<id>/manutencoes` | Access token | Lista manutenções do equipamento (ordenadas por data desc) |
| `POST` | `/api/mobile/equipamentos/<id>/manutencoes` | Access token | Cria manutenção. Body: `{ "descricao", "data_inicio", "tipo?", "status?", "responsavel?", "observacoes?", "data_fim?", "custo?", "nota_fiscal_id?" }` |
| `GET` | `/api/mobile/uploads/<upload_id>/imagem` | Access token | Serve a imagem binária de um Upload (foto equipamento ou imagem material) |

A busca por `tag` tenta primeiro pelo ID (numérico) e depois pelo patrimônio (comparação exata, case-insensitive). Retorna `equipamento` (único) ou `equipamentos` (lista) + `total`.

### Convenções para novas APIs mobile

- Criar arquivos em `controllers/api/mobile/` com prefixo de rota `/mobile/<dominio>/`.
- Usar o decorator `@jwt_required` de `utils/decorators.py` — o usuário fica disponível em `g.usuario_atual`.
- Registrar o módulo em `controllers/api_controller.py` via `register(api_bp)`.
- Retornar sempre JSON com campo `error` (erros) ou dados diretamente (sucesso).

## External Integrations

- **Arquivei API** — Imports NF-e XML invoices automatically (credentials: `ARQUIVEI_API_ID`, `ARQUIVEI_API_KEY`).
- **EvolutionAPI** — WhatsApp messaging (`EVOLUTION_API_TOKEN`, `EVOLUTION_API_INSTANCE`).
- **Email (IMAP/SMTP)** — Reads incoming emails via IMAP, sends via Flask-Mail.
- **iLovePDF / ConvertAPI** — PDF conversion services.

## Deployment

CI/CD is configured in `.github/workflows/deploy.yml`: on push to `main`, SSH deploys to `/home/sfortanks/sfortanks` on the production server and restarts the `sfortanks.service` systemd unit. The scheduler runs as `fortanks-scheduler.service` (see `INSTALACAO_SCHEDULER.md`).

## Language

All code, templates, variable names, and comments are in **Portuguese**. Follow this convention when adding new code.

## UI Conventions

### DataTables

All tables use DataTables initialized via `FT.dtOpcoes({...})` (defined in `static/js/ft-table.js`). Always include:

```javascript
var TITULOS_XYZ = ['Col1', 'Col2', 'Ações'];  // '' skips a column in the toggle checklist
let table = $('#tableId').DataTable(FT.dtOpcoes({ serverSide: false }));
FT.dtColunas.inicializar(table, 'tableId', TITULOS_XYZ);
```

The card header must have `<div class="ft-col-toggle-placeholder"></div>` where the toggle button will be injected. The table wrapper uses `class="ft-datatable-wrapper"` (not `table-responsive`). Add `data-ft-colvis="tableId"` to the `.card` when the primary DOM lookup might fail.

### Action Buttons

All action columns use a single dropdown button — never separate inline `btn-sm` buttons side by side.

**In JavaScript DataTables render functions**, use `FT.renderAcoesDropdown(itens)`:
```javascript
render: function(data, type, row) {
    return FT.renderAcoesDropdown([
        { label: 'Visualizar', icon: 'fa-eye',   iconCor: 'info',    classe: 'btn-visualizar', attrs: 'data-id="' + row.id + '"' },
        { label: 'Editar',     icon: 'fa-edit',  iconCor: 'primary', classe: 'btn-editar',     attrs: 'data-id="' + row.id + '"' },
        { divider: true },
        { label: 'Excluir',    icon: 'fa-trash', iconCor: 'danger',  classe: 'btn-excluir',    attrs: 'data-id="' + row.id + '"' },
    ]);
}
```

**In Python controllers** that return HTML for DataTables AJAX, generate equivalent HTML:
```python
acoes_html = (
    f'<div class="ft-acoes-dropdown dropdown">'
    f'<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false" title="Ações"><i class="fas fa-ellipsis-v"></i></button>'
    f'<ul class="dropdown-menu dropdown-menu-end">'
    f'<li><button type="button" class="dropdown-item btn-editar" data-id="{obj.id}"><i class="fas fa-edit text-primary"></i> Editar</button></li>'
    f'<li><hr class="dropdown-divider"></li>'
    f'<li><button type="button" class="dropdown-item text-danger btn-excluir" data-id="{obj.id}"><i class="fas fa-trash text-danger"></i> Excluir</button></li>'
    f'</ul></div>'
)
```

**In static Jinja2 templates** (`{% for %}` loops), use the same HTML structure inline. For `<form>` POST deletes, place the form inside the `<li>`:
```html
<div class="ft-acoes-dropdown dropdown">
    <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button"
            data-bs-toggle="dropdown" aria-expanded="false" title="Ações">
        <i class="fas fa-ellipsis-v"></i>
    </button>
    <ul class="dropdown-menu dropdown-menu-end">
        <li><a class="dropdown-item" href="..."><i class="fas fa-eye text-info"></i> Visualizar</a></li>
        <li><hr class="dropdown-divider"></li>
        <li>
            <form method="POST" action="..." class="d-inline form-excluir">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="dropdown-item text-danger">
                    <i class="fas fa-trash text-danger"></i> Excluir
                </button>
            </form>
        </li>
    </ul>
</div>
```

Icon color convention: `text-info` = visualizar, `text-primary` = editar, `text-warning` = editar/duplicar, `text-success` = ação positiva, `text-danger` = excluir/cancelar. Always put a `{ divider: true }` before destructive actions. Single-action columns (only one button) may use a plain button instead of a dropdown.
