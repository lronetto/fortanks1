/**
 * Select2 com busca AJAX de NotaFiscal para cadastro/edição de equipamento.
 * Use: <select class="equipamento-select-nota-fiscal" data-busca-url="..."></select>
 */
(function () {
    function initEquipamentoNotaFiscalSelects(root) {
        if (typeof jQuery === 'undefined' || !jQuery.fn || !jQuery.fn.select2) {
            return;
        }
        var $root = root ? jQuery(root) : jQuery(document);
        $root.find('select.equipamento-select-nota-fiscal').each(function () {
            var $el = jQuery(this);
            if ($el.data('select2')) {
                return;
            }
            var url = $el.attr('data-busca-url');
            if (!url) {
                return;
            }
            var $modal = $el.closest('.modal');
            $el.select2({
                theme: 'bootstrap4',
                placeholder: 'Buscar pelo número da NF...',
                allowClear: true,
                width: '100%',
                minimumInputLength: 2,
                language: {
                    inputTooShort: function () {
                        return 'Digite pelo menos 2 caracteres.';
                    },
                    searching: function () {
                        return 'Buscando...';
                    },
                    noResults: function () {
                        return 'Nenhuma nota encontrada.';
                    },
                },
                dropdownParent: $modal.length ? $modal : jQuery(document.body),
                ajax: {
                    url: url,
                    dataType: 'json',
                    delay: 300,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    data: function (params) {
                        return { q: params.term || '' };
                    },
                    processResults: function (data) {
                        var list = data && data.results ? data.results : [];
                        return {
                            results: jQuery.map(list, function (x) {
                                return {
                                    id: x.id,
                                    text: x.text,
                                    data_emissao: x.data_emissao || '',
                                };
                            }),
                        };
                    },
                    cache: true,
                },
            });

            var dataAcqTarget = $el.attr('data-data-aquisicao-target');
            if (dataAcqTarget) {
                $el.on('select2:select', function (e) {
                    var dt = e.params && e.params.data && e.params.data.data_emissao;
                    if (dt) {
                        var campo = document.getElementById(dataAcqTarget);
                        if (campo) campo.value = dt;
                    }
                });
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initEquipamentoNotaFiscalSelects(document);
    });
    window.initEquipamentoNotaFiscalSelects = initEquipamentoNotaFiscalSelects;
})();
