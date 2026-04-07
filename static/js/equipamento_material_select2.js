/**
 * Select2 com busca AJAX de Materiais (Equipamento / Ferramenta) para vínculo em dados_adicionais.
 * Use: <select class="equipamento-select-material" data-busca-url="..."></select>
 */
(function () {
    function initEquipamentoMaterialSelects(root) {
        if (typeof jQuery === 'undefined' || !jQuery.fn || !jQuery.fn.select2) {
            return;
        }
        var $root = root ? jQuery(root) : jQuery(document);
        $root.find('select.equipamento-select-material').each(function () {
            var $el = jQuery(this);
            if ($el.data('select2')) {
                return;
            }
            var url = $el.attr('data-busca-url');
            if (!url) {
                return;
            }
            var ph = $el.attr('data-placeholder') || 'Buscar material (Equipamento/Ferramenta)...';
            var $modal = $el.closest('.modal');
            $el.select2({
                theme: 'bootstrap4',
                placeholder: ph,
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
                        return 'Nenhum material encontrado.';
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
                                var t = x.nome || '';
                                if (x.codigo) {
                                    t += ' (' + x.codigo + ')';
                                }
                                if (x.categoria) {
                                    t += ' [' + x.categoria + ']';
                                }
                                return { id: x.id, text: t };
                            }),
                        };
                    },
                    cache: true,
                },
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initEquipamentoMaterialSelects(document);
    });
    window.initEquipamentoMaterialSelects = initEquipamentoMaterialSelects;
})();
