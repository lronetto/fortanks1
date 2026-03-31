(function () {
    var table = null;
    var tiposSped = ['10', '15', '18'];
    window.cdSomenteDiferencas = false;

    function formatarCodigoErpInteiro(v) {
        if (v == null || v === '') return '';
        var s = String(v).replace(/\.0+$/, '').replace(',', '.');
        var n = parseFloat(s);
        if (!Number.isFinite(n)) return String(v);
        return String(Math.trunc(n));
    }

    function fmtNum(v, frac) {
        var n = parseFloat(v);
        if (!Number.isFinite(n)) n = 0;
        return n.toLocaleString('pt-BR', { minimumFractionDigits: frac, maximumFractionDigits: frac });
    }

    function fmtMoeda(v) {
        var n = parseFloat(v);
        if (!Number.isFinite(n)) n = 0;
        return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    }

    function classeDiff(n) {
        var x = parseFloat(n) || 0;
        if (Math.abs(x) < 1e-9) return 'diff-zero';
        return x > 0 ? 'diff-positivo' : 'diff-negativo';
    }

    function atualizarResumo(rows) {
        if (!rows || !rows.length) {
            $('#cd_resumo_cards').hide();
            return;
        }
        var soA = 0, soB = 0, comDiff = 0;
        rows.forEach(function (r) {
            var qa = parseFloat(r.qtd_data_a) || 0;
            var qb = parseFloat(r.qtd_data_b) || 0;
            var dq = parseFloat(r.diferenca_qtd) || 0;
            if (qa > 0 && qb === 0) soA++;
            if (qb > 0 && qa === 0) soB++;
            if (Math.abs(dq) > 1e-9) comDiff++;
        });
        $('#cd_resumo_total').text(rows.length);
        $('#cd_resumo_so_a').text(soA);
        $('#cd_resumo_so_b').text(soB);
        $('#cd_resumo_diff').text(comDiff);
        $('#cd_resumo_cards').show();
    }

    function atualizarLegenda() {
        var a = $('#cd_data_a').val();
        var b = $('#cd_data_b').val();
        if (a && b) {
            $('#cd_legenda_datas').text('Colunas A = ' + a.split('-').reverse().join('/') + ' · B = ' + b.split('-').reverse().join('/'));
        } else {
            $('#cd_legenda_datas').text('');
        }
    }

    function carregarDatas() {
        return fetch('{{ url_for("estoque_terceiro.api_datas_disponiveis") }}')
            .then(function (r) { return r.json(); })
            .then(function (j) {
                if (!j.success || !j.datas) return;
                var selA = $('#cd_data_a');
                var selB = $('#cd_data_b');
                var curA = selA.val();
                var curB = selB.val();
                selA.find('option:not(:first)').remove();
                selB.find('option:not(:first)').remove();
                j.datas.forEach(function (d) {
                    selA.append($('<option></option>').attr('value', d).text(d.split('-').reverse().join('/')));
                    selB.append($('<option></option>').attr('value', d).text(d.split('-').reverse().join('/')));
                });
                if (curA && selA.find('option[value="' + curA + '"]').length) selA.val(curA);
                if (curB && selB.find('option[value="' + curB + '"]').length) selB.val(curB);
            })
            .catch(function () {});
    }

    function carregarTipos() {
        return fetch('{{ url_for("estoque_terceiro.api_tipos_disponiveis") }}')
            .then(function (r) { return r.json(); })
            .then(function (j) {
                if (!j.success || !j.tipos) return;
                var sel = $('#cd_filtro_tipos');
                sel.empty();
                j.tipos.forEach(function (t) {
                    var valor = t;
                    if (typeof t === 'object' && t !== null && t.valor != null) {
                        valor = t.valor;
                    }
                    sel.append($('<option></option>').attr('value', valor).text(String(valor)));
                });
            })
            .catch(function () {});
    }

    function tiposQueryParam() {
        if ($('#cd_filtro_sped').is(':checked')) {
            return tiposSped.join(',');
        }
        var v = $('#cd_filtro_tipos').val() || [];
        if (v.length) return v.join(',');
        return '';
    }

    function initTable() {
        if (table) {
            try {
                var idx = $.fn.dataTable.ext.search.indexOf(cdExtSearch);
                if (idx >= 0) $.fn.dataTable.ext.search.splice(idx, 1);
            } catch (e) {}
            table.destroy();
            table = null;
        }

        table = $('#tabelaComparativoDatas').DataTable({
            processing: true,
            serverSide: false,
            ajax: {
                url: '{{ url_for("estoque_terceiro.api_comparativo_entre_datas") }}',
                type: 'GET',
                data: function (d) {
                    d.data_a = $('#cd_data_a').val() || '';
                    d.data_b = $('#cd_data_b').val() || '';
                    var tp = tiposQueryParam();
                    if (tp) d.tipos = tp;
                },
                dataSrc: function (json) {
                    if (json.error) {
                        console.error(json.error);
                        alert(json.error);
                        atualizarResumo([]);
                        return [];
                    }
                    atualizarResumo(json.data || []);
                    return json.data || [];
                },
                error: function (xhr) {
                    var msg = 'Erro ao carregar comparativo.';
                    try {
                        var j = JSON.parse(xhr.responseText || '{}');
                        if (j.error) msg = j.error;
                    } catch (e) {}
                    alert(msg);
                    atualizarResumo([]);
                }
            },
            language: {
                url: '{{ url_for("static", filename="js/datatables-pt-BR-1.13.json") }}'
            },
            order: [[0, 'asc']],
            pageLength: 25,
            lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'Todos']],
            scrollX: true,
            columns: [
                {
                    data: 'codigo_erp',
                    render: function (data, type) {
                        if (type === 'sort' || type === 'type') {
                            var n = Number(String(data == null ? '' : data).replace(',', '.'));
                            return Number.isFinite(n) ? Math.trunc(n) : 0;
                        }
                        var ex = formatarCodigoErpInteiro(data);
                        return ex !== '' ? ex : '-';
                    }
                },
                { data: 'tipo' },
                { data: 'material_nome' },
                {
                    data: 'unidade',
                    render: function (d) { return d || '-'; }
                },
                {
                    data: 'qtd_data_a',
                    className: 'text-end',
                    render: function (d, type) {
                        if (type === 'sort' || type === 'type') return parseFloat(d) || 0;
                        return fmtNum(d, 4);
                    }
                },
                {
                    data: 'qtd_data_b',
                    className: 'text-end',
                    render: function (d, type) {
                        if (type === 'sort' || type === 'type') return parseFloat(d) || 0;
                        return fmtNum(d, 4);
                    }
                },
                {
                    data: 'diferenca_qtd',
                    className: 'text-end',
                    render: function (d, type, row) {
                        if (type === 'sort' || type === 'type') return parseFloat(d) || 0;
                        var c = classeDiff(d);
                        return '<span class="' + c + '">' + fmtNum(d, 4) + '</span>';
                    }
                },
                {
                    data: 'diferenca_percentual',
                    className: 'text-end',
                    render: function (d, type) {
                        if (type === 'sort' || type === 'type') return parseFloat(d) || 0;
                        return fmtNum(d, 2) + '%';
                    }
                },
                {
                    data: 'valor_total_a',
                    className: 'text-end',
                    render: function (d, type) {
                        if (type === 'sort' || type === 'type') return parseFloat(d) || 0;
                        return fmtMoeda(d);
                    }
                },
                {
                    data: 'valor_total_b',
                    className: 'text-end',
                    render: function (d, type) {
                        if (type === 'sort' || type === 'type') return parseFloat(d) || 0;
                        return fmtMoeda(d);
                    }
                },
                {
                    data: 'diferenca_valor',
                    className: 'text-end',
                    render: function (d, type) {
                        if (type === 'sort' || type === 'type') return parseFloat(d) || 0;
                        var c = classeDiff(d);
                        return '<span class="' + c + '">' + fmtMoeda(d) + '</span>';
                    }
                }
            ]
        });

        $.fn.dataTable.ext.search.push(cdExtSearch);
    }

    function cdExtSearch(settings, _data, dataIndex) {
        if (!settings || !settings.nTable || settings.nTable.id !== 'tabelaComparativoDatas') return true;
        if (!window.cdSomenteDiferencas) return true;
        var api = new $.fn.dataTable.Api(settings);
        var rowData = api.row(dataIndex).data();
        if (!rowData) return true;
        return Math.abs(parseFloat(rowData.diferenca_qtd) || 0) > 1e-9;
    }

    $('#cd_somente_diferencas').on('change', function () {
        window.cdSomenteDiferencas = $(this).is(':checked');
        if (table) table.draw();
    });

    $('#cd_filtro_sped').on('change', function () {
        $('#cd_filtro_tipos').prop('disabled', $(this).is(':checked'));
    });

    $('#cd_btn_aplicar').on('click', function () {
        var a = $('#cd_data_a').val();
        var b = $('#cd_data_b').val();
        if (!a || !b) {
            alert('Selecione a data A e a data B.');
            return;
        }
        if (a === b) {
            alert('Escolha duas datas diferentes para comparar.');
            return;
        }
        atualizarLegenda();
        if (!table) {
            initTable();
        } else {
            table.ajax.reload(null, false);
        }
    });

    carregarDatas();
    carregarTipos();
    $('#cd_filtro_sped').trigger('change');
})();
