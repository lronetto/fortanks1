/**
 * ft-table.js — Utilitários centralizados para tabelas DataTables
 * Disponível globalmente como window.FT
 */
(function (global) {
    'use strict';

    var FT = {};

    // ─── Escape de atributos HTML ────────────────────────────────────────────
    FT.escAttr = function (s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    };

    // ─── Mapa de status → cor Bootstrap ─────────────────────────────────────
    var _STATUS_MAP = {
        // Geral
        'Ativo':             { cor: 'success' },
        'Inativo':           { cor: 'danger' },
        'Pendente':          { cor: 'secondary' },
        'Concluída':         { cor: 'success' },
        'Concluido':         { cor: 'success' },
        'Em Andamento':      { cor: 'primary' },
        'Aberta':            { cor: 'secondary' },
        'Fechada':           { cor: 'dark' },
        'Cancelada':         { cor: 'danger' },
        'Aprovada':          { cor: 'success' },
        'Reprovada':         { cor: 'danger' },
        'Em Análise':        { cor: 'info',    escuro: true },
        // Equipamentos
        'Em Manutenção':     { cor: 'warning', escuro: true },
        'Aguardando Reparo': { cor: 'warning', escuro: true },
        'Emprestado':        { cor: 'info',    escuro: true },
        // Colaboradores
        'Afastado':          { cor: 'warning', escuro: true },
        'Férias':            { cor: 'info',    escuro: true },
        // Estoque
        'Em Estoque':        { cor: 'success' },
        'Estoque Baixo':     { cor: 'warning', escuro: true },
        'Sem Estoque':       { cor: 'danger' },
        'Reservado':         { cor: 'info',    escuro: true },
        // Financeiro
        'Pago':              { cor: 'success' },
        'Não Pago':          { cor: 'danger' },
        'Parcial':           { cor: 'warning', escuro: true },
        // NF-e
        'Importada':         { cor: 'success' },
        'Não Importada':     { cor: 'secondary' },
        'Com Erro':          { cor: 'danger' },
        'Liberada':          { cor: 'success' },
        'Bloqueada':         { cor: 'danger' },
    };

    /**
     * Renderiza um badge Bootstrap para um status.
     * @param {string} status
     * @param {string} [fallback] HTML retornado quando status é vazio (padrão: badge cinza —)
     */
    FT.renderStatus = function (status, fallback) {
        if (!status) {
            return fallback !== undefined ? fallback : '<span class="badge bg-secondary">—</span>';
        }
        var cfg = _STATUS_MAP[status] || { cor: 'secondary' };
        var extra = cfg.escuro ? ' text-dark' : '';
        return '<span class="badge bg-' + cfg.cor + extra + '">' + FT.escAttr(status) + '</span>';
    };

    // ─── Dropdown de ações padrão ────────────────────────────────────────────
    /**
     * Constrói um dropdown de ações no padrão do sistema.
     *
     * @param {Array} itens  Array de objetos:
     *   { label, icon, iconCor, classe, attrs }  — item normal
     *   { divider: true }                         — separador
     *
     * @example
     * FT.renderAcoesDropdown([
     *   { label: 'Visualizar', icon: 'fa-eye',   iconCor: 'info',    classe: 'btn-visualizar', attrs: 'data-id="1"' },
     *   { label: 'Editar',     icon: 'fa-edit',  iconCor: 'primary', classe: 'btn-editar',     attrs: 'data-id="1"' },
     *   { divider: true },
     *   { label: 'Excluir',    icon: 'fa-trash', iconCor: 'danger',  classe: 'btn-excluir',    attrs: 'data-id="1"' },
     * ])
     */
    FT.renderAcoesDropdown = function (itens) {
        var lis = '';
        itens.forEach(function (item) {
            if (item.divider) {
                lis += '<li><hr class="dropdown-divider"></li>';
                return;
            }
            var icone = item.icon
                ? '<i class="fas ' + item.icon + (item.iconCor ? ' text-' + item.iconCor : '') + '"></i> '
                : '';
            lis += '<li><button type="button" class="dropdown-item ' + (item.classe || '') + '" '
                + (item.attrs || '') + '>'
                + icone + FT.escAttr(item.label)
                + '</button></li>';
        });
        return '<div class="ft-acoes-dropdown dropdown">'
            + '<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" '
            + 'data-bs-toggle="dropdown" aria-expanded="false" title="Ações">'
            + '<i class="fas fa-ellipsis-v"></i></button>'
            + '<ul class="dropdown-menu dropdown-menu-end">' + lis + '</ul>'
            + '</div>';
    };

    // ─── DataTables: URL do arquivo de linguagem PT-BR ───────────────────────
    FT.dtLangUrl = (function () {
        var el = document.getElementById('ft-config');
        return el
            ? el.getAttribute('data-dt-lang')
            : '/static/js/datatables-pt-BR-1.13.json';
    })();

    // ─── DataTables: opções padrão ───────────────────────────────────────────
    /**
     * Retorna um objeto de opções DataTables com os padrões do sistema.
     * Passe `extras` para sobrescrever qualquer chave.
     *
     * @param {Object} [extras]
     * @returns {Object}
     */
    FT.dtOpcoes = function (extras) {
        var base = {
            processing: true,
            serverSide: true,
            responsive: { details: { type: 'column', target: 'tr' } },
            pageLength: 25,
            lengthMenu: [[10, 25, 50, 100], [10, 25, 50, 100]],
            language: { url: FT.dtLangUrl },
            dom: '<"row align-items-center"<"col-sm-12 col-md-auto me-auto"l><"col-sm-12 col-md-auto"f>>rtip',
            order: [[0, 'asc']],
        };
        return $.extend(true, {}, base, extras || {});
    };

    // ─── CSRF token helper ───────────────────────────────────────────────────
    /** Retorna o valor do CSRF token da meta tag do base.html */
    FT.csrf = function () {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    };

    /** Retorna o objeto de headers padrão para fetch/AJAX com CSRF */
    FT.ajaxHeaders = function () {
        return { 'X-CSRFToken': FT.csrf(), 'X-Requested-With': 'XMLHttpRequest' };
    };

    // ─── Exibe um alerta Bootstrap na .alert-container ──────────────────────
    /**
     * @param {string} msg
     * @param {'success'|'danger'|'warning'|'info'} [tipo='success']
     */
    FT.alerta = function (msg, tipo) {
        tipo = tipo || 'success';
        var container = document.querySelector('.alert-container');
        if (!container) return;
        var div = document.createElement('div');
        div.className = 'alert alert-' + tipo + ' alert-dismissible fade show';
        div.innerHTML = FT.escAttr(msg)
            + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
        container.appendChild(div);
    };

    // ─── Visibilidade de colunas com persistência em localStorage ───────────
    FT.dtColunas = {

        storageKey: function (tableId) {
            return 'ft:colunas:' + tableId + ':v1';
        },

        salvar: function (tableId, visiveis) {
            try { localStorage.setItem(FT.dtColunas.storageKey(tableId), JSON.stringify(visiveis)); } catch (e) {}
        },

        carregar: function (tableId) {
            try {
                var raw = localStorage.getItem(FT.dtColunas.storageKey(tableId));
                return raw ? JSON.parse(raw) : null;
            } catch (e) { return null; }
        },

        /** Aplica preferências salvas ao DataTable (deve ser chamado antes do primeiro draw). */
        aplicar: function (dt, tableId) {
            var salvo = FT.dtColunas.carregar(tableId);
            if (!salvo) return;
            dt.columns().every(function (idx) {
                if (idx < salvo.length) { this.visible(salvo[idx], false); }
            });
            dt.columns.adjust();
        },

        /** Lê o estado atual de visibilidade e persiste. */
        _salvarEstadoAtual: function (dt, tableId) {
            var visiveis = [];
            dt.columns().every(function () { visiveis.push(this.visible()); });
            FT.dtColunas.salvar(tableId, visiveis);
        },

        /**
         * Injeta o botão "Colunas" com checklist de visibilidade em `container`.
         * @param {DataTable} dt
         * @param {string}    tableId
         * @param {string[]}  titulos  – nomes das colunas na ordem do DataTable
         * @param {Element}   container – o elemento .ft-col-toggle-placeholder
         */
        renderBotao: function (dt, tableId, titulos, container) {
            var uid = 'ft-col-dd-' + tableId.replace(/\W/g, '_');
            var html = '<div class="dropdown">'
                + '<button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button"'
                + ' id="' + uid + '" data-bs-toggle="dropdown" aria-expanded="false">'
                + '<i class="fas fa-columns"></i>'
                + '<span class="d-none d-md-inline ms-1">Colunas</span>'
                + '</button>'
                + '<div class="dropdown-menu dropdown-menu-end p-2" style="min-width:200px;max-height:380px;overflow-y:auto"'
                + ' aria-labelledby="' + uid + '">'
                + '<div class="d-flex gap-2 mb-2">'
                + '<a href="#" class="ft-col-todos small">Todos</a>'
                + '<a href="#" class="ft-col-nenhum small">Nenhum</a>'
                + '<a href="#" class="ft-col-reset small ms-auto text-muted">Resetar</a>'
                + '</div>'
                + '<div class="ft-col-checklist d-grid gap-1"></div>'
                + '</div>'
                + '</div>';

            container.innerHTML = html;

            var checklist = container.querySelector('.ft-col-checklist');

            // Constrói checkboxes
            dt.columns().every(function (idx) {
                var titulo = (titulos && titulos[idx] != null) ? titulos[idx] : ('Coluna ' + (idx + 1));
                if (!titulo) return; // Pula colunas sem título (responsive expand, etc.)
                var chk = document.createElement('div');
                chk.className = 'form-check form-check-sm';
                var cbId = uid + '_c' + idx;
                chk.innerHTML = '<input class="form-check-input" type="checkbox" id="' + cbId + '"'
                    + (this.visible() ? ' checked' : '') + ' data-col-idx="' + idx + '">'
                    + '<label class="form-check-label small" for="' + cbId + '">' + FT.escAttr(titulo) + '</label>';
                checklist.appendChild(chk);

                chk.querySelector('input').addEventListener('change', function () {
                    dt.column(this.getAttribute('data-col-idx') * 1).visible(this.checked);
                    dt.columns.adjust().draw(false);
                    FT.dtColunas._salvarEstadoAtual(dt, tableId);
                });
            });

            // Todos / Nenhum / Resetar
            container.querySelector('.ft-col-todos').addEventListener('click', function (e) {
                e.preventDefault();
                checklist.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
                    cb.checked = true;
                    dt.column(cb.getAttribute('data-col-idx') * 1).visible(true, false);
                });
                dt.columns.adjust().draw(false);
                FT.dtColunas._salvarEstadoAtual(dt, tableId);
            });

            container.querySelector('.ft-col-nenhum').addEventListener('click', function (e) {
                e.preventDefault();
                checklist.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
                    cb.checked = false;
                    dt.column(cb.getAttribute('data-col-idx') * 1).visible(false, false);
                });
                dt.columns.adjust().draw(false);
                FT.dtColunas._salvarEstadoAtual(dt, tableId);
            });

            container.querySelector('.ft-col-reset').addEventListener('click', function (e) {
                e.preventDefault();
                try { localStorage.removeItem(FT.dtColunas.storageKey(tableId)); } catch (ex) {}
                checklist.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
                    cb.checked = true;
                    dt.column(cb.getAttribute('data-col-idx') * 1).visible(true, false);
                });
                dt.columns.adjust().draw(false);
            });

            // Impede o dropdown de fechar ao clicar nos checkboxes
            container.querySelector('.dropdown-menu').addEventListener('click', function (e) {
                e.stopPropagation();
            });
        },

        /**
         * Ponto de entrada: aplica preferências salvas e injeta o botão de colunas.
         * @param {DataTable} dt
         * @param {string}    tableId  – id do elemento <table>
         * @param {string[]}  titulos  – array com o título de cada coluna
         */
        inicializar: function (dt, tableId, titulos) {
            FT.dtColunas.aplicar(dt, tableId);
            // Colunas não-toggleáveis (título vazio) são sempre forçadas visíveis,
            // ignorando qualquer estado salvo no localStorage.
            if (titulos) {
                dt.columns().every(function (idx) {
                    if (!titulos[idx]) { this.visible(true, false); }
                });
                dt.columns.adjust();
            }
            var $container = $(dt.table().container());
            var placeholder = $container.closest('.card').find('.ft-col-toggle-placeholder')[0]
                || $('[data-ft-colvis="' + tableId + '"]').find('.ft-col-toggle-placeholder')[0];
            if (placeholder) {
                FT.dtColunas.renderBotao(dt, tableId, titulos, placeholder);
            }
        }
    };

    global.FT = FT;
})(window);
