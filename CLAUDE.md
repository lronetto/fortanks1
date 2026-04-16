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

### CSS — Organização e Convenções

**Nunca usar `<style>` inline em templates.** Todo CSS deve ser centralizado nos arquivos abaixo.

#### Arquivos CSS

| Arquivo | Módulo / Uso |
|---|---|
| `static/css/style.css` | Estilos globais: layout, sidebar, utilitários comuns, Select2, DataTables |
| `static/css/notas_fiscais.css` | Módulo de Notas Fiscais (NF-e) |
| `static/css/admin.css` | Módulo Admin — visualizador JSON, logs |
| `static/css/estoque.css` | Estoque, Estoque de Terceiro, Inventário |
| `static/css/equipamentos.css` | Equipamentos — grids de fotos, modais |
| `static/css/relatorios.css` | Módulo de Relatórios e Análises |
| `static/css/seguranca.css` | Segurança — EPIs, entregas |
| `static/css/operacional.css` | Operacional — usinagem, transporte |
| `static/css/cadastros.css` | Cadastros — tanques, peças |
| `static/css/cadastro_operacional.css` | Produto Composto — modais de produção/comparação |
| `static/css/cronograma.css` | Cronograma — matriz semanal |
| `static/css/plr.css` | PLR — tabela de avaliações |
| `static/css/reembolsos.css` | Reembolsos — modal de novo reembolso |
| `static/css/solicitacoes.css` | Solicitações — modal específico |
| `static/css/materiais.css` | Materiais — catálogo, grupos, importação. Tema dark card-header + dropzone de imagem + thumbnail hover |

#### Como usar nos templates

1. **Páginas que estendem `base.html`** — usar `{% block extra_css %}`:
```html
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/MODULO.css') }}">
{% endblock %}
```

2. **Modais e partials** (`{% include %}`) — não têm bloco de CSS próprio. O CSS fica no arquivo do módulo, e a página pai faz o link.

3. **Templates standalone** (PDFs, páginas de erro, login) — podem manter `<style>` inline.

#### Utilitários em `style.css`

Classes compartilhadas prontas para usar:
- `.border-left-primary/success/info/warning/danger` — borda esquerda colorida
- `.filtros-card` — card de filtros com borda esquerda azul
- `.card-resumo` — card KPI com hover
- `.chart-container` — container responsivo para gráficos
- `.card-hover` — hover com elevação
- `.card-title-text` — título de card em caixa alta
- `.ft-page-header` — cabeçalho de página padrão
- `.text-xs`, `.text-gray-300`, `.text-gray-800` — tipografia
- `.diff-positivo`, `.diff-negativo`, `.diff-zero` — diferenças em tabelas
- `.valor-positivo`, `.valor-negativo` — valores financeiros
- `.no-data-message` — estado vazio
- `.sortable` — coluna de tabela ordenável
- `.ft-thumb` — miniatura em tabelas

### DataTables

All tables use DataTables initialized via `FT.dtOpcoes({...})` (defined in `static/js/ft-table.js`).

#### HTML Structure

```html
<!-- .card must have data-ft-colvis="tableId" so the colvis button lookup always works -->
<div class="card" data-ft-colvis="tabelaXyz">
    <div class="card-header d-flex align-items-center justify-content-between">
        <span class="card-title-text"><i class="fas fa-list me-2"></i>Título</span>
        <!-- Placeholder onde o botão "Colunas" será injetado pelo FT.dtColunas.inicializar -->
        <div class="ft-col-toggle-placeholder"></div>
    </div>
    <div class="card-body">
        <!-- Usar ft-datatable-wrapper, nunca table-responsive -->
        <div class="ft-datatable-wrapper">
            <table class="table table-bordered" id="tabelaXyz" style="width:100%">
                <thead>
                    <tr>
                        <!-- Coluna de checkbox para seleção em lote (quando aplicável) -->
                        <th width="40"><input type="checkbox" class="form-check-input" id="selectAllXyz" title="Selecionar todos da página"></th>
                        <th>Coluna 1</th>
                        <th>Coluna 2</th>
                        <th>Ações</th>
                    </tr>
                </thead>
                <tbody>
                    <!-- Dados carregados via AJAX -->
                </tbody>
            </table>
        </div>
    </div>
</div>
```

#### JavaScript — inicialização (server-side com filtros)

```javascript
// Array de títulos na mesma ordem das colunas do DataTable.
// '' (string vazia) pula a coluna no checklist de visibilidade (ex: checkbox e ações).
var TITULOS_XYZ = ['', 'Coluna 1', 'Coluna 2', 'Ações'];

var table = $('#tabelaXyz').DataTable(FT.dtOpcoes({
    ajax: {
        url: '/modulo/api/datatables',
        type: 'GET',
        // Injeta os valores do formulário de filtros na requisição AJAX
        data: function(d) {
            $('#filtrosXyz').serializeArray().forEach(function(item) {
                d[item.name] = item.value;
            });
        }
    },
    // Colunas como índices numéricos (data: N) — o endpoint retorna array de arrays
    columns: [
        { data: 0, name: 'select',   orderable: false, searchable: false, className: 'text-center' },
        { data: 1, name: 'campo1' },
        { data: 2, name: 'campo2' },
        { data: 3, name: 'acoes',    orderable: false, searchable: false }
    ],
    order: [[1, 'asc']],   // ordenação padrão
    pageLength: 50,
    // Resetar o select-all a cada redraw (paginação, filtro, reload)
    drawCallback: function() {
        $('#selectAllXyz').prop('checked', false);
    }
}));

// Injetar botão "Colunas" e restaurar preferências de visibilidade do localStorage
FT.dtColunas.inicializar(table, 'tabelaXyz', TITULOS_XYZ);

// ── Checkbox select-all ──────────────────────────────────────────────────────
$(document).on('change', '#selectAllXyz', function() {
    var checked = this.checked;
    $('#tabelaXyz').find('.xyz-checkbox').each(function() { this.checked = checked; });
});

// ── Botões de ação — delegação de eventos (obrigatório com DataTables) ───────
$(document).on('click', '.btn-editar', function() {
    var id = $(this).data('id');
    // abrir modal, carregar dados, etc.
});

// ── Recarregar tabela após mutação ──────────────────────────────────────────
// table.ajax.reload();          // reseta página para 1
// table.ajax.reload(null, false); // mantém posição atual

// ── Submeter filtros sem recarregar a página ─────────────────────────────────
$('#filtrosXyz').on('submit', function(e) {
    e.preventDefault();
    table.ajax.reload();
});
```

#### Python — endpoint DataTables (server-side)

O endpoint lê os parâmetros padrão do DataTables, aplica filtros e paginação, e retorna
`data` como **array de arrays** (não dicts), onde cada posição corresponde a `data: N` no JS.

```python
@bp.route("/api/datatables", methods=["GET"])
@login_required
def api_datatables():
    # Parâmetros padrão enviados pelo DataTables
    draw   = int(request.args.get('draw', 1))
    start  = int(request.args.get('start', 0))
    length = int(request.args.get('length', 25))
    page   = (start // length) + 1

    # Ordenação: DataTables envia order[0][column] (índice) e order[0][dir]
    order_col_idx = int(request.args.get('order[0][column]', 1))
    order_dir     = request.args.get('order[0][dir]', 'asc')

    # Mapear índice da coluna front → campo do banco (ignorar colunas não ordenáveis)
    column_map = {1: 'campo1', 2: 'campo2'}
    order_by = column_map.get(order_col_idx, 'campo1')

    # Filtros extras vindos do formulário (passados via ajax.data no JS)
    busca = request.args.get('busca', '').strip()

    # Montar query com filtros
    query = Modelo.query
    if busca:
        query = query.filter(Modelo.campo1.ilike(f'%{busca}%'))

    # Totais (DataTables exige distinguir total geral de total filtrado)
    total_geral    = db.session.query(func.count(Modelo.id)).scalar() or 0
    total_filtrado = query.count()

    # Ordenação e paginação
    order_attr = getattr(Modelo, order_by, Modelo.campo1)
    if order_dir == 'desc':
        query = query.order_by(order_attr.desc())
    else:
        query = query.order_by(order_attr.asc())
    itens = query.paginate(page=page, per_page=length, error_out=False).items

    # Montar data como array de arrays
    data = []
    for obj in itens:
        checkbox_html = (
            f'<input type="checkbox" class="form-check-input xyz-checkbox" '
            f'value="{obj.id}" data-id="{obj.id}">'
        )
        acoes_html = (
            f'<div class="ft-acoes-dropdown dropdown">'
            f'<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button"'
            f' data-bs-toggle="dropdown" aria-expanded="false" title="Ações">'
            f'<i class="fas fa-ellipsis-v"></i></button>'
            f'<ul class="dropdown-menu dropdown-menu-end">'
            f'<li><button type="button" class="dropdown-item btn-editar" data-id="{obj.id}">'
            f'<i class="fas fa-edit text-primary"></i> Editar</button></li>'
            f'<li><hr class="dropdown-divider"></li>'
            f'<li><button type="button" class="dropdown-item text-danger btn-excluir" data-id="{obj.id}">'
            f'<i class="fas fa-trash text-danger"></i> Excluir</button></li>'
            f'</ul></div>'
        )
        data.append([
            checkbox_html,   # índice 0
            obj.campo1,      # índice 1
            obj.campo2,      # índice 2
            acoes_html,      # índice 3
        ])

    return jsonify({
        "draw":            draw,
        "recordsTotal":    total_geral,
        "recordsFiltered": total_filtrado,
        "data":            data,
    })
```

#### Regras obrigatórias

- `data` no endpoint é **array de arrays**, nunca array de dicts, porque o JS usa `data: N` (inteiro).
- Todo HTML pré-renderizado em Python (badges, botões) deve seguir os padrões `ft-acoes-dropdown` e `FT.renderStatus`.
- Eventos de botões de ação **sempre** usam `$(document).on('click', '.classe', fn)` — delegação necessária pois o DataTables re-cria os nós a cada draw.
- `table.ajax.reload()` após qualquer mutação (create/update/delete via AJAX).
- O formulário de filtros chama `e.preventDefault()` no submit e dispara `table.ajax.reload()` — nunca recarrega a página inteira.

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
