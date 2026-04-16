    let table;
    let lastConsumoPorPecaTipo = [];
    let reloadTimer = null;
    let tabelaCarregando = false;
    let reloadPendente = false;
    let opcoesSimulacao = [];
    let simulacaoItens = {}; // key -> item
    let consumoPorMaterialSimulacao = null; // {material_id: number}
    let consumoPorMaterialSimulacaoTerceiro = null; // {material_id: number}
    let simulacaoPendente = false;
    let estruturaProdutosCache = {}; // { produto_composto_id(str): { material_id(str): qty_por_unidade } }
    let estruturasLoading = false;
    const TIPO_SIM_TANQUE = 'tanque';
    const TIPO_SIM_MATERIAL_AVULSO = 'material_avulso';
    const TIPO_SIM_PRODUTO_AVULSO = 'produto_avulso';

    /** Material avulso e produto composto avulso: sem coluna de peso; na planilha de índices o consumo é direto (BOM explodido no PC avulso). */
    function tipoItemSemPesoSimulacao(tipo) {
        const t = tipo || TIPO_SIM_TANQUE;
        return t === TIPO_SIM_MATERIAL_AVULSO || t === TIPO_SIM_PRODUTO_AVULSO;
    }

    /** Exibe código ERP como inteiro (sem parte decimal; ex.: 12345.0 → "12345"). */
    function formatarCodigoErpInteiro(v) {
        if (v === null || v === undefined) return '';
        const s = String(v).trim();
        if (s === '') return '';
        const n = Number(s.replace(',', '.'));
        if (Number.isFinite(n)) return String(Math.trunc(n));
        return s;
    }

    const tiposSped = ['10', '15', '18'];
    let tiposSelecionadosAntesSped = [];

    /**
     * Títulos na ordem exata das colunas do DataTable (comparativo principal).
     * Fonte única para cabeçalho da tabela, checklist "Colunas" e exportações alinhadas.
     */
    const TITULOS_TABELA_COMPARATIVO = [
        'Código ERP',
        'Material',
        'Unidade Sistema',
        'Unidade Terceiro',
        'Estoque Sistema',
        'Estoque Terceiro',
        'Valor Unitário',
        'Valor Sistema',
        'Valor Terceiro',
        'Diferença',
        'Diferença %',
        'Valor da Diferença',
        'Consumo Futuro',
        'Estoque Futuro',
        'Estoque Terceiro Futuro',
        'Diferença Futura',
        'Valor Estoque Futuro Sistema',
        'Valor Estoque Futuro Terceiro',
        'Diferença Valor Futuro',
        'Diferença Futura (Terceiro Futuro)'
    ];

    function storageKeyColunas() {
        return 'estoque_terceiro:tabelaComparativo:colunasVisiveis:v1';
    }

    /** Itens da simulação manual (tanque / avulsos) — persistidos no navegador. */
    function storageKeySimulacaoManual() {
        return 'estoque_terceiro:simulacaoManual:v1';
    }

    function persistirSimulacaoManualCliente() {
        try {
            const itensLimpos = {};
            Object.keys(simulacaoItens).forEach(function (k) {
                const it = simulacaoItens[k];
                if (!it) return;
                const copy = Object.assign({}, it);
                copy.materiais_cache = null;
                itensLimpos[k] = copy;
            });
            const payload = {
                v: 1,
                itens: itensLimpos,
                apenas_terceiro: $('#chkSimularApenasTerceiro').is(':checked')
            };
            localStorage.setItem(storageKeySimulacaoManual(), JSON.stringify(payload));
        } catch (e) {}
    }

    function limparPersistenciaSimulacaoManualCliente() {
        try {
            localStorage.removeItem(storageKeySimulacaoManual());
        } catch (e) {}
    }

    function salvarPreferenciaColunas(visiveis) {
        try {
            localStorage.setItem(storageKeyColunas(), JSON.stringify(visiveis || []));
        } catch (e) {}
    }

    function carregarPreferenciaColunas() {
        try {
            const raw = localStorage.getItem(storageKeyColunas());
            const parsed = raw ? JSON.parse(raw) : null;
            return Array.isArray(parsed) ? parsed : null;
        } catch (e) {
            return null;
        }
    }

    function aplicarPreferenciaColunas(table) {
        const preferencia = carregarPreferenciaColunas();
        if (!preferencia) return;
        try {
            table.columns().every(function(idx) {
                const visivel = preferencia.includes(idx);
                this.visible(visivel, false);
            });
            table.columns.adjust().draw(false);
        } catch (e) {}
    }

    function renderChecklistColunas(table) {
        const el = $('#colunasChecklist');
        el.empty();
        table.columns().every(function(idx) {
            const col = this;
            const titulo = TITULOS_TABELA_COMPARATIVO[idx] || `Coluna ${idx + 1}`;
            const checked = col.visible();
            const id = `chk_col_${idx}`;
            el.append(`
                <div class="form-check">
                    <input class="form-check-input chk-coluna" type="checkbox" id="${id}" data-col-idx="${idx}" ${checked ? 'checked' : ''}>
                    <label class="form-check-label" for="${id}">${titulo}</label>
                </div>
            `);
        });
    }

    function aplicarVisibilidadeDeChecklist(table) {
        const visiveis = [];
        $('#colunasChecklist .chk-coluna').each(function() {
            const idx = parseInt($(this).data('col-idx'));
            if ($(this).is(':checked')) {
                visiveis.push(idx);
            }
        });
        // segurança: evitar esconder tudo
        if (visiveis.length === 0) return;

        table.columns().every(function(idx) {
            this.visible(visiveis.includes(idx), false);
        });
        table.columns.adjust().draw(false);
        salvarPreferenciaColunas(visiveis);
    }

    function agendarReloadTabela(motivo) {
        if (!table) return;
        if (tabelaCarregando) {
            reloadPendente = true;
            try {
                console.debug('[DataTables] Reload pendente (tabela carregando)', { motivo: motivo });
            } catch (e) {}
            return;
        }
        if (reloadTimer) clearTimeout(reloadTimer);
        reloadTimer = setTimeout(function() {
            try {
                console.debug('[DataTables] Recarregando (debounced)', { motivo: motivo });
            } catch (e) {}
            table.ajax.reload(null, false);
        }, 150);
    }
    
    // Carregar datas disponíveis
    function carregarDatasDisponiveis() {
        fetch('{{ url_for("estoque_terceiro.api_datas_disponiveis") }}')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const select = $('#filtro_data');
                    select.empty();
                    select.append('<option value="">Todas as datas</option>');
                    data.datas.forEach(data => {
                        const dataFormatada = new Date(data + 'T00:00:00').toLocaleDateString('pt-BR');
                        select.append(`<option value="${data}">${dataFormatada}</option>`);
                    });
                }
            })
            .catch(error => {
                console.error('Erro ao carregar datas:', error);
            });
    }

    // Carregar tipos disponíveis (multi-select)
    function carregarTiposDisponiveis() {
        const dataFiltro = $('#filtro_data').val();
        let url = '{{ url_for("estoque_terceiro.api_tipos_disponiveis") }}';
        if (dataFiltro) {
            url += '?' + $.param({ data_filtro: dataFiltro });
        }

        fetch(url)
            .then(response => response.json())
            .then(data => {
                const select = $('#filtro_tipos');
                const selecionados = (select.val() || []).map(v => String(v));
                select.empty();

                if (data && data.success && Array.isArray(data.tipos)) {
                    data.tipos.forEach(function(t) {
                        if (t === null || t === undefined) return;
                        const v = String(t);
                        select.append(`<option value="${v}">Tipo ${v}</option>`);
                    });
                }

                // Restaura seleção, quando aplicável
                if (selecionados.length) {
                    select.val(selecionados.filter(v => select.find(`option[value="${v}"]`).length > 0));
                }

                // Sincroniza checkbox SPED (se marcado, força seleção 10/15/18)
                sincronizarFiltroSpedComTipos();
                atualizarEstadoFiltroTodosTipos();
            })
            .catch(error => {
                console.error('Erro ao carregar tipos:', error);
            });
    }

    function sincronizarFiltroSpedComTipos() {
        const select = $('#filtro_tipos');
        const spedChecked = $('#filtro_sped').is(':checked');
        if (spedChecked) {
            tiposSelecionadosAntesSped = (select.val() || []).map(v => String(v));
            const tiposExistentes = tiposSped.filter(v => select.find(`option[value="${v}"]`).length > 0);
            select.val(tiposExistentes);
        } else {
            if (tiposSelecionadosAntesSped && tiposSelecionadosAntesSped.length) {
                const existentes = tiposSelecionadosAntesSped.filter(v => select.find(`option[value="${v}"]`).length > 0);
                select.val(existentes);
            } else {
                select.val([]);
            }
        }
        atualizarEstadoFiltroTodosTipos();
    }

    function atualizarEstadoFiltroTodosTipos() {
        const select = $('#filtro_tipos');
        const totalOpcoes = select.find('option').length;
        const selecionados = (select.val() || []).length;
        const chkTodos = $('#filtro_todos_tipos');
        if (!chkTodos.length) return;
        if (totalOpcoes <= 0) {
            chkTodos.prop('checked', false);
            chkTodos.prop('indeterminate', false);
            return;
        }
        chkTodos.prop('checked', selecionados === totalOpcoes);
        chkTodos.prop('indeterminate', selecionados > 0 && selecionados < totalOpcoes);
    }
    
    // Filtros customizados (aplicados no frontend)
    $.fn.dataTable.ext.search.push(
        function(settings, searchData, dataIndex) {
            if (settings.nTable.id !== 'tabelaComparativo') return true;
            var api = new $.fn.dataTable.Api(settings);
            var row = api.row(dataIndex).data();
            if (!row) return true;
            if ($('#filtro_quantidade_zero').is(':checked')) {
                var sys = parseFloat(row.estoque_sistema) || 0;
                var ter = parseFloat(row.estoque_terceiro) || 0;
                var cons = parseFloat(row.consumo_futuro) || 0;
                // Linhas criadas só para a simulação (avulsos fora do retorno da API): não esconder pelo estoque atual.
                if (row._linha_apenas_simulacao) return true;
                // Estoques atuais zerados ainda aparecem se a simulação consome o material.
                if (sys === 0 && ter === 0 && cons === 0) return false;
            }
            if ($('#filtro_sem_material_sistema').is(':checked')) {
                if (row.material_id != null && row.material_id !== '') return false;
            }
            if ($('#filtro_ter_os_dois').is(':checked')) {
                if (row.material_id == null || row.material_id === '') return false;
            }
            return true;
        }
    );
