    
    // Inicializar DataTable (client-side: filtros e ordenação no frontend)
    function inicializarDataTable() {
        table = $('#tabelaComparativo').DataTable({
            processing: true,
            serverSide: false,
            ajax: {
                url: '{{ url_for("estoque_terceiro.api_comparativo") }}',
                type: 'GET',
                beforeSend: function(jqXHR, settings) {
                    tabelaCarregando = true;
                    try {
                        console.debug('[DataTables] Requisição iniciada', {
                            url: settings && settings.url,
                            data: settings && settings.data
                        });
                    } catch (e) {}
                },
                complete: function() {
                    tabelaCarregando = false;
                    if (reloadPendente) {
                        reloadPendente = false;
                        agendarReloadTabela('coalesced_after_complete');
                    }
                },
                data: function(d) {
                    var dataFiltro = $('#filtro_data').val();
                    if (dataFiltro) d.data_filtro = dataFiltro;
                    if ($('#filtro_sped').is(':checked')) {
                        d.tipos = tiposSped.join(',');
                    } else {
                        var tiposSelecionados = $('#filtro_tipos').val() || [];
                        if (tiposSelecionados.length > 0) {
                            d.tipos = tiposSelecionados.join(',');
                        }
                    }
                },
                dataSrc: function(json) {
                    if (json.error) {
                        console.error('Erro ao carregar dados:', json.error);
                        return [];
                    }
                    var consumoPorPecaTipo = json.consumo_por_peca_tipo || [];
                    lastConsumoPorPecaTipo = consumoPorPecaTipo.length ? consumoPorPecaTipo : [];
                    mesclarLinhasSinteticasComparativo(json.data);
                    json.data.forEach(function (row) {
                        aplicarConsumoSimulacaoRow(row);
                    });
                    atualizarCardsEstatisticas(json.data);
                    return json.data;
                },
                error: function(xhr, error, thrown) {
                    if (error === 'abort') {
                        // Abort é esperado quando há reload enquanto uma requisição anterior ainda estava em andamento.
                        return;
                    }
                    try {
                        console.error('[DataTables] Erro AJAX', {
                            error: error,
                            thrown: thrown,
                            status: xhr && xhr.status,
                            statusText: xhr && xhr.statusText,
                            responseURL: xhr && xhr.responseURL,
                            responseText: (xhr && xhr.responseText) ? String(xhr.responseText).slice(0, 2000) : null
                        });
                    } catch (e) {
                        console.error('[DataTables] Erro AJAX:', error, thrown);
                    }
                    alert('Erro ao carregar dados da tabela. Abra o console para ver status/response.');
                }
            },
            language: {
                url: '{{ url_for("static", filename="js/datatables-pt-BR-1.13.json") }}'
            },
            order: [[1, 'asc']],
            pageLength: -1,
            lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "Todos"]],
            scrollX: true,
            scrollY: false,
            columns: [
                {
                    data: 'codigo_erp',
                    name: 'codigo_erp',
                    type: 'num',
                    render: function (data, type) {
                        const exib = formatarCodigoErpInteiro(data);
                        if (type === 'sort' || type === 'type') {
                            const n = Number(String(data == null ? '' : data).replace(',', '.'));
                            return Number.isFinite(n) ? Math.trunc(n) : 0;
                        }
                        return exib !== '' ? exib : '-';
                    }
                },
                { data: 'material_nome', name: 'material_nome' },
                { 
                    data: 'unidade_sistema', 
                    name: 'unidade_sistema',
                    render: function(data, type, row) {
                        return data || '-';
                    }
                },
                { 
                    data: 'unidade_terceiro', 
                    name: 'unidade_terceiro',
                    render: function(data, type, row) {
                        let html = data || '-';
                        if (row.unidade_convertida && row.fator_conversao !== 1.0) {
                            html += ' <i class="fas fa-exchange-alt text-info" title="Convertido: ' + 
                                   parseFloat(row.estoque_terceiro_original).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + 
                                   ' ' + data + ' × ' + parseFloat(row.fator_conversao).toLocaleString('pt-BR', { minimumFractionDigits: 4, maximumFractionDigits: 6 }) + 
                                   ' = ' + parseFloat(row.estoque_terceiro).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + 
                                   ' ' + (row.unidade_sistema || '') + '"></i>';
                        }
                        return html;
                    }
                },
                { 
                    data: 'estoque_sistema', 
                    name: 'estoque_sistema',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        if (type === 'sort' || type === 'type') {
                            return parseFloat(data) || 0.00;
                        }
                        return parseFloat(data).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
                    }
                },
                { 
                    data: 'estoque_terceiro', 
                    name: 'estoque_terceiro',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        if (type === 'sort' || type === 'type') {
                            return parseFloat(data) || 0;
                        }
                        return parseFloat(data).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
                    }
                },
                { 
                    data: 'valor_unitario', 
                    name: 'valor_unitario',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        if (type === 'sort' || type === 'type') {
                            return parseFloat(data) || 0;
                        }
                        return parseFloat(data).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                    }
                },
                { 
                    data: 'valor_sistema', 
                    name: 'valor_sistema',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        if (type === 'sort' || type === 'type') {
                            return parseFloat(data) || 0;
                        }
                        return parseFloat(data).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                    }
                },
                { 
                    data: 'valor_terceiro', 
                    name: 'valor_terceiro',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        if (type === 'sort' || type === 'type') {
                            return parseFloat(data) || 0;
                        }
                        return parseFloat(data).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                    }
                },
                { 
                    data: 'diferenca', 
                    name: 'diferenca',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        const classe = valor < 0 ? 'text-danger' : (valor > 0 ? 'text-success' : '');
                        return `<span class="${classe}">${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>`;
                    }
                },
                { 
                    data: 'diferenca_percentual', 
                    name: 'diferenca_percentual',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        const classe = valor < 0 ? 'text-danger' : (valor > 0 ? 'text-success' : '');
                        return `<span class="${classe}">${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</span>`;
                    }
                },
                { 
                    data: 'valor_diferenca', 
                    name: 'valor_diferenca',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        const classe = valor < 0 ? 'text-danger' : (valor > 0 ? 'text-success' : '');
                        return `<span class="${classe}">${valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</span>`;
                    }
                },
                { 
                    data: 'consumo_futuro', 
                    name: 'consumo_futuro',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        return valor > 0 ? `<span class="text-warning">${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>` : '-';
                    }
                },
                { 
                    data: 'estoque_futuro', 
                    name: 'estoque_futuro',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        const classe = valor < 0 ? 'text-danger' : (valor > 0 ? 'text-success' : '');
                        return `<span class="${classe}">${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>`;
                    }
                },
                { 
                    data: 'estoque_terceiro_futuro', 
                    name: 'estoque_terceiro_futuro',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        const classe = valor < 0 ? 'text-danger' : (valor > 0 ? 'text-success' : '');
                        return `<span class="${classe}">${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>`;
                    }
                },
                { 
                    data: 'diferenca_futura', 
                    name: 'diferenca_futura',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        const classe = valor < 0 ? 'text-danger' : (valor > 0 ? 'text-success' : '');
                        return `<span class="${classe}">${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>`;
                    }
                },
                { 
                    data: 'valor_estoque_futuro_sistema', 
                    name: 'valor_estoque_futuro_sistema',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                    }
                },
                { 
                    data: 'valor_estoque_futuro_terceiro', 
                    name: 'valor_estoque_futuro_terceiro',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                    }
                },
                { 
                    data: 'diferenca_valor_futuro', 
                    name: 'diferenca_valor_futuro',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        const classe = valor < 0 ? 'text-danger' : (valor > 0 ? 'text-success' : '');
                        return `<span class="${classe}">${valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</span>`;
                    }
                },
                { 
                    data: 'diferenca_futura_terceiro', 
                    name: 'diferenca_futura_terceiro',
                    className: 'text-end',
                    type: 'num',
                    render: function(data, type, row) {
                        const valor = parseFloat(data) || 0;
                        if (type === 'sort' || type === 'type') {
                            return valor;
                        }
                        const classe = valor < 0 ? 'text-danger' : (valor > 0 ? 'text-success' : '');
                        return `<span class="${classe}">${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>`;
                    }
                }
            ],
            drawCallback: function() {
                $('[data-bs-toggle="tooltip"]').tooltip();
                // Atualizar cards com dados visíveis (após filtros e busca do frontend)
                if (table) {
                    var dadosVisiveis = table.rows({ search: 'applied' }).data().toArray();
                    atualizarCardsEstatisticas(dadosVisiveis);
                }
            }
        });

        // Colunas persistentes (carregar preferências e montar checklist)
        aplicarPreferenciaColunas(table);
        renderChecklistColunas(table);
    }
