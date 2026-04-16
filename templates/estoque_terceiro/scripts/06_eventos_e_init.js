
    // (removido) Bloco de "Peças não produzidas" e simulação antiga
    // Evento de mudança no filtro de data
    $('#filtro_data').on('change', function() {
        carregarTiposDisponiveis();
        agendarReloadTabela('filtro_data');
    });

    // Evento de mudança no filtro SPED (força tipos 10, 15, 18)
    $('#filtro_sped').on('change', function() {
        sincronizarFiltroSpedComTipos();
        agendarReloadTabela('filtro_sped');
    });

    // Evento de mudança no filtro de tipos (backend filtra, então recarrega via AJAX)
    $('#filtro_tipos').on('change', function() {
        atualizarEstadoFiltroTodosTipos();
        agendarReloadTabela('filtro_tipos');
    });

    // Checkbox para selecionar/desmarcar todos os tipos disponíveis
    $('#filtro_todos_tipos').on('change', function() {
        const select = $('#filtro_tipos');
        if ($(this).is(':checked')) {
            const todos = select.find('option').map(function() { return String($(this).val()); }).get();
            select.val(todos);
        } else {
            select.val([]);
        }
        atualizarEstadoFiltroTodosTipos();
        agendarReloadTabela('filtro_todos_tipos');
    });
    
    // Filtros aplicados no frontend: só redesenha a tabela (sem nova requisição ao backend)
    $('#filtro_quantidade_zero').on('change', function() {
        $('#chkComparativoOcultarZeros').prop('checked', $(this).is(':checked'));
        if (table) table.draw(false);
    });
    $('#filtro_sem_material_sistema, #filtro_ter_os_dois').on('change', function() {
        if (table) table.draw(false);
    });

    /** Espelho do filtro "quantidade 0", logo acima da tabela comparativa */
    $('#chkComparativoOcultarZeros').on('change', function() {
        $('#filtro_quantidade_zero').prop('checked', $(this).is(':checked'));
        if (table) table.draw(false);
    });

    /** Atalho: ao marcar, executa a mesma ação de "Limpar simulação" e desmarca em seguida */
    $('#chkComparativoZerarSimulacao').on('change', function() {
        if (!$(this).is(':checked')) return;
        $(this).prop('checked', false);
        $('#btnLimparSimulacaoManual').trigger('click');
    });
    
    // Botão limpar filtros
    $('#btnLimparFiltros').on('click', function() {
        $('#filtro_data').val('');
        $('#filtro_sped').prop('checked', false);
        $('#filtro_todos_tipos').prop('checked', false).prop('indeterminate', false);
        $('#filtro_tipos').val([]);
        $('#filtro_quantidade_zero').prop('checked', false);
        $('#chkComparativoOcultarZeros').prop('checked', false);
        $('#filtro_sem_material_sistema').prop('checked', false);
        $('#filtro_ter_os_dois').prop('checked', false);
        atualizarEstadoFiltroTodosTipos();
        if (table) table.draw(false);
    });

    $('#chkComparativoOcultarZeros').prop('checked', $('#filtro_quantidade_zero').is(':checked'));
    
    /** Exporta o comparativo exatamente como na tela: filtros do DataTables, ordenação atual e colunas de simulação (consumo/estoques futuros). */
    function exportarComparativoTabelaSimulacaoExcel() {
        if (typeof XLSX === 'undefined') {
            alert('Biblioteca Excel não disponível. Recarregue a página.');
            return;
        }
        if (!table) {
            alert('Carregue a tabela comparativa antes de exportar.');
            return;
        }
        const headers = TITULOS_TABELA_COMPARATIVO.slice().concat(['material_id']);
        const rows = table.rows({ search: 'applied', order: 'current' }).data().toArray();
        const simAtiva = !!(consumoPorMaterialSimulacao && consumoPorMaterialSimulacaoTerceiro);
        const aoa = [];
        const valorTotalEstoqueSistema = rows.reduce((acc, row) => acc + parseFloat(row.valor_sistema) || 0, 0);
        const valorTotalEstoqueTerceiro = rows.reduce((acc, row) => acc + parseFloat(row.valor_terceiro) || 0, 0);
        const valorTotalDiferenca = valorTotalEstoqueTerceiro - valorTotalEstoqueSistema;
        const valorTotalDiferencaPercentual = (valorTotalDiferenca / valorTotalEstoqueSistema) * 100;
        aoa.push(['Valor total estoque (sistema):', '', '', valorTotalEstoqueSistema]);
        aoa.push(['Valor total estoque (terceiro):', '', '', valorTotalEstoqueTerceiro]);
        aoa.push(['Valor total de diferença:','','', valorTotalDiferenca]);
        aoa.push(['Percentual diferença:','','', valorTotalDiferencaPercentual]);

        aoa.push(headers);
        rows.forEach(function (row) {
            const ut = row.unidade_terceiro != null ? String(row.unidade_terceiro).replace(/<[^>]*>/g, '').trim() : '';
            const us = row.unidade_sistema != null ? String(row.unidade_sistema).trim() : '';
            const fatorConversao = parseFloat(row.fator_conversao);
            const possuiConversaoTerceiro = !!row.unidade_convertida
                && Number.isFinite(fatorConversao)
                && fatorConversao > 0
                && Math.abs(fatorConversao - 1) > 1e-9;
            const convSistemaParaUnidadeTerceiro = function (valor) {
                const n = parseFloat(valor) || 0;
                return possuiConversaoTerceiro ? (n / fatorConversao) : n;
            };

            const estoqueSistemaExport = convSistemaParaUnidadeTerceiro(row.estoque_sistema);
            const estoqueTerceiroExport = possuiConversaoTerceiro
                ? (parseFloat(row.estoque_terceiro_original) || 0)
                : (parseFloat(row.estoque_terceiro) || 0);
            const consumoFuturoExport = convSistemaParaUnidadeTerceiro(row.consumo_futuro);
            const estoqueFuturoExport = convSistemaParaUnidadeTerceiro(row.estoque_futuro);
            const estoqueTerceiroFuturoExport = estoqueTerceiroExport - consumoFuturoExport;
            const diferencaExport = estoqueTerceiroExport - estoqueSistemaExport;
            const diferencaFuturaExport = estoqueTerceiroExport - estoqueFuturoExport;
            const diferencaFuturaTerceiroExport = estoqueTerceiroFuturoExport - estoqueFuturoExport;
            const diferencaPercentualExport = estoqueSistemaExport !== 0
                ? ((diferencaExport / estoqueSistemaExport) * 100)
                : (estoqueTerceiroExport !== 0 ? 100 : 0);
            const unidadeSistemaExport = possuiConversaoTerceiro && ut
                ? (us ? (us + ' (conv. p/ ' + ut + ')') : ut)
                : us;

            aoa.push([
                formatarCodigoErpInteiro(row.codigo_erp),
                row.material_nome != null ? String(row.material_nome) : '',
                unidadeSistemaExport,
                ut,
                estoqueSistemaExport,
                estoqueTerceiroExport,
                parseFloat(row.valor_unitario) || 0,
                parseFloat(row.valor_sistema) || 0,
                parseFloat(row.valor_terceiro) || 0,
                diferencaExport,
                diferencaPercentualExport,
                parseFloat(row.valor_diferenca) || 0,
                consumoFuturoExport,
                estoqueFuturoExport,
                estoqueTerceiroFuturoExport,
                diferencaFuturaExport,
                parseFloat(row.valor_estoque_futuro_sistema) || 0,
                parseFloat(row.valor_estoque_futuro_terceiro) || 0,
                parseFloat(row.diferenca_valor_futuro) || 0,
                diferencaFuturaTerceiroExport,
                row.material_id != null && row.material_id !== '' ? row.material_id : ''
            ]);
        });
        const ws = XLSX.utils.aoa_to_sheet(aoa);
        const d = ws['!ref'] ? XLSX.utils.decode_range(ws['!ref']) : { s: { r: 0, c: 0 }, e: { r: 0, c: 0 } };
        const colsMoeda = [6, 7, 8, 11, 16, 17, 18];
        const colsDec4 = [4, 5, 9, 12, 13, 14, 15, 19];
        const colsDec2Pct = [10];
        xlsxAplicarNumFmtCelula(ws, 0, 3, XLSX_FMT_MOEDA_CONTABIL);
        xlsxAplicarNumFmtCelula(ws, 1, 3, XLSX_FMT_MOEDA_CONTABIL);
        xlsxAplicarNumFmtCelula(ws, 2, 3, XLSX_FMT_MOEDA_CONTABIL);
        for (let r = 2; r <= d.e.r; r++) {
            colsMoeda.forEach(function (c) {
                xlsxAplicarNumFmtCelula(ws, r, c, XLSX_FMT_MOEDA_CONTABIL);
            });
            colsDec4.forEach(function (c) {
                xlsxAplicarNumFmtCelula(ws, r, c, XLSX_FMT_DECIMAL_4);
            });
            colsDec2Pct.forEach(function (c) {
                xlsxAplicarNumFmtCelula(ws, r, c, XLSX_FMT_DECIMAL_2);
            });
        }
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Comparativo');
        const ts = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '').replace('T', '_');
        XLSX.writeFile(wb, 'comparativo_estoque_simulacao_' + ts + '.xlsx', { bookType: 'xlsx' });
    }

    $('#btnExportarExcel').on('click', function () {
        exportarComparativoTabelaSimulacaoExcel();
    });

    // Checklist de colunas (persistente)
    $(document).on('change', '#colunasChecklist .chk-coluna', function() {
        if (!table) return;
        aplicarVisibilidadeDeChecklist(table);
    });

    $('#btnResetColunas').on('click', function() {
        if (!table) return;
        table.columns().visible(true, false);
        table.columns.adjust().draw(false);
        renderChecklistColunas(table);
        try { localStorage.removeItem(storageKeyColunas()); } catch (e) {}
    });

    // Simulação manual - adicionar item
    $('#btnAdicionarSimulacaoOpcao').on('click', async function() {
        const idx = $('#selectSimulacaoOpcao').val();
        if (idx === null || idx === undefined || idx === '') return;
        const opt = opcoesSimulacao[parseInt(idx)];
        if (!opt) return;
        const key = `${opt.grupo_label}_${opt.tipo_peca}_${opt.produto_composto_id}`;
        if (!simulacaoItens[key]) {
            simulacaoItens[key] = {
                tipo_item: TIPO_SIM_TANQUE,
                grupo_label: opt.grupo_label || 'Sem grupo',
                tipo_peca: opt.tipo_peca,
                produto_composto_id: opt.produto_composto_id,
                produto_composto_nome: opt.produto_composto_nome,
                quantidade_produzida: parseInt(opt.quantidade_produzida || 0),
                quantidade_simular: 0,
                peso: null,
                materiais_cache: null
            };
            // Cacheia materiais assim que item é adicionado
            try {
                await garantirMateriaisDoItem(simulacaoItens[key]);
            } catch (e) {
                console.warn('Não foi possível cachear materiais ao adicionar item:', e);
            }
        }
        renderTabelaSimulacaoManual();
        setSimulacaoPendente(true);
        persistirSimulacaoManualCliente();
    });

    $('#btnAdicionarMaterialAvulsoSimulacao').on('click', function () {
        const mid = $('#selectMaterialAvulsoSimulacao').val();
        const qtd = parseFloat($('#inputQtdMaterialAvulsoSimulacao').val());
        if (mid === null || mid === undefined || mid === '') {
            alert('Selecione um material.');
            return;
        }
        if (!(qtd > 0)) {
            alert('Informe uma quantidade de consumo maior que zero.');
            return;
        }
        const opt = $('#selectMaterialAvulsoSimulacao option:selected');
        const nome = opt.length ? opt.text() : ('Material #' + mid);
        const key = 'mav_' + mid + '_' + Date.now();
        simulacaoItens[key] = {
            tipo_item: TIPO_SIM_MATERIAL_AVULSO,
            grupo_label: 'Avulso',
            tipo_peca: 'Material',
            material_id: parseInt(mid, 10),
            material_nome: nome,
            produto_composto_id: null,
            produto_composto_nome: null,
            quantidade_produzida: 0,
            quantidade_simular: qtd,
            peso: null,
            materiais_cache: null
        };
        garantirMateriaisDoItem(simulacaoItens[key]).catch(function (e) {
            console.warn(e);
        });
        $('#inputQtdMaterialAvulsoSimulacao').val('');
        renderTabelaSimulacaoManual();
        setSimulacaoPendente(true);
        persistirSimulacaoManualCliente();
    });

    $('#btnAdicionarProdutoAvulsoSimulacao').on('click', async function () {
        const pid = $('#selectProdutoAvulsoSimulacao').val();
        if (pid === null || pid === undefined || pid === '') {
            alert('Selecione um produto composto.');
            return;
        }
        const opt = $('#selectProdutoAvulsoSimulacao option:selected');
        const nome = opt.length ? opt.text() : ('Produto #' + pid);
        const key = 'pcav_' + pid + '_' + Date.now();
        simulacaoItens[key] = {
            tipo_item: TIPO_SIM_PRODUTO_AVULSO,
            grupo_label: 'Avulso',
            tipo_peca: 'Prod. composto',
            produto_composto_id: parseInt(pid, 10),
            produto_composto_nome: nome,
            quantidade_produzida: 0,
            quantidade_simular: 0,
            peso: null,
            materiais_cache: null
        };
        try {
            await garantirMateriaisDoItem(simulacaoItens[key]);
        } catch (e) {
            console.warn('Não foi possível cachear estrutura do produto avulso:', e);
        }
        renderTabelaSimulacaoManual();
        setSimulacaoPendente(true);
        persistirSimulacaoManualCliente();
    });

    // Simulação manual - remover item
    $(document).on('click', '.btn-remover-simulacao', function() {
        const tr = $(this).closest('tr');
        const key = tr.data('key');
        if (key && simulacaoItens[key]) {
            delete simulacaoItens[key];
            renderTabelaSimulacaoManual();
            setSimulacaoPendente(true);
            persistirSimulacaoManualCliente();
        }
    });

    // Simulação manual - alterar quantidade total
    $(document).on('change', '.input-qtd-total', function() {
        const tr = $(this).closest('tr');
        const key = tr.data('key');
        if (!key || !simulacaoItens[key]) return;
        const val = parseFloat($(this).val()) || 0;
        simulacaoItens[key].quantidade_simular = Math.max(val, 0);
        renderTabelaSimulacaoManual();
        setSimulacaoPendente(true);
        persistirSimulacaoManualCliente();
    });

    $(document).on('change', '.input-peso-simulacao', function() {
        const tr = $(this).closest('tr');
        const key = tr.data('key');
        if (!key || !simulacaoItens[key]) return;
        if (tipoItemSemPesoSimulacao(simulacaoItens[key].tipo_item || TIPO_SIM_TANQUE)) return;
        const v = $(this).val();
        simulacaoItens[key].peso = (v === null || v === undefined || String(v).trim() === '') ? null : String(v).trim();
        persistirSimulacaoManualCliente();
    });

    $('#btnExportarIndicesSimulacaoExcel').on('click', async function () {
        const btn = $(this);
        const t = btn.html();
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i>');
        try {
            await exportarIndicesMateriaisSimulacaoExcel();
        } finally {
            btn.prop('disabled', false).html(t);
        }
    });

    $('#chkSimularApenasTerceiro').on('change', function() {
        setSimulacaoPendente(true);
        persistirSimulacaoManualCliente();
    });

    $('#btnExecutarSimulacaoManual').on('click', async function() {
        setSimulacaoPendente(false);
        const btn = $(this);
        const txtOriginal = btn.html();
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Executando...');
        try {
            await recalcularSimulacao();
            persistirSimulacaoManualCliente();
        } finally {
            btn.prop('disabled', false).html(txtOriginal);
        }
    });

    $('#btnLimparSimulacaoManual').on('click', async function() {
        simulacaoItens = {};
        limparPersistenciaSimulacaoManualCliente();
        renderTabelaSimulacaoManual();
        setSimulacaoPendente(false);
        await recalcularSimulacao();
    });
    
    // Função para atualizar cards com estatísticas
    function atualizarCardsEstatisticas(dados) {
        if (!dados || dados.length === 0) {
            $('#resumoAtualValorSistema').text('R$ 0,00');
            $('#resumoAtualValorTerceiro').text('R$ 0,00');
            $('#resumoAtualDiferenca').text('R$ 0,00');
            $('#resumoAtualPercentual').text('0,00%');
            $('#resumoAtualConsumoFuturo').text('—');
            $('#resumoSimuladoValorSistema').text('R$ 0,00');
            $('#resumoSimuladoValorTerceiro').text('R$ 0,00');
            $('#resumoSimuladoDiferenca').text('R$ 0,00');
            $('#resumoSimuladoPercentual').text('0,00%');
            $('#resumoSimuladoConsumoFuturo').text((0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 }));
            return;
        }
        
        let valorTotalSistema = 0;
        let valorTotalTerceiro = 0;
        let diferencaValorTotal = 0;
        let valorTotalSistemaSimulado = 0;
        let valorTotalTerceiroSimulado = 0;
        let totalConsumoFuturo = 0;

        dados.forEach(function(item) {
            const valorUnitario = parseFloat(item.valor_unitario) || 0;
            const valorSistema = parseFloat(item.valor_sistema) || 0;
            const valorTerceiro = parseFloat(item.valor_terceiro) || 0;
            const diferenca = parseFloat(item.diferenca) || 0;
            const estoqueFuturo = parseFloat(item.estoque_futuro) || 0;
            const estoqueTerceiroFuturo = parseFloat(item.estoque_terceiro_futuro) || 0;
            const consumoFuturo = parseFloat(item.consumo_futuro) || 0;

            valorTotalSistema += valorSistema;
            valorTotalTerceiro += valorTerceiro;
            if (valorUnitario > 0) {
                diferencaValorTotal += diferenca * valorUnitario;
            }

            valorTotalSistemaSimulado += (estoqueFuturo * valorUnitario);
            valorTotalTerceiroSimulado += (estoqueTerceiroFuturo * valorUnitario);
            totalConsumoFuturo += consumoFuturo;
        });

        const diferencaAtual = valorTotalTerceiro - valorTotalSistema;
        const percentualAtual = valorTotalSistema !== 0 ? (diferencaAtual / valorTotalSistema) * 100 : (valorTotalTerceiro !== 0 ? 100 : 0);

        const diferencaSimulada = valorTotalTerceiroSimulado - valorTotalSistemaSimulado;
        const percentualSimulado = valorTotalSistemaSimulado !== 0
            ? (diferencaSimulada / valorTotalSistemaSimulado) * 100
            : (valorTotalTerceiroSimulado !== 0 ? 100 : 0);

        const fmtCurrency = (v) => (parseFloat(v) || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const fmtPercent = (v) => (parseFloat(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
        const fmtQtdConsumo = (v) => (parseFloat(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });

        $('#resumoAtualValorSistema').text(fmtCurrency(valorTotalSistema));
        $('#resumoAtualValorTerceiro').text(fmtCurrency(valorTotalTerceiro));
        $('#resumoAtualDiferenca').text(fmtCurrency(diferencaAtual));
        $('#resumoAtualPercentual').text(fmtPercent(percentualAtual));
        $('#resumoAtualConsumoFuturo').text('—');

        $('#resumoSimuladoValorSistema').text(fmtCurrency(valorTotalSistemaSimulado));
        $('#resumoSimuladoValorTerceiro').text(fmtCurrency(valorTotalTerceiroSimulado));
        $('#resumoSimuladoDiferenca').text(fmtCurrency(diferencaSimulada));
        $('#resumoSimuladoPercentual').text(fmtPercent(percentualSimulado));
        $('#resumoSimuladoConsumoFuturo').text(fmtQtdConsumo(totalConsumoFuturo));
    }

    /** Restaura itens da simulação manual salvos em localStorage (após carregar opções/estruturas). */
    async function restaurarSimulacaoManualDoCliente() {
        let raw = null;
        try {
            raw = localStorage.getItem(storageKeySimulacaoManual());
        } catch (e) {}
        if (!raw) return;

        let payload = null;
        try {
            payload = JSON.parse(raw);
        } catch (e) {
            limparPersistenciaSimulacaoManualCliente();
            return;
        }
        if (!payload || payload.v !== 1 || !payload.itens || typeof payload.itens !== 'object') {
            limparPersistenciaSimulacaoManualCliente();
            return;
        }

        const keys = Object.keys(payload.itens);
        if (!keys.length) return;

        simulacaoItens = {};
        keys.forEach(function (k) {
            const it = payload.itens[k];
            if (!it || typeof it !== 'object') return;
            it.materiais_cache = null;
            simulacaoItens[k] = it;
        });

        if (Object.keys(simulacaoItens).length === 0) {
            limparPersistenciaSimulacaoManualCliente();
            return;
        }

        if (typeof payload.apenas_terceiro === 'boolean') {
            $('#chkSimularApenasTerceiro').prop('checked', payload.apenas_terceiro);
        }

        const produtoIds = [];
        Object.keys(simulacaoItens).forEach(function (k) {
            const it = simulacaoItens[k];
            const t = it.tipo_item || TIPO_SIM_TANQUE;
            if (t !== TIPO_SIM_MATERIAL_AVULSO && it.produto_composto_id != null) {
                produtoIds.push(String(it.produto_composto_id));
            }
        });
        try {
            await carregarEstruturasProdutos(produtoIds);
        } catch (e) {
            console.warn('Restaurar simulação: estruturas', e);
        }

        for (const k of Object.keys(simulacaoItens)) {
            try {
                await garantirMateriaisDoItem(simulacaoItens[k]);
            } catch (e) {
                console.warn('Restaurar simulação: item', k, e);
            }
        }

        try {
            await recalcularSimulacao();
        } catch (e) {
            console.warn('Restaurar simulação: recalcular', e);
        }
        setSimulacaoPendente(false);
    }
    
    // Carregar datas e inicializar tabela
    carregarDatasDisponiveis();
    carregarTiposDisponiveis();
    inicializarDataTable();
    carregarMateriaisParaSimulacaoAvulsa();
    carregarProdutosCompostosParaSimulacaoAvulsa();
    carregarOpcoesSimulacao()
        .then(function () {
            return restaurarSimulacaoManualDoCliente();
        })
        .catch(function (e) {
            console.warn('Inicialização simulação:', e);
        })
        .finally(function () {
            renderTabelaSimulacaoManual();
        });
    
    // Recarregar tabela após fechar modal de importação
    $('#modalImportarEstoqueTerceiro').on('hidden.bs.modal', function() {
        carregarDatasDisponiveis();
        agendarReloadTabela('modal_importacao_hidden');
    });
